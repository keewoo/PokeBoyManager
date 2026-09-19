"""`pbm_api.state.grades` (mission point 2) : barème d'état, abréviation Cardmarket, note /10 —
dérivée directement de `pbm_api.pricing.valuation.CONDITION_MULTIPLIERS` (pas un second barème
qui pourrait diverger)."""

from pbm_api.pricing.valuation import CONDITION_MULTIPLIERS
from pbm_api.state.grades import CARDMARKET_LABELS, ConditionGrade, score_10, worst_grade


def test_every_grade_has_a_cardmarket_label():
    assert set(CARDMARKET_LABELS) == set(ConditionGrade)
    assert CARDMARKET_LABELS[ConditionGrade.mint] == "MT"
    assert CARDMARKET_LABELS[ConditionGrade.near_mint] == "NM"
    assert CARDMARKET_LABELS[ConditionGrade.excellent] == "EX"
    assert CARDMARKET_LABELS[ConditionGrade.good] == "GD"
    assert CARDMARKET_LABELS[ConditionGrade.light_played] == "LP"
    assert CARDMARKET_LABELS[ConditionGrade.played] == "PL"
    assert CARDMARKET_LABELS[ConditionGrade.poor] == "PO"


def test_score_10_derives_from_condition_multipliers():
    for grade in ConditionGrade:
        assert score_10(grade) == round(float(CONDITION_MULTIPLIERS[grade.value]) * 10, 1)


def test_score_10_is_monotonic_with_grade_severity():
    scores = [score_10(grade) for grade in ConditionGrade]
    assert scores == sorted(scores, reverse=True)


def test_score_10_none_when_no_grade():
    assert score_10(None) is None


def test_worst_grade_picks_the_most_severe():
    assert worst_grade([ConditionGrade.mint, ConditionGrade.good, ConditionGrade.excellent]) == (
        ConditionGrade.good
    )


def test_worst_grade_ignores_missing_values():
    assert worst_grade([None, ConditionGrade.excellent, None]) == ConditionGrade.excellent


def test_worst_grade_none_when_nothing_available():
    assert worst_grade([None, None]) is None
