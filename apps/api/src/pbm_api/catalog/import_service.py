"""Job d'import du catalogue (TCGdex FR+EN, rapprochement Pokémon TCG API) — mission `v2-catalogue`.

Idempotent : chaque extension et chaque carte est identifiée par son `tcgdex_id`, unique en base ;
relancer l'import ne duplique rien, il met à jour. Reprise sur erreur : une carte ou une extension
en échec est consignée dans le rapport (`errors`) et n'interrompt pas le reste de l'import ; chaque
extension est validée (`commit`) dès qu'elle est complète, pour qu'un arrêt en cours de route ne
perde pas le travail déjà fait.

**Repli de langue (2026-09-22).** Le catalogue français de TCGdex est lui-même incomplet : mesuré
ce jour-là, `fr` expose 202 extensions / 22 170 cartes contre 220 / 23 736 en `en`. Piloter
l'import sur la seule langue primaire laissait donc **18 extensions entières et 1 659 cartes**
hors de la base — Gym Heroes, Gym Challenge, Base Set 2, Legendary Collection, Skyridge, Arceus,
Legendary Treasures, Team Rocket Returns, et les extensions Pocket B2 et B1a, pourtant récentes.

Le manque était invisible dans les comptages, parce que `sets.total_cards` est le total
*imprimé* : la base affichait 22 169 cartes pour 19 793 « attendues » et paraissait donc
excédentaire. On ne juge pas la complétude là-dessus — on compare extension par extension.

Désormais les extensions ET les cartes sont l'**union de toutes les langues** de `languages`, la
première langue qui expose le contenu faisant foi pour ce contenu (donc `fr` quand elle existe,
`en` sinon). Le repli est compté : `sets_by_source_language` et `cards_by_source_language` dans
le rapport. Un repli qui grossit se voit, au lieu de passer pour un import normal.

Quatre extensions (`jumbo`, `rc`, `wp`, `tk-sm-l`) restent vides après ce repli : la source n'a
la donnée dans aucune des deux langues. Ce n'est pas un défaut d'import.
"""

import asyncio
import ipaddress
import logging
from datetime import date
from typing import Any
from urllib.parse import unquote, urlsplit

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


def _is_safe_image_url(url: str) -> bool:
    """Défense en profondeur contre un SSRF via `pbm_api.routers.images` (mission
    `v5-securite`) : `GET /img/cards/{id}` fait chercher, côté serveur, `f"{image_url}/{size}.
    webp"` à l'URL stockée ici. Rien aujourd'hui ne laisse un utilisateur influencer cette URL
    (elle vient exclusivement de la réponse TCGdex, jamais d'une requête entrante) — mais si un
    jour TCGdex renvoyait une URL détournée (compromission amont), ce contrôle l'empêche
    d'atteindre le réseau interne. Volontairement pas une liste blanche stricte du domaine
    `assets.tcgdex.net` : les doublures de test (`tests/test_import_service.py`) utilisent des
    URL factices `https://x/...`, fidèles en forme mais pas en domaine — seuls le schéma et
    l'absence d'IP privée/de boucle/de lien-local sont vérifiés."""
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        return False
    try:
        ip = ipaddress.ip_address(parts.hostname)
    except ValueError:
        return True  # nom de domaine, pas une IP littérale — résolution laissée à httpx
    return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved)


# Étapes d'évolution ordinaires (TCGdex `stage`) : tout `stage` en dehors de cette liste porte
# lui-même une règle spéciale (VMAX, VSTAR, BREAK...), faute de `suffix` pour ces cas (constaté en
# direct le 2026-09-19 : Astronelle VMAX a `stage="VMAX"`, `suffix=None`).
# Les libellés anglais y figurent depuis le repli `fr` → `en` : une carte tirée en anglais annonce
# `stage="Basic"` / `"Stage 1"`, qui seraient sinon pris pour des règles spéciales et recopiés
# dans `rule_marker`. Comparaison en minuscules pour ne pas dépendre de la casse de la source.
ORDINARY_STAGES = {"base", "niveau 1", "niveau 2", "basic", "stage 1", "stage 2"}


def _rule_marker(detail: dict) -> str | None:
    suffix = detail.get("suffix")
    if suffix:
        return suffix
    stage = detail.get("stage")
    if stage and stage.casefold() not in ORDINARY_STAGES:
        return stage
    return None


def _card_number(detail: dict) -> str:
    """Numéro imprimé de la carte.

    TCGdex publie certains numéros **déjà** percent-encodés dans ses propres données : le Zarbi
    « ? » de l'extension `exu` a `localId="%3F"` (relevé le 2026-09-22 — seule carte du catalogue
    dans ce cas). On stocke le numéro imprimé (`?`), pas sa forme encodée : c'est lui qui s'aligne
    avec les autres Zarbi (`A`...`Z`) et avec le rapprochement Pokémon TCG API. `unquote` est sans
    effet sur un numéro ordinaire (`006`, `TG05`, `SV107`)."""
    return unquote(str(detail["localId"]))


