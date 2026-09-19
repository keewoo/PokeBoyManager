"""`pbm_api.state.centering.measure_centering` (mission `v3-etat` point 1) : centrage mesuré sur
un recadrage synthétique dont les marges gauche/droite/haut/bas sont connues à l'avance
(`pbm_api.state.synthetic`, dédié — le contour de `pbm_api.detection.synthetic` n'est qu'un
trait, pas un vrai cadre imprimé décalé).

Avant ce lot, `pbm_api.state` n'existe pas : chacun de ces tests échoue à la collection et passe
une fois le module ajouté.
"""

from pbm_api.state.centering import measure_centering
from pbm_api.state.grades import ConditionGrade
from pbm_api.state.synthetic import generate_dataset, make_full_bleed_crop

_TOLERANCE_PX = 3


def test_measure_centering_recovers_known_margins_within_tolerance():
    for crop in generate_dataset():
        result = measure_centering(crop.image)
        assert result is not None, crop.id
        assert abs(result.left_px - crop.left_px) <= _TOLERANCE_PX, crop.id
        assert abs(result.right_px - crop.right_px) <= _TOLERANCE_PX, crop.id
        assert abs(result.top_px - crop.top_px) <= _TOLERANCE_PX, crop.id
        assert abs(result.bottom_px - crop.bottom_px) <= _TOLERANCE_PX, crop.id


def test_measure_centering_grades_a_near_perfect_card_mint():
    crop = next(c for c in generate_dataset() if c.id == "centre_parfait")
    result = measure_centering(crop.image)
    assert result is not None
    assert result.grade == ConditionGrade.mint


def test_measure_centering_grades_a_heavily_off_center_card_poor():
    crop = next(c for c in generate_dataset() if c.id == "marque_deux_axes")
    result = measure_centering(crop.image)
    assert result is not None
    assert result.grade == ConditionGrade.poor


def test_measure_centering_overall_grade_is_the_worst_of_both_axes():
    """Un léger décalage horizontal combiné à un centrage vertical parfait ne doit jamais
    remonter la note globale au niveau du meilleur axe — le pire des deux l'emporte."""
    crop = next(c for c in generate_dataset() if c.id == "modere_horizontal")
    result = measure_centering(crop.image)
    assert result is not None
    assert result.vertical is not None
    assert result.vertical.grade == ConditionGrade.mint
    assert result.grade == result.horizontal.grade
    assert result.grade != ConditionGrade.mint


def test_measure_centering_returns_none_when_no_border_is_distinguishable():
    """Carte pleine page (full art) : aucun cadre intérieur net à mesurer, jamais une mesure
    inventée (mission « risques & pièges »)."""
    crop = make_full_bleed_crop()

    assert measure_centering(crop.image) is None
