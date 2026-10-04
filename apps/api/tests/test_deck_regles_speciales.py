"""Règles de cartes particulières à la construction d'un deck (R-2.3/2.4/2.7/2.8, R-15.22).

Logique **pure** : on construit des :class:`DeckCardFact` et on lit les constats de
:func:`pbm_api.decks.legality.evaluate`. ``evaluate`` est la source UNIQUE côté serveur et écran.
"""

from __future__ import annotations

import uuid

from pbm_api.decks import regles_speciales as rs
from pbm_api.decks.legality import (
    CODE_ACE_SPEC_LIMIT,
    CODE_PRISM_STAR_LIMIT,
    CODE_RADIANT_LIMIT,
    CODE_STAR_LIMIT,
    CODE_UNKNOWN_RULE_BOX,
    DeckCardFact,
    evaluate,
)


def _fact(name, *, supertype=None, rule_marker=None, prize_marker=None, quantity=1):
    return DeckCardFact(
        card_id=uuid.uuid4(),
        name=name,
        supertype=supertype,
        energy_type=None,
        quantity=quantity,
        owned=quantity,
        rule_marker=rule_marker,
        prize_marker=prize_marker,
    )


def _codes(facts):
    return {i.code for i in evaluate(facts).issues}


# --- Classification pure (R-13.7 : signaux structurés, jamais le nom seul) ---


def _ms(supertype=None, rule_marker=None, prize_marker=None):
    return rs.marqueur_special(
        supertype=supertype, rule_marker=rule_marker, prize_marker=prize_marker
    )


def test_marqueur_special_pokemon():
    assert _ms(supertype="Pokémon", prize_marker="radiant") == rs.RADIANT
    assert _ms(supertype="Pokémon", prize_marker="prisme_etoile") == rs.PRISME_ETOILE
    assert _ms(supertype="Pokémon", prize_marker="etoile") == rs.ETOILE
    assert _ms(supertype="Pokémon", prize_marker="inconnu") == rs.RULE_BOX_INCONNU
    # Un Pokémon ex/GX/V n'a pas de limite de deck PROPRE (la règle des 4 suffit).
    assert _ms(supertype="Pokémon", prize_marker="ex") is None


def test_marqueur_special_ace_spec():
    assert _ms(supertype="Dresseur", rule_marker="ACE SPEC") == rs.ACE_SPEC
    assert _ms(supertype="Dresseur", rule_marker="ace spec") == rs.ACE_SPEC
    # Un Dresseur ordinaire n'est pas un ACE SPEC.
    assert _ms(supertype="Dresseur") is None


# --- Limites au deck ---


def test_deux_ace_spec_refusees():
    """R-2.3 — au plus 1 carte ACE SPEC par deck ; deux la rendent illégale."""
    facts = [
        _fact("Ordinateur de Recherche", supertype="Dresseur", rule_marker="ACE SPEC"),
        _fact("Boîte Secrète", supertype="Dresseur", rule_marker="ACE SPEC"),
    ]
    res = evaluate(facts)
    assert not res.legal
    assert CODE_ACE_SPEC_LIMIT in {i.code for i in res.issues}


def test_une_ace_spec_acceptee():
    facts = [_fact("Ordinateur de Recherche", supertype="Dresseur", rule_marker="ACE SPEC")]
    assert CODE_ACE_SPEC_LIMIT not in _codes(facts)


def test_deux_radiant_refuses():
    """R-2.4 — au plus 1 Pokémon Radiant par deck."""
    facts = [
        _fact("Dracaufeu Radieux", supertype="Pokémon", prize_marker="radiant"),
        _fact("Tortank Radieux", supertype="Pokémon", prize_marker="radiant"),
    ]
    assert CODE_RADIANT_LIMIT in _codes(facts)


def test_deux_prisme_meme_nom_refuses():
    """R-2.7 — au plus 1 Prisme Étoile de MÊME NOM par deck."""
    facts = [
        _fact("Darkrai ◇", supertype="Pokémon", prize_marker="prisme_etoile", quantity=2),
    ]
    assert CODE_PRISM_STAR_LIMIT in _codes(facts)


def test_deux_prisme_noms_differents_acceptes():
    """R-2.7 — deux Prisme Étoile de NOMS DIFFÉRENTS sont permis (limite par nom)."""
    facts = [
        _fact("Darkrai ◇", supertype="Pokémon", prize_marker="prisme_etoile"),
        _fact("Solgaleo ◇", supertype="Pokémon", prize_marker="prisme_etoile"),
    ]
    assert CODE_PRISM_STAR_LIMIT not in _codes(facts)


def test_deux_etoile_refuses():
    """R-2.8 — au plus 1 Pokémon ★ par deck, tous noms confondus."""
    facts = [
        _fact("Latias ☆", supertype="Pokémon", prize_marker="etoile"),
        _fact("Latios ☆", supertype="Pokémon", prize_marker="etoile"),
    ]
    assert CODE_STAR_LIMIT in _codes(facts)


def test_rule_box_inconnu_refuse():
    """R-15.22/R-13.4 — une carte à Rule Box non classable est refusée, jamais devinée."""
    facts = [_fact("Carte Mystère", supertype="Pokémon", prize_marker="inconnu")]
    res = evaluate(facts)
    assert not res.legal
    assert CODE_UNKNOWN_RULE_BOX in {i.code for i in res.issues}
