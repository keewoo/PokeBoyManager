"""Orchestration d'un passage du lot — mission points 1 à 3 : sélection idempotente des
cartes, un appel combiné par carte via la Message Batches API, import idempotent dans
`card_insights`, plafond de budget cumulatif vérifié avant toute soumission.

Un appel à `run_once` = au plus un lot Anthropic (soumission, ou reprise d'un lot déjà soumis).
Prévu pour être relancé (cron ou manuel) jusqu'à couverture complète du catalogue — jamais un
unique run qui engloutirait tout le budget d'un coup sans reprise possible.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.config import settings
from pbm_api.ingame.generation import render_study_text
from pbm_api.ingame.rules import legalities_of, prize_rule_of
from pbm_api.insights.context import (
    BULBAPEDIA_API_URL,
    POKEPEDIA_API_URL,
    MediaWikiClient,
    collect_context,
)
from pbm_api.insights_batch.anthropic_batches import (
    AnthropicBatchClient,
    build_batch_request,
)
from pbm_api.insights_batch.combined_generation import (
    COMBINED_JSON_SCHEMA,
    PROMPT_VERSION,
    CombinedCardInsightExtraction,
    build_combined_prompt,
)
from pbm_api.insights_batch.ledger import (
    DEFAULT_LEDGER_PATH,
    InFlightBatch,
    Ledger,
    load_ledger,
    save_ledger,
)
from pbm_api.insights_batch.pricing import batch_cost_usd
from pbm_api.models import (
    Card,
    CardInsight,
    CardName,
    CardTournamentPresence,
    Set,
    TournamentPresenceStatus,
)
from pbm_api.pricing.exchange_rates import convert_to_eur, get_rate_to_eur

logger = logging.getLogger(__name__)

# Cache positif — mêmes durées que les routes à la demande (`pbm_api.insights.service`
# `_POSITIVE_CACHE_DAYS`=180, `pbm_api.ingame.service` `_POSITIVE_CACHE_DAYS`=30) : une fiche
# pré-générée par ce lot doit rester "fraîche" exactement aussi longtemps qu'une fiche générée
# à la demande, sans quoi les deux chemins se comporteraient différemment pour un utilisateur.
_ANECDOTES_CACHE_DAYS = 180
_GAME_STUDY_CACHE_DAYS = 30
_MAX_TOKENS = 2048
# Estimation grossière (documentée comme telle, pas mesurée) pour trier les cartes AVANT
# soumission et rester sous le budget restant — le coût réel facturé vient de `usage` dans les
# résultats et est seul utilisé pour mettre à jour le grand livre.
_ESTIMATED_CHARS_PER_TOKEN = 4
_ESTIMATED_OUTPUT_TOKENS = 800


def source_marker(model: str) -> str:
    return f"anthropic:{model}:batch:{PROMPT_VERSION}"


def _now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass
class CardApplyOutcome:
    card_id: uuid.UUID
    status: str  # "ready" | "no_context" | "provider_error" | "invalid_schema"


@dataclass
class RunReport:
    status: str  # voir docstring de run_once
    cards_selected: int = 0
    cards_applied: int = 0
    cards_rejected: int = 0
    anecdotes_rejected_out_of_context: int = 0
    # Coût RÉEL (facturé, depuis `usage` des résultats) quand `status == "termine"` ; coût
    # ESTIMÉ (heuristique caractères/jeton, jamais mesuré) quand `status == "dry_run"` — jamais
    # les deux à la fois, `scripts/measure_insights_batch_cost.py` doit étiqueter en
    # conséquence dans son rapport.
    cost_usd: Decimal = Decimal("0")
    cost_eur: Decimal = Decimal("0")
    budget_remaining_eur: Decimal = Decimal("0")
    batch_id: str | None = None
    detail: str = ""
    outcomes: list[CardApplyOutcome] = field(default_factory=list)


async def _select_candidate_cards(db: AsyncSession, *, limit: int) -> list[Card]:
    """Idempotent et incrémental : une carte sans `CardInsight`, ou dont les anecdotes ou
    l'étude en jeu sont encore absentes, reste candidate ; une carte déjà couverte (par ce lot
    ou par une génération à la demande antérieure) ne l'est plus — jamais de re-dépense sur une
    fiche déjà utilisable, même si elle manque encore les anecdotes EN (amélioration future,
    voir compte rendu)."""
    stmt = (
        select(Card)
        .outerjoin(CardInsight, CardInsight.card_id == Card.id)
        .where(
            (CardInsight.id.is_(None))
            | (CardInsight.anecdotes.is_(None))
            | (CardInsight.in_game_study.is_(None))
        )
        .order_by(Card.id)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def _english_card_name(db: AsyncSession, card: Card) -> str:
    result = await db.execute(
        select(CardName.name).where(CardName.card_id == card.id, CardName.language == "en")
    )
    name = result.scalar_one_or_none()
    return name or card.name


async def _tournament_decks(db: AsyncSession, card_id: uuid.UUID) -> list[dict] | None:
    result = await db.execute(
        select(CardTournamentPresence).where(CardTournamentPresence.card_id == card_id)
    )
    presence = result.scalar_one_or_none()
    if presence is None or presence.status != TournamentPresenceStatus.checked:
        return None
    return list(presence.decks or [])


@dataclass
class PreparedCard:
    card_id: uuid.UUID
    custom_id: str
    request: dict
    allowed_urls: list[str]
    estimated_input_tokens: int
    has_context: bool


async def _prepare_card(
    db: AsyncSession,
    card: Card,
    *,
    model: str,
    pokepedia_client: MediaWikiClient,
    bulbapedia_client: MediaWikiClient,
) -> PreparedCard:
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
    legalities = legalities_of(
        legal_standard=card.legal_standard, legal_expanded=card.legal_expanded
    )
    prize_rule = prize_rule_of(card_name=card.name, supertype=card.supertype)
    tournament_decks = await _tournament_decks(db, card.id)

    prompt = build_combined_prompt(
        card_name=card.name,
        set_name=set_name,
        context_pages=pages,
        legal_standard=legalities.standard,
        legal_expanded=legalities.expanded,
        prize_label=prize_rule.label,
        attacks=card.attacks,
        abilities=card.abilities,
        tournament_decks=tournament_decks,
    )
    custom_id = str(card.id)
    request = build_batch_request(
        custom_id=custom_id,
        model=model,
        max_tokens=_MAX_TOKENS,
        prompt=prompt,
        json_schema=COMBINED_JSON_SCHEMA,
    )
    estimated_input_tokens = len(prompt) // _ESTIMATED_CHARS_PER_TOKEN
    return PreparedCard(
        card_id=card.id,
        custom_id=custom_id,
        request=request,
        allowed_urls=[page.source_url for page in pages],
        estimated_input_tokens=estimated_input_tokens,
        has_context=bool(pages),
    )


def _remaining_budget_eur(ledger: Ledger) -> Decimal:
    spent = Decimal(ledger.total_spent_eur)
    return Decimal(str(settings.insights_budget_eur)) - spent


async def _apply_result(
    db: AsyncSession, *, card_id: uuid.UUID, text: str | None, allowed_urls: set[str], model: str
) -> tuple[CardApplyOutcome, int]:
    """Écrit `card_insights` pour une carte, renvoie l'issue et le nombre d'anecdotes rejetées
    (URL hors contexte, défense en profondeur comme `pbm_api.insights.service`)."""
    if text is None:
        return CardApplyOutcome(card_id=card_id, status="provider_error"), 0

    try:
        extraction = CombinedCardInsightExtraction.model_validate_json(text)
    except ValidationError:
        return CardApplyOutcome(card_id=card_id, status="invalid_schema"), 0

    anecdotes_fr = [a for a in extraction.anecdotes_fr if a.source_url in allowed_urls]
    anecdotes_en = [a for a in extraction.anecdotes_en if a.source_url in allowed_urls]
    rejected = (
        (len(extraction.anecdotes_fr) - len(anecdotes_fr))
        + (len(extraction.anecdotes_en) - len(anecdotes_en))
    )

    existing = await db.execute(select(CardInsight).where(CardInsight.card_id == card_id))
    card_insight = existing.scalar_one_or_none() or CardInsight(card_id=card_id)

    now = _now_naive()
    marker = source_marker(model)
    card_insight.anecdotes = [a.model_dump() for a in anecdotes_fr]
    card_insight.anecdotes_en = [a.model_dump() for a in anecdotes_en]
    card_insight.source_model = marker
    card_insight.generated_at = now
    card_insight.cached_until = now + timedelta(days=_ANECDOTES_CACHE_DAYS)
    card_insight.in_game_study = render_study_text(extraction.game_study)
    card_insight.game_study_source_model = marker
    card_insight.game_study_generated_at = now
    card_insight.game_study_cached_until = now + timedelta(days=_GAME_STUDY_CACHE_DAYS)
    db.add(card_insight)

    # L'étude en jeu est toujours produite (déterministe + IA, jamais dépendante d'un contexte
    # externe) ; seules les anecdotes peuvent manquer faute de source wiki — "no_context" ne
    # signale que ça, pas un échec de l'appel.
    status = "ready" if anecdotes_fr else "no_context"
    return CardApplyOutcome(card_id=card_id, status=status), rejected


async def _finish_batch(
    db: AsyncSession,
    client: AnthropicBatchClient,
    *,
    ledger: Ledger,
    in_flight: InFlightBatch,
    results_url: str,
) -> RunReport:
    results = await client.iter_results(results_url)
    report = RunReport(status="termine", batch_id=in_flight.batch_id)

    already_counted = in_flight.batch_id in ledger.completed_batch_ids
    total_input = sum(r.input_tokens for r in results)
    total_output = sum(r.output_tokens for r in results)

    for result in results:
        card_id_str = in_flight.custom_id_to_card_id.get(result.custom_id)
        if card_id_str is None:
            logger.warning("résultat sans carte connue pour custom_id=%s", result.custom_id)
            continue
        allowed = set(in_flight.allowed_urls.get(result.custom_id, []))
        outcome, rejected = await _apply_result(
            db,
            card_id=uuid.UUID(card_id_str),
            text=result.text if result.result_type == "succeeded" else None,
            allowed_urls=allowed,
            model=in_flight.model,
        )
        report.outcomes.append(outcome)
        report.anecdotes_rejected_out_of_context += rejected
        if outcome.status in ("ready", "no_context"):
            report.cards_applied += 1
        else:
            report.cards_rejected += 1
    await db.commit()

    if not already_counted:
        cost_usd = batch_cost_usd(
            in_flight.model, input_tokens=total_input, output_tokens=total_output
        )
        cost_eur = convert_to_eur(cost_usd, Decimal(in_flight.usd_to_eur_rate))
        ledger.total_spent_usd = str(Decimal(ledger.total_spent_usd) + cost_usd)
        ledger.total_spent_eur = str(Decimal(ledger.total_spent_eur) + cost_eur)
        ledger.completed_batch_ids.append(in_flight.batch_id)
        report.cost_usd = cost_usd
        report.cost_eur = cost_eur

    ledger.cards_processed += report.cards_applied
    ledger.runs.append(
        {
            "batch_id": in_flight.batch_id,
            "finished_at": _now_naive().isoformat(),
            "cards_applied": report.cards_applied,
            "cards_rejected": report.cards_rejected,
        }
    )
    ledger.in_flight_batch = None
    report.budget_remaining_eur = _remaining_budget_eur(ledger)
    report.detail = (
        f"{report.cards_applied} carte(s) appliquée(s), {report.cards_rejected} en échec"
    )
    return report


async def run_once(
    db: AsyncSession,
    *,
    dry_run: bool = False,
    pokepedia_client: MediaWikiClient | None = None,
    bulbapedia_client: MediaWikiClient | None = None,
    batch_client: AnthropicBatchClient | None = None,
    ledger_path: Path = DEFAULT_LEDGER_PATH,
) -> RunReport:
    """Un passage : reprend un lot Anthropic déjà soumis si `ledger.in_flight_batch` en a un,
    sinon en sélectionne et en soumet un nouveau sous réserve de budget restant. `dry_run=True`
    prépare les requêtes (contexte réel, prompt réel) sans appeler l'API Anthropic — utilisé par
    `scripts/measure_insights_batch_cost.py` en l'absence de clé plateforme réelle (D4).

    `pokepedia_client`/`bulbapedia_client`/`batch_client`/`ledger_path` : mêmes seams
    d'injection que `pbm_api.routers.card_insights.get_pokepedia_client`/`get_bulbapedia_client`
    — construits en dur par défaut, substitués par la suite pytest (réponses enregistrées,
    aucun réseau, grand livre dans un répertoire temporaire)."""
    ledger = load_ledger(ledger_path)

    if not dry_run and not settings.platform_anthropic_api_key:
        return RunReport(
            status="pas_de_cle_plateforme", detail="PLATFORM_ANTHROPIC_API_KEY absente"
        )

    client = batch_client or AnthropicBatchClient(settings.platform_anthropic_api_key or "dry-run")
    owns_wiki_clients = pokepedia_client is None and bulbapedia_client is None
    try:
        if ledger.in_flight_batch is not None:
            in_flight = ledger.in_flight_batch
            status = await client.get_batch(in_flight.batch_id)
            if status.processing_status != "ended":
                save_ledger(ledger, ledger_path)
                return RunReport(
                    status="en_cours",
                    batch_id=in_flight.batch_id,
                    detail=f"lot Anthropic encore en traitement ({status.request_counts})",
                )
            report = await _finish_batch(
                db, client, ledger=ledger, in_flight=in_flight, results_url=status.results_url or ""
            )
            save_ledger(ledger, ledger_path)
            return report

        # `dry_run` ne dépense rien : le mesurer sur 100 cartes (mission point 3) ne doit pas
        # exiger un budget déjà configuré (`INSIGHTS_BUDGET_EUR` sert justement à le calibrer
        # à partir de cette mesure) — seul un passage réel est plafonné.
        remaining_eur = Decimal("Infinity") if dry_run else _remaining_budget_eur(ledger)
        if not dry_run and remaining_eur <= 0:
            return RunReport(
                status="budget_epuise",
                budget_remaining_eur=remaining_eur,
                detail="plafond INSIGHTS_BUDGET_EUR atteint sur les passages cumulés",
            )

        # Taux de change requis AVANT toute dépense (fail-closed) : un taux manquant ne doit
        # jamais se replier silencieusement sur un coût à 0 — voir `InFlightBatch.usd_to_eur_rate`.
        usd_to_eur_rate = await get_rate_to_eur(db, "USD", _now_naive().date())
        if usd_to_eur_rate is None:
            return RunReport(
                status="taux_de_change_indisponible",
                budget_remaining_eur=remaining_eur,
                detail="aucun taux USD->EUR connu (pbm_api.pricing.exchange_rates) : "
                "le relevé quotidien BCE n'a pas encore tourné sur cette base",
            )

        candidates = await _select_candidate_cards(db, limit=settings.insights_batch_chunk_size)
        if not candidates:
            return RunReport(status="catalogue_couvert", budget_remaining_eur=remaining_eur)

        pokepedia = pokepedia_client or MediaWikiClient(POKEPEDIA_API_URL)
        bulbapedia = bulbapedia_client or MediaWikiClient(BULBAPEDIA_API_URL)
        try:
            prepared = [
                await _prepare_card(
                    db,
                    card,
                    model=settings.insights_batch_model,
                    pokepedia_client=pokepedia,
                    bulbapedia_client=bulbapedia,
                )
                for card in candidates
            ]
        finally:
            if owns_wiki_clients:
                await pokepedia.aclose()
                await bulbapedia.aclose()

        model = settings.insights_batch_model
        kept: list[PreparedCard] = []
        estimated_cost = Decimal("0")
        for item in prepared:
            # Estimation grossière (docstring du module) seulement pour ne pas soumettre plus
            # que le budget restant ne peut couvrir ; le coût réel vient de l'usage facturé.
            projected = batch_cost_usd(
                model,
                input_tokens=item.estimated_input_tokens,
                output_tokens=_ESTIMATED_OUTPUT_TOKENS,
            )
            projected_eur = convert_to_eur(projected, usd_to_eur_rate)
            if estimated_cost + projected_eur > remaining_eur:
                break
            kept.append(item)
            estimated_cost += projected_eur

        if not kept:
            return RunReport(
                status="budget_insuffisant",
                budget_remaining_eur=remaining_eur,
                detail="budget restant trop faible pour couvrir même une seule carte estimée",
            )

        if dry_run:
            report = RunReport(status="dry_run", cards_selected=len(kept))
            report.detail = "requêtes préparées, aucun appel Anthropic effectué"
            # "prepared_no_context" compte les cartes sans aucune page wiki trouvée — mesure
            # réelle du taux d'anecdotes rejetées faute de source (mission point 3), même sans
            # appel Anthropic réel.
            report.outcomes = [
                CardApplyOutcome(
                    card_id=p.card_id,
                    status="prepared" if p.has_context else "prepared_no_context",
                )
                for p in kept
            ]
            report.cost_usd = sum(
                (
                    batch_cost_usd(
                        model,
                        input_tokens=p.estimated_input_tokens,
                        output_tokens=_ESTIMATED_OUTPUT_TOKENS,
                    )
                    for p in kept
                ),
                Decimal("0"),
            )
            report.cost_eur = convert_to_eur(report.cost_usd, usd_to_eur_rate)
            return report

        batch_status = await client.create_batch([p.request for p in kept])
        ledger.in_flight_batch = InFlightBatch(
            batch_id=batch_status.batch_id,
            model=model,
            usd_to_eur_rate=str(usd_to_eur_rate),
            custom_id_to_card_id={p.custom_id: str(p.card_id) for p in kept},
            allowed_urls={p.custom_id: p.allowed_urls for p in kept},
        )
        save_ledger(ledger, ledger_path)

        report = await _poll_until_ended_or_give_up(db, client, ledger, ledger_path)
        return report
    finally:
        await client.aclose()


async def _poll_until_ended_or_give_up(
    db: AsyncSession, client: AnthropicBatchClient, ledger: Ledger, ledger_path: Path
) -> RunReport:
    in_flight = ledger.in_flight_batch
    assert in_flight is not None
    for _attempt in range(settings.insights_batch_poll_max_attempts):
        status = await client.get_batch(in_flight.batch_id)
        if status.processing_status == "ended":
            report = await _finish_batch(
                db, client, ledger=ledger, in_flight=in_flight, results_url=status.results_url or ""
            )
            save_ledger(ledger, ledger_path)
            return report
        await asyncio.sleep(settings.insights_batch_poll_interval_seconds)

    save_ledger(ledger, ledger_path)
    return RunReport(
        status="en_cours",
        batch_id=in_flight.batch_id,
        cards_selected=len(in_flight.custom_id_to_card_id),
        detail=(
            "lot soumis, toujours en traitement après le nombre max de sondages — "
            "relancer plus tard"
        ),
    )
