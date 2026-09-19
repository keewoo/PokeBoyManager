"""Rapport de complétude du catalogue — mission `v2-catalogue-complet` point 4.

Écrit `docs/catalogue/COMPLETUDE.md` à partir de la base pointée par `DATABASE_URL`. Ne suppose
jamais que l'import est complet : chiffre ce qui est réellement en base, liste les trous.

Usage :
    DATABASE_URL=postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_catalogue_ref \
        uv run python scripts/generate_completeness_report.py
"""

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select

from pbm_api.db import async_session_factory
from pbm_api.models import Card, CardName, CardPriceDaily, Set

REPORT_PATH = Path(__file__).resolve().parents[3] / "docs" / "catalogue" / "COMPLETUDE.md"


async def main() -> None:
    async with async_session_factory() as session:
        sets_total = (await session.execute(select(func.count(Set.id)))).scalar_one()
        cards_total = (await session.execute(select(func.count(Card.id)))).scalar_one()

        names_by_lang = dict(
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
            await session.execute(
                select(func.count(func.distinct(CardPriceDaily.card_id)))
            )
        ).scalar_one()

        sets_without_ptcg = (
            await session.execute(
                select(Set.code, Set.name)
                .outerjoin(Card, (Card.set_id == Set.id) & Card.ptcg_id.is_not(None))
                .where(Card.id.is_(None))
                .order_by(Set.name)
            )
        ).all()

        # Trous restants : extensions où le nombre de cartes importées est inférieur au total
        # officiel annoncé par TCGdex (`Set.total_cards`) — import partiel ou source incomplète.
        cards_per_set = dict(
            (
                await session.execute(
                    select(Card.set_id, func.count(Card.id)).group_by(Card.set_id)
                )
            ).all()
        )
        all_sets = (
            await session.execute(select(Set.id, Set.code, Set.name, Set.total_cards))
        ).all()
        gaps = [
            (code, name, cards_per_set.get(set_id, 0), total_cards)
            for set_id, code, name, total_cards in all_sets
            if total_cards is not None and cards_per_set.get(set_id, 0) < total_cards
        ]
        gaps.sort(key=lambda g: g[1])

    def pct(n: int, total: int) -> str:
        return f"{(100 * n / total):.1f} %" if total else "n/a"

    def stat_line(label: str, n: int, total: int) -> str:
        return f"- {label} : **{n}** ({pct(n, total)})"

    lines = [
        "# Rapport de complétude du catalogue",
        "",
        f"Généré le {datetime.now(UTC).isoformat()} — mission `v2-catalogue-complet` point 4.",
        "",
        "## Vue d'ensemble",
        "",
        f"- Extensions : **{sets_total}**",
        f"- Cartes : **{cards_total}**",
        stat_line("Noms FR", names_by_lang.get("fr", 0), cards_total),
        stat_line("Noms EN", names_by_lang.get("en", 0), cards_total),
        stat_line("Cartes avec image officielle", cards_with_image, cards_total),
        stat_line(
            "Cartes avec `ptcg_id` (rapprochement Pokémon TCG API)", cards_with_ptcg, cards_total
        ),
        stat_line(
            "Cartes avec faiblesses ou résistances",
            cards_with_weaknesses_or_resistances,
            cards_total,
        ),
        stat_line("Cartes avec coût de retraite", cards_with_retreat, cards_total),
        stat_line("Cartes avec variantes connues", cards_with_variants, cards_total),
        stat_line("Cartes avec au moins un prix relevé", cards_with_price, cards_total),
        "",
        "## Extensions non rapprochées avec Pokémon TCG API",
        "",
        f"{len(sets_without_ptcg)} extension(s) sans une seule carte avec `ptcg_id` "
        "(absente de Pokémon TCG API, ou rapprochement raté — voir "
        "`catalog/reconciliation.py`) :",
        "",
    ]
    if sets_without_ptcg:
        lines += [f"- `{code}` — {name}" for code, name in sets_without_ptcg]
    else:
        lines.append("(aucune)")

    lines += [
        "",
        "## Trous restants (cartes manquantes par rapport au total officiel TCGdex)",
        "",
        f"{len(gaps)} extension(s) dont l'import n'a pas ramené toutes les cartes officielles :",
        "",
    ]
    if gaps:
        lines.append("| Extension | Importées | Officiel (TCGdex) |")
        lines.append("|---|---|---|")
        lines += [f"| `{code}` {name} | {got} | {total} |" for code, name, got, total in gaps]
    else:
        lines.append("(aucun — toutes les extensions ont autant de cartes que le total officiel)")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Rapport écrit : {REPORT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
