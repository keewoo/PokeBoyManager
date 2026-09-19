"""Jeu de test de 30 photos et taux de détection (mission `v3-detection` point 3, objectif
≥ 95 %).

⚠️ Aucun appareil photo ni carte physique sur chimera (voir le compte rendu du lot) : ces 30
photos sont **synthétiques** (`pbm_api.detection.synthetic.generate_dataset`), construites pour
ressembler aux quatre familles demandées par la mission — carte seule, classeur 3×3 en
toploaders, table, reflets — plus un cinquième cas listé dans les risques du lot (fond clair).
Le repli LLM est simulé par un double qui renvoie directement les boîtes exactes de la photo :
ce test valide donc la *mécanique* du pipeline (contours, ratio, ordre de lecture, repli,
affinage) et son taux de détection sur ces cas construits, pas la précision réelle d'un LLM de
vision sur une vraie photo — seul un essai avec une vraie clé (mission « aucune clé IA réelle »)
peut mesurer cela, hors de portée de chimera aujourd'hui.

Avant ce lot, `pbm_api.detection` n'existait pas : ce module échoue à la collection et passe une
fois le pipeline ajouté.
"""

import json

from pbm_api.ai.base import AIProvider, ExtractionUsage, ImageInput, T
from pbm_api.detection.annotate import encode_jpeg
from pbm_api.detection.pipeline import run_detection
from pbm_api.detection.synthetic import generate_dataset
from pbm_api.models import AiProvider as AiProviderEnum

_TARGET_DETECTION_RATE = 0.95


class _GroundTruthBoxProvider(AIProvider):
    """Simule un LLM de vision parfait : renvoie les boîtes exactes de la photo passée en
    argument. Voir l'avertissement en tête de module — ce n'est pas une mesure de précision IA
    réelle, seulement une validation du reste du pipeline (affinage, recadrage, ordre)."""

    PROVIDER = AiProviderEnum.anthropic
    DEFAULT_MODEL = "ground-truth-stub"

    def __init__(self, quads_pixels, width: int, height: int) -> None:
        super().__init__(api_key="fake-key")

        def clamp(value: float) -> float:
            return max(0.0, min(1.0, value))

        self._boxes = [
            {
                "x_min": clamp(float(q[:, 0].min() / width)),
                "y_min": clamp(float(q[:, 1].min() / height)),
                "x_max": clamp(float(q[:, 0].max() / width)),
                "y_max": clamp(float(q[:, 1].max() / height)),
            }
            for q in quads_pixels
        ]

    async def _call(
        self, images: list[ImageInput], schema: type[T], prompt: str, model: str, retry_hint
    ) -> tuple[str, ExtractionUsage]:
        return (
            json.dumps({"boxes": self._boxes}),
            ExtractionUsage(provider=self.PROVIDER, model=model, input_tokens=0, output_tokens=0),
        )


async def test_detection_rate_on_synthetic_dataset_meets_target():
    photos = generate_dataset()
    assert len(photos) == 30

    successes = 0
    by_category: dict[str, list[int]] = {}
    for photo in photos:
        height, width = photo.image.shape[:2]
        provider = _GroundTruthBoxProvider(photo.ground_truth_quads, width, height)
        result = await run_detection(
            encode_jpeg(photo.image),
            ai_provider=provider,
            ai_model=None,
            ai_media_type="image/jpeg",
        )
        ok = len(result.crops) == photo.expected_count
        successes += int(ok)
        by_category.setdefault(photo.category, [0, 0])
        by_category[photo.category][1] += 1
        by_category[photo.category][0] += int(ok)

    rate = successes / len(photos)
    detail = ", ".join(f"{cat}={ok}/{n}" for cat, (ok, n) in sorted(by_category.items()))
    assert rate >= _TARGET_DETECTION_RATE, f"taux {rate:.1%} ({detail})"
