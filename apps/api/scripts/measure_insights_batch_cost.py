"""Mesure exigée par la mission `v4-insights-batch` point 3 : coût, durée et taux d'anecdotes
rejetées faute de source sur 100 cartes représentatives, puis extrapolation au catalogue
complet. Collecte réellement le contexte sur Poképédia/Bulbapedia (réseau réel, débit
raisonnable — voir `pbm_api.insights.context`) pour 100 cartes réelles, choisies pour leur
diversité (Pokémon iconiques, plusieurs époques/extensions) ; les 100 cartes elles-mêmes sont
semées dans une transaction annulée en fin de script (comme
`scripts/measure_identification_rate.py`) — rien n'est laissé dans la base pointée par
`DATABASE_URL`.

Aucune clé Anthropic réelle sur chimera (D4) : `pbm_api.insights_batch.runner.run_once` est
appelé en `dry_run=True`, qui prépare les 100 requêtes réelles (contexte réel, prompt réel)
SANS appeler l'API Anthropic. Le coût rapporté est donc une ESTIMATION (heuristique
caractères/jeton documentée dans `pbm_api.insights_batch.runner`), pas une mesure facturée —
la mesure RÉELLE (`status == "termine"`, coût `usage`) suppose `PLATFORM_ANTHROPIC_API_KEY` et
`INSIGHTS_BUDGET_EUR`, fournies par JF (D4), absentes ici : `--live` réutilise ce même script
pour la lancer dès qu'elles seront disponibles.

Usage :
    uv run python scripts/measure_insights_batch_cost.py                  # estimation (dry-run)
    uv run python scripts/measure_insights_batch_cost.py --live           # mesure réelle facturée
    uv run python scripts/measure_insights_batch_cost.py --out report.json
"""

import argparse
import asyncio
import json
import time
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from pbm_api.config import settings
from pbm_api.insights.context import BULBAPEDIA_API_URL, POKEPEDIA_API_URL, MediaWikiClient
from pbm_api.insights_batch.runner import run_once
from pbm_api.models import Card, Set

CARD_NAMES = [
    "Dracaufeu", "Pikachu", "Mewtwo", "Évoli", "Léviator", "Rayquaza", "Lugia", "Ronflex",
    "Dracolosse", "Tortank", "Florizarre", "Sulfura", "Artikodin", "Électhor", "Gardevoir",
    "Ectoplasma", "Metaglinite", "Farfuret", "Miaouss", "Roucarnage", "Salamèche", "Bulbizarre",
    "Carapuce", "Raichu", "Nidoking", "Alakazam", "Machamp", "Rondoudou", "Magicarpe", "Mew",
    "Feunard", "Arcanin", "Ossatueur", "Scarabrute", "Lokhlass", "Ptera", "Aquali", "Pyroli",
    "Voltali", "Noctali", "Phyllali", "Givrali", "Nymphali", "Minidraco", "Draco", "Dracaufeu-GX",
    "Pikachu-VMAX", "Sablaireau", "Excavarion", "Groudon",
]

SET_NAMES = [
    "Base Set", "Jungle", "Fossil", "Team Rocket", "Neo Genesis", "Neo Discovery",
    "Aquapolis", "Skyridge", "Diamant et Perle", "Platine", "HeartGold SoulSilver",
    "Noir et Blanc", "XY", "Soleil et Lune", "Épée et Bouclier", "Écarlate et Violet",
    "Célébrations", "Évolutions Prismatiques", "Obsidian Flames", "Double Danger",
]

TARGET_CARD_COUNT = 100


def _representative_cards() -> list[tuple[str, str]]:
    """100 couples (carte, extension) réels, cycliques sur les deux listes ci-dessus (noms
    inchangés — un nom altéré casserait la recherche MediaWiki) : la diversité prime sur
    l'exactitude historique carte/extension pour cette mesure de coût, pas un jeu de test
    d'identification. `number` (dans `_seed_cards`) suffit à distinguer les lignes en base."""
    return [
        (CARD_NAMES[i % len(CARD_NAMES)], SET_NAMES[i % len(SET_NAMES)])
        for i in range(TARGET_CARD_COUNT)
    ]


async def _seed_cards(session: AsyncSession) -> list[Card]:
    cards = []
    sets_by_name: dict[str, Set] = {}
    for index, (name, set_name) in enumerate(_representative_cards()):
        set_row = sets_by_name.get(set_name)
        if set_row is None:
            set_row = Set(code=f"measure-{index}", name=set_name, release_date=date(2020, 1, 1))
            session.add(set_row)
            await session.flush()
            sets_by_name[set_name] = set_row
        card = Card(
            set_id=set_row.id,
            number=str(index),
            name=name,
            supertype="Pokemon",
            legal_standard=index % 2 == 0,
            legal_expanded=True,
            attacks=[{"name": "Attaque", "damage": 60 + (index % 5) * 20}],
        )
        session.add(card)
        cards.append(card)
    await session.flush()
    return cards


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--live",
        action="store_true",
        help="mesure réelle facturée (nécessite PLATFORM_ANTHROPIC_API_KEY)",
    )
    parser.add_argument("--out", type=str, default=None)
    args = parser.parse_args()

    engine = create_async_engine(settings.database_url)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(bind=connection, expire_on_commit=False)
        try:
            cards = await _seed_cards(session)
            print(f"{len(cards)} cartes représentatives semées (transaction non validée).")

            start = time.monotonic()
            report = await run_once(
                session,
                dry_run=not args.live,
                pokepedia_client=MediaWikiClient(POKEPEDIA_API_URL),
                bulbapedia_client=MediaWikiClient(BULBAPEDIA_API_URL),
            )
            elapsed = time.monotonic() - start

            no_context = sum(1 for o in report.outcomes if o.status == "prepared_no_context")
            with_context = len(report.outcomes) - no_context

            summary = {
                "mode": "reel_facture" if args.live else "estimation_dry_run",
                "cartes_traitees": len(report.outcomes),
                "cartes_avec_contexte": with_context,
                "cartes_sans_contexte": no_context,
                "taux_sans_contexte": (
                    round(no_context / len(report.outcomes), 3) if report.outcomes else None
                ),
                "duree_secondes": round(elapsed, 1),
                "cout_usd": str(report.cost_usd),
                "cout_eur": str(report.cost_eur),
                "statut": report.status,
                "detail": report.detail,
            }
            if summary["cartes_traitees"]:
                cost_per_card_eur = report.cost_eur / summary["cartes_traitees"]
                summary["cout_par_carte_eur"] = str(cost_per_card_eur)
                # Extrapolation au catalogue complet — nombre de cartes non connu de ce script
                # (dépend du catalogue réellement importé, lot v2-catalogue-complet) : le
                # multiplicateur est donné en clair dans le compte rendu, pas deviné ici.
                for total in (5_000, 15_000, 30_000):
                    summary[f"extrapolation_{total}_cartes_eur"] = str(cost_per_card_eur * total)

            print(json.dumps(summary, indent=2, ensure_ascii=False))
            if args.out:
                with open(args.out, "w") as f:
                    json.dump(summary, f, indent=2, ensure_ascii=False)
                print(f"Rapport écrit dans {args.out}")
        finally:
            await session.close()
            await transaction.rollback()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
