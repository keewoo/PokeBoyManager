"""Essai manuel de l'extraction par carte (mission `v3-identification` point 1) avec une vraie
clé — jamais exécuté par la suite pytest.

Aucune clé IA réelle n'est disponible sur chimera : la suite automatisée
(`tests/test_identification_service.py`) remplace tout appel réseau par un double
(`AIProvider` stubé). Ce script sert à vérifier, plus tard, à la main, la qualité réelle de la
lecture d'une carte (nom, numéro, extension, langue, PV, variante, confiance par champ) contre
le vrai réseau — pas seulement le format documenté. L'image envoyée est une carte synthétique
(`pbm_api.detection.synthetic.make_single_card`), pas une vraie photo : ce script prouve le
format de la requête, l'authentification et le rapprochement catalogue en aval, pas la
précision d'un LLM de vision sur une vraie carte physique.

Usage :
    uv run python scripts/test_identification_manual.py anthropic sk-ant-...
    uv run python scripts/test_identification_manual.py openai sk-...
    uv run python scripts/test_identification_manual.py gemini AIza...
"""

import asyncio
import sys

import cv2

from pbm_api.ai.base import ImageInput
from pbm_api.ai.errors import AIProviderError
from pbm_api.ai.factory import create_provider
from pbm_api.detection.geometry import warp_card
from pbm_api.detection.synthetic import make_single_card
from pbm_api.identification.extraction import extract_card
from pbm_api.models import AiProvider


async def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(1)

    provider_name = AiProvider(sys.argv[1])
    api_key = sys.argv[2]

    photo = make_single_card(seed=1, index=0)
    crop = warp_card(photo.image, photo.ground_truth_quads[0])
    ok, buffer = cv2.imencode(".jpg", crop)
    assert ok
    image = ImageInput(data=buffer.tobytes(), media_type="image/jpeg")

    provider = create_provider(provider_name, api_key)
    try:
        extraction, usage = await extract_card(provider, image)
    except AIProviderError as error:
        print(f"{provider_name.value}: échec — {error.user_message}")
        raise SystemExit(1) from error
    finally:
        await provider.aclose()

    print(f"{provider_name.value}: {extraction.model_dump()}")
    print(f"usage={usage.model_dump()}")


if __name__ == "__main__":
    asyncio.run(main())
