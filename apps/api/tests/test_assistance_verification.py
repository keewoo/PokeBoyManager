"""La porte DJ8 (`pbm_api.jeu.scripts.assistance.verification`) — pure, aucune E/S.

Le cœur du lot : un script n'entre en jeu (`scripte`) que si ses tests passent ET que le
contradicteur l'approuve. Tout le reste est refusé — jamais joué « au mieux ».
"""

from __future__ import annotations

from pbm_api.jeu.scripts.assistance.fournisseur import Proposition, VerdictContradicteur
from pbm_api.jeu.scripts.assistance.verification import (
    GATE_A_REVOIR,
    GATE_NON_SUPPORTE,
    GATE_SCRIPTE,
    evaluer,
)

_TEXTE = "Piochez 1 carte."
_SCRIPT_OK = {"version": 1, "effets": [{"op": "piocher", "nombre": 1}]}
_ESSAI_OK = {
    "nom": "pioche 1",
    "etat": {"alice": {"pioche": 3, "main": 0}, "bob": {}},
    "attendu": {"etat": {"alice": {"pioche": 2, "main": 1}}},
}


def _prop(**kw) -> Proposition:
    base = {
        "non_supporte": False,
        "confiance": "moyenne",
        "script": _SCRIPT_OK,
        "essais": [_ESSAI_OK],
    }
    base.update(kw)
    return Proposition(**base)


def test_non_supporte_est_refuse_mais_nomme():
    prop = Proposition(non_supporte=True, raison="tournure absente du langage", confiance="basse")
    porte = evaluer(texte_fr=_TEXTE, proposition=prop, verdict=None)
    assert porte.resultat == GATE_NON_SUPPORTE
    assert "tournure" in porte.raison


def test_tests_rouges_restent_a_revoir_sans_contredire():
    """Un attendu faux : le script n'est pas validé, le contradicteur n'est pas sollicité."""
    essai_faux = {**_ESSAI_OK, "attendu": {"etat": {"alice": {"main": 2}}}}  # il n'en pioche qu'1
    porte = evaluer(texte_fr=_TEXTE, proposition=_prop(essais=[essai_faux]), verdict=None)
    assert porte.resultat == GATE_A_REVOIR
    assert porte.tests_ok is False
    assert porte.contradicteur_ok is None  # l'étape n'a pas eu lieu, et on le dit


def test_tests_verts_sans_verdict_restent_a_revoir():
    porte = evaluer(texte_fr=_TEXTE, proposition=_prop(), verdict=None)
    assert porte.resultat == GATE_A_REVOIR
    assert porte.tests_ok is True


def test_contradicteur_rejette_bloque_meme_avec_tests_verts():
    verdict = VerdictContradicteur(verdict="rejete", raison="mauvaise cible")
    porte = evaluer(texte_fr=_TEXTE, proposition=_prop(), verdict=verdict)
    assert porte.resultat == GATE_A_REVOIR
    assert porte.contradicteur_ok is False


def test_contre_cas_du_contradicteur_met_le_script_en_defaut():
    """Même si le contradicteur approuve, un contre-cas qui mord fait refuser (preuve > avis)."""
    contre = {
        "nom": "contre",
        "etat": {"alice": {"pioche": 3, "main": 0}, "bob": {}},
        "attendu": {"etat": {"alice": {"main": 2}}},  # faux pour « pioche 1 »
    }
    verdict = VerdictContradicteur(verdict="approuve", raison="ok", essai_contre=contre)
    porte = evaluer(texte_fr=_TEXTE, proposition=_prop(), verdict=verdict)
    assert porte.resultat == GATE_A_REVOIR
    assert porte.tests_ok is False


def test_tests_verts_et_contradicteur_approuve_donne_scripte():
    verdict = VerdictContradicteur(verdict="approuve", raison="conforme")
    porte = evaluer(texte_fr=_TEXTE, proposition=_prop(), verdict=verdict)
    assert porte.resultat == GATE_SCRIPTE
    assert porte.tests_ok is True
    assert porte.contradicteur_ok is True
    assert porte.famille == "pioche"
