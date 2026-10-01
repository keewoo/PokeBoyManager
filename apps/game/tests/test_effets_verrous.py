"""Verrous nommés et leurs portées — lot j-effets-architecture.

On pose les trois verrous de la fiche, on vérifie qu'un coup verrouillé se refuse **en nommant
la carte responsable** (R-5.5), et que les verrous « ce tour » / « prochain tour » **expirent
au Checkup** avec une ligne de journal (R-12.5) — jamais en silence.
"""

from __future__ import annotations

import pytest

from pbm_game.effets.pile import SourceEffet
from pbm_game.effets.verrous import (
    EVT_VERROU_LEVE,
    EVT_VERROU_POSE,
    PORTEE_CE_TOUR,
    PORTEE_PROCHAIN_TOUR,
    PORTEE_TANT_QUE_ACTIF,
    VERROU_NE_PEUT_ATTAQUER,
    VERROU_PAS_DE_SUPPORTER,
    VERROU_TALENTS_SANS_EFFET,
    VERROUS_VIDES,
    JeuDeVerrous,
    Verrou,
)


def _src(nom: str) -> SourceEffet:
    return SourceEffet(libelle=nom, ref=f"ref-{nom}", instance_id=f"i-{nom}")


def test_verrou_pas_de_supporter_refuse_en_nommant_la_carte_r55():
    verrou = Verrou(
        nom=VERROU_PAS_DE_SUPPORTER, portee=PORTEE_CE_TOUR, source=_src("Zone de Combat"),
        regle="R-5.5", cible="bob", pose_au_tour=4,
    )
    jeu, evt = VERROUS_VIDES.poser(verrou)
    assert evt.type == EVT_VERROU_POSE
    assert jeu.est_verrouille(VERROU_PAS_DE_SUPPORTER, cible="bob")
    assert not jeu.est_verrouille(VERROU_PAS_DE_SUPPORTER, cible="alice")  # ciblé, pas global
    source = jeu.source_du_verrou(VERROU_PAS_DE_SUPPORTER, cible="bob")
    assert source is not None and source.libelle == "Zone de Combat"


def test_verrou_global_frappe_tout_le_monde():
    verrou = Verrou(
        nom=VERROU_TALENTS_SANS_EFFET, portee=PORTEE_TANT_QUE_ACTIF, source=_src("Garbodor"),
        regle="R-12.3", cible=None,
    )
    jeu, _ = VERROUS_VIDES.poser(verrou)
    assert jeu.est_verrouille(VERROU_TALENTS_SANS_EFFET, cible="alice")
    assert jeu.est_verrouille(VERROU_TALENTS_SANS_EFFET, cible="bob")


def test_verrou_ce_tour_expire_au_checkup_et_le_dit_r125():
    verrou = Verrou(
        nom=VERROU_PAS_DE_SUPPORTER, portee=PORTEE_CE_TOUR, source=_src("X"), regle="R-5.5",
        cible="alice", pose_au_tour=4,
    )
    jeu, _ = VERROUS_VIDES.poser(verrou)
    jeu2, leves = jeu.expirer_au_checkup(numero_tour=4)
    assert [e.type for e in leves] == [EVT_VERROU_LEVE]  # levée journalisée, jamais muette
    assert not jeu2.est_verrouille(VERROU_PAS_DE_SUPPORTER, cible="alice")


def test_verrou_prochain_tour_survit_au_tour_courant_puis_tombe():
    verrou = Verrou(
        nom=VERROU_NE_PEUT_ATTAQUER, portee=PORTEE_PROCHAIN_TOUR, source=_src("Y"),
        regle="R-5.7", cible="a-1", pose_au_tour=4,
    )
    jeu, _ = VERROUS_VIDES.poser(verrou)
    # Au Checkup du tour 4 (celui où il est posé) il PÈSE encore sur le prochain tour.
    jeu_t4, leves_t4 = jeu.expirer_au_checkup(numero_tour=4)
    assert leves_t4 == []
    assert jeu_t4.est_verrouille(VERROU_NE_PEUT_ATTAQUER, cible="a-1")
    # Au Checkup du tour 5, il tombe.
    jeu_t5, leves_t5 = jeu_t4.expirer_au_checkup(numero_tour=5)
    assert [e.type for e in leves_t5] == [EVT_VERROU_LEVE]
    assert not jeu_t5.est_verrouille(VERROU_NE_PEUT_ATTAQUER, cible="a-1")


def test_verrou_lie_a_une_source_tombe_quand_la_source_quitte_le_jeu():
    verrou = Verrou(
        nom=VERROU_TALENTS_SANS_EFFET, portee=PORTEE_TANT_QUE_ACTIF, source=_src("Garbodor"),
        regle="R-12.3", cible=None,
    )
    jeu, _ = VERROUS_VIDES.poser(verrou)
    # i-Garbodor encore en jeu : le verrou tient.
    jeu2, leves2 = jeu.retirer_sources_absentes(frozenset({"i-Garbodor"}))
    assert leves2 == [] and jeu2.est_verrouille(VERROU_TALENTS_SANS_EFFET, cible="alice")
    # i-Garbodor a quitté le jeu : le verrou tombe, journalisé.
    jeu3, leves3 = jeu.retirer_sources_absentes(frozenset())
    assert [e.type for e in leves3] == [EVT_VERROU_LEVE]
    assert not jeu3.est_verrouille(VERROU_TALENTS_SANS_EFFET, cible="alice")


def test_verrou_inconnu_refuse_d9():
    with pytest.raises(ValueError, match="jamais inventé|Connus"):
        Verrou(nom="fais_ce_que_je_veux", portee=PORTEE_CE_TOUR, source=_src("X"), regle="R-1.1")


def test_demander_un_verrou_inconnu_est_refuse():
    with pytest.raises(ValueError, match="inconnu"):
        JeuDeVerrous().est_verrouille("verrou_imaginaire")
