"""Les **Stades** — zone partagée, un seul en jeu, effets continus pour les deux camps.

Lot ``j-cartes-stades``. Trois Stades **réels** scriptés et testés (critère d'acceptation n°3),
chacun dérivé de ce qui est en jeu (jamais une mutation à la pose) :

* **Stade en Liesse** (``sv08-180``) — chaque Pokémon **de base** en jeu reçoit **+30 PV** ;
* **Montagne Gravité** (``sv08-177``) — chaque Pokémon de **Niveau 2** en jeu **perd 30 PV** ;
* **Hôtel « Au paradis des Pokémon »** (``svp-224``) — la **retraite** de chaque **Psykokwak** en
  jeu coûte **1 de moins** (le Stade qui prouve « un Stade modifie le coût de retraite des deux
  camps »).

Les trois tests exigés par la fiche sont ici : le **remplacement** d'un Stade à bonus fait
disparaître le bonus au bon moment
(:func:`test_stade_en_liesse_donne_30_pv_aux_deux_camps_et_le_retrait_restaure_r35`), un Stade de
**même nom** est refusé (:func:`test_stade_de_meme_nom_refuse_a_la_liste_et_par_valider_r35`), et
un Stade modifie le **coût de retraite des deux camps**
(:func:`test_hotel_rend_la_retraite_moins_chere_dans_les_coups_legaux_des_deux_camps_r82`).

Un test qui **mord sans le changement** : rien de ce module (la transition ``jouer_stade``, le
drapeau ``Tour.stade_joue``, ``effets.stades``, le coût de retraite continu de ``effets.continus``,
``DefinitionStade``/``FamilleJouerStade``) n'existe avant ce lot — toute la suite échoue donc à
l'import sans le câblage livré ici. La CI fait foi.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from fabrique_dsl import carte, etat, joueur, pokemon, rng

# ``import pbm_game`` enregistre la transition ``jouer_stade`` dans le REGISTRE du journal
# (via ``effets.stades``), comme pour ``jouer_objet`` : indispensable à ``appliquer``.
import pbm_game  # noqa: F401
from pbm_game.actions import actions_legales, valider
from pbm_game.actions.familles_jeu import CatalogueJeu, DefinitionStade, familles_jeu
from pbm_game.cartes import DefinitionCarte
from pbm_game.effets.continus import (
    collecter_effets_continus,
    cout_retraite_effectif,
    delta_cout_retraite,
    seuil_ko,
)
from pbm_game.effets.stades import (
    HOTEL_PARADIS,
    MONTAGNE_GRAVITE,
    STADE_EN_LIESSE,
    appliquer_jouer_stade,
    producteur_hotel_paradis,
    registre_stades,
)
from pbm_game.journal.modele import (
    ACTION_JOUER_STADE,
    ACTION_RETRAITE,
    EVT_STADE_JOUE,
    Action,
)
from pbm_game.state import depuis_json, vers_json

_RNG = rng()

#: Métadonnées catalogue minimales que le service fournirait au moteur (``ref → {stade, nom}``).
_META = {
    "poke-base": {"stade": "base", "nom": "Pikachu"},
    "poke-stade2": {"stade": "stade2", "nom": "Dracaufeu"},
    "psyduck": {"stade": "base", "nom": "Psykokwak"},
}


def _action_stade(jid: str, carte_main: str, nom: str) -> Action:
    return Action(ACTION_JOUER_STADE, jid, {"carte_main": carte_main, "nom": nom})


def _coups(etat_, jid, type_, familles):
    """Les coups légaux de ``jid`` du type demandé (aide de lisibilité pour les tests)."""
    return [c for c in actions_legales(etat_, jid, familles=familles) if c.action.type == type_]


# --- Critère n°2 + n°1 : Stade en Liesse (+30 PV aux deux camps), retrait restaure (R-3.5) -----
def test_stade_en_liesse_donne_30_pv_aux_deux_camps_et_le_retrait_restaure_r35():
    """R-3.5/R-13.1 — +30 PV aux Pokémon de base **des deux camps** ; le remplacement l'annule."""
    registre = registre_stades(_META)
    al = joueur("alice", actif=pokemon("p-a", ref="poke-base"))
    bo = joueur("bob", actif=pokemon("p-b", ref="poke-base"))
    e = etat(al, bo, stade=carte("st-liesse", ref=STADE_EN_LIESSE), stade_proprietaire="alice")

    effets = collecter_effets_continus(e, registre)
    # Le seuil de K.O. monte de 30 pour les DEUX Pokémon : le Stade appartient à la partie (n°2).
    assert seuil_ko(60, effets, "p-a") == 90
    assert seuil_ko(60, effets, "p-b") == 90

    # alice remplace le Stade par Montagne Gravité (la transition défausse l'ancien chez elle).
    al2 = replace(e.joueurs[0], main=(carte("h-montagne", ref=MONTAGNE_GRAVITE),))
    e = replace(e, joueurs=(al2, e.joueurs[1]))
    e2, evts = appliquer_jouer_stade(
        e, _action_stade("alice", "h-montagne", "Montagne Gravité"), _RNG
    )

    assert e2.stade.ref == MONTAGNE_GRAVITE and e2.stade_proprietaire == "alice"
    assert any(c.ref == STADE_EN_LIESSE for c in e2.joueurs[0].defausse)  # ancien Stade en défausse
    assert evts[0].type == EVT_STADE_JOUE
    assert evts[0].donnees["remplace"] == "st-liesse"
    assert evts[0].donnees["proprietaire_remplace"] == "alice"

    # Le bonus de Liesse a disparu AU BON MOMENT, par simple disparition de l'état (critère n°1).
    effets2 = collecter_effets_continus(e2, registre)
    assert seuil_ko(60, effets2, "p-a") == 60
    assert seuil_ko(60, effets2, "p-b") == 60


