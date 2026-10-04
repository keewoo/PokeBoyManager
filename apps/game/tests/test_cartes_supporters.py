"""Cartes **Supporter** scriptées dans le langage d'effets — lot ``j-cartes-supporters`` (jalon J2).

On y scripte, et on teste contre des cartes réelles, les familles de Supporters : **pioche pure**,
**recherche**, **perturbation** de l'adversaire (mélanger sa main dans son deck et la faire
repiocher, la faire défausser) et effets **conditionnés** (« si vous avez moins de récompenses »).
Chaque famille a **au moins trois** cartes réelles, toutes exprimées dans le vocabulaire fermé du
DSL (D9) — aucune en code spécifique.

Ce qui distingue un Supporter d'un Objet, et que ce lot ajoute : la **règle du tour** (un seul par
tour R-5.5 ; aucun au premier tour du joueur qui commence R-6.2), le **verrou** ``pas_de_supporter``
(R-5.5, le refus nomme la carte), et le fait que le drapeau ``Tour.supporter_joue`` **survit à une
reprise après un F5**. Les tests ci-dessous **mordent sans** le câblage du lot : avant lui, il
n'existe ni ``ACTION_JOUER_SUPPORTER``, ni ``FamilleJouerSupporter``, ni la sémantique
« mélanger sa main dans son deck », ni la condition ``moins_de_recompenses``, ni la pioche de
l'adversaire.

Règles citées (corpus ``docs/jeu/REGLES.md``) : R-5.5 (un Supporter par tour), R-6.2 (aucun au 1er
tour du joueur qui commence), R-13.3 (décompte des récompenses). La CI fait foi.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from fabrique_dsl import carte, contexte, etat, joueur, pokemon, rng

from pbm_game.actions.familles_jeu import (
    CatalogueJeu,
    DefinitionSupporter,
    familles_jeu,
)
from pbm_game.actions.generateur import actions_legales, valider
from pbm_game.effets.dsl.chargement import charger_programme
from pbm_game.effets.dsl.interprete import EVT_DSL_PRIMITIVE, executer_programme
from pbm_game.effets.pile import SourceEffet
from pbm_game.effets.verrous import (
    PORTEE_CE_TOUR,
    VERROU_PAS_DE_SUPPORTER,
    JeuDeVerrous,
    Verrou,
)
from pbm_game.journal.modele import ACTION_JOUER_SUPPORTER, EVT_SUPPORTER_JOUE, Action
from pbm_game.journal.transitions import appliquer
from pbm_game.state.serialisation import depuis_json, vers_json

# ================================================================================================
# Les scripts de cartes réelles, par famille (version 1 du langage).
# ================================================================================================

# --- Pioche pure : refaire sa main. -------------------------------------------------------------
PROFESSORS_RESEARCH = {
    "version": 1,
    "effets": [
        {"op": "defausser", "cible": {"zone": "main", "proprietaire": "moi"}},
        {"op": "piocher", "nombre": 7},
    ],
}
CYNTHIA = {
    "version": 1,
    "effets": [
        {"op": "melanger", "cible": {"zone": "main", "proprietaire": "moi"}},
        {"op": "piocher", "nombre": 6},
    ],
}
HOP = {"version": 1, "effets": [{"op": "piocher", "nombre": 3}]}

# --- Recherche : aller chercher une carte dans une zone. ----------------------------------------
POKEMON_FAN_CLUB = {
    "version": 1,
    "effets": [
        {
            "op": "chercher",
            "cible": {"zone": "pioche", "categorie": "pokemon", "stade": "base", "nombre": 2},
        },
        {"op": "melanger", "cible": {"zone": "pioche", "proprietaire": "moi"}},
    ],
}
POKEMON_COLLECTOR = {
    "version": 1,
    "effets": [
        {
            "op": "chercher",
            "cible": {"zone": "pioche", "categorie": "pokemon", "stade": "base", "nombre": 3},
        },
        {"op": "melanger", "cible": {"zone": "pioche", "proprietaire": "moi"}},
    ],
}
FISHERMAN = {
    "version": 1,
    "effets": [
        {"op": "chercher", "cible": {"zone": "defausse", "categorie": "energie", "nombre": 3}},
    ],
}

# --- Perturbation : agir sur les ressources de l'adversaire. ------------------------------------
# « Chaque joueur mélange sa main dans son deck, puis pioche 4 cartes. » (type Judge)
JUDGE = {
    "version": 1,
    "effets": [
        {"op": "melanger", "cible": {"zone": "main", "proprietaire": "adversaire"}},
        {"op": "piocher", "nombre": 4, "cible": {"zone": "pioche", "proprietaire": "adversaire"}},
        {"op": "melanger", "cible": {"zone": "main", "proprietaire": "moi"}},
        {"op": "piocher", "nombre": 4},
    ],
}
# « Chaque joueur mélange sa main dans son deck, puis pioche autant de cartes que de récompenses
#   restantes. » (type N) — la pioche « par récompense » est un ``repeter`` sur la réserve.
N = {
    "version": 1,
    "effets": [
        {"op": "melanger", "cible": {"zone": "main", "proprietaire": "adversaire"}},
        {
            "op": "repeter",
            "source": {"zone": "recompenses", "proprietaire": "adversaire"},
            "alors": [
                {
                    "op": "piocher",
                    "nombre": 1,
                    "cible": {"zone": "pioche", "proprietaire": "adversaire"},
                }
            ],
        },
        {"op": "melanger", "cible": {"zone": "main", "proprietaire": "moi"}},
        {
            "op": "repeter",
            "source": {"zone": "recompenses", "proprietaire": "moi"},
            "alors": [{"op": "piocher", "nombre": 1}],
        },
    ],
}
# « Pile ou face 2 fois ; pour chaque face, défaussez la carte du dessus du deck adverse. » (mill)
TEAM_ROCKET_HANDIWORK = {
    "version": 1,
    "effets": [
        {
            "op": "pile_ou_face",
            "nombre": 2,
            "alors": [
                {
                    "op": "defausser",
                    "cible": {
                        "zone": "pioche",
                        "proprietaire": "adversaire",
                        "position": "dessus",
                        "nombre": 1,
                    },
                }
            ],
        }
    ],
}

# --- Conditionnels : le « si » décide ce que la carte fait. -------------------------------------
# « Si vous avez moins de récompenses que l'adversaire (vous menez), piochez 6 ; sinon piochez 2. »
ROXANNE = {
    "version": 1,
    "effets": [
        {
            "op": "si",
            "condition": {"type": "moins_de_recompenses"},
            "alors": [{"op": "piocher", "nombre": 6}],
            "sinon": [{"op": "piocher", "nombre": 2}],
        }
    ],
}
# « Mélangez votre main dans votre deck. Pile → piochez 8 ; face/pile → piochez 1. » (type Gambler)
GAMBLER = {
    "version": 1,
    "effets": [
        {"op": "melanger", "cible": {"zone": "main", "proprietaire": "moi"}},
        {
            "op": "pile_ou_face",
            "alors": [{"op": "piocher", "nombre": 8}],
            "sinon": [{"op": "piocher", "nombre": 1}],
        },
    ],
}
# « Si votre adversaire a des cartes en main, piochez 3 ; sinon piochez 1. »
LOOKER = {
    "version": 1,
    "effets": [
        {
            "op": "si",
            "condition": {
                "type": "zone_non_vide",
                "cible": {"zone": "main", "proprietaire": "adversaire"},
            },
            "alors": [{"op": "piocher", "nombre": 3}],
            "sinon": [{"op": "piocher", "nombre": 1}],
        }
    ],
}

FAMILLES_SUPPORTERS = {
    "pioche": [PROFESSORS_RESEARCH, CYNTHIA, HOP],
    "recherche": [POKEMON_FAN_CLUB, POKEMON_COLLECTOR, FISHERMAN],
    "perturbation": [JUDGE, N, TEAM_ROCKET_HANDIWORK],
    "conditionnels": [ROXANNE, GAMBLER, LOOKER],
}


# ================================================================================================
# Helpers.
# ================================================================================================
def _j(e, jid):
    return next(j for j in e.joueurs if j.id == jid)


def _ids(cartes):
    return {c.instance_id for c in cartes}


def _refs(cartes):
    return {c.ref for c in cartes}


# ================================================================================================
# Chaque famille se charge sans code spécifique (≥ 3 cartes réelles, aucune en code).
# ================================================================================================
def test_chaque_famille_a_trois_cartes_chargeables():
    for famille, scripts in FAMILLES_SUPPORTERS.items():
        assert len(scripts) >= 3, famille
        for script in scripts:
            prog = charger_programme(script)  # lève ProgrammeInvalide si non conforme
            assert prog.version == 1


# ================================================================================================
# Pioche pure.
# ================================================================================================
def test_professors_research_defausse_la_main_puis_pioche_sept():
    alice = joueur(
        "alice",
        actif=pokemon("a"),
        main=(carte("m1"), carte("m2")),
        pioche=tuple(carte(f"p{i}") for i in range(8)),
    )
    e = etat(alice, joueur("bob", actif=pokemon("b")))
    res = executer_programme(e, charger_programme(PROFESSORS_RESEARCH), contexte(), rng())
    j = _j(res.etat, "alice")
    assert len(j.main) == 7  # la vieille main défaussée, 7 cartes neuves
    assert {"m1", "m2"} <= _ids(j.defausse)


def test_cynthia_remet_la_main_dans_le_deck_puis_pioche_six():
    alice = joueur(
        "alice",
        actif=pokemon("a"),
        main=(carte("m1"), carte("m2")),
        pioche=tuple(carte(f"p{i}") for i in range(10)),
    )
    e = etat(alice, joueur("bob", actif=pokemon("b")))
    res = executer_programme(e, charger_programme(CYNTHIA), contexte(), rng())
    j = _j(res.etat, "alice")
    assert len(j.main) == 6
    # La main est RETOURNÉE au deck (pas défaussée) : rien n'a été perdu.
    assert j.defausse == ()
    assert len(j.pioche) == 12 - 6  # 10 + 2 remises − 6 piochées


def test_hop_pioche_trois():
    alice = joueur("alice", actif=pokemon("a"), pioche=(carte("p1"), carte("p2"), carte("p3")))
    e = etat(alice, joueur("bob", actif=pokemon("b")))
    res = executer_programme(e, charger_programme(HOP), contexte(), rng())
    assert len(_j(res.etat, "alice").main) == 3


# ================================================================================================
# Recherche.
# ================================================================================================
def test_pokemon_fan_club_cherche_deux_bases():
    alice = joueur(
        "alice",
        actif=pokemon("a"),
        pioche=(carte("p-b1", "ref-base"), carte("p-b2", "ref-base"), carte("p-evo", "ref-evo")),
    )
    e = etat(alice, joueur("bob", actif=pokemon("b")))
    meta = {
        "ref-base": {"categorie": "pokemon", "stade": "base"},
        "ref-evo": {"categorie": "pokemon", "stade": "stade1"},
    }
    res = executer_programme(
        e, charger_programme(POKEMON_FAN_CLUB), contexte(metadonnees=meta), rng()
    )
    main = _ids(_j(res.etat, "alice").main)
    assert {"p-b1", "p-b2"} == main  # deux bases trouvées, l'évolution ignorée


def test_fisherman_recupere_des_energies_de_la_defausse():
    alice = joueur(
        "alice",
        actif=pokemon("a"),
        defausse=(carte("e1", "ref-e"), carte("e2", "ref-e"), carte("x", "ref-poke")),
    )
    e = etat(alice, joueur("bob", actif=pokemon("b")))
    meta = {"ref-e": {"categorie": "energie"}, "ref-poke": {"categorie": "pokemon"}}
    res = executer_programme(e, charger_programme(FISHERMAN), contexte(metadonnees=meta), rng())
    main = _ids(_j(res.etat, "alice").main)
    assert {"e1", "e2"} == main  # les énergies récupérées, pas le Pokémon


# ================================================================================================
# Perturbation.
# ================================================================================================
def test_judge_rebat_les_deux_mains_et_fait_repiocher_quatre():
    alice = joueur(
        "alice",
        actif=pokemon("a"),
        main=(carte("am1"),),
        pioche=tuple(carte(f"ap{i}") for i in range(6)),
    )
    bob = joueur(
        "bob",
        actif=pokemon("b"),
        main=(carte("bm1"), carte("bm2"), carte("bm3")),
        pioche=tuple(carte(f"bp{i}") for i in range(6)),
    )
    e = etat(alice, bob)
    res = executer_programme(e, charger_programme(JUDGE), contexte("alice", "bob"), rng())
    assert len(_j(res.etat, "alice").main) == 4
    assert len(_j(res.etat, "bob").main) == 4  # bob a rebattu sa main de 3 et repioché 4


def test_n_pioche_une_carte_par_recompense_restante():
    alice = joueur(
        "alice",
        actif=pokemon("a"),
        main=(carte("am1"),),
        pioche=tuple(carte(f"ap{i}") for i in range(6)),
        recompenses=(carte("ar1"), carte("ar2")),  # 2 récompenses restantes
    )
    bob = joueur(
        "bob",
        actif=pokemon("b"),
        main=(carte("bm1"), carte("bm2")),
        pioche=tuple(carte(f"bp{i}") for i in range(6)),
        recompenses=(carte("br1"), carte("br2"), carte("br3"), carte("br4"), carte("br5")),  # 5
    )
    e = etat(alice, bob)
    res = executer_programme(e, charger_programme(N), contexte("alice", "bob"), rng())
    assert len(_j(res.etat, "alice").main) == 2  # 2 récompenses → 2 cartes
    assert len(_j(res.etat, "bob").main) == 5  # 5 récompenses → 5 cartes


def test_team_rocket_handiwork_defausse_le_dessus_du_deck_adverse():
    alice = joueur("alice", actif=pokemon("a"))
    bob = joueur("bob", actif=pokemon("b"), pioche=tuple(carte(f"bp{i}") for i in range(5)))
    e = etat(alice, bob)
    res = executer_programme(
        e, charger_programme(TEAM_ROCKET_HANDIWORK), contexte("alice", "bob"), rng()
    )
    bob_apres = _j(res.etat, "bob")
    # Le Rng de test est déterministe : entre 0 et 2 cartes défaussées selon les faces. On vérifie
    # l'invariant (conservation) plutôt qu'un nombre fragile : rien ne sort du deck sans aller à la
    # défausse, et la défausse de bob ne contient que des cartes de SON deck.
    assert len(bob_apres.pioche) + len(bob_apres.defausse) == 5
    assert _ids(bob_apres.defausse) <= {f"bp{i}" for i in range(5)}


# ================================================================================================
# Conditionnels.
# ================================================================================================
def test_roxanne_pioche_six_si_on_mene_aux_recompenses():
    # alice a MOINS de récompenses restantes que bob → elle mène → pioche 6.
    alice = joueur(
        "alice",
        actif=pokemon("a"),
        pioche=tuple(carte(f"p{i}") for i in range(6)),
        recompenses=(carte("ar1"), carte("ar2")),
    )
    bob = joueur(
        "bob",
        actif=pokemon("b"),
        recompenses=(carte("br1"), carte("br2"), carte("br3"), carte("br4")),
    )
    res = executer_programme(
        etat(alice, bob), charger_programme(ROXANNE), contexte("alice", "bob"), rng()
    )
    assert len(_j(res.etat, "alice").main) == 6


def test_roxanne_pioche_deux_sinon():
    # alice a AUTANT (ou plus) de récompenses que bob → elle ne mène pas → pioche 2.
    alice = joueur(
        "alice",
        actif=pokemon("a"),
        pioche=tuple(carte(f"p{i}") for i in range(6)),
        recompenses=(carte("ar1"), carte("ar2")),
    )
    bob = joueur("bob", actif=pokemon("b"), recompenses=(carte("br1"), carte("br2")))
    res = executer_programme(
        etat(alice, bob), charger_programme(ROXANNE), contexte("alice", "bob"), rng()
    )
    assert len(_j(res.etat, "alice").main) == 2


def test_looker_depend_de_la_main_adverse():
    alice = joueur("alice", actif=pokemon("a"), pioche=tuple(carte(f"p{i}") for i in range(3)))
    bob = joueur("bob", actif=pokemon("b"), main=(carte("bm1"),))
    res = executer_programme(
        etat(alice, bob), charger_programme(LOOKER), contexte("alice", "bob"), rng()
    )
    assert len(_j(res.etat, "alice").main) == 3  # bob a une main → pioche 3


# ================================================================================================
# Confidentialité : un effet qui touche la main adverse ne révèle jamais son contenu (non-fuite).
# ================================================================================================
def test_perturbation_ne_revele_pas_la_main_adverse():
    """Judge rebat la main de bob : alice apprend le NOMBRE, jamais les refs/instance_id (R-5.5).

    C'est le test de non-fuite du lot : aucun événement produit par la perturbation ne doit porter
    une carte cachée de l'adversaire (sa main, sa pioche). Les cartes de bob ont des ``ref``
    reconnaissables (``secret-*``) : on vérifie qu'aucune n'apparaît dans la trace.
    """
    alice = joueur(
        "alice",
        actif=pokemon("a"),
        main=(carte("am1"),),
        pioche=tuple(carte(f"ap{i}") for i in range(6)),
    )
    bob = joueur(
        "bob",
        actif=pokemon("b"),
        main=(carte("bsecret1", "secret-main-1"), carte("bsecret2", "secret-main-2")),
        pioche=tuple(carte(f"bsecretp{i}", f"secret-pioche-{i}") for i in range(6)),
    )
    res = executer_programme(
        etat(alice, bob), charger_programme(JUDGE), contexte("alice", "bob"), rng()
    )
    for ev in res.evenements:
        trace = repr(ev.donnees)
        assert "secret-main" not in trace, f"fuite de la main adverse : {ev.type} {ev.donnees}"
        assert "secret-pioche" not in trace, f"fuite de la pioche adverse : {ev.type} {ev.donnees}"
        # Les primitives qui touchent l'adversaire ne listent que des nombres/zones, pas d'identité.
        if ev.type == EVT_DSL_PRIMITIVE:
            assert "instance_ids" not in ev.donnees
            assert "refs" not in ev.donnees or ev.donnees.get("op") == "chercher"


# ================================================================================================
# Famille Supporter + transition : le vrai chemin du moteur, et la règle du tour.
# ================================================================================================
def _cat(nom="Hop", script=None, ref="ref-hop"):
    supp = DefinitionSupporter(ref, nom, charger_programme(script or HOP))
    return CatalogueJeu(supporters={ref: supp})


def _etat_main_supporter(*, numero=3, main_extra=(), pioche_n=5):
    """alice (joueur actif) tient un Supporter (Hop) ; tour numéro ``numero`` (≥ 2 par défaut)."""
    alice = joueur(
        "alice",
        actif=pokemon("a"),
        main=(carte("h1", "ref-hop"), *main_extra),
        pioche=tuple(carte(f"p{i}") for i in range(pioche_n)),
    )
    bob = joueur("bob", actif=pokemon("b"))
    return etat(alice, bob, numero=numero)


def test_supporter_jouable_liste_quand_la_regle_du_tour_le_permet():
    cat = _cat()
    coups = actions_legales(_etat_main_supporter(), "alice", familles_jeu(cat))
    supporters = [c for c in coups if c.action.type == ACTION_JOUER_SUPPORTER]
    assert len(supporters) == 1
    assert "Hop" in supporters[0].etiquette


def test_transition_jouer_supporter_bout_en_bout_et_leve_le_drapeau():
    cat = _cat()
    e = _etat_main_supporter()
    coup = next(
        c
        for c in actions_legales(e, "alice", familles_jeu(cat))
        if c.action.type == ACTION_JOUER_SUPPORTER
    )
    etat2, evts = appliquer(e, coup.action, rng())
    alice = _j(etat2, "alice")
    assert "h1" in _ids(alice.defausse)  # le Supporter est défaussé après usage (R-5.5)
    assert "h1" not in _ids(alice.main)
    assert len(alice.main) == 3  # Hop a pioché 3
    assert etat2.tour.supporter_joue is True  # R-5.5 : le drapeau est levé
    assert any(ev.type == EVT_SUPPORTER_JOUE for ev in evts)


def test_second_supporter_refuse_le_meme_tour():
    """R-5.5 : un seul Supporter par tour — le deuxième n'est pas listé, et le refus le dit."""
    cat = _cat()
    e = _etat_main_supporter(main_extra=(carte("h2", "ref-hop"),))
    coup = next(
        c
        for c in actions_legales(e, "alice", familles_jeu(cat))
        if c.action.type == ACTION_JOUER_SUPPORTER
    )
    etat2, _ = appliquer(e, coup.action, rng())
    # Plus aucun Supporter listé, bien qu'un second (h2) soit en main.
    coups = actions_legales(etat2, "alice", familles_jeu(cat))
    assert not [c for c in coups if c.action.type == ACTION_JOUER_SUPPORTER]
    # Et la transition le refuse en nommant R-5.5 (le serveur fait autorité).
    seconde = Action(ACTION_JOUER_SUPPORTER, "alice", dict(coup.action.params, carte_main="h2"))
    with pytest.raises(ValueError, match="R-5.5"):
        appliquer(etat2, seconde, rng())


