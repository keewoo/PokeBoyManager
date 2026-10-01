"""Les six contraintes de tour, en **verdicts motivés** — la couche « jugement ».

Module **pur** (aucune E/S), bâti sur :mod:`pbm_game.tour.drapeaux` (les prédicats bruts) et
:mod:`pbm_game.actions.modele` (le :class:`~pbm_game.actions.Verdict` et son ``refus`` qui
**exige une règle citée**). Chaque fonction renvoie soit :data:`~pbm_game.actions.ACCORD`,
soit un refus qui nomme le ``R-x.y`` qui bloque — jamais un refus muet.

C'est **le serveur qui tient les contraintes**, pas l'interface (risque nommé dans la fiche
du lot ``j-machine-tour``) : l'écran ne fait que griser ce que ces fonctions refusent. Les
lots de résolution (``j-degats-resolution``, ``j-retraite-banc``, et ceux qui posent/évoluent
les Pokémon quand le catalogue est là) appellent ces gardes avant d'appliquer leur action,
puis lèvent le drapeau correspondant via :mod:`pbm_game.tour.drapeaux`.

Les six contraintes :

* **R-5.4** — attacher une énergie : une seule fois par tour ;
* **R-5.5 / R-6.2** — jouer un Supporter : un seul par tour, et **jamais** au premier tour du
  joueur qui commence ;
* **R-5.6** — battre en retraite : une seule fois par tour ;
* **R-7.3** — pas d'évolution d'un Pokémon entré en jeu **ce tour-ci** ;
* **R-6.5** — pas d'évolution au **premier tour** de chaque joueur ;
* **R-6.1** — le joueur qui commence **n'attaque pas** à son premier tour.
"""

from __future__ import annotations

from ..actions.modele import ACCORD, Verdict, refus
from ..state.modele import Tour
from .drapeaux import (
    energie_deja_posee,
    est_premier_tour_du_joueur_actif,
    est_premier_tour_du_joueur_qui_commence,
    pokemon_entre_ce_tour,
    pokemon_evolue_ce_tour,
    retraite_deja_faite,
    supporter_deja_joue,
)


def peut_attacher_energie(tour: Tour) -> Verdict:
    """R-5.4 — attacher une énergie n'est permis qu'une fois par tour."""
    if energie_deja_posee(tour):
        return refus("R-5.4", "Une énergie a déjà été attachée ce tour : une seule par tour.")
    return ACCORD


def peut_jouer_supporter(tour: Tour) -> Verdict:
    """R-5.5 / R-6.2 — un seul Supporter par tour, et aucun au 1er tour du joueur qui commence."""
    if est_premier_tour_du_joueur_qui_commence(tour):
        return refus(
            "R-6.2",
            "Le joueur qui commence ne peut pas jouer de Supporter à son premier tour.",
        )
    if supporter_deja_joue(tour):
        return refus("R-5.5", "Un Supporter a déjà été joué ce tour : un seul par tour.")
    return ACCORD


def peut_battre_retraite(tour: Tour) -> Verdict:
    """R-5.6 — battre en retraite n'est permis qu'une fois par tour.

    Les autres conditions de la retraite (coût en énergies R-8.2, interdiction sous Sommeil
    ou Paralysie R-8.4/R-11.10) relèvent du lot ``j-retraite-banc`` : cette garde-ci ne porte
    que la limite « une fois par tour ».
    """
    if retraite_deja_faite(tour):
        return refus("R-5.6", "Une retraite a déjà eu lieu ce tour : une seule par tour.")
    return ACCORD


def peut_evoluer(tour: Tour, base_id: str) -> Verdict:
    """R-6.5 / R-7.3 — pas d'évolution au premier tour, ni d'un Pokémon entré en jeu ce tour.

    ``base_id`` est l'identité stable du Pokémon (``instance_id`` de sa carte de base, voir
    :func:`pbm_game.tour.drapeaux.identite_pokemon`). R-7.4 (pas deux évolutions du même
    Pokémon dans le même tour) est vérifiée ici depuis ``tour.evolues_ce_tour``. La **chaîne**
    d'évolution (le bon prédécesseur imprimé, R-7.1) et la possession de la carte relèvent de
    la transition ``evoluer`` qui dispose du catalogue — on ne les approxime pas ici (D9).
    """
    if est_premier_tour_du_joueur_actif(tour):
        return refus("R-6.5", "Aucun Pokémon ne peut évoluer au premier tour de son dresseur.")
    if pokemon_entre_ce_tour(tour, base_id):
        return refus(
            "R-7.3",
            "Ce Pokémon est entré en jeu ce tour-ci : il ne peut évoluer qu'au tour suivant.",
        )
    if pokemon_evolue_ce_tour(tour, base_id):
        return refus(
            "R-7.4",
            "Ce Pokémon a déjà évolué ce tour-ci : un même Pokémon n'évolue qu'une fois par tour.",
        )
    return ACCORD


def attaque_permise(tour: Tour) -> Verdict:
    """R-6.1 — le joueur qui commence ne peut pas attaquer à son premier tour.

    La légalité complète d'une attaque (coût en énergies satisfait, choix d'une attaque de
    l'Actif R-9) appartient au lot ``j-degats-resolution`` : cette garde ne porte que la
    règle du premier tour.
    """
    if est_premier_tour_du_joueur_qui_commence(tour):
        return refus(
            "R-6.1",
            "Le joueur qui commence ne peut pas attaquer à son premier tour (il saute l'attaque).",
        )
    return ACCORD


__all__ = [
    "peut_attacher_energie",
    "peut_jouer_supporter",
    "peut_battre_retraite",
    "peut_evoluer",
    "attaque_permise",
]
