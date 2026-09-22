"""`pbm_api.state.counterfeit.assess_counterfeit` (mission `v3-etat` point 3, étendue par
`v6-contrefacon` mission point 1) : signal explicite de l'IA et contrôles déterministes — carte
gold inexistante au catalogue, variante absente du catalogue, numéro (total de série) impossible.

Avant `v6-contrefacon`, `assess_counterfeit` n'accepte pas `matched_card_variants`/
`extraction_total`/`matched_set_total_cards` : les tests de ce lot échouent (`TypeError`) sans le
changement et passent avec."""

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


def test_flags_reverse_holo_guess_absent_from_catalog_variants():
    """Mission `v6-contrefacon` point 1, « variante absente du catalogue » : reverse holo perçu
    alors que TCGdex ne déclare aucun tirage reverse pour cette carte."""
    result = assess_counterfeit(
        ai_suspected=False,
        ai_reason=None,
        variant_guess="reverse_holo",
        matched_card_rarity="Common",
        has_matched_card=True,
        matched_card_variants={"normal": True, "holo": False, "reverse": False},
    )
    assert result.suspected is True
    assert any("reverse_holo" in reason for reason in result.reasons)


def test_does_not_flag_variant_confirmed_by_catalog():
    result = assess_counterfeit(
        ai_suspected=False,
        ai_reason=None,
        variant_guess="holo",
        matched_card_rarity="Rare Holo",
        has_matched_card=True,
        matched_card_variants={"normal": False, "holo": True, "reverse": False},
    )
    assert result.suspected is False


def test_does_not_flag_variant_when_catalog_key_missing():
    """Catalogue incomplet pour cette carte (clé absente du JSONB, pas de valeur `False`
    explicite) -> pas de signal, jamais un faux positif par excès de prudence inverse."""
    result = assess_counterfeit(
        ai_suspected=False,
        ai_reason=None,
        variant_guess="first_edition",
        matched_card_rarity="Common",
        has_matched_card=True,
        matched_card_variants={"normal": True, "holo": False},
    )
    assert result.suspected is False


def test_does_not_flag_full_art_or_other_variant_guess():
    """`full_art`/`other` n'ont aucune clé de catalogue correspondante (mission : seules les
    variantes que TCGdex modélise sont contrôlables) -> jamais de signal sur ces valeurs seules."""
    result = assess_counterfeit(
        ai_suspected=False,
        ai_reason=None,
        variant_guess="full_art",
        matched_card_rarity="Rare Ultra",
        has_matched_card=True,
        matched_card_variants={"normal": False, "holo": False, "reverse": False},
    )
    assert result.suspected is False


def test_flags_printed_total_inconsistent_with_matched_set():
    """Mission `v6-contrefacon` point 1, « numéro impossible » : le total de série imprimé
    (ex. 999) ne correspond pas au total officiel de l'extension reconnue (ex. 102)."""
    result = assess_counterfeit(
        ai_suspected=False,
        ai_reason=None,
        variant_guess="normal",
        matched_card_rarity="Common",
        has_matched_card=True,
        extraction_total=999,
        matched_set_total_cards=102,
    )
    assert result.suspected is True
    assert any("999" in reason and "102" in reason for reason in result.reasons)


def test_does_not_flag_secret_rare_number_beyond_set_total():
    """Un secret rare a un NUMÉRO supérieur au total (ex. 202/198) sans que le TOTAL imprimé ne
    change — seuls les deux totaux sont comparés, jamais le numéro contre le total (mission
    « risques & pièges » : ne pas signaler une rareté légitime)."""
    result = assess_counterfeit(
        ai_suspected=False,
        ai_reason=None,
        variant_guess="normal",
        matched_card_rarity="Rare Secret",
        has_matched_card=True,
        extraction_total=198,
        matched_set_total_cards=198,
    )
    assert result.suspected is False


def test_does_not_flag_total_mismatch_when_no_catalog_card_matched():
    result = assess_counterfeit(
        ai_suspected=False,
        ai_reason=None,
        variant_guess="normal",
        matched_card_rarity=None,
        has_matched_card=False,
        extraction_total=999,
        matched_set_total_cards=None,
    )
    assert result.suspected is False


def test_combines_multiple_deterministic_reasons():
    result = assess_counterfeit(
        ai_suspected=True,
        ai_reason="police inhabituelle",
        variant_guess="gold",
        matched_card_rarity="Common",
        has_matched_card=True,
        matched_card_variants={"normal": True, "holo": False},
        extraction_total=999,
        matched_set_total_cards=102,
    )
    assert result.suspected is True
    assert len(result.reasons) == 3
