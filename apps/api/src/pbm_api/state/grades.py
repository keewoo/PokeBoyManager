"""Barème d'état partagé (mission point 2) : sept paliers, du meilleur au pire, alignés sur les
clés déjà utilisées par `pbm_api.pricing.valuation.CONDITION_MULTIPLIERS` (posées par un lot
antérieur pour la décote de valeur) — ce lot ne réinvente pas un second vocabulaire, il l'étend
avec l'abréviation Cardmarket affichée à l'utilisateur et une note sur 10 dérivée directement du
multiplicateur existant (`score_10`), pour ne jamais faire dériver deux échelles en parallèle.
"""

from enum import StrEnum

from pbm_api.pricing.valuation import CONDITION_MULTIPLIERS


class ConditionGrade(StrEnum):
    mint = "mint"
    near_mint = "near_mint"
    excellent = "excellent"
    good = "good"
    light_played = "light_played"
    played = "played"
    poor = "poor"


# Du meilleur au pire — sert à combiner plusieurs paliers (centrage, coins, bords, surface) en
# retenant le plus sévère, comme le ferait un gradeur professionnel (un seul défaut marqué
# suffit à abaisser la note globale).
GRADE_ORDER: list[ConditionGrade] = [
    ConditionGrade.mint,
    ConditionGrade.near_mint,
    ConditionGrade.excellent,
    ConditionGrade.good,
    ConditionGrade.light_played,
    ConditionGrade.played,
    ConditionGrade.poor,
]

assert {g.value for g in GRADE_ORDER} == set(CONDITION_MULTIPLIERS), (
    "le barème d'état doit rester aligné avec pbm_api.pricing.valuation.CONDITION_MULTIPLIERS"
)

CARDMARKET_LABELS: dict[ConditionGrade, str] = {
    ConditionGrade.mint: "MT",
    ConditionGrade.near_mint: "NM",
    ConditionGrade.excellent: "EX",
    ConditionGrade.good: "GD",
    ConditionGrade.light_played: "LP",
    ConditionGrade.played: "PL",
    ConditionGrade.poor: "PO",
}


def worst_grade(grades: list[ConditionGrade | None]) -> ConditionGrade | None:
    """Le palier le plus sévère parmi ceux disponibles (`None` ignorés) — `None` si aucun n'a pu
    être établi (ni centrage mesurable, ni extraction IA)."""
    present = [g for g in grades if g is not None]
    if not present:
        return None
    return max(present, key=GRADE_ORDER.index)


def score_10(grade: ConditionGrade | None) -> float | None:
    if grade is None:
        return None
    return round(float(CONDITION_MULTIPLIERS[grade.value]) * 10, 1)
