"""Fabrique d'états de partie **aléatoires mais valides** pour les tests de propriété.

Déterministe pour une graine donnée (``random.Random(seed)``) : les tests sont donc
reproductibles. Chaque carte reçoit un ``instance_id`` **globalement unique** (compteur
partagé) et un ``ref`` qui en dérive — ce qui rend le test de non-fuite précis : une
chaîne cachée ne peut pas apparaître par hasard comme sous-chaîne d'une autre.

Ce fichier n'est **pas** une suite de tests (il ne commence pas par ``test_``) : pytest
ne le collecte pas, les autres fichiers l'importent.
"""

from __future__ import annotations

import random

from pbm_game.state import (
    ETATS_MARQUEUR,
    ETATS_ORIENTATION,
    PHASES,
    Carte,
    EtatPartie,
    Joueur,
    PokemonEnJeu,
    Tour,
)


class _Compteur:
    """Donne un suffixe entier unique sur toute la fabrication d'un état."""

    def __init__(self) -> None:
        self.n = 0

    def suivant(self) -> int:
        self.n += 1
        return self.n


def _carte(compteur: _Compteur, zone: str) -> Carte:
    n = compteur.suivant()
    return Carte(instance_id=f"{zone}-{n}", ref=f"ref-{zone}-{n}")


def _cartes(rng: random.Random, compteur: _Compteur, zone: str, maxi: int) -> tuple[Carte, ...]:
    return tuple(_carte(compteur, zone) for _ in range(rng.randint(0, maxi)))


def _pokemon(
    rng: random.Random, compteur: _Compteur, zone: str, *, avec_etats: bool
) -> PokemonEnJeu:
    cartes = tuple(_carte(compteur, f"{zone}-pk") for _ in range(rng.randint(1, 3)))
    energies = _cartes(rng, compteur, f"{zone}-en", 4)
    outil = _carte(compteur, f"{zone}-ou") if rng.random() < 0.3 else None
    etats: set[str] = set()
    if avec_etats:  # R-11.2 : seul l'Actif subit un état spécial.
        if rng.random() < 0.5:
            etats.add(rng.choice(sorted(ETATS_ORIENTATION)))  # un seul (R-11.8)
        for marqueur in sorted(ETATS_MARQUEUR):
            if rng.random() < 0.3:
                etats.add(marqueur)
    return PokemonEnJeu(
        cartes=cartes,
        energies=energies,
        outil=outil,
        compteurs_degats=rng.choice([0, 10, 30, 120]),
        etats_speciaux=frozenset(etats),
    )


def _joueur(rng: random.Random, compteur: _Compteur, jid: str) -> Joueur:
    a_actif = rng.random() < 0.9
    actif = _pokemon(rng, compteur, f"{jid}-actif", avec_etats=True) if a_actif else None
    nb_banc = rng.randint(0, 5) if actif is not None else 0  # R-3.3 : pas de banc sans Actif
    banc = tuple(
        _pokemon(rng, compteur, f"{jid}-banc{i}", avec_etats=False) for i in range(nb_banc)
    )
    return Joueur(
        id=jid,
        pioche=_cartes(rng, compteur, f"{jid}-pioche", 10),
        main=_cartes(rng, compteur, f"{jid}-main", 7),
        actif=actif,
        banc=banc,
        defausse=_cartes(rng, compteur, f"{jid}-defausse", 5),
        recompenses=tuple(_carte(compteur, f"{jid}-recompense") for _ in range(rng.randint(0, 6))),
        zone_perdue=_cartes(rng, compteur, f"{jid}-zoneperdue", 2),
    )


def fabrique_etat(seed: int, ids: tuple[str, str] = ("alice", "bob")) -> EtatPartie:
    """Un :class:`EtatPartie` aléatoire **valide** (il passe ``verifier`` sans violation)."""
    rng = random.Random(seed)
    compteur = _Compteur()
    j0 = _joueur(rng, compteur, ids[0])
    j1 = _joueur(rng, compteur, ids[1])
    tour = Tour(
        joueur_actif=rng.choice(ids),
        numero=rng.randint(1, 30),
        phase=rng.choice(sorted(PHASES)),
        energie_posee=rng.random() < 0.5,
        supporter_joue=rng.random() < 0.5,
        retraite_faite=rng.random() < 0.5,
    )
    stade = _carte(compteur, "stade") if rng.random() < 0.4 else None
    stade_proprietaire = rng.choice(ids) if stade is not None else None
    return EtatPartie(
        joueurs=(j0, j1),
        tour=tour,
        stade=stade,
        stade_proprietaire=stade_proprietaire,
    )
