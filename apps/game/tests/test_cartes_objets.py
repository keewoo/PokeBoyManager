"""Cartes **Objet** scriptées dans le langage d'effets — lot ``j-cartes-objets`` (jalon J2).

On y scripte, et on y teste contre des **cartes réelles**, les familles d'Objets : recherche dans
la pioche, pioche, soin, changement d'Actif de son côté, et l'**appât** (sortir du banc l'Actif
adverse — type *Gust of Wind* / *Pokémon Catcher*). Chaque famille couverte a **au moins trois**
cartes réelles (critère d'acceptation). Aucune ne demande de code spécifique : elles s'expriment
toutes dans le vocabulaire fermé du DSL (D9).

**Le test qui mord sans le changement** : avant ce lot, ``changer_actif`` ne nettoyait pas l'Actif
qui descend (R-8.6) et ne notait aucun passage pour le bus ; il n'existait ni ``FamilleJouerObjet``
ni transition ``jouer_objet``. ``test_appat_nettoie_le_descendant`` et toute la suite échouent donc
sans le câblage de ce lot.

Règles citées (corpus ``docs/jeu/REGLES.md``) : R-5.5 (Objets illimités), R-8.6 (passage au banc),
R-8.8 (échange forcé, sans coût ni retraite), R-16.12 (échange forcé autorisé sous Sommeil/
Paralysie). La CI fait foi.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from fabrique_dsl import carte, contexte, etat, joueur, pokemon, rng

from pbm_game.actions.familles_jeu import CatalogueJeu, DefinitionObjet, familles_jeu
from pbm_game.actions.generateur import actions_legales, valider
from pbm_game.demandes.modele import CAT_CARTE, DemandeDecision
from pbm_game.demandes.moteur import ResolutionEnCours
from pbm_game.effets.dsl.chargement import charger_programme
from pbm_game.effets.dsl.interprete import executer_programme
from pbm_game.effets.dsl.jouabilite import programme_jouable
from pbm_game.effets.pile import EVT_EFFET_SANS_CIBLE, EffetEnAttente, PileEffets, SourceEffet
from pbm_game.journal.modele import ACTION_JOUER_OBJET, EVT_OBJET_JOUE, Action
from pbm_game.journal.transitions import appliquer
from pbm_game.state.modele import ENDORMI

# ------------------------------------------------------------------------------------------------
# Les scripts de cartes réelles, par famille (version 1 du langage).
# ------------------------------------------------------------------------------------------------

# --- Recherche dans la pioche : chercher un Pokémon, le mettre en main, mélanger. ---------------
GREAT_BALL = {
    "version": 1,
    "effets": [
        {"op": "chercher", "cible": {"zone": "pioche", "categorie": "pokemon", "nombre": 1}},
        {"op": "melanger", "cible": {"zone": "pioche", "proprietaire": "moi"}},
    ],
}
ULTRA_BALL = {
    "version": 1,
    "cout": [{"op": "defausser", "cible": {"zone": "main", "proprietaire": "moi", "nombre": 2}}],
    "effets": [
        {"op": "chercher", "cible": {"zone": "pioche", "categorie": "pokemon", "nombre": 1}},
        {"op": "melanger", "cible": {"zone": "pioche", "proprietaire": "moi"}},
    ],
}
QUICK_BALL = {
    "version": 1,
    "cout": [{"op": "defausser", "cible": {"zone": "main", "proprietaire": "moi", "nombre": 1}}],
    "effets": [
        {
            "op": "chercher",
            "cible": {"zone": "pioche", "categorie": "pokemon", "stade": "base", "nombre": 1},
        },
        {"op": "melanger", "cible": {"zone": "pioche", "proprietaire": "moi"}},
    ],
}

# --- Pioche. ------------------------------------------------------------------------------------
BICYCLE = {"version": 1, "effets": [{"op": "piocher", "nombre": 3}]}
ACRO_BIKE = {
    "version": 1,
    "effets": [
        {"op": "piocher", "nombre": 2},
        {
            "op": "choisir",
            "cible": {"zone": "main", "proprietaire": "moi", "nombre": 1},
            "alors": [{"op": "defausser"}],
        },
    ],
}
ROLLER_SKATES = {
    "version": 1,
    "effets": [{"op": "pile_ou_face", "alors": [{"op": "piocher", "nombre": 3}]}],
}

# --- Soin (de PV ou de statut). -----------------------------------------------------------------
POTION = {
    "version": 1,
    "effets": [
        {
            "op": "choisir",
            "cible": {"zone": "en_jeu", "proprietaire": "moi", "nombre": 1},
            "alors": [{"op": "soigner", "nombre": 3}],
        }
    ],
}
MOOMOO_MILK = {
    "version": 1,
    "effets": [
        {
            "op": "choisir",
            "cible": {"zone": "en_jeu", "proprietaire": "moi", "nombre": 1},
            "alors": [
                {"op": "pile_ou_face", "nombre": 2, "alors": [{"op": "soigner", "nombre": 3}]}
            ],
        }
    ],
}
FULL_HEAL = {
    "version": 1,
    "effets": [{"op": "retirer_etat", "cible": {"zone": "actif", "proprietaire": "moi"}}],
}

# --- Changement d'Actif de son côté (type Switch). ----------------------------------------------
SWITCH = {
    "version": 1,
    "effets": [
        {
            "op": "choisir",
            "cible": {"zone": "banc", "proprietaire": "moi", "nombre": 1},
            "alors": [{"op": "changer_actif"}],
        }
    ],
}
SWITCH_CART = {
    "version": 1,
    "effets": [
        {
            "op": "choisir",
            "cible": {"zone": "banc", "proprietaire": "moi", "nombre": 1},
            "alors": [{"op": "changer_actif"}, {"op": "soigner", "nombre": 5}],
        }
    ],
}
ESCAPE_ROPE = {
    "version": 1,
    "effets": [
        {
            "op": "choisir",
            "cible": {"zone": "banc", "proprietaire": "moi", "nombre": 1},
            "alors": [{"op": "changer_actif"}],
        },
        {
            "op": "choisir",
            "cible": {"zone": "banc", "proprietaire": "adversaire", "nombre": 1},
            "alors": [{"op": "changer_actif"}],
        },
    ],
}

# --- Appât : forcer l'Actif adverse à changer (type Gust of Wind / Pokémon Catcher). ------------
GUST_OF_WIND = {
    "version": 1,
    "effets": [
        {
            "op": "choisir",
            "cible": {"zone": "banc", "proprietaire": "adversaire", "nombre": 1},
            "alors": [{"op": "changer_actif"}],
        }
    ],
}
POKEMON_CATCHER = {
    "version": 1,
    "effets": [
        {
            "op": "pile_ou_face",
            "alors": [
                {
                    "op": "choisir",
                    "cible": {"zone": "banc", "proprietaire": "adversaire", "nombre": 1},
                    "alors": [{"op": "changer_actif"}],
                }
            ],
        }
    ],
}
POKEMON_REVERSAL = POKEMON_CATCHER  # même mécanique (pile ou face ; si face, appât), autre carte

# Appât **direct** (sans choix du joueur) — sert à prouver le chemin « sans cible » de la primitive
# elle-même : banc adverse vide ⇒ ``changer_actif`` journalise EVT_EFFET_SANS_CIBLE (jamais muet).
APPAT_DIRECT = {
    "version": 1,
    "effets": [{"op": "changer_actif", "cible": {"zone": "banc", "proprietaire": "adversaire"}}],
}

FAMILLES_OBJETS = {
    "recherche": [GREAT_BALL, ULTRA_BALL, QUICK_BALL],
    "pioche": [BICYCLE, ACRO_BIKE, ROLLER_SKATES],
    "soin": [POTION, MOOMOO_MILK, FULL_HEAL],
    "changement_actif": [SWITCH, SWITCH_CART, ESCAPE_ROPE],
    "appat": [GUST_OF_WIND, POKEMON_CATCHER, POKEMON_REVERSAL],
}


# ------------------------------------------------------------------------------------------------
# Helpers.
# ------------------------------------------------------------------------------------------------
def _joueur(e, jid):
    return next(j for j in e.joueurs if j.id == jid)


def _mains(ids):
    return {c.instance_id for c in ids}


# ------------------------------------------------------------------------------------------------
# Chaque famille se charge et se valide (critère : ≥ 3 cartes réelles par famille, aucune en code).
# ------------------------------------------------------------------------------------------------
def test_chaque_famille_a_trois_cartes_chargeables():
    """Les trois cartes de chaque famille se chargent sans code spécifique (D9, critère n°2)."""
    for famille, scripts in FAMILLES_OBJETS.items():
        assert len(scripts) >= 3, famille
        for script in scripts:
            prog = charger_programme(script)  # lève ProgrammeInvalide si non conforme
            assert prog.version == 1


# ------------------------------------------------------------------------------------------------
# Recherche.
# ------------------------------------------------------------------------------------------------
def test_great_ball_met_un_pokemon_en_main():
    alice = joueur(
        "alice",
        actif=pokemon("a"),
        main=(carte("m1"),),
        pioche=(carte("p-poke", "ref-poke"), carte("p-energie", "ref-e")),
    )
    e = etat(alice, joueur("bob", actif=pokemon("b")))
    meta = {"ref-poke": {"categorie": "pokemon"}, "ref-e": {"categorie": "energie"}}
    res = executer_programme(e, charger_programme(GREAT_BALL), contexte(metadonnees=meta), rng())
    assert "p-poke" in _mains(_joueur(res.etat, "alice").main)


def test_ultra_ball_defausse_deux_cartes_en_cout():
    alice = joueur(
        "alice",
        actif=pokemon("a"),
        main=(carte("m1"), carte("m2")),
        pioche=(carte("p-poke", "ref-poke"),),
    )
    e = etat(alice, joueur("bob", actif=pokemon("b")))
    meta = {"ref-poke": {"categorie": "pokemon"}}
    res = executer_programme(e, charger_programme(ULTRA_BALL), contexte(metadonnees=meta), rng())
    j = _joueur(res.etat, "alice")
    assert res.cout_paye
    assert {"m1", "m2"} == _mains(j.defausse)
    assert "p-poke" in _mains(j.main)


def test_quick_ball_cherche_une_base():
    alice = joueur(
        "alice",
        actif=pokemon("a"),
        main=(carte("m1"),),
        pioche=(carte("p-base", "ref-base"), carte("p-evo", "ref-evo")),
    )
    e = etat(alice, joueur("bob", actif=pokemon("b")))
    meta = {
        "ref-base": {"categorie": "pokemon", "stade": "base"},
        "ref-evo": {"categorie": "pokemon", "stade": "stade1"},
    }
    res = executer_programme(e, charger_programme(QUICK_BALL), contexte(metadonnees=meta), rng())
    main_ids = _mains(_joueur(res.etat, "alice").main)
    assert "p-base" in main_ids
    assert "p-evo" not in main_ids  # le filtre « base » n'a pas pris l'évolution


# ------------------------------------------------------------------------------------------------
# Pioche.
# ------------------------------------------------------------------------------------------------
def test_bicycle_pioche_trois():
    alice = joueur(
        "alice", actif=pokemon("a"), pioche=(carte("p1"), carte("p2"), carte("p3"), carte("p4"))
    )
    e = etat(alice, joueur("bob", actif=pokemon("b")))
    res = executer_programme(e, charger_programme(BICYCLE), contexte(), rng())
    assert len(_joueur(res.etat, "alice").main) == 3


def test_acro_bike_pioche_deux_puis_defausse_une():
    alice = joueur("alice", actif=pokemon("a"), pioche=(carte("p1"), carte("p2"), carte("p3")))
    e = etat(alice, joueur("bob", actif=pokemon("b")))
    res = executer_programme(e, charger_programme(ACRO_BIKE), contexte(), rng())
    j = _joueur(res.etat, "alice")
    assert len(j.main) == 1  # pioché 2, défaussé 1
    assert len(j.defausse) == 1


# ------------------------------------------------------------------------------------------------
# Soin.
# ------------------------------------------------------------------------------------------------
def test_potion_soigne_trente():
    alice = joueur("alice", actif=pokemon("a", compteurs=50))
    e = etat(alice, joueur("bob", actif=pokemon("b")))
    res = executer_programme(e, charger_programme(POTION), contexte(), rng())
    assert _joueur(res.etat, "alice").actif.compteurs_degats == 20  # 50 − 30


def test_full_heal_retire_les_etats():
    alice = joueur("alice", actif=pokemon("a", etats=frozenset({ENDORMI})))
    e = etat(alice, joueur("bob", actif=pokemon("b")))
    res = executer_programme(e, charger_programme(FULL_HEAL), contexte(), rng())
    assert _joueur(res.etat, "alice").actif.etats_speciaux == frozenset()


# ------------------------------------------------------------------------------------------------
# Changement d'Actif de son côté.
# ------------------------------------------------------------------------------------------------
def test_switch_change_mon_actif():
    alice = joueur("alice", actif=pokemon("a-actif"), banc=(pokemon("a-banc"),))
    e = etat(alice, joueur("bob", actif=pokemon("b")))
    res = executer_programme(e, charger_programme(SWITCH), contexte(), rng())
    j = _joueur(res.etat, "alice")
    assert j.actif.cartes[0].instance_id == "a-banc"
    assert j.banc[0].cartes[0].instance_id == "a-actif"
    assert res.devenus_actifs == (("alice", "a-banc"),)


# ------------------------------------------------------------------------------------------------
# Appât.
# ------------------------------------------------------------------------------------------------
def _etat_appat(*, bob_actif_etats=frozenset(), bob_bancs=("b-fragile",)):
    alice = joueur("alice", actif=pokemon("a"))
    bob = joueur(
        "bob",
        actif=pokemon("b-actif", etats=bob_actif_etats, compteurs=20, energies=(carte("e1"),)),
        banc=tuple(pokemon(b) for b in bob_bancs),
    )
    return etat(alice, bob)


def test_appat_change_lactif_adverse():
    """L'appât sort le Pokémon de banc adverse au front (R-8.8)."""
    e = _etat_appat()
    res = executer_programme(e, charger_programme(GUST_OF_WIND), contexte("alice", "bob"), rng())
    bob = _joueur(res.etat, "bob")
    assert bob.actif.cartes[0].instance_id == "b-fragile"
    assert res.devenus_actifs == (("bob", "b-fragile"),)


