"""`pbm_api.state.counterfeit.assess_counterfeit` (mission point 3) : signal explicite de l'IA
et contrôle déterministe « carte gold inexistante au catalogue »."""

from pbm_api.state.counterfeit import assess_counterfeit


def test_no_signal_when_nothing_suspicious():
    result = assess_counterfeit(
        ai_suspected=False,
        ai_reason=None,
        variant_guess="normal",
        matched_card_rarity="Common",
        has_matched_card=True,
    )
    assert result.suspected is False
    assert result.reasons == []


def test_flags_ai_reported_suspicion_with_its_reason():
    result = assess_counterfeit(
        ai_suspected=True,
        ai_reason="police inhabituelle et couleurs délavées",
        variant_guess="normal",
        matched_card_rarity="Common",
        has_matched_card=True,
    )
    assert result.suspected is True
    assert result.reasons == ["police inhabituelle et couleurs délavées"]


def test_flags_ai_reported_suspicion_even_without_a_reason():
    result = assess_counterfeit(
        ai_suspected=True, ai_reason=None, variant_guess=None,
        matched_card_rarity=None, has_matched_card=False,
    )
    assert result.suspected is True
    assert result.reasons


def test_flags_gold_variant_guess_unconfirmed_by_catalog_rarity():
    """Mission point 3, exemple donné : carte "gold" métal inexistante au catalogue."""
    result = assess_counterfeit(
        ai_suspected=False,
        ai_reason=None,
        variant_guess="gold",
        matched_card_rarity="Common",
        has_matched_card=True,
    )
    assert result.suspected is True
    assert any("gold" in reason.lower() for reason in result.reasons)


def test_does_not_flag_gold_variant_guess_confirmed_by_catalog_rarity():
    result = assess_counterfeit(
        ai_suspected=False,
        ai_reason=None,
        variant_guess="gold",
        matched_card_rarity="Rare Secret",
        has_matched_card=True,
    )
    assert result.suspected is False


def test_does_not_flag_gold_variant_guess_when_no_catalog_card_matched():
    """Aucune carte rapprochée -> pas de contrôle possible, jamais un faux positif par excès de
    prudence inverse (mission « risques & pièges »)."""
    result = assess_counterfeit(
        ai_suspected=False,
        ai_reason=None,
        variant_guess="gold",
        matched_card_rarity=None,
        has_matched_card=False,
    )
    assert result.suspected is False
