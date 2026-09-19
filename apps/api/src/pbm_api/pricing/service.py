"""Job du relevé quotidien de prix (mission point 1) — `card_prices_daily`, idempotent.

Reprise sur erreur à la carte/au set près, à l'image de `catalog.import_service` : une carte ou
un set en échec est consigné dans `errors` et n'interrompt pas le reste du relevé. Point 4
(sonde) : si aucun prix n'a pu être écrit alors que le catalogue contient des cartes, on lève
`EmptyPriceRunError` plutôt que de rendre un rapport vide en silence — c'est au worker de
transformer ça en `Job` en échec.
"""

import asyncio
import logging
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.catalog.ptcg_client import PtcgClient, PtcgUnavailableError
from pbm_api.catalog.tcgdex_client import TcgdexClient
from pbm_api.models import Card, CardPriceDaily, PriceSource
from pbm_api.pricing.extract import extract_cardmarket_prices, extract_tcgplayer_prices

logger = logging.getLogger(__name__)

# Bride les appels TCGdex en parallèle : un par carte, pas d'endpoint de prix en masse (mission
# risque réseau — voir aussi ~/.claude/CLAUDE.md, chimera plafonne à ~250 ko/s).
TCGDEX_CONCURRENCY = 5


class EmptyPriceRunError(RuntimeError):
    """Relevé vide alors que le catalogue contient des cartes — jamais un succès silencieux."""


async def _upsert_price(
    session: AsyncSession,
    card_id: Any,
    source: PriceSource,
    variant: Any,
    day: date,
    currency: str,
    prices: dict,
) -> None:
    stmt = pg_insert(CardPriceDaily).values(
        card_id=card_id,
        source=source,
        variant=variant,
        day=day,
        currency=currency,
        price_low=prices.get("low"),
        price_mid=prices.get("mid"),
        price_trend=prices.get("trend"),
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_card_prices_daily_unique_point",
        set_={
            "currency": stmt.excluded.currency,
            "price_low": stmt.excluded.price_low,
            "price_mid": stmt.excluded.price_mid,
            "price_trend": stmt.excluded.price_trend,
        },
    )
    await session.execute(stmt)


async def _collect_cardmarket(
    session: AsyncSession,
    tcgdex: TcgdexClient,
    cards: list,
    day: date,
    report: dict,
    progress_callback: Any = None,
) -> None:
    semaphore = asyncio.Semaphore(TCGDEX_CONCURRENCY)
    done = 0
    total = len(cards)

    async def _one(card: Any) -> None:
        nonlocal done
        async with semaphore:
            try:
                detail = await tcgdex.get_card("en", card.tcgdex_id)
            except Exception as exc:  # noqa: BLE001 — une carte en échec ne stoppe pas le relevé
                logger.warning("Échec relevé cardmarket %s : %s", card.tcgdex_id, exc)
                report["errors"].append(f"cardmarket {card.tcgdex_id} : {exc}")
            else:
                pricing = (detail.get("pricing") or {}).get("cardmarket")
                if pricing:
                    for variant, prices in extract_cardmarket_prices(pricing).items():
                        await _upsert_price(
                            session, card.id, PriceSource.cardmarket, variant, day, "EUR", prices
                        )
                        report["prices_written_cardmarket"] += 1
            finally:
                done += 1
                if progress_callback is not None:
                    progress_callback(done, total)

    await asyncio.gather(*(_one(card) for card in cards))


async def _collect_tcgplayer(
    session: AsyncSession, ptcg: PtcgClient | None, cards: list, day: date, report: dict
) -> None:
    if ptcg is None:
        report["tcgplayer_status"] = "non tentée (pas de client)"
        return

    by_set: dict[str, list] = {}
    for card in cards:
        set_id = card.ptcg_id.rsplit("-", 1)[0]
        by_set.setdefault(set_id, []).append(card)

    for set_id, set_cards in by_set.items():
        try:
            ptcg_cards = await ptcg.list_cards_in_set(set_id)
        except PtcgUnavailableError as exc:
            logger.warning("Échec relevé tcgplayer set %s : %s", set_id, exc)
            report["errors"].append(f"tcgplayer set {set_id} : {exc}")
            continue
        by_id = {c["id"]: c for c in ptcg_cards}
        for card in set_cards:
            ptcg_card = by_id.get(card.ptcg_id)
            tcgplayer = (ptcg_card or {}).get("tcgplayer")
            if not tcgplayer:
                continue
            for variant, prices in extract_tcgplayer_prices(tcgplayer).items():
                await _upsert_price(
                    session, card.id, PriceSource.tcgplayer, variant, day, "USD", prices
                )
                report["prices_written_tcgplayer"] += 1
    report["tcgplayer_status"] = "ok"


async def collect_daily_prices(
    session: AsyncSession,
    tcgdex: TcgdexClient,
    ptcg: PtcgClient | None,
    day: date | None = None,
    progress_callback: Any = None,
) -> dict[str, Any]:
    """`progress_callback(done, total)` optionnel, appelé après chaque carte Cardmarket traitée —
    observabilité d'un relevé complet (~20 000 cartes), sans changer le comportement si omis."""
    day = day or datetime.now(UTC).date()
    cards = (await session.execute(select(Card.id, Card.tcgdex_id, Card.ptcg_id))).all()

    report: dict[str, Any] = {
        "day": day.isoformat(),
        "cards_total": len(cards),
        "cards_with_tcgdex": sum(1 for c in cards if c.tcgdex_id),
        "cards_with_ptcg": sum(1 for c in cards if c.ptcg_id),
        "prices_written_cardmarket": 0,
        "prices_written_tcgplayer": 0,
        "tcgplayer_status": "non tentée (pas de client)",
        "errors": [],
    }

    await _collect_cardmarket(
        session, tcgdex, [c for c in cards if c.tcgdex_id], day, report, progress_callback
    )
    await _collect_tcgplayer(session, ptcg, [c for c in cards if c.ptcg_id], day, report)
    await session.commit()

    if (
        report["cards_total"] > 0
        and report["prices_written_cardmarket"] == 0
        and report["prices_written_tcgplayer"] == 0
    ):
        raise EmptyPriceRunError(
            f"relevé vide le {day.isoformat()} sur {report['cards_total']} cartes du "
            f"catalogue : {report}"
        )

    return report
