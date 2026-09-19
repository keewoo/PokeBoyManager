"""Orchestration des anecdotes sourcées — mission `v4-anecdotes`.

`card_insights` est un cache partagé entre tous les utilisateurs (une ligne par carte,
principe « la base sait, l'IA reconnaît », `docs/ARCHITECTURE.md`) : la génération n'a lieu
qu'à la première ouverture de la fiche par n'importe quel utilisateur, avec **la clé IA de
celui qui l'a déclenchée** (mission point 2) — jamais une clé plateforme dans ce lot. Un
verrou consultatif Postgres, tenu le temps de la transaction, empêche deux requêtes
concurrentes sur une carte jamais vue de payer chacune un appel IA pour le même résultat.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.ai.base import AIProvider
from pbm_api.ai.factory import create_provider
from pbm_api.insights.context import MediaWikiClient, collect_context
from pbm_api.insights.errors import NoAiKeyConfiguredError
from pbm_api.insights.generation import AnecdotesExtraction, build_prompt
from pbm_api.models import AiCredential, Card, CardInsight, CardInsightReport, CardName, Set, User
from pbm_api.models import AiProvider as AiProviderEnum
from pbm_api.security.crypto import decrypt_api_key

ProviderFactory = Callable[[AiProviderEnum, str], AIProvider]

# Cache positif long (le principe des données : une anecdote sourcée ne se périme pas) ; cache
# négatif court (une carte sans contexte aujourd'hui peut en trouver un demain, si les wikis
# sont enrichis) — jamais un échec permanent silencieux.
_POSITIVE_CACHE_DAYS = 180
_NEGATIVE_CACHE_DAYS = 1
# Espace de nom du verrou consultatif (`pg_advisory_xact_lock(key1, key2)`), pour ne pas entrer
# en collision avec un autre usage de verrous consultatifs dans la base partagée.
_ADVISORY_LOCK_NAMESPACE = 785_431


@dataclass
class InsightsResult:
    card_insight: CardInsight
    status: str  # "ready" | "no_context" | "no_ai_key"


def _now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _fresh(card_insight: CardInsight | None) -> CardInsight | None:
    if card_insight is None or card_insight.cached_until is None:
        return None
    if card_insight.cached_until <= _now_naive():
        return None
    return card_insight


def _status_of(card_insight: CardInsight) -> str:
    return "ready" if card_insight.anecdotes else "no_context"


async def _existing_insight(db: AsyncSession, card_id: uuid.UUID) -> CardInsight | None:
    result = await db.execute(select(CardInsight).where(CardInsight.card_id == card_id))
    return result.scalar_one_or_none()


async def _lock_card(db: AsyncSession, card_id: uuid.UUID) -> None:
    await db.execute(
        text("SELECT pg_advisory_xact_lock(:namespace, hashtext(:card_id))"),
        {"namespace": _ADVISORY_LOCK_NAMESPACE, "card_id": str(card_id)},
    )


async def _default_credential(db: AsyncSession, user: User) -> AiCredential | None:
    if user.ai_default_provider is None:
        return None
    result = await db.execute(
        select(AiCredential).where(
            AiCredential.user_id == user.id, AiCredential.provider == user.ai_default_provider
        )
    )
    return result.scalar_one_or_none()


async def _english_card_name(db: AsyncSession, card: Card) -> str:
    result = await db.execute(
        select(CardName.name).where(CardName.card_id == card.id, CardName.language == "en")
    )
    name = result.scalar_one_or_none()
    return name or card.name


async def get_or_create_card_insight(
    db: AsyncSession,
    *,
    card: Card,
    current_user: User,
    pokepedia_client: MediaWikiClient,
    bulbapedia_client: MediaWikiClient,
    provider_factory: ProviderFactory = create_provider,
) -> InsightsResult:
    cached = _fresh(await _existing_insight(db, card.id))
    if cached is not None:
        return InsightsResult(card_insight=cached, status=_status_of(cached))

    await _lock_card(db, card.id)
    # Une autre requête a pu générer pendant l'attente du verrou : on relit avant de continuer.
    existing = await _existing_insight(db, card.id)
    cached = _fresh(existing)
    if cached is not None:
        return InsightsResult(card_insight=cached, status=_status_of(cached))

    credential = await _default_credential(db, current_user)
    if credential is None:
        if existing is not None:
            return InsightsResult(card_insight=existing, status="no_ai_key")
        raise NoAiKeyConfiguredError

    set_row = await db.get(Set, card.set_id)
    set_name = set_row.name if set_row is not None else ""
    en_card_name = await _english_card_name(db, card)

    pages = await collect_context(
        card_name=card.name,
        set_name=set_name,
        en_card_name=en_card_name,
        pokepedia_client=pokepedia_client,
        bulbapedia_client=bulbapedia_client,
    )

    now = _now_naive()

    if not pages:
        card_insight = existing or CardInsight(card_id=card.id)
        card_insight.anecdotes = []
        card_insight.generated_at = now
        card_insight.cached_until = now + timedelta(days=_NEGATIVE_CACHE_DAYS)
        db.add(card_insight)
        await db.commit()
        await db.refresh(card_insight)
        return InsightsResult(card_insight=card_insight, status="no_context")

    allowed_urls = {page.source_url for page in pages}
    prompt = build_prompt(card_name=card.name, set_name=set_name, pages=pages)

    decrypted_key = decrypt_api_key(credential.encrypted_key, credential.nonce, current_user.id)
    provider = provider_factory(credential.provider, decrypted_key)
    try:
        extraction, _usage = await provider.extract(
            [], AnecdotesExtraction, prompt, model=current_user.ai_default_model
        )
        used_model = current_user.ai_default_model or provider.DEFAULT_MODEL
    finally:
        await provider.aclose()

    # Rejet de toute anecdote sans URL présente dans le contexte (mission point 2), même si le
    # modèle a respecté la consigne du prompt — défense en profondeur contre l'hallucination.
    sourced = [
        {"text": item.text, "source_url": item.source_url}
        for item in extraction.anecdotes
        if item.source_url in allowed_urls
    ]

    card_insight = existing or CardInsight(card_id=card.id)
    card_insight.anecdotes = sourced
    card_insight.source_model = f"{credential.provider.value}:{used_model}"
    card_insight.generated_at = now
    card_insight.cached_until = now + timedelta(
        days=_POSITIVE_CACHE_DAYS if sourced else _NEGATIVE_CACHE_DAYS
    )
    db.add(card_insight)
    await db.commit()
    await db.refresh(card_insight)
    return InsightsResult(card_insight=card_insight, status=_status_of(card_insight))


async def report_card_insight(
    db: AsyncSession, *, card_id: uuid.UUID, user: User, reason: str | None
) -> None:
    """Bouton « Signaler une erreur » (mission point 3) — un signalement par utilisateur et
    par carte ; un second signalement met juste à jour la raison."""
    result = await db.execute(
        select(CardInsightReport).where(
            CardInsightReport.card_id == card_id, CardInsightReport.user_id == user.id
        )
    )
    report = result.scalar_one_or_none()
    if report is None:
        report = CardInsightReport(card_id=card_id, user_id=user.id)
        db.add(report)
    report.reason = reason
    await db.commit()