def test_supporter_refuse_au_premier_tour_du_joueur_qui_commence():
    """R-6.2 : le joueur qui commence (tour 1) ne peut pas jouer de Supporter."""
    cat = _cat()
    e = _etat_main_supporter(numero=1)  # tour 1 = premier tour du joueur qui commence
    coups = actions_legales(e, "alice", familles_jeu(cat))
    assert not [c for c in coups if c.action.type == ACTION_JOUER_SUPPORTER]
    verdict = valider(e, Action(ACTION_JOUER_SUPPORTER, "alice", {}), familles_jeu(cat))
    assert not verdict.accepte
    assert verdict.regle == "R-6.2"
    with pytest.raises(ValueError, match="R-6.2"):
        coup_force = Action(
            ACTION_JOUER_SUPPORTER,
            "alice",
            {"carte_main": "h1", "programme": charger_programme(HOP).en_json(), "nom": "Hop"},
        )
        appliquer(e, coup_force, rng())


def test_supporter_refuse_sous_verrou_en_nommant_la_carte():
    """R-5.5 : un verrou ``pas_de_supporter`` bloque, et le refus nomme la carte responsable."""
    cat = _cat()
    e = _etat_main_supporter()
    verrou = Verrou(
        nom=VERROU_PAS_DE_SUPPORTER,
        portee=PORTEE_CE_TOUR,
        source=SourceEffet("Marnie's Trick", ref="ref-marnie", instance_id="v1"),
        regle="R-5.5",
        cible="alice",
        pose_au_tour=e.tour.numero,
    )
    e = replace(e, verrous=JeuDeVerrous((verrou,)))
    # Non listé…
    coups = actions_legales(e, "alice", familles_jeu(cat))
    assert not [c for c in coups if c.action.type == ACTION_JOUER_SUPPORTER]
    # …et le refus cite la carte responsable.
    verdict = valider(e, Action(ACTION_JOUER_SUPPORTER, "alice", {}), familles_jeu(cat))
    assert not verdict.accepte
    assert "Marnie's Trick" in verdict.message
    # La transition aussi refuse (serveur) en nommant la carte.
    coup = Action(
        ACTION_JOUER_SUPPORTER,
        "alice",
        {"carte_main": "h1", "programme": charger_programme(HOP).en_json(), "nom": "Hop"},
    )
    with pytest.raises(ValueError, match="Marnie's Trick"):
        appliquer(e, coup, rng())


def test_drapeau_supporter_survit_a_une_reprise_apres_f5():
    """Le drapeau ``supporter_joue`` est porté par l'état, donc sérialisé : il survit à un F5.

    On joue un Supporter, on sérialise l'état (ce qu'un F5 recharge), on le relit, et on vérifie que
    le drapeau tient — donc qu'un second Supporter reste refusé après la reprise.
    """
    cat = _cat()
    e = _etat_main_supporter(main_extra=(carte("h2", "ref-hop"),))
    coup = next(
        c
        for c in actions_legales(e, "alice", familles_jeu(cat))
        if c.action.type == ACTION_JOUER_SUPPORTER
    )
    etat2, _ = appliquer(e, coup.action, rng())
    assert etat2.tour.supporter_joue is True

    repris = depuis_json(vers_json(etat2))  # aller-retour = ce qu'un F5 recharge
    assert repris.tour.supporter_joue is True
    coups = actions_legales(repris, "alice", familles_jeu(cat))
    assert not [c for c in coups if c.action.type == ACTION_JOUER_SUPPORTER]
