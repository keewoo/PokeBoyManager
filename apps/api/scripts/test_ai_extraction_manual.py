"""Essai manuel d'`AIProvider.extract` avec une vraie clé — jamais exécuté par la suite pytest.

Aucune clé IA réelle n'est disponible sur chimera : la suite automatisée
(`tests/test_ai_providers.py`) remplace tout appel réseau par des réponses enregistrées. Ce
script sert à vérifier, plus tard, à la main, la sortie structurée native de chaque
fournisseur contre le vrai réseau — pas seulement le format documenté. L'image envoyée est un
pixel 1x1 sans rapport avec une carte Pokémon : ce script prouve le format de la requête,
l'authentification et le décodage de la réponse, pas la qualité de la reconnaissance (lot
futur, une fois `import_catalogue` et une vraie photo de carte disponibles).

Usage :
    uv run python scripts/test_ai_extraction_manual.py anthropic sk-ant-...
    uv run python scripts/test_ai_extraction_manual.py openai sk-...
    uv run python scripts/test_ai_extraction_manual.py gemini AIza...
"""

import asyncio
import base64
import sys

from pydantic import BaseModel

from pbm_api.ai.base import ImageInput
from pbm_api.ai.errors import AIProviderError
from pbm_api.ai.factory import create_provider
from pbm_api.models import AiProvider

# PNG 1x1 rouge opaque — suffisant pour valider le format de requête vision d'un fournisseur,
# pas pour juger de sa capacité de reconnaissance.
_RED_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class SampleExtraction(BaseModel):
    dominant_color: str


async def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(1)

    provider_name = AiProvider(sys.argv[1])
    api_key = sys.argv[2]

    provider = create_provider(provider_name, api_key)
    try:
        result, usage = await provider.extract(
            [ImageInput(data=_RED_PIXEL_PNG, media_type="image/png")],
            SampleExtraction,
            "Réponds avec la couleur dominante de l'image en un mot.",
        )
    except AIProviderError as error:
        print(f"{provider_name.value}: échec — {error.user_message}")
        raise SystemExit(1) from error
    finally:
        await provider.aclose()

    print(f"{provider_name.value}: {result.model_dump()} — usage={usage.model_dump()}")


if __name__ == "__main__":
    asyncio.run(main())
