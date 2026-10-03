"""Familles de coups du jeu — lot ``j-coups-joueur``. La CI fait foi.

Chaque test nomme le ``R-x.y`` qu'il vérifie (principe du corpus) et prouve l'invariant central :
**une seule source de vérité, la liste** — tout coup listé par ``actions_legales`` (familles
du jeu) est accepté par ``valider``, un coup hors liste est refusé. La suite échoue sans le module
``pbm_game.actions.familles_jeu`` : c'est le « test qui échoue sans le changement et passe avec ».
"""

from __future__ import annotations

from fabrique_dsl import carte, etat, joueur, pokemon

from pbm_game.actions import actions_legales, valider
from pbm_game.actions.familles_jeu import CatalogueJeu, familles_jeu
from pbm_game.cartes import AttaqueDef, DefinitionCarte
from pbm_game.cartes.energie import DefinitionEnergie
from pbm_game.combat.modele import CoutAttaque, Faiblesse
from pbm_game.journal import Action, appliquer
from pbm_game.journal.modele import (
    ACTION_ATTACHER_ENERGIE,
    ACTION_AVANCER_PHASE,
    ACTION_DECLARER_ATTAQUE,
    ACTION_EVOLUER,
    ACTION_POSER,
    ACTION_PROMOUVOIR,
    ACTION_RETRAITE,
    EVT_DEGATS,
    EVT_ENERGIE_ATTACHEE,
    EVT_EVOLUTION,
    EVT_KO,
    EVT_POKEMON_POSE,
    EVT_PROMOTION,
    EVT_RETRAITE,
)
from pbm_game.rng import Rng
from pbm_game.state import PHASE_CHECKUP, assert_invariants

_RNG = Rng(b"coups-joueur-seed")

# --- Catalogue de test (deux Pokémon et une énergie de base) ---------------------------------
PIKA = DefinitionCarte(
    ref="pika", nom="Pikachu", stade="base", pv=60, type="electrique", marqueur="ordinaire",
    cout_retraite=1,
    attaques=(AttaqueDef("Éclair", CoutAttaque(types={"electrique": 1}), 30),),
)
RAICHU = DefinitionCarte(
    ref="raichu", nom="Raichu", stade="stade1", pv=90, type="electrique", marqueur="ordinaire",
    evolue_depuis="Pikachu", cout_retraite=1,
    attaques=(AttaqueDef("Tonnerre", CoutAttaque(incolore=2), 60),),
)
CARA = DefinitionCarte(
    ref="cara", nom="Carapuce", stade="base", pv=50, type="eau", marqueur="ordinaire",
    cout_retraite=1, faiblesse=Faiblesse("electrique", 2), attaques=(),
)
ENERGIE = DefinitionEnergie(ref="e-elec", nom="Énergie Électrique", fournit={"electrique": 1})

CAT = CatalogueJeu(
    pokemon={d.ref: d for d in (PIKA, RAICHU, CARA)},
    energies={ENERGIE.ref: ENERGIE},
)
FAMILLES = familles_jeu(CAT)


def _legaux(etat_, jid):
    return actions_legales(etat_, jid, familles=FAMILLES)


def _un(etat_, jid, type_):
    coups = [c for c in _legaux(etat_, jid) if c.action.type == type_]
    assert coups, f"aucun coup « {type_} » listé pour {jid}"
    return coups[0]


def _coherence(etat_, jid):
    """Tout coup listé est accepté par valider ; un hors-liste est refusé (une seule vérité)."""
    for coup in _legaux(etat_, jid):
        v = valider(etat_, coup.action, familles=FAMILLES)
        assert v.accepte, f"coup listé refusé : {coup.action}"
    hors = valider(etat_, Action("coup_imaginaire", jid), familles=FAMILLES)
    assert hors.refuse and hors.regle


