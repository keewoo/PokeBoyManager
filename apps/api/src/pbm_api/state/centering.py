"""Mesure du centrage (mission point 1) sur le recadrage redressé (630×880 px,
`pbm_api.detection.geometry`) : la plupart des cartes Pokémon impriment une bordure de couleur
unie autour du cadre (illustration + texte) — jamais parfaitement centrée par l'imprimeur. On
retrouve ce cadre intérieur par contraste de couleur avec la bordure, sans jamais faire appel à
l'IA (mesure déterministe, disponible même sans clé IA, D4).

Limite documentée (mission « risques & pièges ») : une carte sans bordure imprimée (full art,
gold — voir `pbm_api.identification.schemas.CardVariantGuess`) ou une photo trop peu contrastée
(reflet de pochette) ne permet pas de distinguer un cadre intérieur — `measure_centering` renvoie
alors `None` plutôt que d'inventer une mesure.
"""

from dataclasses import dataclass

import cv2
import numpy as np

from pbm_api.state.grades import ConditionGrade, worst_grade

# Épaisseur de la bande échantillonnée le long de chaque bord pour estimer la couleur de la
# bordure — assez fine pour rester dans la bordure même sur une carte à faibles marges.
_BORDER_SAMPLE_PX = 3

# Le rectangle intérieur trouvé doit rester dans cette fourchette de la surface totale : trop
# grand (proche de 100 %) -> aucune bordure distincte (carte full art, ou contraste insuffisant) ;
# trop petit -> probablement du bruit plutôt qu'un vrai cadre.
_MIN_INNER_AREA_RATIO = 0.20
_MAX_INNER_AREA_RATIO = 0.95

# En dessous de cette marge (px), un côté est considéré comme "sans marge mesurable" plutôt que
# parfaitement centré à zéro — évite de confondre un cadre mal détecté avec un centrage parfait.
_MIN_MEASURABLE_MARGIN_PX = 3

# Seuils de centrage (pourcentage du côté le plus marqué, ex: 58/42) — barème indicatif inspiré
# des grilles usuelles du marché, pas une norme professionnelle (mission « estimation
# indicative, pas une gradation »).
_CENTERING_THRESHOLDS: list[tuple[float, ConditionGrade]] = [
    (55.0, ConditionGrade.mint),
    (60.0, ConditionGrade.near_mint),
    (65.0, ConditionGrade.excellent),
    (70.0, ConditionGrade.good),
    (75.0, ConditionGrade.light_played),
    (80.0, ConditionGrade.played),
]


@dataclass(frozen=True)
class AxisCentering:
    near_px: int
    far_px: int
    ratio_label: str  # ex: "58/42" (côté le plus marqué en premier)
    grade: ConditionGrade


@dataclass(frozen=True)
class CenteringResult:
    left_px: int
    right_px: int
    top_px: int
    bottom_px: int
    horizontal: AxisCentering | None
    vertical: AxisCentering | None
    grade: ConditionGrade | None


def _border_color(image: np.ndarray) -> np.ndarray:
    h, w = image.shape[:2]
    strips = [
        image[:_BORDER_SAMPLE_PX, :],
        image[h - _BORDER_SAMPLE_PX :, :],
        image[:, :_BORDER_SAMPLE_PX],
        image[:, w - _BORDER_SAMPLE_PX :],
    ]
    pixels = np.concatenate([s.reshape(-1, 3) for s in strips], axis=0)
    return np.median(pixels, axis=0)


def _inner_bbox(image: np.ndarray) -> tuple[int, int, int, int] | None:
    """Boîte englobante du plus grand composant connexe qui contredit la couleur de bordure —
    le cadre intérieur (illustration + texte). `None` si rien d'assez net ne s'en distingue."""
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB).astype(np.float32)
    border_bgr = _border_color(image).reshape(1, 1, 3).astype(np.uint8)
    border_lab = cv2.cvtColor(border_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)[0, 0]

    distance = np.linalg.norm(lab - border_lab, axis=2)
    normalized = cv2.normalize(distance, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    _, mask = cv2.threshold(normalized, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Nettoyage morphologique : une bordure texturée (illustration interne au cadre lui-même)
    # laisse de petits îlots faux-positifs que l'ouverture élimine sans bouger le grand cadre.
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

    num_labels, _labels, stats, _centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if num_labels <= 1:
        return None

    areas = stats[1:, cv2.CC_STAT_AREA]
    largest_index = int(np.argmax(areas)) + 1
    total_area = image.shape[0] * image.shape[1]
    area_ratio = stats[largest_index, cv2.CC_STAT_AREA] / total_area
    if not (_MIN_INNER_AREA_RATIO <= area_ratio <= _MAX_INNER_AREA_RATIO):
        return None

    x = int(stats[largest_index, cv2.CC_STAT_LEFT])
    y = int(stats[largest_index, cv2.CC_STAT_TOP])
    w = int(stats[largest_index, cv2.CC_STAT_WIDTH])
    h = int(stats[largest_index, cv2.CC_STAT_HEIGHT])
    return x, y, w, h


def _axis_centering(near_px: int, far_px: int) -> AxisCentering | None:
    total = near_px + far_px
    if total < _MIN_MEASURABLE_MARGIN_PX:
        return None
    near_pct = 100.0 * near_px / total
    far_pct = 100.0 * far_px / total
    worse_pct = max(near_pct, far_pct)
    grade = ConditionGrade.poor
    for threshold, candidate in _CENTERING_THRESHOLDS:
        if worse_pct <= threshold:
            grade = candidate
            break
    label = (
        f"{round(near_pct)}/{round(far_pct)}"
        if near_pct >= far_pct
        else f"{round(far_pct)}/{round(near_pct)}"
    )
    return AxisCentering(near_px=near_px, far_px=far_px, ratio_label=label, grade=grade)


def measure_centering(crop_bgr: np.ndarray) -> CenteringResult | None:
    bbox = _inner_bbox(crop_bgr)
    if bbox is None:
        return None
    x, y, w, h = bbox
    height, width = crop_bgr.shape[:2]

    left_px, right_px = x, width - (x + w)
    top_px, bottom_px = y, height - (y + h)

    horizontal = _axis_centering(left_px, right_px)
    vertical = _axis_centering(top_px, bottom_px)
    grade = worst_grade(
        [horizontal.grade if horizontal else None, vertical.grade if vertical else None]
    )

    return CenteringResult(
        left_px=left_px,
        right_px=right_px,
        top_px=top_px,
        bottom_px=bottom_px,
        horizontal=horizontal,
        vertical=vertical,
        grade=grade,
    )
