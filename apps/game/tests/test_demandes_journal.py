"""Les demandes dans le **journal** — garde « demande en cours », actions, et rejeu fidèle.

Lot ``j-effets-choix``. Répondre à une demande (ou laisser le délai expirer) sont des coups
**journalisés** : on prouve ici qu'ils passent par ``appliquer`` comme les autres, que la garde
bloque toute autre action pendant qu'une demande attend (sauf l'abandon, R-14.3), et surtout que le
**rejeu** d'une partie interrompue au milieu d'une demande la reconstruit à l'identique — c'est la
reprise après reconnexion (critère d'acceptation du lot).

``pbm_game`` est importé (les transitions ``repondre_demande`` / ``expirer_demande`` et le résolveur
DSL s'enregistrent à l'import) : on s'appuie sur le registre réel, pas sur un montage de test.
"""

from __future__ import annotations

import pytest
from fabrique_dsl import etat, joueur, pokemon

import pbm_game  # noqa: F401  (enregistre transitions + résolveur DSL)
from pbm_game.demandes.moteur import demarrer_resolution
from pbm_game.effets.dsl import charger_programme, compiler_en_effet
from pbm_game.effets.dsl.contexte import ContexteEffet
from pbm_game.effets.pile import PileEffets, SourceEffet
from pbm_game.journal.empreinte import empreinte
from pbm_game.journal.modele import (
    ACTION_ABANDONNER,
    ACTION_EXPIRER_DEMANDE,
    ACTION_PIOCHER,
    ACTION_REPONDRE_DEMANDE,
    AUTEUR_SYSTEME,
    Action,
)
from pbm_game.journal.rejeu import rejouer
from pbm_game.journal.transitions import appliquer, jouer, partie_neuve
from pbm_game.rng import Rng

_GRAINE_HEX = "00112233445566778899aabbccddeeff"  # 16 octets


def _etat_avec_demande():
    """Un état **suspendu** sur un ``choisir`` DSL — une partie reprise en pleine demande.

    Le destinataire est « alice » (qui joue l'effet). Renvoie ``(etat1, demande)``.
    """
    alice = joueur(
        "alice", actif=pokemon("a-actif", compteurs=30), banc=(pokemon("a-banc", compteurs=20),)
    )
    bob = joueur("bob", actif=pokemon("b"))
    prog = charger_programme(
        {
            "version": 1,
            "effets": [
                {
                    "op": "choisir",
                    "cible": {"zone": "en_jeu", "proprietaire": "moi", "nombre": 1},
                    "alors": [{"op": "soigner"}],
                }
            ],
        }
    )
    ctx = ContexteEffet(
        source=SourceEffet("Potion", ref="ref-potion", instance_id="i-potion"),
        joueur="alice",
        adversaire="bob",
    )
    effet = compiler_en_effet(prog, ctx, libelle="Potion", regle="R-9.3")
    pile = PileEffets().empiler(effet)
    etat1, _ = demarrer_resolution(etat(alice, bob), pile, Rng(bytes.fromhex(_GRAINE_HEX)))
    return etat1, etat1.resolution.demande


def test_garde_bloque_toute_action_sauf_reponse_et_abandon():
    etat1, _ = _etat_avec_demande()
    # Piocher pendant qu'une demande attend : refusé, et le refus nomme la demande.
    with pytest.raises(ValueError, match="Décision en attente"):
        appliquer(
            etat1, Action(ACTION_PIOCHER, "alice", {"nombre": 1}), Rng(bytes.fromhex(_GRAINE_HEX))
        )
    # Abandonner, lui, reste permis (R-14.3) : la partie se fige, l'adversaire gagne.
    etat2, _ = appliquer(etat1, Action(ACTION_ABANDONNER, "alice"), Rng(bytes.fromhex(_GRAINE_HEX)))
    assert etat2.terminee and etat2.vainqueur == "bob"


