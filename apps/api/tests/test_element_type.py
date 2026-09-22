"""Normalisation du type élémentaire vers le code du jeu (lot `pbm-carte-remplacement`)."""

import pytest

from pbm_api.catalog.element_type import ELEMENT_CODES, element_code


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (["Plante"], "grass"),
        (["Feu"], "fire"),
        (["Eau"], "water"),
        (["Électrique"], "lightning"),
        (["Electrik"], "lightning"),  # localisation ancienne
        (["Psy"], "psychic"),
        (["Combat"], "fighting"),
        (["Obscurité"], "darkness"),
        (["Métal"], "metal"),
        (["Dragon"], "dragon"),
        (["Fée"], "fairy"),
        (["Incolore"], "colorless"),
        # Anglais (filet de sécurité)
        (["Grass"], "grass"),
        (["Colorless"], "colorless"),
        (["Steel"], "metal"),
        # Bi-type : le premier l'emporte.
        (["Feu", "Vol"], "fire"),
    ],
)
def test_libelles_connus(raw, expected):
    assert element_code(raw) == expected
    assert expected in ELEMENT_CODES


@pytest.mark.parametrize("raw", [None, [], "", ["Vol"], "n'importe quoi", 42, {"a": 1}])
def test_absent_ou_inconnu_donne_none(raw):
    # Un type inconnu ne devient JAMAIS un code inventé : NULL en base, "colorless" à l'affichage.
    assert element_code(raw) is None


def test_libelle_isole_accepte():
    assert element_code("Plante") == "grass"
