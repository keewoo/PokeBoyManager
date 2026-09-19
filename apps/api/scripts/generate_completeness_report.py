"""Rapport de complétude du catalogue — mission `v2-catalogue-complet` point 4.

Écrit `docs/catalogue/COMPLETUDE.md` à partir de la base pointée par `DATABASE_URL`.

Usage :
    DATABASE_URL=postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_catalogue_ref \
        uv run python scripts/generate_completeness_report.py
"""

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from pbm_api.catalog.completeness import CompletenessStats, compute_completeness_stats
from pbm_api.db import async_session_factory

REPORT_PATH = Path(__file__).resolve().parents[3] / "docs" / "catalogue" / "COMPLETUDE.md"


def _render(stats: CompletenessStats) -> str:
    def stat_line(label: str, n: int) -> str:
        return f"- {label} : **{n}** ({stats.pct(n):.1f} %)"

    lines = [
        "# Rapport de complétude du catalogue",
        "",
        f"Généré le {datetime.now(UTC).isoformat()} — mission `v2-catalogue-complet` point 4.",
        "",
        "## Vue d'ensemble",
        "",
        f"- Extensions : **{stats.sets_total}**",
        f"- Cartes : **{stats.cards_total}**",
        stat_line("Noms FR", stats.names_by_lang.get("fr", 0)),
        stat_line("Noms EN", stats.names_by_lang.get("en", 0)),
        stat_line("Cartes avec image officielle", stats.cards_with_image),
        stat_line("Cartes avec `ptcg_id` (rapprochement Pokémon TCG API)", stats.cards_with_ptcg),
        stat_line(
            "Cartes avec faiblesses ou résistances", stats.cards_with_weaknesses_or_resistances
        ),
        stat_line("Cartes avec coût de retraite", stats.cards_with_retreat),
        stat_line("Cartes avec variantes connues", stats.cards_with_variants),
        stat_line("Cartes avec au moins un prix relevé", stats.cards_with_price),
        "",
        "## Extensions non rapprochées avec Pokémon TCG API",
        "",
        f"{len(stats.sets_without_ptcg)} extension(s) sans une seule carte avec `ptcg_id` "
        "(absente de Pokémon TCG API, ou rapprochement raté — voir "
        "`catalog/reconciliation.py`) :",
        "",
    ]
    if stats.sets_without_ptcg:
        lines += [f"- `{code}` — {name}" for code, name in stats.sets_without_ptcg]
    else:
        lines.append("(aucune)")

    lines += [
        "",
        "## Trous restants (cartes manquantes par rapport au total officiel TCGdex)",
        "",
        f"{len(stats.gaps)} extension(s) dont l'import n'a pas ramené toutes les cartes "
        "officielles :",
        "",
    ]
    if stats.gaps:
        lines.append("| Extension | Importées | Officiel (TCGdex) |")
        lines.append("|---|---|---|")
        lines += [f"| `{code}` {name} | {got} | {total} |" for code, name, got, total in stats.gaps]
    else:
        lines.append("(aucun — toutes les extensions ont autant de cartes que le total officiel)")

    return "\n".join(lines) + "\n"


async def main() -> None:
    async with async_session_factory() as session:
        stats = await compute_completeness_stats(session)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(_render(stats), encoding="utf-8")
    print(f"Rapport écrit : {REPORT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
