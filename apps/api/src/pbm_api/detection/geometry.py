"""Redressement perspective d'un quadrilatère et ordre de lecture (mission point 1).

Une carte standard mesure 63×88 mm : le recadrage final est toujours 630×880 px (10 px/mm),
quel que soit l'angle de prise de vue — c'est le ratio qui identifie une carte parmi les
contours de la photo, pas sa taille apparente.
"""

import cv2
import numpy as np

CARD_WIDTH_PX = 630
CARD_HEIGHT_PX = 880
CARD_ASPECT_RATIO = CARD_WIDTH_PX / CARD_HEIGHT_PX  # 63/88 ≈ 0.7159

_DEST_CORNERS = np.array(
    [
        [0, 0],
        [CARD_WIDTH_PX - 1, 0],
        [CARD_WIDTH_PX - 1, CARD_HEIGHT_PX - 1],
        [0, CARD_HEIGHT_PX - 1],
    ],
    dtype=np.float32,
)


def order_corners(points: np.ndarray) -> np.ndarray:
    """Ordonne 4 points en (haut-gauche, haut-droite, bas-droite, bas-gauche).

    Méthode standard (somme/différence des coordonnées) : le point de somme minimale est le
    coin haut-gauche, celui de somme maximale le coin bas-droite ; la différence x-y minimale
    donne le haut-droite, la différence maximale le bas-gauche.
    """
    pts = points.reshape(4, 2).astype(np.float32)
    ordered = np.zeros((4, 2), dtype=np.float32)

    sums = pts.sum(axis=1)
    diffs = pts[:, 0] - pts[:, 1]

    ordered[0] = pts[np.argmin(sums)]
    ordered[2] = pts[np.argmax(sums)]
    ordered[1] = pts[np.argmax(diffs)]
    ordered[3] = pts[np.argmin(diffs)]
    return ordered


def quad_center(quad: np.ndarray) -> tuple[float, float]:
    pts = quad.reshape(4, 2)
    return float(pts[:, 0].mean()), float(pts[:, 1].mean())


def order_reading_sequence(quads: list[np.ndarray]) -> list[np.ndarray]:
    """Ordre de lecture ligne par ligne (mission point 1) : classeur 3×3, gauche à droite puis
    haut en bas. Les cartes sont groupées par ligne à partir de leur centre Y (tolérance =
    la moitié de la hauteur moyenne des cartes détectées), puis triées par X dans chaque ligne.
    """
    if not quads:
        return []

    centers = [quad_center(q) for q in quads]
    heights = [_quad_height(q) for q in quads]
    row_tolerance = (sum(heights) / len(heights)) / 2

    order = sorted(range(len(quads)), key=lambda i: centers[i][1])
    rows: list[list[int]] = []
    for i in order:
        placed = False
        for row in rows:
            row_y = sum(centers[j][1] for j in row) / len(row)
            if abs(centers[i][1] - row_y) <= row_tolerance:
                row.append(i)
                placed = True
                break
        if not placed:
            rows.append([i])

    ordered_indices: list[int] = []
    for row in rows:
        ordered_indices.extend(sorted(row, key=lambda i: centers[i][0]))
    return [quads[i] for i in ordered_indices]


def _quad_height(quad: np.ndarray) -> float:
    pts = quad.reshape(4, 2)
    return float(pts[:, 1].max() - pts[:, 1].min())


def warp_card(image: np.ndarray, quad: np.ndarray) -> np.ndarray:
    """Redressement perspective d'un quadrilatère vers 630×880 px."""
    src = order_corners(quad)
    matrix = cv2.getPerspectiveTransform(src, _DEST_CORNERS)
    return cv2.warpPerspective(image, matrix, (CARD_WIDTH_PX, CARD_HEIGHT_PX))