def test_repondre_par_appliquer_resout_et_journalise():
    etat1, demande = _etat_avec_demande()
    action = Action(
        ACTION_REPONDRE_DEMANDE, "alice", {"demande_id": demande.id, "choix": ["a-banc"]}
    )
    etat2, evts = appliquer(etat1, action, Rng(bytes.fromhex(_GRAINE_HEX)))
    assert etat2.resolution is None
    alice = next(j for j in etat2.joueurs if j.id == "alice")
    degats = {p.cartes[0].instance_id: p.compteurs_degats for p in (alice.actif, *alice.banc)}
    assert degats == {"a-actif": 30, "a-banc": 0}  # le banc choisi est soigné


def test_repondre_a_la_place_de_l_autre_refuse():
    etat1, demande = _etat_avec_demande()
    # La demande vise « alice » : « bob » ne répond pas à sa place (le serveur fait foi).
    action = Action(ACTION_REPONDRE_DEMANDE, "bob", {"demande_id": demande.id, "choix": ["a-banc"]})
    with pytest.raises(ValueError, match="ne peut pas répondre à la place"):
        appliquer(etat1, action, Rng(bytes.fromhex(_GRAINE_HEX)))


def test_expirer_par_appliquer_applique_le_defaut():
    etat1, _ = _etat_avec_demande()
    action = Action(ACTION_EXPIRER_DEMANDE, AUTEUR_SYSTEME)
    etat2, _ = appliquer(etat1, action, Rng(bytes.fromhex(_GRAINE_HEX)))
    assert etat2.resolution is None
    alice = next(j for j in etat2.joueurs if j.id == "alice")
    degats = {p.cartes[0].instance_id: p.compteurs_degats for p in (alice.actif, *alice.banc)}
    assert degats == {"a-actif": 0, "a-banc": 20}  # défaut = 1re option = l'Actif


def test_expirer_doit_etre_une_action_systeme():
    etat1, _ = _etat_avec_demande()
    with pytest.raises(ValueError, match="action système"):
        appliquer(etat1, Action(ACTION_EXPIRER_DEMANDE, "alice"), Rng(bytes.fromhex(_GRAINE_HEX)))


def test_empreinte_distingue_une_demande_en_cours():
    # Une résolution en cours fait partie de l'état : elle change l'empreinte (donc le rejeu la
    # contrôle au coup près, et une partie suspendue ne se confond pas avec la même sans demande).
    from dataclasses import replace

    etat1, _ = _etat_avec_demande()
    sans = replace(etat1, resolution=None)
    assert empreinte(etat1) != empreinte(sans)


def test_rejeu_d_une_partie_interrompue_au_milieu_d_une_demande():
    """Reprise après reconnexion : on rejoue une partie figée sur une demande, puis sa réponse.

    ``etat_initial`` est l'état suspendu (persisté avant la coupure). Le journal porte la
    réponse. ``rejouer`` repart de l'état initial, applique la réponse, et contrôle l'empreinte à
    chaque coup : aucune divergence, et la partie termine sans demande en attente.
    """
    etat1, demande = _etat_avec_demande()
    partie = partie_neuve(etat1, _GRAINE_HEX)
    rng = Rng(bytes.fromhex(_GRAINE_HEX))
    action = Action(
        ACTION_REPONDRE_DEMANDE, "alice", {"demande_id": demande.id, "choix": ["a-banc"]}
    )
    partie, etat2 = jouer(partie, action, "2026-10-02T10:00:00+00:00", etat1, rng)

    rejoue, _ = rejouer(partie)  # vérifie l'empreinte (et les événements) à chaque coup
    assert rejoue == etat2
    assert rejoue.resolution is None
    alice = next(j for j in rejoue.joueurs if j.id == "alice")
    degats = {p.cartes[0].instance_id: p.compteurs_degats for p in (alice.actif, *alice.banc)}
    assert degats == {"a-actif": 30, "a-banc": 0}
