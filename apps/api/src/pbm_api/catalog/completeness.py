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

# Libellés TCGdex de la catégorie "Dresseur" et de l'Énergie spéciale, dans les deux langues
# d'import (le contenu est pris en français quand il existe, en anglais sinon — voir le repli de
# `import_service`). On compte sur les DEUX pour que le chiffre ne dépende pas de la langue source.
TRAINER_SUPERTYPES = ("Dresseur", "Trainer")
SPECIAL_ENERGY_TYPES = ("Spécial", "Special")


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
    # Texte d'effet (lot `cat-textes-effets`) : les Dresseurs et les Énergies spéciales sont les
    # seules cartes censées en avoir. On mesure le remplissage réel, jamais supposé complet.
    cards_trainers: int
    cards_trainers_with_effect: int
    trainers_by_type: list[tuple[str, int, int]]  # sous-type, total, avec effet
    cards_special_energy: int
    cards_special_energy_with_effect: int
    sets_without_ptcg: list[tuple[str, str]]
    gaps: list[tuple[str, str, int, int]]  # code, name, cartes importées, total officiel TCGdex

    def pct(self, n: int) -> float:
        return (100 * n / self.cards_total) if self.cards_total else 0.0

    @staticmethod
    def ratio_pct(n: int, total: int) -> float:
        """Pourcentage de `n` sur un sous-ensemble `total` (ex. Dresseurs avec effet / Dresseurs),
        et non sur l'ensemble des cartes — `pct` surestimerait en divisant par `cards_total`."""
        return (100 * n / total) if total else 0.0


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

    # Texte d'effet des Dresseurs et des Énergies spéciales (lot `cat-textes-effets`). « Avec
    # effet » = `effect` non nul ET non vide : une carte sans texte chez TCGdex reste vide et se
    # compte comme telle, jamais un texte inventé.
    has_effect = Card.effect.is_not(None) & (Card.effect != "")
    is_trainer = Card.supertype.in_(TRAINER_SUPERTYPES)
    is_special_energy = Card.energy_type.in_(SPECIAL_ENERGY_TYPES)

    cards_trainers = (
        await session.execute(select(func.count(Card.id)).where(is_trainer))
    ).scalar_one()
    cards_trainers_with_effect = (
        await session.execute(select(func.count(Card.id)).where(is_trainer & has_effect))
    ).scalar_one()
    trainers_by_type = [
        (subtype if subtype is not None else "(sans sous-type)", total, with_effect)
        for subtype, total, with_effect in (
            await session.execute(
                select(
                    Card.trainer_type,
                    func.count(Card.id),
                    func.count(Card.id).filter(has_effect),
                )
                .where(is_trainer)
                .group_by(Card.trainer_type)
                .order_by(func.count(Card.id).desc())
            )
        ).all()
    ]
    cards_special_energy = (
        await session.execute(select(func.count(Card.id)).where(is_special_energy))
    ).scalar_one()
    cards_special_energy_with_effect = (
        await session.execute(select(func.count(Card.id)).where(is_special_energy & has_effect))
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
        cards_trainers=cards_trainers,
        cards_trainers_with_effect=cards_trainers_with_effect,
        trainers_by_type=trainers_by_type,
        cards_special_energy=cards_special_energy,
        cards_special_energy_with_effect=cards_special_energy_with_effect,
        sets_without_ptcg=list(sets_without_ptcg),
        gaps=gaps,
    )
