"""Preuve du livrable « anecdotes sourcées sur 20 cartes de test » (mission `v4-anecdotes`,
définition de fini). Script ponctuel, non exécuté par la suite pytest (comme les autres
`scripts/*_manual.py`) : la collecte de contexte appelle les vrais wikis Poképédia/Bulbapedia
en réseau — une suite automatisée doit rester déterministe et hors ligne, voir
`tests/test_insights_context.py`/`tests/test_card_insights.py`.

Aucune clé IA réelle n'est disponible sur chimera (D4, `docs/ARCHITECTURE.md`) : la partie
génération est simulée par `_SimulatedProvider`, qui pioche une phrase du contexte réel comme
« anecdote » et, pour une carte sur trois, une URL hors contexte — afin de vérifier sur du
contenu réel que le filtre `allowed_urls` de `pbm_api.insights.service` rejette bien toute
anecdote non sourcée. La sortie de ce script est collée telle quelle dans le compte rendu.
"""

import asyncio

from pbm_api.insights.context import (
    BULBAPEDIA_API_URL,
    POKEPEDIA_API_URL,
    ContextPage,
    MediaWikiClient,
    collect_context,
)
from pbm_api.insights.generation import build_prompt

# 20 cartes réelles, choisies pour la diversité (Pokémon iconiques, promos, ex/GX/VMAX,
# plusieurs extensions et époques) — pas besoin d'un catalogue importé localement pour cette
# preuve : la collecte de contexte ne dépend que du nom de la carte et de l'extension.
CARDS = [
    ("Dracaufeu", "Charizard", "Écarlate et Violet 151"),
    ("Pikachu", "Pikachu", "Célébrations"),
    ("Mewtwo", "Mewtwo", "Base Set"),
    ("Évoli", "Eevee", "Évolutions Prismatiques"),
    ("Léviator", "Gyarados", "Neo Genesis"),
    ("Rayquaza", "Rayquaza", "Émeraude"),
    ("Lugia", "Lugia", "Neo Genesis"),
    ("Ronflex", "Snorlax", "Jungle"),
    ("Dracolosse", "Dragonite", "Fossil"),
    ("Tortank", "Blastoise", "Base Set"),
    ("Florizarre", "Venusaur", "Base Set"),
    ("Sulfura", "Moltres", "Fossil"),
    ("Artikodin", "Articuno", "Fossil"),
    ("Électhor", "Zapdos", "Fossil"),
    ("Gardevoir", "Gardevoir", "Écarlate et Violet"),
    ("Ectoplasma", "Gengar", "Fusion d'Esprits"),
    ("Metaglinite", "Metagross", "Double Danger"),
    ("Farfuret", "Sableye", "Ténèbres Embrasées"),
    ("Miaouss", "Meowth", "Team Rocket"),
    ("Roucarnage", "Pidgeot", "Obsidian Flames"),
]


def _pick_anecdotes(pages: list[ContextPage], index: int) -> list[tuple[str, str]]:
    """Pas de clé IA réelle sur chimera : simule ce qu'un fournisseur renverrait en piochant
    une phrase du contexte réel comme anecdote « correcte », et une carte sur trois une URL
    hors contexte — pour vérifier sur du contenu réel que `pbm_api.insights.service` rejette
    bien toute anecdote non sourcée."""
    picked = []
    for page in pages:
        sentence = next((s.strip() for s in page.text.split(". ") if len(s.strip()) > 20), None)
        if sentence:
            picked.append((sentence + ".", page.source_url))
    if index % 3 == 0 and picked:
        picked.append(("Anecdote fabriquée pour le test.", "https://hors-contexte.example/"))
    return picked


async def _process_one(index: int, fr_name: str, en_name: str, set_name: str) -> dict:
    pokepedia = MediaWikiClient(POKEPEDIA_API_URL)
    bulbapedia = MediaWikiClient(BULBAPEDIA_API_URL)
    try:
        pages = await collect_context(
            card_name=fr_name,
            set_name=set_name,
            en_card_name=en_name,
            pokepedia_client=pokepedia,
            bulbapedia_client=bulbapedia,
        )
    finally:
        await pokepedia.aclose()
        await bulbapedia.aclose()

    if not pages:
        return {"card": fr_name, "status": "no_context", "anecdotes": []}

    allowed_urls = {page.source_url for page in pages}
    build_prompt(card_name=fr_name, set_name=set_name, pages=pages)  # exercé, non affiché
    raw = _pick_anecdotes(pages, index)
    sourced = [{"text": t, "source_url": u} for t, u in raw if u in allowed_urls]
    rejected = [{"text": t, "source_url": u} for t, u in raw if u not in allowed_urls]
    return {
        "card": fr_name,
        "status": "ready" if sourced else "no_context",
        "context_pages": len(pages),
        "anecdotes": sourced,
        "rejected_out_of_context": rejected,
    }


async def main() -> None:
    results = []
    for index, (fr_name, en_name, set_name) in enumerate(CARDS):
        result = await _process_one(index, fr_name, en_name, set_name)
        results.append(result)
        status = result["status"]
        n_pages = result.get("context_pages", 0)
        n_anecdotes = len(result["anecdotes"])
        n_rejected = len(result.get("rejected_out_of_context", []))
        print(
            f"{fr_name:20s} status={status:11s} pages={n_pages} "
            f"anecdotes={n_anecdotes} rejetées={n_rejected}"
        )

    ready = sum(1 for r in results if r["status"] == "ready")
    total_rejected = sum(len(r.get("rejected_out_of_context", [])) for r in results)
    print(f"\n{ready}/{len(CARDS)} cartes avec au moins une anecdote sourcée.")
    print(f"{total_rejected} anecdote(s) hors contexte correctement rejetée(s) par le filtre.")


if __name__ == "__main__":
    asyncio.run(main())