# Bride les appels `get_card` en parallèle par extension : purement réseau (aucun accès à
# `session`, qui n'est pas sûr en usage concurrent), les upserts en base restent séquentiels.
# Même ordre de grandeur que `pricing.service.TCGDEX_CONCURRENCY` — décisif pour tenir un import
# complet (~24 000 cartes) sur le lien à ~250 ko/s de chimera (mission risque réseau).
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


async def _list_set_summaries(
    tcgdex: TcgdexClient, languages: tuple[str, ...], report: dict[str, Any]
) -> list[dict]:
    """Union ordonnée des extensions de toutes les langues, la langue primaire d'abord.

    Le catalogue `fr` ne liste pas tout (voir l'en-tête du module) : une extension absente de
    `fr` mais présente en `en` doit entrer en base, pas disparaître."""
    summaries: list[dict] = []
    seen: set[str] = set()
    for lang in languages:
        try:
            lang_summaries = await tcgdex.list_sets(lang)
        except Exception as exc:  # noqa: BLE001 — une langue muette ne doit pas tout arrêter
            report["errors"].append(f"liste des extensions en '{lang}' indisponible : {exc}")
            continue
        for summary in lang_summaries:
            if summary["id"] not in seen:
                seen.add(summary["id"])
                summaries.append(summary)
    if not summaries:
        # Aucune langue n'a répondu. Sans cette levée, l'import « réussirait » en ne faisant
        # rien et rendrait un rapport à 0 extension vue, indiscernable d'un catalogue à jour.
        raise RuntimeError(
            f"aucune extension listée dans aucune des langues {list(languages)} — "
            "import interrompu (TCGdex injoignable ?)"
        )
    return summaries


async def _upsert_set(session: AsyncSession, tcgdex_set_id: str, detail: dict) -> tuple[Set, bool]:
    """`detail` vient de la première langue où l'extension existe — français en principe,
    anglais pour les 18 extensions que le catalogue `fr` ne publie pas."""
    result = await session.execute(select(Set).where(Set.tcgdex_id == tcgdex_set_id))
    set_row = result.scalar_one_or_none()
    created = set_row is None
    if set_row is None:
        set_row = Set(tcgdex_id=tcgdex_set_id, code=tcgdex_set_id)
        session.add(set_row)

    release_date_str = detail.get("releaseDate")
    set_row.name = detail["name"]
    set_row.series = (detail.get("serie") or {}).get("name")
    set_row.release_date = date.fromisoformat(release_date_str) if release_date_str else None
    set_row.total_cards = (detail.get("cardCount") or {}).get("official")
    set_row.symbol_url = detail.get("symbol")
    set_row.logo_url = detail.get("logo")
    await session.flush()
    return set_row, created


