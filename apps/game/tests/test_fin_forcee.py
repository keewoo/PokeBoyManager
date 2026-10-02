"""Clôtures forcées d'une partie — ``deserter`` et ``expirer_inactivite`` (lot
``j-deconnexion-abandon``).

On prouve les deux transitions système que ce lot ajoute : la **désertion** (forfait d'un joueur
déconnecté qui ne revient pas) et l'**expiration pour inactivité** (ménage d'une partie fantôme,
sans vainqueur). Toutes deux sont **terminales** et **journalisées** (``EVT_PARTIE_TERMINEE``) —
jamais un effacement muet (critère d'acceptation : « chaque clôture porte son motif dans le
journal »). Chaque test cite la règle de fin qu'il exerce (R-14.6).
"""

from __future__ import annotations

from dataclasses import replace

import pytest

# Importer ``pbm_game`` enregistre les clôtures forcées dans le REGISTRE du journal.
import pbm_game  # noqa: F401
from pbm_game.demandes.gestionnaire import Gestionnaire
from pbm_game.demandes.modele import CAT_CARTE, DemandeDecision
from pbm_game.demandes.moteur import resoudre
from pbm_game.effets.pile import EffetEnAttente, PileEffets, SourceEffet
from pbm_game.journal import appliquer
from pbm_game.journal.modele import (
    ACTION_ABANDONNER,
    ACTION_DESERTER,
    ACTION_EXPIRER_INACTIVITE,
    AUTEUR_SYSTEME,
    EVT_PARTIE_TERMINEE,
    RAISON_ABANDON,
    RAISON_DESERTION,
    RAISON_INACTIVITE,
    Action,
    Evenement,
)
from pbm_game.journal.transitions import _ACTIONS_PENDANT_DEMANDE
from pbm_game.rng import Rng
from pbm_game.state.modele import (
    PHASE_PRINCIPALE,
    Carte,
    EtatPartie,
    Joueur,
    PokemonEnJeu,
    Tour,
)


def _etat(actif: str = "alice") -> EtatPartie:
    base = PokemonEnJeu(cartes=(Carte("a-1", "ref-a"),))
    alice = Joueur(id="alice", actif=base)
    bob = Joueur(id="bob", actif=base)
    return EtatPartie(
        joueurs=(alice, bob), tour=Tour(joueur_actif=actif, numero=3, phase=PHASE_PRINCIPALE)
    )


def _rng() -> Rng:
    return Rng(b"seed-0123456789a")


# --- deserter : forfait du joueur déconnecté (R-14.6) ------------------------


def test_deserter_termine_la_partie_pour_l_adversaire():
    """R-14.6 — le déserteur perd, l'adversaire gagne, la fin est journalisée avec son motif."""
    etat2, evts = appliquer(
        _etat(), Action(ACTION_DESERTER, AUTEUR_SYSTEME, {"joueur": "alice"}), _rng()
    )
    assert etat2.terminee and etat2.vainqueur == "bob"
    assert etat2.raison_fin == RAISON_DESERTION
    evt = next(e for e in evts if e.type == EVT_PARTIE_TERMINEE)
    assert evt.donnees["deserteur"] == "alice" and evt.donnees["raison"] == RAISON_DESERTION


def test_deserter_exige_l_auteur_systeme_et_un_deserteur_de_la_partie():
    with pytest.raises(ValueError):  # auteur joueur refusé (c'est une clôture système)
        appliquer(_etat(), Action(ACTION_DESERTER, "alice", {"joueur": "alice"}), _rng())
    with pytest.raises(ValueError):  # déserteur absent de « params »
        appliquer(_etat(), Action(ACTION_DESERTER, AUTEUR_SYSTEME, {}), _rng())
    with pytest.raises(ValueError):  # déserteur inconnu de la partie
        appliquer(_etat(), Action(ACTION_DESERTER, AUTEUR_SYSTEME, {"joueur": "zoe"}), _rng())


# --- expirer_inactivite : ménage d'une partie fantôme, sans vainqueur --------


