"""Statistiques de complétude du catalogue — mission `v2-catalogue-complet` point 4.

Ne suppose jamais que l'import est complet : chiffre ce qui est réellement en base. Réutilisé par
`scripts/generate_completeness_report.py` (rapport Markdown) et par les tests (seuils minimaux sur
un échantillon, mission point 6).
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.models import Card, CardName, CardPriceDaily, Set


@dataclass
class CompletenessStats:
    sets_total: int
    cards_total: int
    names_by_lang: dict[str, int]
    cards_with_image: int
    cards_with_ptcg: int
    cards_with_weaknesses_or_resistances: int
    cards_with_retreat: int
    cards_with_variants: int
    cards_with_price: int
    sets_without_ptcg: list[tuple[str, str]]
    gaps: list[tuple[str, str, int, int]]  # code, name, cartes importées, total officiel TCGdex

    def pct(self, n: int) -> float:
        return (100 * n / self.cards_total) if self.cards_total else 0.0


async def compute_completeness_stats(session: AsyncSession) -> CompletenessStats:
    sets_total = (await session.execute(select(func.count(Set.id)))).scalar_one()
    cards_total = (await session.execute(select(func.count(Card.id)))).scalar_one()

    names_by_lang: dict[str, int] = dict(
        (
            await session.execute(
                select(CardName.language, func.count(func.distinct(CardName.card_id))).group_by(
                    CardName.language
                )
            )
        ).all()
    )

    cards_with_image = (
        await session.execute(select(func.count(Card.id)).where(Card.image_url.is_not(None)))
    ).scalar_one()
    cards_with_ptcg = (
        await session.execute(select(func.count(Card.id)).where(Card.ptcg_id.is_not(None)))
    ).scalar_one()
    cards_with_weaknesses_or_resistances = (
        await session.execute(
            select(func.count(Card.id)).where(
                Card.weaknesses.is_not(None) | Card.resistances.is_not(None)
            )
        )
    ).scalar_one()
    cards_with_retreat = (
        await session.execute(select(func.count(Card.id)).where(Card.retreat_cost.is_not(None)))
    ).scalar_one()
    cards_with_variants = (
        await session.execute(select(func.count(Card.id)).where(Card.variants.is_not(None)))
    ).scalar_one()
    cards_with_price = (
        await session.execute(select(func.count(func.distinct(CardPriceDaily.card_id))))
    ).scalar_one()

    sets_without_ptcg: list[Any] = (
        await session.execute(
            select(Set.code, Set.name)
            .outerjoin(Card, (Card.set_id == Set.id) & Card.ptcg_id.is_not(None))
            .where(Card.id.is_(None))
            .order_by(Set.name)
        )
    ).all()

    # Trous restants : extensions où le nombre de cartes importées est inférieur au total
    # officiel annoncé par TCGdex (`Set.total_cards`) — import partiel ou source incomplète.
    cards_per_set_result = await session.execute(
        select(Card.set_id, func.count(Card.id)).group_by(Card.set_id)
    )
    cards_per_set: dict[Any, int] = dict(cards_per_set_result.all())
    all_sets = (await session.execute(select(Set.id, Set.code, Set.name, Set.total_cards))).all()
    gaps = sorted(
        (
            (code, name, cards_per_set.get(set_id, 0), total_cards)
            for set_id, code, name, total_cards in all_sets
            if total_cards is not None and cards_per_set.get(set_id, 0) < total_cards
        ),
        key=lambda g: g[1],
    )

    return CompletenessStats(
        sets_total=sets_total,
        cards_total=cards_total,
        names_by_lang=names_by_lang,
        cards_with_image=cards_with_image,
        cards_with_ptcg=cards_with_ptcg,
        cards_with_weaknesses_or_resistances=cards_with_weaknesses_or_resistances,
        cards_with_retreat=cards_with_retreat,
        cards_with_variants=cards_with_variants,
        cards_with_price=cards_with_price,
        sets_without_ptcg=list(sets_without_ptcg),
        gaps=gaps,
    )