def test_appat_nettoie_le_descendant_et_marche_sous_sommeil():
    """R-8.6 : l'Actif qui descend perd ses états ; R-16.12 : l'échange marche même Endormi."""
    e = _etat_appat(bob_actif_etats=frozenset({ENDORMI}))
    res = executer_programme(e, charger_programme(GUST_OF_WIND), contexte("alice", "bob"), rng())
    bob = _joueur(res.etat, "bob")
    descendu = next(p for p in bob.banc if p.cartes[0].instance_id == "b-actif")
    assert descendu.etats_speciaux == frozenset()  # R-8.6 : nettoyé en descendant
    assert descendu.compteurs_degats == 20  # mais garde ses compteurs
    assert _mains(descendu.energies) == {"e1"}  # et ses énergies (pas de coût R-8.8)


def test_appat_banc_vide_ne_fait_rien_et_le_dit():
    """Appât sur un banc adverse vide : aucune cible, journalisé, état inchangé (critère n°2)."""
    e = _etat_appat(bob_bancs=())
    res = executer_programme(e, charger_programme(APPAT_DIRECT), contexte("alice", "bob"), rng())
    assert res.devenus_actifs == ()
    assert _joueur(res.etat, "bob").actif.cartes[0].instance_id == "b-actif"  # inchangé
    assert any(ev.type == EVT_EFFET_SANS_CIBLE for ev in res.evenements)