# --- Critère n°3 : deuxième Stade réel — Montagne Gravité (−30 PV aux Niveau 2, deux camps) -----
def test_montagne_gravite_retire_30_pv_aux_pokemon_niveau2_des_deux_camps_r35():
    """R-3.5/R-13.1 — −30 PV à chaque Pokémon de Niveau 2 en jeu, des deux joueurs."""
    registre = registre_stades(_META)
    actif_a = pokemon("base-a", cartes=(carte("base-a", "poke-base"), carte("ev-a", "poke-stade2")))
    actif_b = pokemon("base-b", cartes=(carte("base-b", "poke-base"), carte("ev-b", "poke-stade2")))
    e = etat(
        joueur("alice", actif=actif_a),
        joueur("bob", actif=actif_b),
        stade=carte("st-mont", ref=MONTAGNE_GRAVITE),
        stade_proprietaire="bob",
    )
    effets = collecter_effets_continus(e, registre)
    # L'identité est la carte de base (``cartes[0]``), même si le sommet est une évolution.
    assert seuil_ko(150, effets, "base-a") == 120
    assert seuil_ko(150, effets, "base-b") == 120


# --- Critère n°3 + retraite : Hôtel « Au paradis des Pokémon » (coût de retraite −1, deux camps) -
def test_hotel_diminue_le_cout_de_retraite_des_psykokwak_des_deux_camps_r35():
    """R-3.5/R-8.2 — le coût de retraite de chaque Psykokwak en jeu baisse de 1 (plancher à 0)."""
    registre = {HOTEL_PARADIS: producteur_hotel_paradis(_META)}
    e = etat(
        joueur("alice", actif=pokemon("p-a", ref="psyduck")),
        joueur("bob", actif=pokemon("p-b", ref="psyduck")),
        stade=carte("st-hotel", ref=HOTEL_PARADIS),
        stade_proprietaire="alice",
    )
    effets = collecter_effets_continus(e, registre)
    assert delta_cout_retraite(effets, "p-a") == -1
    assert delta_cout_retraite(effets, "p-b") == -1  # les deux camps
    assert cout_retraite_effectif(2, effets, "p-a") == 1
    assert cout_retraite_effectif(2, effets, "p-b") == 1
    assert cout_retraite_effectif(0, effets, "p-a") == 0  # jamais sous 0


