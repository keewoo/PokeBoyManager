"""Modèle des horloges — validation et sérialisation bidirectionnelle (lot ``j-timer``).

On prouve : les durées sont des **données** validées (une durée absurde est une panne),
et ``depuis_json(en_json(x)) == x`` pour la config, le compteur et l'état complet — ce qui fait
qu'une horloge survit à un F5 (elle est relue à l'identique depuis la base).
"""

from __future__ import annotations

import pytest

from pbm_game.horloges.modele import (
    SCHEMA_HORLOGES_VERSION,
    CompteurActif,
    ConfigHorloges,
    EtatHorloges,
)


def _config() -> ConfigHorloges:
    return ConfigHorloges(
        par_tour_s=90, par_joueur_s=1500, par_decision_s=30,
        tolerance_reseau_s=10, pause_deconnexion_s=120,
    )


def test_config_round_trip():
    c = _config()
    assert ConfigHorloges.depuis_json(c.en_json()) == c


@pytest.mark.parametrize("champ", ["par_tour_s", "par_joueur_s", "par_decision_s"])
def test_config_refuse_une_duree_non_strictement_positive(champ):
    """Une horloge à 0 ou négative est une panne de configuration (jamais « raisonnable »)."""
    valeurs = {"par_tour_s": 90, "par_joueur_s": 1500, "par_decision_s": 30}
    valeurs[champ] = 0
    with pytest.raises(ValueError):
        ConfigHorloges(**valeurs)


def test_config_tolerance_et_pause_peuvent_etre_nulles():
    """La tolérance et la pause peuvent valoir 0 (pas de marge) — mais jamais négatives."""
    ConfigHorloges(par_tour_s=90, par_joueur_s=1500, par_decision_s=30)  # défauts à 0 : OK
    with pytest.raises(ValueError):
        ConfigHorloges(par_tour_s=90, par_joueur_s=1500, par_decision_s=30, tolerance_reseau_s=-1)


def test_compteur_actif_round_trip_et_genre_inconnu():
    c = CompteurActif(joueur="alice", genre="tour", depuis=1000.0)
    assert CompteurActif.depuis_json(c.en_json()) == c
    with pytest.raises(ValueError):
        CompteurActif(joueur="alice", genre="sieste", depuis=0.0)


def test_etat_round_trip_avec_compteur_et_pause():
    etat = EtatHorloges(
        config=_config(),
        budgets_s={"alice": 1450.0, "bob": 1500.0},
        actif=CompteurActif(joueur="alice", genre="tour", depuis=1000.0),
        pause_depuis=1020.0,
        pause_joueur="bob",
    )
    assert EtatHorloges.depuis_json(etat.en_json()) == etat
    assert etat.en_pause is True


def test_etat_round_trip_sans_compteur_ni_pause():
    etat = EtatHorloges(config=_config(), budgets_s={"alice": 1500.0, "bob": 1500.0})
    rejoue = EtatHorloges.depuis_json(etat.en_json())
    assert rejoue == etat
    assert rejoue.actif is None and rejoue.en_pause is False


def test_depuis_json_refuse_une_version_inconnue():
    etat = EtatHorloges(config=_config(), budgets_s={"alice": 1.0, "bob": 1.0})
    brut = etat.en_json()
    brut["schema_version"] = SCHEMA_HORLOGES_VERSION + 1
    with pytest.raises(ValueError):
        EtatHorloges.depuis_json(brut)


def test_pause_incoherente_refusee():
    """``pause_depuis`` et ``pause_joueur`` vont ensemble — l'un sans l'autre est incohérent."""
    with pytest.raises(ValueError):
        EtatHorloges(config=_config(), budgets_s={"alice": 1.0, "bob": 1.0}, pause_depuis=5.0)
