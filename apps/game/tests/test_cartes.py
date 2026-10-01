"""Tests du lot ``j-cartes-pokemon`` — définition de carte, pose, pile d'évolution (R-5.3, R-7).

Le moteur reste **pur** : ces tests construisent des états et rejouent des actions journalisées
(``poser`` / ``evoluer``) via :func:`pbm_game.journal.transitions.appliquer`, sans aucune E/S.
Chaque test de règle nomme le ``R-x.y`` qu'il vérifie — les cas exécutables de
``docs/jeu/cas-executables/evolution.yaml`` couvrent les six cas d'évolution ; ceux-ci ajoutent
la validation de la **fiche de carte** (marqueur de règle inconnu, champ manquant) et les cas
limites des transitions (banc plein, mauvais Pokémon, carte de base refusée à l'évolution).
"""

from __future__ import annotations

import pytest

from pbm_game.cartes import (
    AttaqueDef,
    definition_depuis_dict,
)
from pbm_game.cas.constructeur import GRAINE_DEFAUT, construire
from pbm_game.combat.fin import resoudre_kos
from pbm_game.combat.modele import CoutAttaque
from pbm_game.journal.modele import ACTION_EVOLUER, ACTION_POSER, Action
from pbm_game.journal.transitions import appliquer
from pbm_game.rng import Rng

DEF_CARAPUCE = {
    "ref": "r-carapuce",
    "nom": "Carapuce",
    "stade": "base",
    "pv": 60,
    "type": "eau",
    "marqueur": "ordinaire",
}
DEF_CARABAFFE = {
    "ref": "r-carabaffe",
    "nom": "Carabaffe",
    "stade": "stade1",
    "pv": 80,
    "type": "eau",
    "marqueur": "ordinaire",
    "evolue_depuis": "Carapuce",
}
DEF_TORTANK = {
    "ref": "r-tortank",
    "nom": "Tortank",
    "stade": "stade2",
    "pv": 150,
    "type": "eau",
    "marqueur": "ordinaire",
    "evolue_depuis": "Carabaffe",
}


def _appliquer(etat, type_, auteur, params):
    return appliquer(etat, Action(type_, auteur, params), Rng(GRAINE_DEFAUT))


def _etat(spec):
    etat, fiches = construire(spec)
    return etat, fiches


# --- Définition de carte : la fiche catalogue, validée (D9) --------------------------------


def test_definition_base_et_evolution_valides():
    """R-7.1 — une base n'a pas de prédécesseur ; une évolution nomme le sien."""
    base = definition_depuis_dict(DEF_CARAPUCE)
    assert base.stade == "base" and base.evolue_depuis is None and not base.est_evolution
    evo = definition_depuis_dict(DEF_CARABAFFE)
    assert evo.est_evolution and evo.evolue_depuis == "Carapuce"
    assert evo.recompenses == 1  # marqueur « ordinaire » (R-13.3)
    assert evo.fiche() == {"pv": 80, "marqueur": "ordinaire"}


def test_marqueur_de_regle_inconnu_refuse():
    """R-13.4 / R-15.22 — un marqueur de règle inconnu est refusé, jamais « par défaut 1 »."""
    with pytest.raises(ValueError, match="inconnu"):
        definition_depuis_dict({**DEF_CARAPUCE, "marqueur": "zarbi"})


def test_champ_manquant_bloque_la_carte():
    """Risque nommé : un champ manquant bloque la carte, jamais deviné (D9)."""
    with pytest.raises(ValueError, match="PV"):
        definition_depuis_dict({k: v for k, v in DEF_CARAPUCE.items() if k != "pv"})
    with pytest.raises(ValueError, match="stade"):
        definition_depuis_dict({k: v for k, v in DEF_CARAPUCE.items() if k != "stade"})
    # Une évolution sans prédécesseur imprimé est bloquée (R-7.1).
    with pytest.raises(ValueError, match="evolue_depuis"):
        definition_depuis_dict({k: v for k, v in DEF_CARABAFFE.items() if k != "evolue_depuis"})
    # Une base qui prétend évoluer de quelque chose est incohérente.
    with pytest.raises(ValueError, match="base"):
        definition_depuis_dict({**DEF_CARAPUCE, "evolue_depuis": "Rien"})


