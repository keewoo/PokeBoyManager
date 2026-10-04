"""Les **essais de script** (:mod:`pbm_game.effets.dsl.essais`) — prouver un script par des cas.

Chaque test cite la règle qu'il vérifie : conservation des cartes et zones (R-3.1), invariants
(R-3), pioche (R-5.1), compteurs directs (R-10.6). Module pur : aucune E/S.
"""

from __future__ import annotations

from pbm_game.cas.constructeur import construire
from pbm_game.effets.dsl.chargement import charger_programme
from pbm_game.effets.dsl.essais import (
    anomalies_coherence,
    executer_essai,
    verifier_script,
)
from pbm_game.effets.dsl.interprete import ResultatProgramme

# --- Script valide, essai qui passe -------------------------------------------------------


def _script_pioche(n: int) -> dict:
    return {"version": 1, "effets": [{"op": "piocher", "nombre": n, "regle": "R-5.1"}]}


def _etat_pioche() -> dict:
    return {
        "alice": {"actif": {"pv": 60, "recompenses": 1}, "pioche": 5, "main": 0},
        "bob": {},
    }


def test_essai_pioche_passe_et_conserve_les_cartes():
    """Un « piochez 2 » déplace 2 cartes de la pioche vers la main (R-5.1) sans en créer (R-3.1)."""
    essai = {
        "nom": "pioche 2",
        "etat": _etat_pioche(),
        "attendu": {"etat": {"alice": {"pioche": 3, "main": 2}}},
    }
    programme = charger_programme(_script_pioche(2))
    assert executer_essai(programme, essai) == []


def test_essai_detecte_un_attendu_non_tenu():
    """Un attendu faux est rapporté, jamais avalé : le script pioche 2, l'essai en attend 3."""
    essai = {
        "nom": "attendu faux",
        "etat": {"alice": {"pioche": 5, "main": 0}, "bob": {}},
        "attendu": {"etat": {"alice": {"main": 3}}},  # faux : il n'en pioche que 2
    }
    programme = charger_programme(_script_pioche(2))
    anomalies = executer_essai(programme, essai)
    assert any("main" in a for a in anomalies)


def test_essai_poser_compteurs_directs():
    """« Placez 2 compteurs sur l'Actif adverse » = 20 PV posés directement (R-10.6)."""
    essai = {
        "nom": "2 compteurs",
        "etat": {
            "alice": {"actif": {"pv": 60, "recompenses": 1}},
            "bob": {"actif": {"pv": 60, "recompenses": 1}},
        },
        "attendu": {"etat": {"bob": {"actif": {"degats": 20}}}},
    }
    programme = charger_programme(
        {
            "version": 1,
            "effets": [
                {
                    "op": "poser_compteurs",
                    "cible": {"zone": "actif", "proprietaire": "adversaire"},
                    "nombre": 2,
                    "regle": "R-10.6",
                }
            ],
        }
    )
    assert executer_essai(programme, essai) == []


# --- Cohérence maison ---------------------------------------------------------------------


def test_coherence_signale_une_carte_disparue():
    """Conservation des cartes (R-3.1) : moins de cartes après qu'avant est une anomalie."""
    avant, _ = construire({"alice": {"pioche": 5}, "bob": {}})
    apres, _ = construire({"alice": {"pioche": 3}, "bob": {}})  # 2 cartes « perdues »
    resultat = ResultatProgramme(
        etat=apres, evenements=(), verrous=(), degats_annules=False, cout_paye=True
    )
    anomalies = anomalies_coherence(avant, resultat)
    assert any("conservation des cartes" in a for a in anomalies)


def test_coherence_etat_identique_est_sain():
    """Un état inchangé ne porte aucune anomalie de cohérence (R-3.1, R-3)."""
    avant, _ = construire(
        {
            "alice": {"actif": {"pv": 60, "recompenses": 1}, "pioche": 5},
            "bob": {"actif": {"pv": 60, "recompenses": 1}},
        }
    )
    resultat = ResultatProgramme(
        etat=avant, evenements=(), verrous=(), degats_annules=False, cout_paye=True
    )
    assert anomalies_coherence(avant, resultat) == []


# --- verifier_script : la porte -----------------------------------------------------------


def test_verifier_script_refuse_un_script_illisible():
    """Un script hors du langage est refusé au chargement, jamais « au mieux » (D9)."""
    verdict = verifier_script(
        {"version": 1, "effets": [{"op": "code_libre"}]},
        [{"etat": {"alice": {}, "bob": {}}}],
    )
    assert verdict["valide"] is False
    assert "langage" in verdict["raison"]


def test_verifier_script_refuse_sans_essai():
    """On ne valide pas un effet qu'aucun cas ne prouve (D9)."""
    verdict = verifier_script(_script_pioche(1), [])
    assert verdict["valide"] is False
    assert "aucun essai" in verdict["raison"]


def test_verifier_script_valide_quand_tout_passe():
    """Script conforme + essai vert = valide ; le détail porte l'essai sans anomalie."""
    essai = {
        "nom": "pioche 1",
        "etat": {"alice": {"pioche": 3, "main": 0}, "bob": {}},
        "attendu": {"etat": {"alice": {"pioche": 2, "main": 1}}},
    }
    verdict = verifier_script(_script_pioche(1), [essai])
    assert verdict["valide"] is True
    assert verdict["essais"][0]["anomalies"] == []


def test_verifier_script_refuse_si_un_essai_echoue():
    """Un seul essai qui mord suffit à refuser le script (jamais « partiellement » validé)."""
    base = {"etat": {"alice": {"pioche": 3, "main": 0}, "bob": {}}}
    bon = {"nom": "bon", **base, "attendu": {"etat": {"alice": {"main": 1}}}}
    faux = {"nom": "faux", **base, "attendu": {"etat": {"alice": {"main": 2}}}}
    verdict = verifier_script(_script_pioche(1), [bon, faux])
    assert verdict["valide"] is False
    assert "faux" in verdict["raison"]
