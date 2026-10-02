"""Sélection de cibles — un sélecteur trouve les bonnes cartes/Pokémon, et pas d'autres."""

from __future__ import annotations

from fabrique_dsl import carte, contexte, etat, joueur, pokemon

from pbm_game.effets.dsl.modele import Selecteur
from pbm_game.effets.dsl.selection import CibleCarte, CiblePokemon, candidats


def _deux_joueurs():
    alice = joueur(
        "alice",
        actif=pokemon("a-actif"),
        banc=(pokemon("a-banc1"), pokemon("a-banc2")),
        main=(carte("a-main1"), carte("a-main2")),
        pioche=(carte("a-p1"), carte("a-p2"), carte("a-p3")),
    )
    bob = joueur("bob", actif=pokemon("b-actif"), banc=(pokemon("b-banc1"),))
    return etat(alice, bob)


def test_mon_actif():
    cands = candidats(_deux_joueurs(), Selecteur(zone="actif", proprietaire="moi"), contexte())
    assert [c.identite for c in cands] == ["a-actif"]
    assert all(isinstance(c, CiblePokemon) for c in cands)


def test_un_de_mes_pokemon_de_banc():
    cands = candidats(_deux_joueurs(), Selecteur(zone="banc", proprietaire="moi"), contexte())
    assert sorted(c.identite for c in cands) == ["a-banc1", "a-banc2"]


def test_en_jeu_couvre_actif_et_banc():
    cands = candidats(_deux_joueurs(), Selecteur(zone="en_jeu", proprietaire="moi"), contexte())
    assert sorted(c.identite for c in cands) == ["a-actif", "a-banc1", "a-banc2"]


def test_adversaire_ne_voit_que_l_autre_camp():
    cands = candidats(
        _deux_joueurs(), Selecteur(zone="en_jeu", proprietaire="adversaire"), contexte()
    )
    assert {c.joueur for c in cands} == {"bob"}


def test_les_deux_camps():
    cands = candidats(_deux_joueurs(), Selecteur(zone="actif", proprietaire="les_deux"), contexte())
    assert sorted(c.joueur for c in cands) == ["alice", "bob"]


def test_cartes_de_la_main():
    cands = candidats(_deux_joueurs(), Selecteur(zone="main", proprietaire="moi"), contexte())
    assert all(isinstance(c, CibleCarte) for c in cands)
    assert sorted(c.instance_id for c in cands) == ["a-main1", "a-main2"]


def test_pioche_dans_l_ordre_du_sommet():
    cands = candidats(_deux_joueurs(), Selecteur(zone="pioche", proprietaire="moi"), contexte())
    # Le sommet (pioche[0]) vient en premier (même convention que journal.transitions).
    assert [c.instance_id for c in cands] == ["a-p1", "a-p2", "a-p3"]


def test_filtre_categorie_pokemon_de_base_dans_la_pioche():
    """« Un Pokémon de base dans ma pioche » — le filtre lit les métadonnées de catalogue."""
    alice = joueur(
        "alice",
        actif=pokemon("a-actif"),
        pioche=(
            carte("p-pok", "ref-pok"),
            carte("p-ener", "ref-ener"),
            carte("p-pok2", "ref-pok2"),
        ),
    )
    bob = joueur("bob", actif=pokemon("b-actif"))
    meta = {
        "ref-pok": {"categorie": "pokemon", "stade": "base"},
        "ref-pok2": {"categorie": "pokemon", "stade": "stade1"},
        "ref-ener": {"categorie": "energie"},
    }
    sel = Selecteur(zone="pioche", proprietaire="moi", categorie="pokemon", stade="base")
    cands = candidats(etat(alice, bob), sel, contexte(metadonnees=meta))
    assert [c.instance_id for c in cands] == ["p-pok"]


def test_ref_sans_metadonnee_exclue_par_un_filtre():
    """On ne devine pas une catégorie (D9) : sans métadonnée, la carte n'est pas retenue."""
    alice = joueur("alice", actif=pokemon("a-actif"), main=(carte("m1", "ref-inconnue"),))
    bob = joueur("bob", actif=pokemon("b-actif"))
    sel = Selecteur(zone="main", proprietaire="moi", categorie="energie")
    assert candidats(etat(alice, bob), sel, contexte(metadonnees={})) == []


def test_stade_global_et_proprietaire():
    alice = joueur("alice", actif=pokemon("a-actif"))
    bob = joueur("bob", actif=pokemon("b-actif"))
    e = etat(alice, bob, stade=carte("stade-1", "ref-stade"), stade_proprietaire="alice")
    a_moi = candidats(e, Selecteur(zone="stade", proprietaire="moi"), contexte())
    assert [c.instance_id for c in a_moi] == ["stade-1"]
    a_adv = candidats(e, Selecteur(zone="stade", proprietaire="adversaire"), contexte())
    assert a_adv == []