def test_attaque_degats_secs_vs_effet():
    """R-9.2 / R-10.6 — dégâts secs jouables, un effet non (D9), dégâts multiple de 10."""
    seche = AttaqueDef(nom="Pistolet à O", cout=CoutAttaque(types={"eau": 1}), degats=20)
    assert seche.degats_secs
    a_effet = AttaqueDef(
        nom="Berceuse", cout=CoutAttaque(incolore=1), degats=0, effet="Endort la cible."
    )
    assert not a_effet.degats_secs
    with pytest.raises(ValueError, match="multiple de 10"):
        AttaqueDef(nom="Bizarre", cout=CoutAttaque(), degats=15)


# --- Pose d'un Pokémon de base (R-5.3, R-3.2, R-3.3) ---------------------------------------


def _etat_pose(**tour):
    base_tour = {"joueur": "alice", "phase": "principale", "numero": 3}
    base_tour.update(tour)
    return _etat({"alice": {"main": 1}, "bob": {"actif": {}}, "tour": base_tour})


def test_poser_au_banc_marque_entree():
    """R-5.3 / R-7.3 — poser une base au banc ; elle est « nouvelle en jeu » ce tour."""
    etat, _ = _etat_pose()
    etat2, evts = _appliquer(
        etat, ACTION_POSER, "alice", {"carte_main": "alice.main0", "definition": DEF_CARAPUCE}
    )
    alice = etat2.joueurs[0]
    assert len(alice.banc) == 1 and len(alice.main) == 0
    assert "alice.main0" in etat2.tour.entres_en_jeu_ce_tour
    assert evts[0].type == "pokemon_pose" and evts[0].donnees["zone"] == "banc"


def test_poser_banc_plein_refuse():
    """R-3.2 / R-8.1 — on ne pose pas un 6e Pokémon au banc."""
    etat, _ = _etat(
        {
            "alice": {"main": 1, "banc": 5},
            "bob": {"actif": {}},
            "tour": {"joueur": "alice", "phase": "principale", "numero": 3},
        }
    )
    with pytest.raises(ValueError, match="R-3.2"):
        _appliquer(
            etat, ACTION_POSER, "alice", {"carte_main": "alice.main0", "definition": DEF_CARAPUCE}
        )


def test_poser_hors_phase_principale_refuse():
    """R-5.3 — poser est un coup de la phase principale."""
    etat, _ = _etat_pose(phase="pioche")
    with pytest.raises(ValueError, match="R-5.3"):
        _appliquer(
            etat, ACTION_POSER, "alice", {"carte_main": "alice.main0", "definition": DEF_CARAPUCE}
        )


def test_poser_actif_place_vide():
    """Cas particulier (R-3.3) — une base entre directement comme Actif si la place est vide."""
    etat, _ = _etat(
        {
            "alice": {"main": 1},
            "bob": {"actif": {}},
            "tour": {"joueur": "alice", "phase": "principale", "numero": 3},
        }
    )
    etat2, _ = _appliquer(
        etat,
        ACTION_POSER,
        "alice",
        {"carte_main": "alice.main0", "definition": DEF_CARAPUCE, "zone": "actif"},
    )
    assert etat2.joueurs[0].actif is not None


def test_poser_actif_occupe_refuse():
    """R-3.3 — une pose ne remplace jamais un Actif présent."""
    etat, _ = _etat_pose()  # alice a déjà... non : _etat_pose n'a pas d'actif alice
    etat, _ = _etat(
        {
            "alice": {"main": 1, "actif": {}},
            "bob": {"actif": {}},
            "tour": {"joueur": "alice", "phase": "principale", "numero": 3},
        }
    )
    with pytest.raises(ValueError, match="R-3.3"):
        _appliquer(
            etat,
            ACTION_POSER,
            "alice",
            {"carte_main": "alice.main0", "definition": DEF_CARAPUCE, "zone": "actif"},
        )


def test_poser_evolution_refusee():
    """R-7.1 — une carte d'évolution ne se pose pas directement : elle entre par « evoluer »."""
    etat, _ = _etat_pose()
    with pytest.raises(ValueError, match="R-7.1"):
        _appliquer(
            etat, ACTION_POSER, "alice", {"carte_main": "alice.main0", "definition": DEF_CARABAFFE}
        )


