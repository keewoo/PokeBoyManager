"""Primitives de **mise K.O.** — détection, défausse et prise de récompenses (R-13).

Module **pur** (aucune E/S), au cœur du jeu et de son moment le plus coûteux en cas d'erreur :
la fin d'une partie. Ces primitives sont **partagées** à dessein — un K.O. survient aussi bien
dans la résolution d'une attaque que pendant le Pokémon Checkup (poison, brûlure…). Le code de
victoire ne doit donc **pas** vivre uniquement dans la résolution d'attaque (risque nommé dans
la fiche du lot ``j-checkup``) : il vit ici, et ``pbm_game.checkup`` comme la future résolution
d'attaque l'appellent.

**Le moteur ne devine ni PV ni récompenses (D9).** Les PV (R-13.1) et le nombre de récompenses
(marqueur de règle, R-13.3/R-13.4) se lisent **sur la carte, dans le catalogue** — que le moteur
ne connaît pas. Le service les fournit ; ces fonctions les reçoivent et **valident bruyamment**
une valeur absurde, jamais un repli « par défaut 1 ».

Règles servies (``docs/jeu/REGLES.md``) :

* **R-13.1** — K.O. quand les compteurs de dégâts ≥ PV ;
* **R-13.2** — un K.O. défausse le Pokémon avec **toute** sa pile d'évolutions, ses énergies et
  son Outil ;
* **R-13.3** — l'adversaire prend des récompenses selon le marqueur de règle de la carte K.O.

Le **nombre** de récompenses prises est borné par la réserve restante ; la **victoire** qui en
découle (plus de récompenses à prendre, R-14.1) est résolue par ``j-ko-recompenses``, pas ici.
"""

from __future__ import annotations

from dataclasses import replace

from ..state.modele import Carte, Joueur, PokemonEnJeu


def cartes_a_defausser(pokemon: PokemonEnJeu) -> tuple[Carte, ...]:
    """Toutes les cartes qu'un K.O. envoie à la défausse (R-13.2), dans un ordre stable.

    Pile d'évolutions (du bas vers le haut), puis énergies attachées, puis l'Outil s'il y en a
    un. C'est **tout** ce que porte le Pokémon : rien ne reste en jeu après un K.O.
    """
    cartes: list[Carte] = list(pokemon.cartes)
    cartes.extend(pokemon.energies)
    if pokemon.outil is not None:
        cartes.append(pokemon.outil)
    return tuple(cartes)


def est_ko(compteurs_degats: int, pv: int) -> bool:
    """Vrai si ``compteurs_degats ≥ pv`` (R-13.1). Lève si ``pv`` est absurde (≤ 0).

    Les PV viennent du catalogue (le moteur ne les connaît pas) : un PV ≤ 0 n'est pas un
    Pokémon jouable, c'est une donnée fausse — on la refuse bruyamment plutôt que de conclure
    un K.O. de travers (pas de repli silencieux).
    """
    if not isinstance(compteurs_degats, int) or isinstance(compteurs_degats, bool):
        raise ValueError(f"Compteurs de dégâts invalides : {compteurs_degats!r} (entier).")
    if not isinstance(pv, int) or isinstance(pv, bool) or pv <= 0:
        raise ValueError(f"PV invalides : {pv!r} (entier ≥ 1, lu sur la carte — R-13.1).")
    return compteurs_degats >= pv


def prendre_recompenses(joueur: Joueur, nombre: int) -> tuple[Joueur, int]:
    """Le joueur **prend** ``nombre`` récompenses (R-13.3) : de sa réserve vers sa main.

    Les récompenses sont face cachée (R-3.4) ; on en prend depuis le **début** de la réserve
    (ordre déterministe, rejouable). Renvoie le joueur augmenté et le **nombre réellement
    pris** — borné par la réserve restante : prendre la dernière est une victoire (R-14.1),
    résolue en aval (``j-ko-recompenses``), jamais ici. Lève si ``nombre`` est absurde.
    """
    if not isinstance(nombre, int) or isinstance(nombre, bool) or nombre < 1:
        raise ValueError(
            f"Nombre de récompenses à prendre invalide : {nombre!r} — un entier ≥ 1, lu sur le "
            "marqueur de règle de la carte K.O. (R-13.3), jamais deviné."
        )
    prises = min(nombre, len(joueur.recompenses))
    gagnees = joueur.recompenses[:prises]
    reste = joueur.recompenses[prises:]
    return replace(joueur, recompenses=reste, main=joueur.main + gagnees), prises


__all__ = [
    "cartes_a_defausser",
    "est_ko",
    "prendre_recompenses",
]