def test_hotel_rend_la_retraite_moins_chere_dans_les_coups_legaux_des_deux_camps_r82():
    """R-3.5/R-8.2 — dans les coups légaux, la retraite d'un Psykokwak coûte 1 au lieu de 2, pour
    les deux joueurs (le Stade est partagé)."""
    psy = DefinitionCarte(
        ref="psyduck", nom="Psykokwak", stade="base", pv=70, type="eau",
        marqueur="ordinaire", cout_retraite=2, attaques=(),
    )
    meta = {"psyduck": {"stade": "base", "nom": "Psykokwak"}}
    cat = CatalogueJeu(
        pokemon={"psyduck": psy},
        registre_continus={HOTEL_PARADIS: producteur_hotel_paradis(meta)},
    )
    familles = familles_jeu(cat)
    al = joueur(
        "alice",
        actif=pokemon("p-a", ref="psyduck", energies=(carte("e1"), carte("e2"))),
        banc=(pokemon("p-a2", ref="psyduck"),),
    )
    bo = joueur(
        "bob",
        actif=pokemon("p-b", ref="psyduck", energies=(carte("e3"), carte("e4"))),
        banc=(pokemon("p-b2", ref="psyduck"),),
    )
    e = etat(al, bo, stade=carte("st-hotel", ref=HOTEL_PARADIS), stade_proprietaire="alice")

    coups = _coups(e, "alice", ACTION_RETRAITE, familles)
    assert coups and coups[0].action.params["cout_retraite"] == 1  # 2 − 1 (Hôtel), R-8.2
    assert valider(e, coups[0].action, familles=familles).accepte  # une seule source : la liste

    # Même Stade partagé → même réduction au tour de bob (preuve « des deux camps »).
    e_bob = replace(e, tour=replace(e.tour, joueur_actif="bob"))
    coups_b = _coups(e_bob, "bob", ACTION_RETRAITE, familles)
    assert coups_b and coups_b[0].action.params["cout_retraite"] == 1

    # Sans Stade : le coût redevient le prix imprimé (2) — c'est bien le Stade qui l'abaisse.
    e_sans = replace(e, stade=None, stade_proprietaire=None)
    coups_sans = _coups(e_sans, "alice", ACTION_RETRAITE, familles)
    assert coups_sans and coups_sans[0].action.params["cout_retraite"] == 2


# --- Critère n°1 bis : règle de remplacement R-3.5, « même nom » refusé ------------------------
def test_stade_de_meme_nom_refuse_a_la_liste_et_par_valider_r35():
    """R-3.5 — on ne joue pas un Stade de même nom qu'un Stade déjà en jeu (même nom, autre ref)."""
    cat = CatalogueJeu(
        stades={
            "liesse-a": DefinitionStade(ref="liesse-a", nom="Stade en Liesse"),
            "liesse-b": DefinitionStade(ref="liesse-b", nom="Stade en Liesse"),  # autre impression
            "montagne": DefinitionStade(ref="montagne", nom="Montagne Gravité"),
        }
    )
    familles = familles_jeu(cat)
    al = joueur(
        "alice",
        actif=pokemon("p-a"),
        main=(carte("h-liesse-b", "liesse-b"), carte("h-montagne", "montagne")),
    )
    e = etat(al, joueur("bob", actif=pokemon("p-b")),
             stade=carte("st-a", ref="liesse-a"), stade_proprietaire="alice")

    coups = _coups(e, "alice", ACTION_JOUER_STADE, familles)
    mains = {c.action.params["carte_main"] for c in coups}
    assert "h-liesse-b" not in mains  # R-3.5 : même nom → pas listé
    assert "h-montagne" in mains  # un Stade de nom différent reste jouable
    for c in coups:  # une seule source de vérité : tout coup listé est accepté
        assert valider(e, c.action, familles=familles).accepte

    v = valider(e, _action_stade("alice", "h-liesse-b", "Stade en Liesse"), familles=familles)
    assert v.refuse and v.regle == "R-3.5"


