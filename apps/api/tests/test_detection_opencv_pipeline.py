"""Détection par contours OpenCV (mission `v3-detection` point 1) : ratio 63×88 mm, ordre de
lecture, signal de repli sur cartes qui se touchent (mission point 2).

Avant ce lot, `pbm_api.detection.opencv_pipeline` n'existait pas : ce module échoue à la
collection et passe une fois le fichier ajouté. La preuve ciblée sur le filtrage par ratio
(`test_rejects_non_card_shaped_contour`) est la garantie que ce n'est pas « n'importe quel
rectangle » qui est retenu comme carte — désactiver `_ratio_matches_card` dans
`opencv_pipeline.py` fait échouer ce test précis sans toucher au reste de la suite.
"""

import numpy as np

from pbm_api.detection.opencv_pipeline import find_card_quads, has_unclaimed_regions
from pbm_api.detection.synthetic import (
    draw_card,
    make_binder_grid,
    make_single_card,
    make_table_scatter,
    noisy_background,
)


def test_find_card_quads_detects_single_card():
    photo = make_single_card(seed=1, index=0)

    quads = find_card_quads(photo.image)

    assert len(quads) == 1


def test_find_card_quads_detects_binder_grid_in_reading_order():
    photo = make_binder_grid(seed=1, index=0, glare=False)

    quads = find_card_quads(photo.image)

    assert len(quads) == 9
    # Ordre de lecture : les centres Y croissent globalement ligne par ligne.
    centers_y = [q.reshape(4, 2)[:, 1].mean() for q in quads]
    row0, row1, row2 = centers_y[0:3], centers_y[3:6], centers_y[6:9]
    assert max(row0) < min(row1)
    assert max(row1) < min(row2)


def test_rejects_non_card_shaped_contour():
    """Un carré (ratio 1:1) n'est pas retenu comme carte (ratio cible 63/88 ≈ 0.716)."""
    rng = np.random.default_rng(0)
    canvas = noisy_background(rng, (300, 300), (200, 200, 200))
    square = np.array([[70, 70], [230, 70], [230, 230], [70, 230]], dtype=np.float32)
    draw_card(canvas, square, fill=(210, 200, 170), border=(40, 40, 40))

    quads = find_card_quads(canvas)

    assert quads == []


def test_has_unclaimed_regions_true_when_cards_touch():
    """Deux cartes proches se chevauchent assez pour fusionner en un contour non-carte :
    `find_card_quads` en sous-compte, mais `has_unclaimed_regions` doit signaler la zone
    laissée de côté (mission point 2 : repli sur « nombre ou forme incohérent »)."""
    photo = make_table_scatter(seed=300, index=0, count=2)

    quads = find_card_quads(photo.image)

    assert len(quads) < photo.expected_count
    assert has_unclaimed_regions(photo.image, quads) is True


def test_has_unclaimed_regions_false_when_all_cards_found():
    photo = make_binder_grid(seed=1, index=0, glare=False)
    quads = find_card_quads(photo.image)

    assert has_unclaimed_regions(photo.image, quads) is False
