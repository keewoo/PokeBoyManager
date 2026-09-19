"""Essai manuel avec une vraie clé IA — jamais exécuté par la suite pytest.

Aucune clé IA réelle n'est disponible sur chimera : ce script sert à vérifier, plus tard, à
la main, que `ProviderKeyTester` fonctionne contre les vrais fournisseurs (pas seulement le
double utilisé dans les tests).

Usage :
    uv run python scripts/test_ai_key_manual.py anthropic sk-ant-...
    uv run python scripts/test_ai_key_manual.py openai sk-...
    uv run python scripts/test_ai_key_manual.py gemini AIza...
"""

import asyncio
import sys

from pbm_api.ai.providers import ProviderKeyTester
from pbm_api.models import AiProvider


async def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(1)

    provider = AiProvider(sys.argv[1])
    api_key = sys.argv[2]

    valid, message = await ProviderKeyTester().test(provider, api_key)
    print(f"{provider.value}: valide={valid} — {message}")


if __name__ == "__main__":
    asyncio.run(main())
