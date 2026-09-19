"""Job d'import du catalogue (TCGdex FR+EN, rapprochement Pokémon TCG API) — mission `v2-catalogue`.

Idempotent : chaque extension et chaque carte est identifiée par son `tcgdex_id`, unique en base ;
relancer l'import ne duplique rien, il met à jour. Reprise sur erreur : une carte ou une extension
en échec est consignée dans le rapport (`errors`) et n'interrompt pas le reste de l'import ; chaque
extension est validée (`commit`) dès qu'elle est complète, pour qu'un arrêt en cours de route ne
perde pas le travail déjà fait.
"""

import asyncio
import logging
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.catalog.ptcg_client import PtcgClient, PtcgUnavailableError
from pbm_api.catalog.reconciliation import (
    match_card_number,
    normalize_card_number,
    resolve_ptcg_set_id,
)
from pbm_api.catalog.tcgdex_client import TcgdexClient
from pbm_api.models import Card, CardName, Set

logger = logging.getLogger(__name__)

MAX_UNMATCHED_SAMPLE = 50

# Étapes d'évolution ordinaires (TCGdex `stage`, en français — seule langue dont on récupère le
# détail complet de carte, voir `import_catalogue`) : tout `stage` en dehors de cette liste porte
# lui-même une règle spéciale (VMAX, VSTAR, BREAK...), faute de `suffix` pour ces cas (constaté en
# direct le 2026-09-19 : Astronelle VMAX a `stage="VMAX"`, `suffix=None`).
ORDINARY_STAGES = {"Base", "Niveau 1", "Niveau 2"}


def _rule_marker(detail: dict) -> str | None:
    suffix = detail.get("suffix")
    if suffix:
        return suffix
    stage = detail.get("stage")
    if stage and stage not in ORDINARY_STAGES:
        return stage
    return None

# Bride les appels `get_card` en parallèle par extension : purement réseau (aucun accès à
# `session`, qui n'est pas sûr en usage concurrent), les upserts en base restent séquentiels.
# Même ordre de grandeur que `pricing.service.TCGDEX_CONCURRENCY` — décisif pour tenir un import
# complet (~20 000 cartes) sur le lien à ~250 ko/s de chimera (mission risque réseau).
TCGDEX_CARD_FETCH_CONCURRENCY = 8


async def _fetch_card_details(
    tcgdex: TcgdexClient, lang: str, card_ids: list[str], concurrency: int
) -> dict[str, dict | Exception]:
    semaphore = asyncio.Semaphore(concurrency)

    async def _one(card_id: str) -> tuple[str, dict | Exception]:
        async with semaphore:
            try:
                return card_id, await tcgdex.get_card(lang, card_id)
            except Exception as exc:  # noqa: BLE001 — une carte en échec ne doit pas arrêter l'import
                return card_id, exc

    results = await asyncio.gather(*(_one(card_id) for card_id in card_ids))
    return dict(results)


async def _upsert_set(
    session: AsyncSession, tcgdex_set_id: str, fr_detail: dict
) -> tuple[Set, bool]:
    result = await session.execute(select(Set).where(Set.tcgdex_id == tcgdex_set_id))
    set_row = result.scalar_one_or_none()
    created = set_row is None
    if set_row is None:
        set_row = Set(tcgdex_id=tcgdex_set_id, code=tcgdex_set_id)
        session.add(set_row)

    release_date_str = fr_detail.get("releaseDate")
    set_row.name = fr_detail["name"]
    set_row.series = (fr_detail.get("serie") or {}).get("name")
    set_row.release_date = date.fromisoformat(release_date_str) if release_date_str else None
    set_row.total_cards = (fr_detail.get("cardCount") or {}).get("official")
    set_row.symbol_url = fr_detail.get("symbol")
    set_row.logo_url = fr_detail.get("logo")
    await session.flush()
    return set_row, created


async def _upsert_card(
    session: AsyncSession, set_row: Set, tcgdex_card_id: str, detail: dict
) -> tuple[Card, bool]:
    result = await session.execute(select(Card).where(Card.tcgdex_id == tcgdex_card_id))
    card = result.scalar_one_or_none()
    created = card is None
    if card is None:
        card = Card(tcgdex_id=tcgdex_card_id, set_id=set_row.id, number=detail["localId"])
        session.add(card)

    legal = detail.get("legal") or {}
    card.set_id = set_row.id
    card.number = detail["localId"]
    card.name = detail["name"]
    card.rarity = detail.get("rarity")
    card.supertype = detail.get("category")
    card.hp = detail.get("hp")
    card.image_url = detail.get("image")
    card.illustrator = detail.get("illustrator")
    card.attacks = detail.get("attacks")
    card.abilities = detail.get("abilities")
    card.legal_standard = legal.get("standard")
    card.legal_expanded = legal.get("expanded")
    card.weaknesses = detail.get("weaknesses")
    card.resistances = detail.get("resistances")
    card.retreat_cost = detail.get("retreat")
    card.rule_marker = _rule_marker(detail)
    card.variants = detail.get("variants")
    await session.flush()
    return card, created


async def _upsert_card_name(session: AsyncSession, card: Card, language: str, name: str) -> None:
    result = await session.execute(
        select(CardName).where(CardName.card_id == card.id, CardName.language == language)
    )
    card_name = result.scalar_one_or_none()
    if card_name is None:
        session.add(CardName(card_id=card.id, language=language, name=name))
    elif card_name.name != name:
        card_name.name = name
    await session.flush()