def test_appat_puis_attaque_frappe_le_nouvel_actif():
    """Appât puis attaque : les dégâts tombent sur le Pokémon tiré au front (scénario fiche)."""
    e = _etat_appat()
    # 1) l'appât promeut b-fragile.
    e = executer_programme(e, charger_programme(GUST_OF_WIND), contexte("alice", "bob"), rng()).etat
    # 2) une attaque (dégâts d'effet) vise l'Actif adverse — c'est maintenant b-fragile.
    degats = {
        "version": 1,
        "effets": [
            {"op": "infliger_degats", "cible": {"zone": "actif", "proprietaire": "adversaire"},
             "nombre": 30}
        ],
    }
    res = executer_programme(e, charger_programme(degats), contexte("alice", "bob"), rng())
    bob = _joueur(res.etat, "bob")
    assert bob.actif.cartes[0].instance_id == "b-fragile"
    assert bob.actif.compteurs_degats == 30  # l'attaque a frappé le Pokémon appâté


def test_appat_ne_consomme_pas_la_retraite_du_tour():
    """L'échange forcé ne marque pas la retraite du tour (R-8.8) : le DSL ne touche pas ``tour``."""
    from pbm_game.tour.drapeaux import retraite_deja_faite

    e = _etat_appat()
    res = executer_programme(e, charger_programme(GUST_OF_WIND), contexte("alice", "bob"), rng())
    assert not retraite_deja_faite(res.etat.tour)


