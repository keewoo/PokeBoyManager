"""Exécute la **batterie de cas de règles** (docs/jeu/cas-executables/) contre le moteur.

C'est le test qui donne corps au lot ``j-tests-regles`` : chaque cas écrit en données est
**rejoué** contre les fonctions réelles de ``pbm_game`` et son résultat **vérifié**. Un cas qui
échoue nomme son identifiant — on sait immédiatement quelle règle a cessé d'être tenue.

Ce fichier fait l'**entrée/sortie** (charger les YAML) ; l'exécuteur (``pbm_game.cas``) reste pur.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from pbm_game.cas import EchecCas, construire, executer, trouver_graine
from pbm_game.cas.couverture import regles_d_un_cas
from pbm_game.cas.executeur import OPERATIONS

# apps/game/tests/test_cas_executables.py -> racine du dépôt (parents[3]).
RACINE_DEPOT = Path(__file__).resolve().parents[3]
DOSSIER_CAS = RACINE_DEPOT / "docs" / "jeu" / "cas-executables"

#: Nombre minimal de cas exigé par la mission (critère d'acceptation).
CAS_MINIMUM = 200


def _charger_tous_les_cas() -> list[dict]:
    assert DOSSIER_CAS.is_dir(), f"Dossier des cas introuvable : {DOSSIER_CAS}"
    cas: list[dict] = []
    for fichier in sorted(DOSSIER_CAS.glob("*.yaml")):
        donnees = yaml.safe_load(fichier.read_text(encoding="utf-8"))
        assert isinstance(donnees, dict) and isinstance(donnees.get("cas"), list), (
            f"{fichier.name} : attendu un mapping avec une liste « cas »."
        )
        for c in donnees["cas"]:
            c["_fichier"] = fichier.name  # trace pour les messages d'erreur
            cas.append(c)
    return cas


_TOUS_LES_CAS = _charger_tous_les_cas()


@pytest.mark.parametrize("cas", _TOUS_LES_CAS, ids=[c["id"] for c in _TOUS_LES_CAS])
def test_cas_passe(cas: dict):
    """Chaque cas de la batterie est vert contre le moteur réel."""
    executer(cas)


def test_au_moins_200_cas():
    """La mission exige au moins 200 cas (critère d'acceptation)."""
    assert len(_TOUS_LES_CAS) >= CAS_MINIMUM, (
        f"{len(_TOUS_LES_CAS)} cas seulement, {CAS_MINIMUM} exigés."
    )


def test_tous_les_cas_sont_bien_formes():
    """Chaque cas cite au moins une règle R-x.y, a un id unique et une opération connue."""
    ids: set[str] = set()
    for cas in _TOUS_LES_CAS:
        regles_d_un_cas(cas)  # valide id, regles, op, description
        cid = cas["id"]
        assert cid not in ids, f"Identifiant de cas en double : « {cid} »."
        ids.add(cid)
        assert cas["op"] in OPERATIONS, f"Cas « {cid} » : opération inconnue « {cas['op']} »."


# --- Le harnais doit MORDRE : un cas faux échoue, une opération inconnue échoue. ---


def test_executeur_mord_sur_un_attendu_faux():
    """Un attendu délibérément faux fait échouer l'exécuteur (sinon il ne prouverait rien)."""
    faux = {
        "id": "faux-exprès",
        "regles": ["R-10.2"],
        "op": "degats",
        "description": "faux",
        "args": {"base": 60, "type_attaque": "feu", "faiblesse": {"type": "feu"}},
        "attendu": {"degats": 999},
    }
    with pytest.raises(EchecCas):
        executer(faux)


def test_executeur_refuse_une_operation_inconnue():
    with pytest.raises(EchecCas, match="opération inconnue"):
        executer({"id": "x", "regles": ["R-1.1"], "op": "voler", "description": "d"})


def test_executeur_mord_si_une_erreur_attendue_ne_survient_pas():
    """Un cas qui attend une erreur mais dont l'action réussit échoue."""
    cas = {
        "id": "erreur-absente",
        "regles": ["R-14.3"],
        "op": "appliquer",
        "description": "abandon légal mais on attend (à tort) une erreur",
        "etat": {"alice": {"actif": {}}, "bob": {"actif": {}},
                 "tour": {"joueur": "alice", "phase": "principale"}},
        "action": {"type": "abandonner", "auteur": "alice"},
        "erreur": "R-99.9 impossible",
    }
    with pytest.raises(EchecCas):
        executer(cas)


# --- Le constructeur et la recherche de graine : briques pures, testées à part. ---


def test_constructeur_refuse_une_cle_inconnue():
    with pytest.raises(ValueError, match="inconnue"):
        construire({"alice": {"zorglub": 1}, "bob": {}})


def test_constructeur_fabrique_les_fiches():
    _, fiches = construire(
        {"alice": {"actif": {"pv": 120, "marqueur": "ex"}}, "bob": {"actif": {}}}
    )
    assert any(f.get("marqueur") == "ex" and f["pv"] == 120 for f in fiches.values())


def test_trouver_graine_produit_les_tirages_voulus():
    from pbm_game.rng import Rng

    graine = trouver_graine([("confusion:alice", "pile"), ("confusion:alice", "face")])
    rng = Rng(graine)
    assert rng.pile_ou_face("confusion:alice", "test") == "pile"
    assert rng.pile_ou_face("confusion:alice", "test") == "face"
