"""Précision mesurée sur 60 cartes étiquetées (mission `v6-contrefacon`, livrable) : 30
contrefaçons connues et 30 vraies cartes (`pbm_api.state.counterfeit_synthetic`), passées telles
quelles à `assess_counterfeit` — logique pure, aucune base ni image nécessaire.

Avant `v6-contrefacon`, les familles B (« variante absente du catalogue ») et C (« numéro
impossible ») ne sont détectées par aucun contrôle : ce test échoue (précision/rappel en dessous
de la cible) sans les nouveaux paramètres d'`assess_counterfeit` et passe une fois ajoutés.
"""

from pbm_api.state.counterfeit import assess_counterfeit
from pbm_api.state.counterfeit_synthetic import generate_dataset


def test_counterfeit_precision_on_synthetic_dataset():
    cases = generate_dataset()
    assert len(cases) == 60

    true_positives = 0
    false_positives = 0
    false_negatives = 0
    true_negatives = 0

    for case in cases:
        result = assess_counterfeit(
            ai_suspected=case.ai_suspected,
            ai_reason=case.ai_reason,
            variant_guess=case.variant_guess,
            matched_card_rarity=case.card.rarity,
            has_matched_card=True,
            matched_card_variants=case.card.variants,
            extraction_total=case.extraction_total,
            matched_set_total_cards=case.card.total_cards,
        )

        if case.is_counterfeit and result.suspected:
            true_positives += 1
        elif case.is_counterfeit and not result.suspected:
            false_negatives += 1
        elif not case.is_counterfeit and result.suspected:
            false_positives += 1
        else:
            true_negatives += 1

    total = len(cases)
    precision = true_positives / (true_positives + false_positives)
    recall = true_positives / (true_positives + false_negatives)

    assert (true_positives, false_positives, false_negatives, true_negatives) == (
        30,
        0,
        0,
        30,
    ), (
        f"precision {precision:.1%}, recall {recall:.1%} sur {total} cartes "
        f"(TP={true_positives} FP={false_positives} FN={false_negatives} TN={true_negatives})"
    )