# ------------------------------------------------------------------------------------------------
# Jouabilité : un Objet sans cible valide n'est pas jouable, et la raison s'affiche.
# ------------------------------------------------------------------------------------------------
def test_programme_jouable_appat_banc_vide_refuse_avec_raison():
    e = _etat_appat(bob_bancs=())
    prog = charger_programme(GUST_OF_WIND)
    jouable, raison = programme_jouable(e, prog, contexte("alice", "bob"))
    assert not jouable
    assert "cible" in raison.lower()


def test_programme_jouable_appat_avec_banc_accepte():
    e = _etat_appat()
    prog = charger_programme(GUST_OF_WIND)
    jouable, raison = programme_jouable(e, prog, contexte("alice", "bob"))
    assert jouable
    assert raison == ""


def test_programme_jouable_roller_skates_toujours_jouable():
    """Roller Skates (pile ou face ; si face pioche 3) reste jouable — on ignore l'issue du jet."""
    alice = joueur("alice", actif=pokemon("a"), pioche=(carte("p1"), carte("p2"), carte("p3")))
    e = etat(alice, joueur("bob", actif=pokemon("b")))
    jouable, _ = programme_jouable(e, charger_programme(ROLLER_SKATES), contexte())
    assert jouable


# ------------------------------------------------------------------------------------------------
# FamilleJouerObjet + transition jouer_objet (le vrai chemin du moteur).
# ------------------------------------------------------------------------------------------------
def _catalogue_appat():
    gust = DefinitionObjet("ref-gust", "Gust of Wind", charger_programme(GUST_OF_WIND))
    return CatalogueJeu(objets={"ref-gust": gust})


