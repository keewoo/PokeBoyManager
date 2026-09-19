"""Orchestration de l'étude en jeu — mission `v4-jeu`.

Légalités et règle des Prix (point 1) sont recalculées à chaque appel : déterministes et
gratuites, elles ne dépendent d'aucun état mutable, aucun cache n'est nécessaire ni souhaitable
(un changement de légalité doit être visible immédiatement, pas après l'expiration d'un cache).
La présence en tournoi (point 2) est lue telle quelle depuis `card_tournament_presence`,
alimentée par le relevé périodique (`pbm_api.worker.weekly_tournament_presence_task`) — jamais
récupérée à la demande (site tiers, courtoisie réseau, voir `pbm_api.ingame.tournaments`).

La synthèse IA (point 3) suit le même principe de cache partagé que les anecdotes
(`pbm_api.insights.service`) : générée une fois par carte avec la clé de l'utilisateur qui
ouvre la fiche en premier, verrou consultatif Postgres dédié (namespace différent de celui des
anecdotes : les deux synthèses sont indépendantes et ne doivent jamais se bloquer l'une
l'autre). Elle est regénérée si le dernier relevé de tournoi est plus récent que la dernière
synthèse — une étude qui ignore une actualisation de la présence en tournoi serait fausse.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.ai.base import AIProvider
from pbm_api.ai.factory import create_provider
from pbm_api.ingame.generation import InGameStudyExtraction, build_prompt, render_study_text
from pbm_api.ingame.rules import Legalities, PrizeRule, legalities_of, prize_rule_of
from pbm_api.models import (
    AiCredential,
    Card,
    CardInsight,
    CardTournamentPresence,
    Set,
    TournamentPresenceStatus,
    User,
)
from pbm_api.models import AiProvider as AiProviderEnum
from pbm_api.security.crypto import decrypt_api_key

ProviderFactory = Callable[[AiProviderEnum, str], AIProvider]

# Le profil (légalités, règle des Prix, attaques) change rarement et la présence en tournoi
# n'est rafraîchie qu'une fois par semaine (voir worker) : un cache positif plus court que les
# anecdotes (qui ne périment jamais) reste largement suffisant et évite une synthèse figée
# pendant des mois sur une méta qui bouge chaque semaine.
_POSITIVE_CACHE_DAYS = 30
# Espace de nom distinct de celui des anecdotes (`785_431`, `pbm_api.insights.service`) : les
# deux verrous ne doivent jamais interférer, une carte peut générer ses anecdotes et son étude
# en jeu en parallèle sans se bloquer.
_ADVISORY_LOCK_NAMESPACE = 785_432


@dataclass
class InGameStudyResult:
    legalities: Legalities
    prize_rule: PrizeRule
    attacks: list | None
    abilities: list | None
    tournament_status: TournamentPresenceStatus
    tournament_source_url: str | None
    tournament_checked_at: datetime | None
    tournament_decks: list[dict]
    study_status: str  # "ready" | "no_ai_key" (le routeur produit "no_ai_key" sur l'exception)
    study_text: str | None
    study_generated_at: datetime | None


def _now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


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


async def _tournament_presence(
    db: AsyncSession, card_id: uuid.UUID
) -> CardTournamentPresence | None:
    result = await db.execute(
        select(CardTournamentPresence).where(CardTournamentPresence.card_id == card_id)
    )
    return result.scalar_one_or_none()


def _study_fresh(card_insight: CardInsight | None, tournament_checked_at: datetime | None) -> bool:
    if card_insight is None or card_insight.game_study_cached_until is None:
        return False
    if card_insight.game_study_cached_until <= _now_naive():
        return False
    if (
        tournament_checked_at is not None
        and card_insight.game_study_generated_at is not None
        and tournament_checked_at > card_insight.game_study_generated_at
    ):
        return False
    return True


async def get_or_create_in_game_study(
    db: AsyncSession,
    *,
    card: Card,
    current_user: User,
    provider_factory: ProviderFactory = create_provider,
) -> InGameStudyResult:
    legalities = legalities_of(
        legal_standard=card.legal_standard, legal_expanded=card.legal_expanded
    )
    prize_rule = prize_rule_of(card_name=card.name, supertype=card.supertype)
    presence = await _tournament_presence(db, card.id)

    tournament_status = presence.status if presence else TournamentPresenceStatus.unavailable
    tournament_source_url = presence.source_url if presence else None
    tournament_checked_at = presence.checked_at if presence else None
    tournament_decks = list(presence.decks or []) if presence else []

    def _result(card_insight: CardInsight, study_status: str) -> InGameStudyResult:
        return InGameStudyResult(
            legalities=legalities,
            prize_rule=prize_rule,
            attacks=card.attacks,
            abilities=card.abilities,
            tournament_status=tournament_status,
            tournament_source_url=tournament_source_url,
            tournament_checked_at=tournament_checked_at,
            tournament_decks=tournament_decks,
            study_status=study_status,
            study_text=card_insight.in_game_study,
            study_generated_at=card_insight.game_study_generated_at,
        )

    existing = await _existing_insight(db, card.id)
    if _study_fresh(existing, tournament_checked_at):
        return _result(existing, "ready")

    await _lock_card(db, card.id)
    # Une autre requête a pu générer pendant l'attente du verrou : on relit avant de continuer.
    existing = await _existing_insight(db, card.id)
    if _study_fresh(existing, tournament_checked_at):
        return _result(existing, "ready")

    credential = await _default_credential(db, current_user)
    if credential is None:
        if existing is not None and existing.in_game_study:
            return _result(existing, "ready")
        # Contrairement aux anecdotes, l'absence de clé IA (D4) ne masque que la synthèse :
        # légalités, règle des Prix et présence en tournoi restent déterministes et sont
        # renvoyées quand même (mission point 1 et 2, indépendantes du point 3).
        return _result(existing or CardInsight(card_id=card.id), "no_ai_key")

    set_row = await db.get(Set, card.set_id)
    set_name = set_row.name if set_row is not None else ""

    prompt = build_prompt(
        card_name=card.name,
        set_name=set_name,
        legal_standard=card.legal_standard,
        legal_expanded=card.legal_expanded,
        prize_label=prize_rule.label,
        attacks=card.attacks,
        abilities=card.abilities,
        tournament_decks=(
            tournament_decks if tournament_status == TournamentPresenceStatus.checked else None
        ),
    )

    decrypted_key = decrypt_api_key(credential.encrypted_key, credential.nonce, current_user.id)
    provider = provider_factory(credential.provider, decrypted_key)
    try:
        extraction, _usage = await provider.extract(
            [], InGameStudyExtraction, prompt, model=current_user.ai_default_model
        )
        used_model = current_user.ai_default_model or provider.DEFAULT_MODEL
    finally:
        await provider.aclose()

    now = _now_naive()
    card_insight = existing or CardInsight(card_id=card.id)
    card_insight.in_game_study = render_study_text(extraction)
    card_insight.game_study_source_model = f"{credential.provider.value}:{used_model}"
    card_insight.game_study_generated_at = now
    card_insight.game_study_cached_until = now + timedelta(days=_POSITIVE_CACHE_DAYS)
    db.add(card_insight)
    await db.commit()
    await db.refresh(card_insight)

    return _result(card_insight, "ready")