async def _reconcile_set_with_ptcg(
    ptcg: PtcgClient, tcgdex_set_id: str, known_ptcg_set_ids: set[str]
) -> dict[str, str] | None:
    """Retourne {numéro normalisé -> ptcg_id} pour l'extension, ou None si non rapprochée."""
    ptcg_set_id = resolve_ptcg_set_id(tcgdex_set_id, known_ptcg_set_ids)
    if ptcg_set_id is None:
        return None
    ptcg_cards = await ptcg.list_cards_in_set(ptcg_set_id)
    return {
        normalize_card_number(c["number"]): c["id"]
        for c in ptcg_cards
        if c.get("number")
    }


async def import_catalogue(
    session: AsyncSession,
    tcgdex: TcgdexClient,
    ptcg: PtcgClient | None,
    languages: tuple[str, ...] = ("fr", "en"),
    set_ids: list[str] | None = None,
    mode: str = "full",
    progress_callback: Any = None,
) -> dict[str, Any]:
    """`progress_callback(tcgdex_set_id, report)` optionnel, appelé après chaque extension
    (succès ou échec) : observabilité d'un import complet (~200 extensions), sans changer le
    comportement si omis."""
    primary_lang, *secondary_langs = languages
    report: dict[str, Any] = {
        "mode": mode,
        "languages": list(languages),
        "sets_seen": 0,
        "sets_created": 0,
        "sets_updated": 0,
        "cards_created": 0,
        "cards_updated": 0,
        "cards_by_language": dict.fromkeys(languages, 0),
        "ptcg_reconciliation": "non tentée (pas de client)",
        "cards_matched_ptcg": 0,
        "cards_unmatched_ptcg_count": 0,
        "cards_unmatched_ptcg_sample": [],
        "errors": [],
    }

    known_ptcg_set_ids: set[str] = set()
    if ptcg is not None:
        try:
            ptcg_sets = await ptcg.list_sets()
            known_ptcg_set_ids = {s["id"] for s in ptcg_sets}
            report["ptcg_reconciliation"] = "ok"
        except PtcgUnavailableError as exc:
            report["ptcg_reconciliation"] = f"indisponible : {exc}"
            ptcg = None

    set_summaries = await tcgdex.list_sets(primary_lang)
    if set_ids is not None:
        set_summaries = [s for s in set_summaries if s["id"] in set_ids]
    if mode == "incremental":
        existing = await session.execute(select(Set.tcgdex_id).where(Set.tcgdex_id.is_not(None)))
        existing_ids = {row[0] for row in existing}
        set_summaries = [s for s in set_summaries if s["id"] not in existing_ids]

    for set_summary in set_summaries:
        tcgdex_set_id = set_summary["id"]
        report["sets_seen"] += 1
        try:
            fr_detail = await tcgdex.get_set(primary_lang, tcgdex_set_id)
            set_row, set_created = await _upsert_set(session, tcgdex_set_id, fr_detail)
            report["sets_created" if set_created else "sets_updated"] += 1

            secondary_names: dict[str, dict[str, str]] = {}
            for lang in secondary_langs:
                lang_detail = await tcgdex.get_set(lang, tcgdex_set_id)
                secondary_names[lang] = {c["id"]: c["name"] for c in lang_detail.get("cards", [])}

            number_to_ptcg_id: dict[str, str] | None = None
            if ptcg is not None:
                try:
                    number_to_ptcg_id = await _reconcile_set_with_ptcg(
                        ptcg, tcgdex_set_id, known_ptcg_set_ids
                    )
                except PtcgUnavailableError as exc:
                    report["errors"].append(f"rapprochement {tcgdex_set_id} : {exc}")
                    number_to_ptcg_id = None

            card_ids = [card_summary["id"] for card_summary in fr_detail.get("cards", [])]
            card_details = await _fetch_card_details(
                tcgdex, primary_lang, card_ids, TCGDEX_CARD_FETCH_CONCURRENCY
            )

            for tcgdex_card_id in card_ids:
                try:
                    card_detail = card_details[tcgdex_card_id]
                    if isinstance(card_detail, Exception):
                        raise card_detail
                    card, card_created = await _upsert_card(
                        session, set_row, tcgdex_card_id, card_detail
                    )
                    report["cards_created" if card_created else "cards_updated"] += 1

                    await _upsert_card_name(session, card, primary_lang, card_detail["name"])
                    report["cards_by_language"][primary_lang] += 1
                    for lang in secondary_langs:
                        lang_name = secondary_names.get(lang, {}).get(tcgdex_card_id)
                        if lang_name is not None:
                            await _upsert_card_name(session, card, lang, lang_name)
                            report["cards_by_language"][lang] += 1

                    if number_to_ptcg_id is not None:
                        matched = match_card_number(card_detail["localId"], number_to_ptcg_id)
                        if matched is not None:
                            card.ptcg_id = matched
                            await session.flush()
                            report["cards_matched_ptcg"] += 1
                        else:
                            report["cards_unmatched_ptcg_count"] += 1
                            if len(report["cards_unmatched_ptcg_sample"]) < MAX_UNMATCHED_SAMPLE:
                                report["cards_unmatched_ptcg_sample"].append(
                                    {"set": tcgdex_set_id, "number": card_detail["localId"]}
                                )
                except Exception as exc:  # noqa: BLE001 — une carte en échec ne doit pas arrêter l'import
                    logger.exception("Échec import carte %s", tcgdex_card_id)
                    report["errors"].append(f"carte {tcgdex_card_id} : {exc}")

            await session.commit()
        except Exception as exc:  # noqa: BLE001 — une extension en échec ne doit pas arrêter l'import
            await session.rollback()
            logger.exception("Échec import extension %s", tcgdex_set_id)
            report["errors"].append(f"extension {tcgdex_set_id} : {exc}")

        if progress_callback is not None:
            progress_callback(tcgdex_set_id, report)

    return report