def _etat_main_appat(*, bob_bancs=("b-fragile",)):
    """alice (joueur actif) tient un Gust of Wind ; bob a un Actif et un banc."""
    alice = joueur("alice", actif=pokemon("a"), main=(carte("g1", "ref-gust"),))
    bob = joueur("bob", actif=pokemon("b-actif"), banc=tuple(pokemon(b) for b in bob_bancs))
    return etat(alice, bob)


def test_objet_jouable_liste_quand_la_cible_existe():
    cat = _catalogue_appat()
    coups = actions_legales(_etat_main_appat(), "alice", familles_jeu(cat))
    objets = [c for c in coups if c.action.type == ACTION_JOUER_OBJET]
    assert len(objets) == 1
    assert "Gust of Wind" in objets[0].etiquette


def test_objet_sans_cible_non_liste_et_refus_motive():
    """Banc adverse vide : l'appât n'est pas proposé, et le refus cite la raison (critère)."""
    cat = _catalogue_appat()
    e = _etat_main_appat(bob_bancs=())
    coups = actions_legales(e, "alice", familles_jeu(cat))
    assert not [c for c in coups if c.action.type == ACTION_JOUER_OBJET]
    verdict = valider(e, Action(ACTION_JOUER_OBJET, "alice", {}), familles_jeu(cat))
    assert not verdict.accepte
    assert "cible valide" in verdict.message


def test_transition_jouer_objet_appat_bout_en_bout():
    cat = _catalogue_appat()
    e = _etat_main_appat()
    coup = next(
        c for c in actions_legales(e, "alice", familles_jeu(cat))
        if c.action.type == ACTION_JOUER_OBJET
    )
    etat2, evts = appliquer(e, coup.action, rng())
    alice = _joueur(etat2, "alice")
    bob = _joueur(etat2, "bob")
    assert "g1" in _mains(alice.defausse)  # l'Objet est défaussé après usage (R-5.5)
    assert "g1" not in _mains(alice.main)
    assert bob.actif.cartes[0].instance_id == "b-fragile"  # l'appât a tiré le banc au front
    objet_joue = next(ev for ev in evts if ev.type == EVT_OBJET_JOUE)
    assert objet_joue.donnees["devient_actif"] == [["bob", "b-fragile"]]


def _etat_avec_demande(e):
    """Le même état, mais avec une demande de décision en cours (partie en pause)."""
    demande = DemandeDecision(
        destinataire="alice",
        categorie=CAT_CARTE,
        source=SourceEffet("Effet en attente"),
        regle="R-9.3",
        libelle="Choisis une carte",
        options=("x",),
        minimum=1,
        maximum=1,
    ).avec_id("d0")
    effet = EffetEnAttente("dsl", SourceEffet("Effet"), "R-9.3", "Effet")
    resolution = ResolutionEnCours(pile=PileEffets().empiler(effet), demande=demande)
    return replace(e, resolution=resolution)


def test_objet_non_liste_pendant_une_demande():
    cat = _catalogue_appat()
    e = _etat_avec_demande(_etat_main_appat())
    coups = actions_legales(e, "alice", familles_jeu(cat))
    assert not [c for c in coups if c.action.type == ACTION_JOUER_OBJET]


def test_jouer_objet_refuse_pendant_une_demande():
    """La garde centrale d'``appliquer`` refuse tout coup (sauf réponse/abandon) sous demande."""
    cat = _catalogue_appat()
    e = _etat_main_appat()
    coup = next(
        c for c in actions_legales(e, "alice", familles_jeu(cat))
        if c.action.type == ACTION_JOUER_OBJET
    )
    e_demande = _etat_avec_demande(e)
    with pytest.raises(ValueError, match="[Dd]écision"):
        appliquer(e_demande, coup.action, rng())