# --- Poser (R-5.3) ---------------------------------------------------------------------------
def test_poser_un_pokemon_de_base_liste_et_applique_r53():
    al = joueur("alice", actif=pokemon("a-pika", ref="pika"), main=(carte("h-cara", "cara"),))
    bo = joueur("bob", actif=pokemon("b-cara", ref="cara"))
    e = etat(al, bo, numero=3, phase="principale")
    coup = _un(e, "alice", ACTION_POSER)
    assert valider(e, coup.action, familles=FAMILLES).accepte
    e2, evts = appliquer(e, coup.action, _RNG)
    assert_invariants(e2)
    assert len(e2.joueurs[0].banc) == 1
    assert any(ev.type == EVT_POKEMON_POSE for ev in evts)
    _coherence(e, "alice")


def test_poser_non_liste_sans_actif_promotion_dabord_r87():
    # Actif absent : on ne pose pas, on doit d'abord promouvoir (R-8.7).
    al = joueur(
        "alice", actif=None, banc=(pokemon("a-cara", ref="cara"),), main=(carte("h-cara", "cara"),)
    )
    bo = joueur("bob", actif=pokemon("b-cara", ref="cara"))
    e = etat(al, bo, numero=3, phase="principale")
    types = {c.action.type for c in _legaux(e, "alice")}
    assert ACTION_POSER not in types
    assert ACTION_AVANCER_PHASE not in types  # passer interdit tant qu'on doit promouvoir
    assert ACTION_PROMOUVOIR in types


# --- Attacher une énergie (R-5.4) ------------------------------------------------------------
def test_attacher_energie_liste_applique_et_une_seule_fois_r54():
    al = joueur("alice", actif=pokemon("a-pika", ref="pika"), main=(carte("h-en", "e-elec"),))
    bo = joueur("bob", actif=pokemon("b-cara", ref="cara"))
    e = etat(al, bo, numero=3, phase="principale")
    coup = _un(e, "alice", ACTION_ATTACHER_ENERGIE)
    assert coup.cibles and coup.cibles[0].reference == "a-pika"
    e2, evts = appliquer(e, coup.action, _RNG)
    assert_invariants(e2)
    assert len(e2.joueurs[0].actif.energies) == 1
    assert e2.tour.energie_posee is True
    assert any(ev.type == EVT_ENERGIE_ATTACHEE for ev in evts)
    # R-5.4 — une seule énergie par tour : plus aucune attache listée après.
    assert not [c for c in _legaux(e2, "alice") if c.action.type == ACTION_ATTACHER_ENERGIE]
    _coherence(e, "alice")


# --- Attaquer (R-9/R-10/R-13) ----------------------------------------------------------------
def test_attaquer_inflige_des_degats_avec_faiblesse_r102_et_termine_le_tour_r58():
    actif = pokemon("a-pika", ref="pika", energies=(carte("en-1", "e-elec"),))
    al = joueur("alice", actif=actif, recompenses=(carte("r1"), carte("r2"), carte("r3"),
                                                   carte("r4"), carte("r5"), carte("r6")))
    bo = joueur("bob", actif=pokemon("b-cara", ref="cara"), banc=(pokemon("b-cara2", ref="cara"),))
    e = etat(al, bo, numero=3, phase="principale")
    coup = _un(e, "alice", ACTION_DECLARER_ATTAQUE)
    e2, evts = appliquer(e, coup.action, _RNG)
    # Éclair 30 × 2 (faiblesse électrique de Carapuce, R-10.2) = 60 ≥ 50 PV → K.O.
    degats = next(ev for ev in evts if ev.type == EVT_DEGATS)
    assert degats.donnees["degats"] == 60
    assert any(ev.type == EVT_KO for ev in evts)
    assert len(e2.joueurs[0].recompenses) == 5  # alice a pris 1 récompense (R-13.3)
    assert e2.tour.phase == PHASE_CHECKUP  # R-5.8 — l'attaque termine le tour
    assert e2.joueurs[1].actif is None  # bob doit promouvoir (R-8.7) — état transitoire
    # Le défenseur promeut (R-8.7), ce qui résout l'état transitoire : l'invariant R-3.3 est tenu.
    promo = _un(e2, "bob", ACTION_PROMOUVOIR)
    e3, _ = appliquer(e2, promo.action, _RNG)
    assert_invariants(e3)
    assert e3.joueurs[1].actif is not None
    _coherence(e, "alice")