# --- Évolution : pile, conservation, chaîne (R-7) ------------------------------------------


def _etat_evo(actif_spec, **tour):
    base_tour = {"joueur": "alice", "phase": "principale", "numero": 3}
    base_tour.update(tour)
    return _etat(
        {"alice": {"actif": actif_spec, "main": 1}, "bob": {"actif": {}}, "tour": base_tour}
    )


def _evoluer(etat, definition, nom_base="Carapuce"):
    return _appliquer(
        etat,
        ACTION_EVOLUER,
        "alice",
        {
            "base": "alice.actif",
            "carte_main": "alice.main0",
            "nom_base": nom_base,
            "definition": definition,
        },
    )


def test_evoluer_conserve_et_soigne():
    """R-7.1 / R-7.2 — l'évolution garde énergies et compteurs, et retire les états spéciaux."""
    etat, _ = _etat_evo({"energies": 2, "degats": 30, "etats": ["endormi"]})
    etat2, evts = _evoluer(etat, DEF_CARABAFFE)
    actif = etat2.joueurs[0].actif
    assert len(actif.cartes) == 2 and len(actif.energies) == 2 and actif.compteurs_degats == 30
    assert actif.etats_speciaux == frozenset()
    assert "alice.actif" in etat2.tour.evolues_ce_tour
    assert evts[0].type == "evolution" and evts[0].donnees["etats_soignes"] == ["endormi"]


def test_evoluer_stade2_sur_stade1():
    """R-7.1 — un stade 2 se pose sur son stade 1 ; la pile atteint trois cartes."""
    etat, _ = _etat_evo({"cartes": 2})  # pile base + stade 1 déjà en jeu
    etat2, _ = _evoluer(etat, DEF_TORTANK, nom_base="Carabaffe")
    assert len(etat2.joueurs[0].actif.cartes) == 3


def test_evoluer_mauvais_pokemon_refuse():
    """R-7.1 — on n'évolue que sur le bon prédécesseur imprimé."""
    etat, _ = _etat_evo({})
    with pytest.raises(ValueError, match="R-7.1"):
        _evoluer(etat, DEF_CARABAFFE, nom_base="Salamèche")


def test_evoluer_carte_de_base_refusee():
    """R-7.1 — une carte de base ne fait évoluer aucun Pokémon."""
    etat, _ = _etat_evo({})
    with pytest.raises(ValueError, match="R-7.1"):
        _evoluer(etat, DEF_CARAPUCE)


def test_evoluer_premier_tour_refuse():
    """R-6.5 — aucune évolution au premier tour."""
    etat, _ = _etat_evo({}, numero=1)
    with pytest.raises(ValueError, match="R-6.5"):
        _evoluer(etat, DEF_CARABAFFE)


def test_evoluer_entre_ce_tour_refuse():
    """R-7.3 — pas d'évolution d'un Pokémon entré en jeu ce tour."""
    etat, _ = _etat_evo({}, entres=["alice.actif"])
    with pytest.raises(ValueError, match="R-7.3"):
        _evoluer(etat, DEF_CARABAFFE)


def test_evoluer_deux_fois_refuse():
    """R-7.4 — un Pokémon n'évolue qu'une fois par tour."""
    etat, _ = _etat_evo({}, evolues=["alice.actif"])
    with pytest.raises(ValueError, match="R-7.4"):
        _evoluer(etat, DEF_CARABAFFE)


def test_ko_pile_evolution_defausse_tout():
    """R-13.2 — un K.O. défausse toute la pile d'évolution ET ses énergies."""
    etat, fiches = _etat(
        {
            "alice": {
                "actif": {
                    "cartes": 3,
                    "energies": 2,
                    "degats": 120,
                    "pv": 120,
                    "marqueur": "ordinaire",
                },
                "banc": 1,
                "recompenses": 6,
            },
            "bob": {"actif": {}, "recompenses": 6},
            "tour": {"joueur": "alice", "phase": "checkup", "numero": 4},
        }
    )
    etat2, _ = resoudre_kos(etat, fiches, ("alice", "bob"))
    alice = etat2.joueurs[0]
    assert alice.actif is None
    assert len(alice.defausse) == 5  # 3 cartes de la pile + 2 énergies (R-13.2)
