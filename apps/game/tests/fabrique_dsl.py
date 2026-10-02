"""Fabrique d'états **contrôlés** pour les tests du langage d'effets (lot j-effets-dsl).

Contrairement à ``fabrique_etats`` (aléatoire, pour les tests de propriété), celle-ci construit
des états **précis et minimaux** : un test de primitive veut savoir exactement ce qu'il y a dans
la main, sur le banc, combien de compteurs porte l'Actif. Ce fichier ne commence pas par
``test_`` : pytest ne le collecte pas, les suites l'importent.
"""

from __future__ import annotations

from pbm_game.effets.dsl.contexte import ContexteEffet
from pbm_game.effets.pile import SourceEffet
from pbm_game.rng import Rng
from pbm_game.state import Carte, EtatPartie, Joueur, PokemonEnJeu, Tour


def carte(iid: str, ref: str | None = None) -> Carte:
    """Une carte d'``instance_id`` ``iid`` ; sa ``ref`` en dérive si non donnée."""
    return Carte(instance_id=iid, ref=ref if ref is not None else f"ref-{iid}")


def pokemon(
    base: str,
    *,
    ref: str | None = None,
    energies: tuple[Carte, ...] = (),
    compteurs: int = 0,
    etats: frozenset[str] = frozenset(),
    outil: Carte | None = None,
    cartes: tuple[Carte, ...] | None = None,
) -> PokemonEnJeu:
    """Un Pokémon en jeu dont l'identité (carte de base) est ``base``."""
    pile = cartes if cartes is not None else (carte(base, ref),)
    return PokemonEnJeu(
        cartes=pile,
        energies=energies,
        outil=outil,
        compteurs_degats=compteurs,
        etats_speciaux=etats,
    )


def joueur(
    jid: str,
    *,
    actif: PokemonEnJeu | None = None,
    banc: tuple[PokemonEnJeu, ...] = (),
    main: tuple[Carte, ...] = (),
    pioche: tuple[Carte, ...] = (),
    defausse: tuple[Carte, ...] = (),
    recompenses: tuple[Carte, ...] = (),
    zone_perdue: tuple[Carte, ...] = (),
) -> Joueur:
    return Joueur(
        id=jid,
        actif=actif,
        banc=banc,
        main=main,
        pioche=pioche,
        defausse=defausse,
        recompenses=recompenses,
        zone_perdue=zone_perdue,
    )


def etat(
    j0: Joueur,
    j1: Joueur,
    *,
    numero: int = 1,
    phase: str = "principale",
    stade: Carte | None = None,
    stade_proprietaire: str | None = None,
) -> EtatPartie:
    tour = Tour(joueur_actif=j0.id, numero=numero, phase=phase)
    return EtatPartie(
        joueurs=(j0, j1), tour=tour, stade=stade, stade_proprietaire=stade_proprietaire
    )


def contexte(
    joueur: str = "alice",
    adversaire: str = "bob",
    *,
    acteur_actif: str | None = None,
    defenseur: str | None = None,
    metadonnees: dict | None = None,
    libelle: str = "Carte de test",
) -> ContexteEffet:
    return ContexteEffet(
        source=SourceEffet(libelle=libelle, ref="ref-test", instance_id="src-1"),
        joueur=joueur,
        adversaire=adversaire,
        acteur_actif=acteur_actif,
        defenseur=defenseur,
        metadonnees=metadonnees or {},
    )


def rng(graine: bytes = b"graine-de-test--") -> Rng:
    """Un :class:`~pbm_game.rng.Rng` déterministe (graine ≥ 16 octets)."""
    return Rng(graine)
