"""Détection de cartes par contours OpenCV (mission point 1) : Canny + approximation
polygonale, filtrage par ratio 63×88 mm — pas de dépendance à l'IA dans ce chemin, c'est le
premier essai avant tout repli (`pbm_api.detection.llm_fallback`).
"""

import cv2
import numpy as np

from pbm_api.detection.geometry import CARD_ASPECT_RATIO, order_reading_sequence, warp_card

# Tolérance sur le ratio largeur/hauteur d'un contour retenu comme carte : une carte peut être
# détectée dans les deux orientations (portrait ou tournée à ~90°), la seconde borne est donc
# l'inverse du ratio. Marge ±12 % pour absorber l'erreur de perspective résiduelle après
# `approxPolyDP` (mesurée sur le jeu de test synthétique, mission point 3).
_RATIO_TOLERANCE = 0.12
_MIN_AREA_FRACTION = 0.01  # une carte plus petite que 1 % de la photo est un bruit de contour
_MAX_AREA_FRACTION = 0.95
_CANNY_LOW, _CANNY_HIGH = 40, 120


def _ratio_matches_card(quad: np.ndarray) -> bool:
    pts = quad.reshape(4, 2)
    ordered = pts[np.argsort(pts[:, 1])]
    top, bottom = ordered[:2], ordered[2:]
    width = float(np.linalg.norm(top[0] - top[1]) + np.linalg.norm(bottom[0] - bottom[1])) / 2
    height_pts = pts[np.argsort(pts[:, 0])]
    left, right = height_pts[:2], height_pts[2:]
    height = float(np.linalg.norm(left[0] - left[1]) + np.linalg.norm(right[0] - right[1])) / 2
    if width <= 0 or height <= 0:
        return False
    ratio = min(width, height) / max(width, height)
    return abs(ratio - CARD_ASPECT_RATIO) <= _RATIO_TOLERANCE


def _rect_intersection_area(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> int:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix1, iy1 = max(ax, bx), max(ay, by)
    ix2, iy2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0
    return (ix2 - ix1) * (iy2 - iy1)


def _rect_iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    aw, ah = a[2], a[3]
    bw, bh = b[2], b[3]
    intersection = _rect_intersection_area(a, b)
    union = aw * ah + bw * bh - intersection
    return intersection / union if union > 0 else 0.0


def _rect_containment(inner: tuple[int, int, int, int], outer: tuple[int, int, int, int]) -> float:
    """Fraction de `inner` couverte par `outer` — contrairement à l'IoU, un petit contour
    entièrement à l'intérieur d'un plus grand (le dessin à l'intérieur d'une carte) obtient un
    score de 1.0 au lieu d'être ignoré à cause de la différence de taille des deux boîtes."""
    inner_area = inner[2] * inner[3]
    if inner_area == 0:
        return 0.0
    return _rect_intersection_area(inner, outer) / inner_area


def _deduplicate(quads: list[np.ndarray]) -> list[np.ndarray]:
    kept: list[np.ndarray] = []
    for quad in sorted(quads, key=cv2.contourArea, reverse=True):
        quad_rect = cv2.boundingRect(quad.astype(np.int32))
        if all(_rect_iou(quad_rect, cv2.boundingRect(k.astype(np.int32))) < 0.5 for k in kept):
            kept.append(quad)
    return kept


def _edges(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, _CANNY_LOW, _CANNY_HIGH)
    return cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)


def find_card_quads(image: np.ndarray) -> list[np.ndarray]:
    """Renvoie les quadrilatères détectés (coordonnées pixels dans `image`), en ordre de
    lecture (`order_reading_sequence`). Liste vide si aucun contour plausible."""
    height, width = image.shape[:2]
    image_area = height * width
    contours, _ = cv2.findContours(_edges(image), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    candidates: list[np.ndarray] = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < image_area * _MIN_AREA_FRACTION or area > image_area * _MAX_AREA_FRACTION:
            continue
        perimeter = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        if len(approx) != 4 or not cv2.isContourConvex(approx):
            continue
        if _ratio_matches_card(approx):
            candidates.append(approx.reshape(4, 2).astype(np.float32))

    return order_reading_sequence(_deduplicate(candidates))


def has_unclaimed_regions(image: np.ndarray, quads: list[np.ndarray]) -> bool:
    """Signal de repli (mission point 2, « nombre ou forme incohérent ») : une zone de la taille
    d'une carte a des contours marqués mais n'a été rattachée à aucun quadrilatère retenu — deux
    cartes qui se touchent fusionnent souvent en un contour non convexe à plus de 4 côtés,
    rejeté par `find_card_quads`, ce qui sous-compte silencieusement sans ce signal.
    """
    height, width = image.shape[:2]
    image_area = height * width
    accepted_rects = [cv2.boundingRect(q.astype(np.int32)) for q in quads]

    contours, _ = cv2.findContours(_edges(image), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        area = cv2.contourArea(contour)
        # Un contour fusionné (cartes jointes) peut être plus grand qu'une carte isolée ; on ne
        # borne donc que par le bas, avec une marge sous le seuil d'acceptation normal — mais un
        # contour qui couvre (presque) toute la photo est le cadre de l'image, pas une carte.
        if area < image_area * _MIN_AREA_FRACTION * 0.6 or area > image_area * _MAX_AREA_FRACTION:
            continue
        rect = cv2.boundingRect(contour)
        if not any(_rect_containment(rect, accepted) > 0.7 for accepted in accepted_rects):
            return True
    return False


def warp_all(image: np.ndarray, quads: list[np.ndarray]) -> list[np.ndarray]:
    return [warp_card(image, quad) for quad in quads]
