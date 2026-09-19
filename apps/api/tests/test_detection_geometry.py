"""Ordre de lecture et redressement perspective (mission `v3-detection` point 1).

Avant ce lot, `pbm_api.detection` n'existait pas : ce module échoue à la collection
(`ModuleNotFoundError`) et passe une fois `pbm_api/detection/geometry.py` ajouté.
"""

import numpy as np

from pbm_api.detection.geometry import (
    CARD_HEIGHT_PX,
    CARD_WIDTH_PX,
    order_corners,
    order_reading_sequence,
    quad_center,
    warp_card,
)


def _quad(cx: float, cy: float, w: float = 60, h: float = 84) -> np.ndarray:
    return np.array(
        [
            [cx - w / 2, cy - h / 2],
            [cx + w / 2, cy - h / 2],
            [cx + w / 2, cy + h / 2],
            [cx - w / 2, cy + h / 2],
        ],
        dtype=np.float32,
    )


def test_order_corners_handles_shuffled_points():
    quad = _quad(100, 100)
    shuffled = quad[[2, 0, 3, 1]]  # ordre arbitraire, pas déjà tl/tr/br/bl

    ordered = order_corners(shuffled)

    assert np.allclose(ordered, quad, atol=1e-4)


def test_order_reading_sequence_groups_rows_left_to_right_top_to_bottom():
    # Classeur 3×3 : grille régulière, mais listée dans un ordre quelconque.
    grid = [_quad(col * 100, row * 140) for row in range(3) for col in range(3)]
    shuffled = [grid[i] for i in [8, 0, 5, 3, 1, 7, 4, 2, 6]]

    ordered = order_reading_sequence(shuffled)

    centers = [quad_center(q) for q in ordered]
    expected_centers = [quad_center(q) for q in grid]
    assert centers == expected_centers


def test_order_reading_sequence_empty_list():
    assert order_reading_sequence([]) == []


def test_warp_card_produces_fixed_size_output():
    image = np.zeros((400, 400, 3), dtype=np.uint8)
    quad = _quad(200, 200, w=120, h=168)

    warped = warp_card(image, quad)

    assert warped.shape == (CARD_HEIGHT_PX, CARD_WIDTH_PX, 3)