async def _upsert_card(
    session: AsyncSession, set_row: Set, tcgdex_card_id: str, detail: dict
) -> tuple[Card, bool]:
    result = await session.execute(select(Card).where(Card.tcgdex_id == tcgdex_card_id))
    card = result.scalar_one_or_none()
    created = card is None
    number = _card_number(detail)
    if card is None:
        card = Card(tcgdex_id=tcgdex_card_id, set_id=set_row.id, number=number)
        session.add(card)

    legal = detail.get("legal") or {}
    card.set_id = set_row.id
    card.number = number
    card.name = detail["name"]
    card.rarity = detail.get("rarity")
    card.supertype = detail.get("category")
    # "Normal" (Énergie de base) / "Special" (Énergie spéciale) chez TCGdex, `None` hors Énergie
    # — distingue les deux régimes de légalité des decks (lot `v7-decks-api`, D10).
    card.energy_type = detail.get("energyType")
    card.hp = detail.get("hp")
    image_url = detail.get("image")
    if image_url is not None and not _is_safe_image_url(image_url):
        logger.warning("image_url rejetée pour %s (hôte suspect) : %s", tcgdex_card_id, image_url)
        image_url = None
    card.image_url = image_url
    card.illustrator = detail.get("illustrator")
    card.attacks = detail.get("attacks")
    card.abilities = detail.get("abilities")
    card.legal_standard = legal.get("standard")
    card.legal_expanded = legal.get("expanded")
    card.weaknesses = detail.get("weaknesses")
    card.resistances = detail.get("resistances")
    card.retreat_cost = detail.get("retreat")
    card.rule_marker = _rule_marker(detail)
    # Stade d'évolution (`stage`) — sert au « au moins un Pokémon de base » de la légalité
    # des decks (lot `v7-decks-legalite`). `None` hors Pokémon. `is_basic_pokemon` accepte déjà
    # les libellés des deux langues ("Base" / "Basic"), le repli `en` ne le met pas en défaut.
    card.stage = detail.get("stage")
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
    (succès ou échec) : observabilité d'un import complet (~220 extensions), sans changer le
    comportement si omis."""
    report: dict[str, Any] = {
        "mode": mode,
        "languages": list(languages),
        "sets_seen": 0,
        "sets_created": 0,
        "sets_updated": 0,
        "cards_created": 0,
        "cards_updated": 0,
        "cards_by_language": dict.fromkeys(languages, 0),
        # Langue d'où vient le CONTENU (par opposition à `cards_by_language`, qui compte les
        # noms enregistrés) : rend le repli visible et mesurable d'un import à l'autre.
        "sets_by_source_language": dict.fromkeys(languages, 0),
        "cards_by_source_language": dict.fromkeys(languages, 0),
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

    set_summaries = await _list_set_summaries(tcgdex, languages, report)
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
            details_by_lang: dict[str, dict] = {}
            missing_langs: list[tuple[str, Exception]] = []
            for lang in languages:
                try:
                    details_by_lang[lang] = await tcgdex.get_set(lang, tcgdex_set_id)
                except Exception as exc:  # noqa: BLE001 — extension sans édition dans cette langue
                    missing_langs.append((lang, exc))
            if not details_by_lang:
                raise RuntimeError(
                    f"pas d'édition dans les langues {list(languages)} : "
                    + " ; ".join(f"{lang} ({exc})" for lang, exc in missing_langs)
                )
            content_lang = next(lang for lang in languages if lang in details_by_lang)
            for lang, exc in missing_langs:
                report["errors"].append(
                    f"extension {tcgdex_set_id} : pas d'édition '{lang}' ({exc}) — "
                    f"contenu pris en '{content_lang}'"
                )

            set_row, set_created = await _upsert_set(
                session, tcgdex_set_id, details_by_lang[content_lang]
            )
            report["sets_created" if set_created else "sets_updated"] += 1
            report["sets_by_source_language"][content_lang] += 1

            names_by_lang: dict[str, dict[str, str]] = {
                lang: {
                    c["id"]: c["name"] for c in detail.get("cards", []) if c.get("name") is not None
                }
                for lang, detail in details_by_lang.items()
            }

            # Union ordonnée des cartes de toutes les langues : une carte que le catalogue
            # français ignore (B2, B1a, Gym Heroes...) entre en base par l'anglais au lieu
            # d'être silencieusement absente.
            card_source_lang: dict[str, str] = {}
            card_ids: list[str] = []
            for lang in languages:
                for card_summary in details_by_lang.get(lang, {}).get("cards", []):
                    card_id = card_summary["id"]
                    if card_id not in card_source_lang:
                        card_source_lang[card_id] = lang
                        card_ids.append(card_id)

            card_details: dict[str, dict | Exception] = {}
            for lang in languages:
                ids_for_lang = [c for c in card_ids if card_source_lang[c] == lang]
                if ids_for_lang:
                    card_details.update(
                        await _fetch_card_details(
                            tcgdex, lang, ids_for_lang, TCGDEX_CARD_FETCH_CONCURRENCY
                        )
                    )

            number_to_ptcg_id: dict[str, str] | None = None
            if ptcg is not None:
                try:
                    number_to_ptcg_id = await _reconcile_set_with_ptcg(
                        ptcg, tcgdex_set_id, known_ptcg_set_ids
                    )
                except PtcgUnavailableError as exc:
                    report["errors"].append(f"rapprochement {tcgdex_set_id} : {exc}")
                    number_to_ptcg_id = None

            for tcgdex_card_id in card_ids:
                try:
                    card_detail = card_details[tcgdex_card_id]
                    if isinstance(card_detail, Exception):
                        raise card_detail
                    source_lang = card_source_lang[tcgdex_card_id]
                    card, card_created = await _upsert_card(
                        session, set_row, tcgdex_card_id, card_detail
                    )
                    report["cards_created" if card_created else "cards_updated"] += 1
                    report["cards_by_source_language"][source_lang] += 1

                    for lang in languages:
                        lang_name = (
                            card_detail["name"]
                            if lang == source_lang
                            else names_by_lang.get(lang, {}).get(tcgdex_card_id)
                        )
                        if lang_name is not None:
                            await _upsert_card_name(session, card, lang, lang_name)
                            report["cards_by_language"][lang] += 1

                    if number_to_ptcg_id is not None:
                        matched = match_card_number(_card_number(card_detail), number_to_ptcg_id)
                        if matched is not None:
                            card.ptcg_id = matched
                            await session.flush()
                            report["cards_matched_ptcg"] += 1
                        else:
                            report["cards_unmatched_ptcg_count"] += 1
                            if len(report["cards_unmatched_ptcg_sample"]) < MAX_UNMATCHED_SAMPLE:
                                report["cards_unmatched_ptcg_sample"].append(
                                    {"set": tcgdex_set_id, "number": _card_number(card_detail)}
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