def test_transition_refuse_de_rejouer_le_meme_stade_par_reference_r35():
    """R-3.5 (défense/rejeu) — la transition refuse un Stade de même **référence** que l'actuel."""
    al = joueur("alice", actif=pokemon("p-a"), main=(carte("h-liesse2", ref=STADE_EN_LIESSE),))
    e = etat(al, joueur("bob", actif=pokemon("p-b")),
             stade=carte("st-liesse", ref=STADE_EN_LIESSE), stade_proprietaire="alice")
    with pytest.raises(ValueError, match="R-3.5"):
        appliquer_jouer_stade(e, _action_stade("alice", "h-liesse2", "Stade en Liesse"), _RNG)


def test_un_seul_stade_par_tour_r55():
    """R-5.5 — un Stade déjà joué ce tour (drapeau levé) bloque un second Stade."""
    al = joueur("alice", actif=pokemon("p-a"), main=(carte("h-1", ref=STADE_EN_LIESSE),))
    e = etat(al, joueur("bob", actif=pokemon("p-b")))
    e = replace(e, tour=replace(e.tour, stade_joue=True))
    with pytest.raises(ValueError, match="R-5.5"):
        appliquer_jouer_stade(e, _action_stade("alice", "h-1", "Stade en Liesse"), _RNG)


def test_stade_appartient_a_la_partie_le_remplacement_defausse_chez_le_proprietaire_r35():
    """R-3.5 — l'ancien Stade retourne à la défausse de SON propriétaire, pas de qui le remplace."""
    al = joueur("alice", actif=pokemon("p-a"), main=(carte("h-new", ref=STADE_EN_LIESSE),))
    e = etat(al, joueur("bob", actif=pokemon("p-b")),
             stade=carte("st-bob", ref=MONTAGNE_GRAVITE), stade_proprietaire="bob")
    e2, evts = appliquer_jouer_stade(e, _action_stade("alice", "h-new", "Stade en Liesse"), _RNG)
    assert e2.stade.ref == STADE_EN_LIESSE and e2.stade_proprietaire == "alice"
    assert any(c.instance_id == "st-bob" for c in e2.joueurs[1].defausse)  # défausse de BOB
    assert all(c.instance_id != "st-bob" for c in e2.joueurs[0].defausse)
    assert evts[0].donnees["proprietaire_remplace"] == "bob"


def test_le_drapeau_stade_joue_survit_a_la_serialisation_r55():
    """R-5.5 — ``Tour.stade_joue`` est porté par l'état, donc repris après un F5 (JSON)."""
    e = etat(joueur("alice", actif=pokemon("p-a")), joueur("bob", actif=pokemon("p-b")))
    e = replace(e, tour=replace(e.tour, stade_joue=True))
    assert depuis_json(vers_json(e)).tour.stade_joue is True


def test_les_producteurs_de_stade_sont_purs():
    """Moteur pur : un producteur ne mute pas l'état et redonne le même résultat (rejouabilité)."""
    registre = registre_stades(_META)
    e = etat(
        joueur("alice", actif=pokemon("p-a", ref="poke-base")),
        joueur("bob", actif=pokemon("p-b", ref="poke-base")),
        stade=carte("st", ref=STADE_EN_LIESSE),
        stade_proprietaire="alice",
    )
    r1 = collecter_effets_continus(e, registre)
    r2 = collecter_effets_continus(e, registre)
    assert [(x.cible, x.pv) for x in r1] == [(x.cible, x.pv) for x in r2]
    assert e.joueurs[0].actif.cartes[0].instance_id == "p-a"  # état inchangé
