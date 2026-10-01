"""Tests de l'adaptateur **catalogue → moteur** (``pbm_api.jeu.catalogue``).

Pur : on fabrique des cartes de catalogue **factices** (un ``SimpleNamespace`` portant les mêmes
attributs que le modèle ``Card``) et on vérifie que l'adaptateur en tire une ``DefinitionCarte``
valide — ou **bloque** la carte quand une donnée manque ou qu'un marqueur de règle est inconnu
(jamais deviné, D9). Aucun accès base : l'adaptateur ne lit que des attributs.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from pbm_api.jeu import definition_depuis_card


def _carte(**kw):
    base = {
        "tcgdex_id": "swsh3-25",
        "name": "Carapuce",
        "supertype": "Pokémon",
        "stage": "Base",
        "hp": 60,
        "energy_type": "eau",
        "element_type": "eau",
        "prize_marker": "ordinaire",
        "retreat_cost": 1,
        "weaknesses": [{"type": "Plante", "value": "×2"}],
        "resistances": None,
        "attacks": [
            {"name": "Charge", "cost": ["Eau", "Incolore"], "damage": "20", "effect": ""},
        ],
    }
    base.update(kw)
    return SimpleNamespace(**base)


def test_carte_base_complete():
    d = definition_depuis_card(_carte())
    assert d.ref == "swsh3-25" and d.nom == "Carapuce" and d.stade == "base"
    assert d.pv == 60 and d.type == "eau" and d.cout_retraite == 1
    assert d.evolue_depuis is None and not d.est_evolution
    assert d.faiblesse is not None and d.faiblesse.type == "plante" and d.faiblesse.facteur == 2
    assert len(d.attaques) == 1
    attaque = d.attaques[0]
    assert attaque.nom == "Charge" and attaque.degats == 20 and attaque.degats_secs
    assert attaque.cout.types == {"eau": 1} and attaque.cout.incolore == 1


def test_carte_evolution_avec_predecesseur():
    carte = _carte(name="Carabaffe", stage="Niveau 1", hp=80)
    d = definition_depuis_card(carte, evolue_depuis="Carapuce")
    assert d.stade == "stade1" and d.est_evolution and d.evolue_depuis == "Carapuce"


def test_marqueur_de_regle_inconnu_refuse():
    """R-13.4 / R-15.22 — prize_marker « inconnu » = refus, jamais « par défaut 1 »."""
    with pytest.raises(ValueError, match="inconnu"):
        definition_depuis_card(_carte(prize_marker="inconnu"))


def test_marqueur_absent_refuse():
    with pytest.raises(ValueError, match="marqueur"):
        definition_depuis_card(_carte(prize_marker=None))


def test_stade_absent_bloque():
    with pytest.raises(ValueError, match="stade"):
        definition_depuis_card(_carte(stage=None))


def test_cout_retraite_absent_bloque():
    with pytest.raises(ValueError, match="retraite"):
        definition_depuis_card(_carte(retreat_cost=None))


def test_pv_absent_bloque():
    with pytest.raises(ValueError, match="PV"):
        definition_depuis_card(_carte(hp=None))


def test_carte_non_pokemon_refusee():
    with pytest.raises(ValueError, match="Pokémon"):
        definition_depuis_card(_carte(supertype="Trainer"))


def test_attaque_a_effet_non_seche():
    """Une attaque à effet, ou à dégâts variables, est chargée mais marquée non sèche (D9)."""
    carte = _carte(
        attacks=[
            {
                "name": "Berceuse",
                "cost": ["Incolore"],
                "damage": "",
                "effect": "La cible est Endormie.",
            },
            {"name": "Vague", "cost": ["Eau"], "damage": "20×", "effect": ""},
        ]
    )
    d = definition_depuis_card(carte)
    assert not d.attaques[0].degats_secs and d.attaques[0].degats == 0
    assert not d.attaques[1].degats_secs and d.attaques[1].degats == 0
