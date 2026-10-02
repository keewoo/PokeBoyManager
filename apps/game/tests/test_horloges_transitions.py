"""Coups journalisés des expirations — ``fin_tour`` et ``defaite_temps`` (lot ``j-timer``).

On prouve les deux actions par défaut nommées par DJ4 (la troisième, la réponse par défaut d'une
demande, est déjà couverte par ``test_demandes_moteur``), et surtout **le pont** entre l'horloge et
le moteur : quand l'horloge de décision d'un adversaire expire, la réponse par défaut est bien celle
que le moteur applique. Une expiration produit **toujours** un coup journalisé, jamais un blocage
(critère d'acceptation).
"""

from __future__ import annotations

from dataclasses import replace

import pytest

# Importer ``pbm_game`` enregistre les transitions d'horloge dans le REGISTRE du journal.
import pbm_game  # noqa: F401
from pbm_game.demandes.gestionnaire import Gestionnaire
from pbm_game.demandes.modele import CAT_CARTE, DemandeDecision
from pbm_game.demandes.moteur import EVT_DEMANDE_EXPIREE, expirer, resoudre
from pbm_game.effets.pile import EffetEnAttente, PileEffets, SourceEffet
from pbm_game.horloges import calcul
from pbm_game.horloges.modele import CAUSE_DECISION, ConfigHorloges
from pbm_game.journal import appliquer
from pbm_game.journal.modele import (
    ACTION_DEFAITE_TEMPS,
    ACTION_FIN_TOUR,
    AUTEUR_SYSTEME,
    EVT_FIN_TOUR,
    EVT_PARTIE_TERMINEE,
    RAISON_TEMPS_ECOULE,
    Action,
    Evenement,
)
from pbm_game.journal.transitions import _ACTIONS_PENDANT_DEMANDE
from pbm_game.rng import Rng
from pbm_game.state.modele import (
    PHASE_CHECKUP,
    PHASE_PRINCIPALE,
    Carte,
    EtatPartie,
    Joueur,
    PokemonEnJeu,
    Tour,
)

T0 = 1_000_000.0


def _etat(phase: str = PHASE_PRINCIPALE, actif: str = "alice") -> EtatPartie:
    base = PokemonEnJeu(cartes=(Carte("a-1", "ref-a"),))
    alice = Joueur(id="alice", actif=base)
    bob = Joueur(id="bob", actif=base)
    return EtatPartie(
        joueurs=(alice, bob), tour=Tour(joueur_actif=actif, numero=3, phase=phase)
    )


def _rng() -> Rng:
    return Rng(b"seed-0123456789a")


# --- fin_tour : l'horloge par tour a expiré ----------------------------------


def test_fin_tour_entre_en_checkup_et_journalise():
    etat2, evts = appliquer(_etat(), Action(ACTION_FIN_TOUR, AUTEUR_SYSTEME, {}), _rng())
    assert etat2.tour.phase == PHASE_CHECKUP  # le tour est terminé (R-5.8 / R-12.1)
    assert etat2.tour.joueur_actif == "alice"  # le tour suivant s'ouvrira ensuite
    types = [e.type for e in evts]
    assert EVT_FIN_TOUR in types  # jamais un abandon muet


def test_fin_tour_refuse_un_auteur_etranger():
    with pytest.raises(ValueError):
        appliquer(_etat(), Action(ACTION_FIN_TOUR, "bob", {}), _rng())


def test_fin_tour_refuse_hors_phase_jouable():
    """On ne « termine » pas un tour en phase de pioche (il n'a pas commencé) ni déjà en Checkup."""
    with pytest.raises(ValueError):
        appliquer(_etat(phase=PHASE_CHECKUP), Action(ACTION_FIN_TOUR, AUTEUR_SYSTEME, {}), _rng())


# --- defaite_temps : le budget total est épuisé ------------------------------


def test_defaite_temps_termine_la_partie_pour_l_adversaire():
    etat2, evts = appliquer(
        _etat(), Action(ACTION_DEFAITE_TEMPS, AUTEUR_SYSTEME, {"joueur": "alice"}), _rng()
    )
    assert etat2.terminee and etat2.vainqueur == "bob"
    assert etat2.raison_fin == RAISON_TEMPS_ECOULE
    assert any(e.type == EVT_PARTIE_TERMINEE for e in evts)


def test_defaite_temps_exige_l_auteur_systeme_et_un_perdant_de_la_partie():
    with pytest.raises(ValueError):  # auteur joueur refusé
        appliquer(_etat(), Action(ACTION_DEFAITE_TEMPS, "alice", {"joueur": "alice"}), _rng())
    with pytest.raises(ValueError):  # perdant inconnu
        appliquer(_etat(), Action(ACTION_DEFAITE_TEMPS, AUTEUR_SYSTEME, {"joueur": "zoe"}), _rng())


def test_defaite_temps_permise_pendant_une_demande_mais_pas_fin_tour():
    """Un budget peut s'épuiser pendant la décision adverse → défaite permise (comme l'abandon).

    ``fin_tour``, elle, n'a pas de sens pendant une demande (le tour est suspendu) : la garde du
    noyau la refuse, car elle n'est pas dans l'ensemble des actions permises pendant une demande.
    """
    assert ACTION_DEFAITE_TEMPS in _ACTIONS_PENDANT_DEMANDE
    assert ACTION_FIN_TOUR not in _ACTIONS_PENDANT_DEMANDE


# --- Le pont horloge → moteur : expiration d'une décision adverse ------------


def _effet(**params) -> EffetEnAttente:
    return EffetEnAttente(
        type_effet="carte",
        source=SourceEffet("carte Appat", ref="r-appat", instance_id="i-appat"),
        regle="R-9.3",
        libelle="Appat",
        params=params,
    )


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


def test_expiration_decision_adverse_applique_la_reponse_par_defaut(caplog):
    """C'est le tour d'alice ; bob doit décider, son horloge de décision expire → défaut.

    On relie les deux moitiés du lot : l'**horloge** attribue bien l'échéance à bob (``decision``),
    et le **moteur** applique la réponse par défaut, écrite au journal (`EVT_DEMANDE_EXPIREE`).
    """
    reg = {"carte": _resolveur_carte}
    etat = _etat(actif="alice")
    pile = PileEffets().empiler(_effet(destinataire="bob", options=["b1", "b2"]))
    rng = _rng()
    etat1, _evts, resolution = resoudre(etat, pile, reg, rng, Gestionnaire())
    assert resolution is not None and resolution.demande.destinataire == "bob"
    etat1 = replace(etat1, resolution=resolution)

    # L'horloge : c'est le tour d'alice, mais bob décide — son horloge de décision court.
    h = calcul.poser_decision(
        calcul.demarrer(
            ConfigHorloges(
                par_tour_s=90, par_joueur_s=1500, par_decision_s=30,
                tolerance_reseau_s=10,
            ),
            ("alice", "bob"), "alice", T0,
        ),
        "bob", T0 + 5,
    )
    echeance = calcul.premiere_echeance(h, T0 + 100)
    assert echeance == ("bob", CAUSE_DECISION)

    # Puisque la cause est « decision » et que le destinataire est bob, la réponse par défaut (la
    # première option valide) est appliquée par le moteur et journalisée.
    etat2, evts = expirer(etat1, rng, registre=reg)
    assert etat2.resolution is None  # la demande est levée, la partie n'est plus en pause
    assert any(e.type == EVT_DEMANDE_EXPIREE for e in evts)
