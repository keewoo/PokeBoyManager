"""Orchestration de la détection (mission points 1 et 2) : essai OpenCV d'abord, repli par
boîtes englobantes LLM + affinage OpenCV dans chaque boîte si le résultat n'est pas plausible.
"""

from dataclasses import dataclass

import cv2
import numpy as np

from pbm_api.ai.base import AIProvider, ExtractionUsage, ImageInput
from pbm_api.detection.annotate import draw_control_image
from pbm_api.detection.geometry import warp_card
from pbm_api.detection.llm_fallback import NormalizedBox, denormalize_box, detect_boxes_with_llm
from pbm_api.detection.opencv_pipeline import find_card_quads, has_unclaimed_regions

# Marge ajoutée autour d'une boîte LLM avant l'affinage OpenCV local (mission point 2) : la
# boîte du modèle vision est rarement pixel-parfaite, cette marge laisse le contour réel de la
# carte apparaître entièrement dans la sous-image analysée.
_REFINE_MARGIN_FRACTION = 0.08


class DetectionFailedError(Exception):
    """Ni OpenCV ni le repli LLM (absent ou en échec) n'ont produit de carte plausible."""


@dataclass(frozen=True)
class DetectionRunResult:
    quads: list[np.ndarray]  # coordonnées pixels dans l'image d'origine, ordre de lecture
    crops: list[np.ndarray]  # BGR, 630×880, un par quad
    annotated_jpeg: bytes
    method: str  # "opencv" | "llm_fallback"
    ai_usage: ExtractionUsage | None


def decode_image(data: bytes) -> np.ndarray:
    array = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if image is None:
        raise DetectionFailedError("photo illisible par OpenCV (décodage échoué)")
    return image


def _is_plausible(image: np.ndarray, quads: list[np.ndarray]) -> bool:
    """Heuristique de repli (mission point 2, « nombre ou forme incohérent ») : aucune carte
    trouvée, ou une zone de la taille d'une carte laissée sans quadrilatère retenu (cartes qui
    se touchent, contour fusionné rejeté par `find_card_quads` — voir `has_unclaimed_regions`).
    """
    if not quads:
        return False
    return not has_unclaimed_regions(image, quads)


def refine_box_with_opencv(image: np.ndarray, box: NormalizedBox) -> np.ndarray:
    """Affinage OpenCV local d'une boîte LLM — public depuis `pbm-hotfix-fallback-ia-confiance` :
    le secours d'identification (`pbm_api.identification.rescue`) réutilise exactement le même
    affinage pour redécouper une carte mal cadrée, jamais une seconde implémentation."""
    height, width = image.shape[:2]
    x_min, y_min, x_max, y_max = denormalize_box(box, width, height)
    box_width, box_height = x_max - x_min, y_max - y_min
    margin_x = round(box_width * _REFINE_MARGIN_FRACTION)
    margin_y = round(box_height * _REFINE_MARGIN_FRACTION)
    crop_x0 = max(0, x_min - margin_x)
    crop_y0 = max(0, y_min - margin_y)
    crop_x1 = min(width, x_max + margin_x)
    crop_y1 = min(height, y_max + margin_y)

    sub_image = image[crop_y0:crop_y1, crop_x0:crop_x1]
    local_quads = find_card_quads(sub_image) if sub_image.size else []
    if local_quads:
        # Le plus grand contour plausible de la sous-image est la carte visée par la boîte.
        best = max(local_quads, key=cv2.contourArea)
        return best + np.array([crop_x0, crop_y0], dtype=np.float32)

    # Aucun contour net dans la boîte (pochette/reflet) : le rectangle du LLM devient le quad,
    # tel quel — mieux qu'aucune détection.
    return np.array(
        [[x_min, y_min], [x_max, y_min], [x_max, y_max], [x_min, y_max]], dtype=np.float32
    )


async def run_detection(
    image_bytes: bytes,
    *,
    ai_provider: AIProvider | None,
    ai_model: str | None,
    ai_media_type: str | None,
) -> DetectionRunResult:
    image = decode_image(image_bytes)

    quads = find_card_quads(image)
    method = "opencv"
    ai_usage: ExtractionUsage | None = None

    if not _is_plausible(image, quads) and ai_provider is not None:
        boxes, ai_usage = await detect_boxes_with_llm(
            ai_provider,
            ImageInput(data=image_bytes, media_type=ai_media_type or "image/jpeg"),
            model=ai_model,
        )
        quads = [refine_box_with_opencv(image, box) for box in boxes]
        method = "llm_fallback"

    crops = [warp_card(image, quad) for quad in quads]
    annotated = draw_control_image(image, quads)

    return DetectionRunResult(
        quads=quads, crops=crops, annotated_jpeg=annotated, method=method, ai_usage=ai_usage
    )
