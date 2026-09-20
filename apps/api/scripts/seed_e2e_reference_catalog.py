"""Sème le catalogue de démonstration (`pbm_api.seed`, les neuf cartes de la « photo de
référence » du classeur 3×3) et un historique de prix minimal, pour l'e2e Playwright du parcours
complet (lot `v5-e2e`, `apps/web/e2e/parcours-complet.spec.ts`). Idempotent comme `pbm_api.seed`
lui-même — relançable sans dupliquer (upsert par carte × source × variante × jour).

Rafraîchit aussi la vue matérialisée `card_value_rank` (`pbm_api.ranking.service`) : sans ça, le
badge de classement de la fiche carte resterait vide pour ces cartes fraîchement créées.

Usage : uv run python scripts/seed_e2e_reference_catalog.py
"""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from pbm_api.db import async_session_factory
from pbm_api.models import Card, CardPriceDaily, PriceSource, PriceVariant, Set
from pbm_api.ranking.service import refresh_card_value_rank
from pbm_api.seed import DEMO_CARDS
from pbm_api.seed import seed as seed_catalog

# Une tendance par carte (pas un prix plat) pour exercer la variation 7 j/30 j et le tri par
# valeur de la page collection — valeurs arbitraires mais stables (idempotence).
_BASE_PRICE_VALUES = ("4.50", "6.00", "38.00", "22.00", "3.00", "65.00", "5.50", "45.00", "90.00")
_BASE_PRICES = [Decimal(v) for v in _BASE_PRICE_VALUES]

# (décalage en jours, facteur appliqué au prix de base) — trois points par carte.
_PRICE_POINTS = ((30, Decimal("0.90")), (7, Decimal("0.95")), (0, Decimal("1.00")))


async def _card_id(session, set_code: str, number: str):
    result = await session.execute(
        select(Card.id).join(Set, Set.id == Card.set_id).where(
            Set.code == set_code, Card.number == number
        )
    )
    return result.scalar_one()


async def _seed_prices(session) -> int:
    today = datetime.now(UTC).date()
    created = 0
    for card_data, base_price in zip(DEMO_CARDS, _BASE_PRICES, strict=True):
        card_id = await _card_id(session, card_data["set_code"], card_data["number"])
        for offset_days, factor in _PRICE_POINTS:
            day = today - timedelta(days=offset_days)
            price = (base_price * factor).quantize(Decimal("0.01"))
            result = await session.execute(
                select(CardPriceDaily).where(
                    CardPriceDaily.card_id == card_id,
                    CardPriceDaily.source == PriceSource.cardmarket,
                    CardPriceDaily.variant == PriceVariant.normal,
                    CardPriceDaily.day == day,
                )
            )
            if result.scalar_one_or_none() is not None:
                continue
            session.add(
                CardPriceDaily(
                    card_id=card_id,
                    source=PriceSource.cardmarket,
                    variant=PriceVariant.normal,
                    day=day,
                    currency="EUR",
                    price_low=price,
                    price_mid=price,
                    price_trend=price,
                )
            )
            created += 1
    await session.commit()
    return created


async def main() -> None:
    async with async_session_factory() as session:
        await seed_catalog(session)
        created = await _seed_prices(session)
        await refresh_card_value_rank(session)
        print(f"catalogue de démonstration à jour, {created} relevé(s) de prix créé(s)")


if __name__ == "__main__":
    asyncio.run(main())