def test_expirer_inactivite_clot_sans_vainqueur():
    """R-14.6 — plus personne ne joue : la partie se ferme, sans vainqueur, motif journalisé."""
    etat2, evts = appliquer(
        _etat(), Action(ACTION_EXPIRER_INACTIVITE, AUTEUR_SYSTEME, {}), _rng()
    )
    assert etat2.terminee and etat2.vainqueur is None
    assert etat2.raison_fin == RAISON_INACTIVITE
    evt = next(e for e in evts if e.type == EVT_PARTIE_TERMINEE)
    assert evt.donnees["vainqueur"] is None and evt.donnees["raison"] == RAISON_INACTIVITE


def test_expirer_inactivite_refuse_un_auteur_joueur():
    with pytest.raises(ValueError):
        appliquer(_etat(), Action(ACTION_EXPIRER_INACTIVITE, "alice", {}), _rng())


# --- Les deux clôtures sont permises même pendant une demande en cours -------


def test_cloture_forcee_permise_pendant_une_demande():
    """Un joueur peut déserter (ou le balayage clore) pendant que l'adversaire décide."""
    assert ACTION_DESERTER in _ACTIONS_PENDANT_DEMANDE
    assert ACTION_EXPIRER_INACTIVITE in _ACTIONS_PENDANT_DEMANDE


# --- R-14.6 : une partie déjà terminée refuse toute clôture ------------------


def test_cloture_forcee_refuse_une_partie_terminee():
    fini = replace(_etat(), terminee=True, vainqueur="bob", raison_fin="abandon")
    with pytest.raises(ValueError):
        appliquer(fini, Action(ACTION_DESERTER, AUTEUR_SYSTEME, {"joueur": "alice"}), _rng())
    with pytest.raises(ValueError):
        appliquer(fini, Action(ACTION_EXPIRER_INACTIVITE, AUTEUR_SYSTEME, {}), _rng())


# --- Abandon et désertion pendant une demande de décision (mission, test #3) -


def _resolveur_carte(etat, effet, rng, gestionnaire):
    d = DemandeDecision(
        destinataire=effet.params["destinataire"],
        categorie=CAT_CARTE,
        source=effet.source,
        regle="R-9.3",
        libelle=effet.libelle,
        options=tuple(effet.params["options"]),
    )
    reponse = gestionnaire.demander(d)
    choisi = reponse.choix[0] if reponse.choix else "aucun"
    return etat, [Evenement("carte_choisie", {"choix": choisi})], []


def _etat_avec_demande() -> EtatPartie:
    """Un état **suspendu sur une demande** adressée à bob (c'est le tour d'alice).

    On passe par la vraie machinerie de décision (``resoudre``) plutôt que de bricoler un état :
    c'est ce qui garantit que le test exerce bien la garde « une demande est en cours » du noyau.
    """
    reg = {"carte": _resolveur_carte}
    effet = EffetEnAttente(
        type_effet="carte",
        source=SourceEffet("carte Appat", ref="r-appat", instance_id="i-appat"),
        regle="R-9.3",
        libelle="Appat",
        params={"destinataire": "bob", "options": ["b1", "b2"]},
    )
    etat1, _evts, resolution = resoudre(
        _etat(), PileEffets().empiler(effet), reg, _rng(), Gestionnaire()
    )
    assert resolution is not None and resolution.demande.destinataire == "bob"
    return replace(etat1, resolution=resolution)


def test_abandon_permis_pendant_une_demande():
    """R-14.3 — abandonner reste permis même quand une décision est en attente (jamais bloqué)."""
    etat = _etat_avec_demande()
    etat2, evts = appliquer(etat, Action(ACTION_ABANDONNER, "alice", {}), _rng())
    assert etat2.terminee and etat2.vainqueur == "bob"
    assert etat2.raison_fin == RAISON_ABANDON
    assert any(e.type == EVT_PARTIE_TERMINEE for e in evts)


def test_desertion_permise_pendant_une_demande():
    """Un joueur peut déserter pendant que l'adversaire décide : la clôture passe, motif propre."""
    etat = _etat_avec_demande()
    action = Action(ACTION_DESERTER, AUTEUR_SYSTEME, {"joueur": "bob"})
    etat2, evts = appliquer(etat, action, _rng())
    assert etat2.terminee and etat2.vainqueur == "alice"
    assert etat2.raison_fin == RAISON_DESERTION
    assert any(e.type == EVT_PARTIE_TERMINEE for e in evts)