def test_attaquer_interdit_au_premier_tour_du_joueur_qui_commence_r61():
    actif = pokemon("a-pika", ref="pika", energies=(carte("en-1", "e-elec"),))
    al = joueur("alice", actif=actif)
    bo = joueur("bob", actif=pokemon("b-cara", ref="cara"))
    e = etat(al, bo, numero=1, phase="principale")  # tour 1 = joueur qui commence
    assert not [c for c in _legaux(e, "alice") if c.action.type == ACTION_DECLARER_ATTAQUE]
    v = valider(
        e, Action(ACTION_DECLARER_ATTAQUE, "alice", {"attaque": {"nom": "x"}}), familles=FAMILLES
    )
    assert v.refuse and v.regle == "R-6.1"


# --- Retraite (R-8.2) ------------------------------------------------------------------------
def test_retraite_liste_applique_paye_le_cout_r82():
    actif = pokemon("a-pika", ref="pika", energies=(carte("en-1", "e-elec"),))
    al = joueur("alice", actif=actif, banc=(pokemon("a-cara", ref="cara"),))
    bo = joueur("bob", actif=pokemon("b-cara", ref="cara"))
    e = etat(al, bo, numero=3, phase="principale")
    coup = _un(e, "alice", ACTION_RETRAITE)
    e2, evts = appliquer(e, coup.action, _RNG)
    assert_invariants(e2)
    assert e2.joueurs[0].actif.cartes[0].instance_id == "a-cara"  # Carapuce est montée
    assert e2.tour.retraite_faite is True
    assert any(ev.type == EVT_RETRAITE for ev in evts)
    _coherence(e, "alice")


# --- Promotion (R-8.7) -----------------------------------------------------------------------
def test_promouvoir_apres_ko_liste_et_applique_r87():
    al = joueur("alice", actif=None, banc=(pokemon("a-cara", ref="cara"),))
    bo = joueur("bob", actif=pokemon("b-cara", ref="cara"))
    e = etat(al, bo, numero=3, phase="principale")
    coup = _un(e, "alice", ACTION_PROMOUVOIR)
    e2, evts = appliquer(e, coup.action, _RNG)
    assert_invariants(e2)
    assert e2.joueurs[0].actif is not None and not e2.joueurs[0].banc
    assert any(ev.type == EVT_PROMOTION for ev in evts)
    _coherence(e, "alice")


# --- Évoluer (R-7.1) -------------------------------------------------------------------------
def test_evoluer_respecte_la_chaine_r71():
    al = joueur("alice", actif=pokemon("a-pika", ref="pika"), main=(carte("h-rai", "raichu"),))
    bo = joueur("bob", actif=pokemon("b-cara", ref="cara"))
    e = etat(al, bo, numero=3, phase="principale")  # pas le premier tour (R-6.5)
    coup = _un(e, "alice", ACTION_EVOLUER)
    assert coup.action.params["nom_base"] == "Pikachu"
    e2, evts = appliquer(e, coup.action, _RNG)
    assert_invariants(e2)
    assert e2.joueurs[0].actif.cartes[-1].ref == "raichu"
    assert any(ev.type == EVT_EVOLUTION for ev in evts)
    _coherence(e, "alice")


def test_evoluer_mauvaise_chaine_non_listee_r71():
    # Raichu n'évolue pas de Carapuce : aucune évolution listée.
    al = joueur("alice", actif=pokemon("a-cara", ref="cara"), main=(carte("h-rai", "raichu"),))
    bo = joueur("bob", actif=pokemon("b-cara", ref="cara"))
    e = etat(al, bo, numero=3, phase="principale")
    assert not [c for c in _legaux(e, "alice") if c.action.type == ACTION_EVOLUER]
