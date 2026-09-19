"""Essai manuel de la génération d'anecdotes avec une vraie clé — jamais exécuté par la suite
pytest (`tests/test_card_insights.py`/`tests/test_insights_context.py` utilisent des doubles
déterministes, aucune clé IA ni wiki réel disponible sur chimera).

Ce script fait le trajet complet en conditions réelles : recherche Poképédia/Bulbapedia,
construction du prompt, appel du fournisseur, puis affiche les anecdotes retenues (filtrées
sur les URLs de contexte, comme `pbm_api.insights.service.get_or_create_card_insight`).

Usage :
    uv run python scripts/test_insights_manual.py anthropic sk-ant-... \\
        "Dracaufeu" "Charizard" "Écarlate et Violet 151"
"""

import asyncio
import sys

from pbm_api.ai.errors import AIProviderError
from pbm_api.ai.factory import create_provider
from pbm_api.insights.context import (
    BULBAPEDIA_API_URL,
    POKEPEDIA_API_URL,
    MediaWikiClient,
    collect_context,
)
from pbm_api.insights.generation import AnecdotesExtraction, build_prompt
from pbm_api.models import AiProvider


async def main() -> None:
    if len(sys.argv) != 6:
        print(__doc__)
        raise SystemExit(1)

    provider_name = AiProvider(sys.argv[1])
    api_key = sys.argv[2]
    fr_name, en_name, set_name = sys.argv[3], sys.argv[4], sys.argv[5]

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

    print(f"Contexte trouvé : {len(pages)} page(s)")
    for page in pages:
        print(f"  - {page.source_url} ({len(page.text)} caractères)")

    if not pages:
        print("Aucun contexte : pas d'appel IA (comportement identique à l'API).")
        return

    allowed_urls = {page.source_url for page in pages}
    prompt = build_prompt(card_name=fr_name, set_name=set_name, pages=pages)

    provider = create_provider(provider_name, api_key)
    try:
        extraction, usage = await provider.extract([], AnecdotesExtraction, prompt)
    except AIProviderError as error:
        print(f"{provider_name.value}: échec — {error.user_message}")
        raise SystemExit(1) from error
    finally:
        await provider.aclose()

    print(f"usage={usage.model_dump()}")
    for item in extraction.anecdotes:
        kept = "gardée" if item.source_url in allowed_urls else "REJETÉE (URL hors contexte)"
        print(f"  [{kept}] {item.text} — {item.source_url}")


if __name__ == "__main__":
    asyncio.run(main())
