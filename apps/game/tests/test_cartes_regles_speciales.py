"""Cartes particulières dans le moteur — Prisme Étoile en zone perdue (R-15.18/R-3.8).

Une carte ◇ qui devrait aller à la défausse va en **zone perdue**, et n'en sort plus (R-3.8).
"""

from __future__ import annotations

from pbm_game.combat.fin import resoudre_kos
from pbm_game.combat.ko import router_cartes_ko
from pbm_game.state.modele import (
    PHASE_ATTAQUE,
    Carte,
    EtatPartie,
    Joueur,
    PokemonEnJeu,
    Tour,
)
from pbm_game.state.serialisation import depuis_json, vers_json


def test_router_cartes_ko_prisme_vers_zone_perdue():
    """R-15.18 — la carte ◇ va en zone perdue ; son énergie attachée (non ◇) à la défausse."""
    carte_prisme = Carte("bob-pk-1", "ref-prisme")
    energie = Carte("bob-en-1", "ref-energie")
    pokemon = PokemonEnJeu(cartes=(carte_prisme,), energies=(energie,))
    vers_zp, vers_def = router_cartes_ko(pokemon, est_prisme_etoile=True)
    assert carte_prisme in vers_zp
    assert energie in vers_def
    assert carte_prisme not in vers_def


def test_router_cartes_ko_ordinaire_tout_en_defausse():
    """Un Pokémon ordinaire K.O. : tout va à la défausse, rien en zone perdue (R-13.2)."""
    pokemon = PokemonEnJeu(cartes=(Carte("c-1", "ref"),), energies=(Carte("e-1", "ref-e"),))
    vers_zp, vers_def = router_cartes_ko(pokemon, est_prisme_etoile=False)
    assert vers_zp == ()
    assert len(vers_def) == 2


def test_prisme_etoile_ko_part_en_zone_perdue():
    """R-15.18/R-3.8 — un Prisme Étoile mis K.O. voit sa carte rejoindre la zone perdue, pas la
    défausse. Détecté sur le marqueur de règle de la fiche (le moteur ne lit pas le catalogue)."""
    carte_prisme = Carte("bob-pk-1", "ref-prisme")
    energie = Carte("bob-en-1", "ref-energie")
    bob = Joueur(
        id="bob",
        actif=PokemonEnJeu(cartes=(carte_prisme,), energies=(energie,), compteurs_degats=70),
        banc=(PokemonEnJeu(cartes=(Carte("bob-bk-1", "ref-bb"),)),),  # un relais : pas de défaite
    )
    alice = Joueur(id="alice", actif=PokemonEnJeu(cartes=(Carte("alice-pk-1", "ref-a"),)),
                   recompenses=(Carte("a-r1", "r"), Carte("a-r2", "r")))
    etat = EtatPartie(joueurs=(alice, bob), tour=Tour("alice", 2, PHASE_ATTAQUE))
    fiches = {"bob-pk-1": {"pv": 60, "marqueur": "prisme_etoile"}}

    etat2, _ = resoudre_kos(etat, fiches, ("alice", "bob"))
    bob2 = next(j for j in etat2.joueurs if j.id == "bob")
    assert carte_prisme in bob2.zone_perdue  # R-15.18
    assert carte_prisme not in bob2.defausse
    assert energie in bob2.defausse  # l'énergie (non ◇) va bien à la défausse (R-13.2)


def test_zone_perdue_sans_retour_apres_f5():
    """R-3.8 — la zone perdue est portée par l'état sérialisé : son contenu survit à un F5."""
    bob = Joueur(id="bob", actif=PokemonEnJeu(cartes=(Carte("b-1", "r"),)),
                 zone_perdue=(Carte("zp-1", "ref-zp"),))
    alice = Joueur(id="alice", actif=PokemonEnJeu(cartes=(Carte("a-1", "r"),)))
    etat = EtatPartie(joueurs=(alice, bob), tour=Tour("alice", 1, PHASE_ATTAQUE))
    repris = depuis_json(vers_json(etat))
    assert repris == etat
    bob2 = next(j for j in repris.joueurs if j.id == "bob")
    assert Carte("zp-1", "ref-zp") in bob2.zone_perdue
