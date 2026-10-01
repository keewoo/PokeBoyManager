"""Le vocabulaire des moments de jeu — lot j-effets-architecture.

Les onze moments de la fiche sont présents, la liste est **fermée** (un moment inconnu est
refusé, D9), et une charge utile se porte sans surprise.
"""

from __future__ import annotations

import pytest

from pbm_game.effets.evenements import (
    EJ_APRES_DEGATS,
    EJ_ATTACHEMENT_ENERGIE,
    EJ_AVANT_DEGATS,
    EJ_DEBUT_TOUR,
    EJ_DEVIENT_ACTIF,
    EJ_ENTRE_TOURS,
    EJ_EVOLUTION,
    EJ_FIN_TOUR,
    EJ_KO,
    EJ_PIOCHE,
    EJ_POSE,
    EVENEMENTS_JEU,
    MECANISMES,
    EvenementJeu,
)


def test_les_onze_moments_sont_reconnus():
    attendus = {
        EJ_DEBUT_TOUR,
        EJ_FIN_TOUR,
        EJ_ENTRE_TOURS,
        EJ_AVANT_DEGATS,
        EJ_APRES_DEGATS,
        EJ_POSE,
        EJ_EVOLUTION,
        EJ_KO,
        EJ_ATTACHEMENT_ENERGIE,
        EJ_PIOCHE,
        EJ_DEVIENT_ACTIF,
    }
    assert EVENEMENTS_JEU == attendus
    assert len(EVENEMENTS_JEU) == 11


def test_evenement_jeu_porte_sa_charge_utile():
    ev = EvenementJeu(EJ_APRES_DEGATS, {"attaquant": "a-1", "defenseur": "b-1", "degats": 60})
    assert ev.type == EJ_APRES_DEGATS
    assert ev.donnees["degats"] == 60


def test_evenement_inconnu_refuse_jamais_approxime_d9():
    with pytest.raises(ValueError, match="jamais approximé"):
        EvenementJeu("quand_la_lune_est_bleue", {})


def test_les_quatre_mecanismes_sont_reconnus():
    assert MECANISMES == {"declenche", "continu", "active", "attaque"}
