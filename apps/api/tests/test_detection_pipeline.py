"""Orchestration OpenCV + repli LLM (mission `v3-detection` points 1 et 2).

Le repli est testé avec un double du fournisseur IA (`_call` renvoie directement les boîtes
attendues, sans réseau) — même principe que les fournisseurs réels (Anthropic/Gemini/OpenAI),
mais sans dépendre de leurs implémentations HTTP (déjà couvertes par `tests/test_ai_providers.py`,
mission `v3-ia-providers`). Ce test-ci porte sur l'orchestration : OpenCV d'abord, LLM seulement
si le résultat n'est pas plausible, affinage OpenCV dans chaque boîte ensuite.

Avant ce lot, `pbm_api.detection.pipeline` n'existait pas : ce module échoue à la collection et
passe une fois le fichier ajouté.
"""

import json

import cv2

from pbm_api.ai.base import AIProvider, ExtractionUsage, ImageInput, T
from pbm_api.detection.geometry import CARD_HEIGHT_PX, CARD_WIDTH_PX
from pbm_api.detection.pipeline import run_detection
from pbm_api.detection.synthetic import make_single_card, make_table_scatter
from pbm_api.models import AiProvider as AiProviderEnum


class _FakeBoxProvider(AIProvider):
    PROVIDER = AiProviderEnum.anthropic
    DEFAULT_MODEL = "fake-vision-model"

    def __init__(self, boxes: list[dict]) -> None:
        super().__init__(api_key="fake-key")
        self._boxes = boxes
        self.calls = 0

    async def _call(
        self, images: list[ImageInput], schema: type[T], prompt: str, model: str, retry_hint
    ) -> tuple[str, ExtractionUsage]:
        self.calls += 1
        return (
            json.dumps({"boxes": self._boxes}),
            ExtractionUsage(
                provider=self.PROVIDER, model=model, input_tokens=120, output_tokens=40
            ),
        )


def _touching_cards_photo():
    photo = make_table_scatter(seed=300, index=0, count=2)
    return photo.image, photo.ground_truth_quads


def _encode(image) -> bytes:
    ok, buffer = cv2.imencode(".jpg", image)
    assert ok
    return buffer.tobytes()


async def test_run_detection_uses_opencv_when_plausible():
    photo = make_single_card(seed=1, index=0)
    provider = _FakeBoxProvider(boxes=[])

    result = await run_detection(
        _encode(photo.image), ai_provider=provider, ai_model=None, ai_media_type="image/jpeg"
    )

    assert result.method == "opencv"
    assert len(result.crops) == 1
    assert result.crops[0].shape == (CARD_HEIGHT_PX, CARD_WIDTH_PX, 3)
    assert result.ai_usage is None
    assert provider.calls == 0  # OpenCV a suffi : aucun appel IA gaspillé


async def test_run_detection_falls_back_to_llm_when_cards_touch():
    canvas, ground_truth = _touching_cards_photo()
    height, width = canvas.shape[:2]
    boxes = [
        {
            "x_min": float(q[:, 0].min() / width),
            "y_min": float(q[:, 1].min() / height),
            "x_max": float(q[:, 0].max() / width),
            "y_max": float(q[:, 1].max() / height),
        }
        for q in ground_truth
    ]
    provider = _FakeBoxProvider(boxes=boxes)

    result = await run_detection(
        _encode(canvas), ai_provider=provider, ai_model=None, ai_media_type="image/jpeg"
    )

    assert result.method == "llm_fallback"
    assert provider.calls == 1
    assert len(result.crops) == 2
    assert all(crop.shape == (CARD_HEIGHT_PX, CARD_WIDTH_PX, 3) for crop in result.crops)
    assert result.ai_usage is not None
    assert result.ai_usage.input_tokens == 120


async def test_run_detection_without_ai_provider_returns_opencv_result_even_if_implausible():
    """D4 : sans clé IA, la reconnaissance reste désactivée — mais la détection ne plante pas,
    elle renvoie simplement ce qu'OpenCV seul a trouvé (potentiellement incomplet)."""
    canvas, _ground_truth = _touching_cards_photo()

    result = await run_detection(
        _encode(canvas), ai_provider=None, ai_model=None, ai_media_type="image/jpeg"
    )

    assert result.method == "opencv"
    assert len(result.crops) < 2
