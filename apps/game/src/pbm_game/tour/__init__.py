"""`pbm_game.tour` — la **machine à tour** : phases, drapeaux « une fois par tour », fenêtres.

Paquet **pur** (aucune E/S, ni HTTP, ni base, ni React) livré par le lot ``j-machine-tour``.
Il porte le **squelette du déroulé d'un tour** (R-5, R-6, R-12) : les prédicats et marqueurs
des drapeaux de tour, les six contraintes en verdicts motivés, et les fenêtres de
déclenchement que la pile d'effets remplira plus tard.

* :mod:`~pbm_game.tour.drapeaux` — prédicats bruts (« l'énergie est-elle posée ? », « est-ce
  le premier tour ? ») et marqueurs qui lèvent un drapeau ; **sans dépendance** à
  ``pbm_game.actions``, pour que ``pbm_game.journal.transitions`` puisse l'importer ;
* :mod:`~pbm_game.tour.fenetres` — :func:`~pbm_game.tour.fenetres.declencher` et les fenêtres
  ``début de tour`` / ``fin de tour`` (vides au jalon J1, mais câblées) ;
* :mod:`~pbm_game.tour.contraintes` — les six contraintes de tour en
  :class:`~pbm_game.actions.Verdict` motivés. **Importé depuis son sous-module**
  (``from pbm_game.tour.contraintes import …``) et volontairement **pas ré-exporté ici** :
  il dépend de ``pbm_game.actions``, dont l'import précoce par ce ``__init__`` créerait un
  cycle avec ``pbm_game.journal.transitions`` (qui importe ce paquet pour les fenêtres).

Le début de tour (pioche obligatoire, défaite sur pioche impossible) et la fin de tour
(déclarer une attaque) sont des **transitions journalisées** : elles vivent dans
``pbm_game.journal.transitions`` avec les autres, et ouvrent ici les fenêtres correspondantes.
"""

from __future__ import annotations

from .drapeaux import (
    est_premier_tour_du_joueur_actif,
    est_premier_tour_du_joueur_qui_commence,
    identite_pokemon,
    marquer_energie_posee,
    marquer_entree_en_jeu,
    marquer_retraite_faite,
    marquer_supporter_joue,
    pokemon_entre_ce_tour,
)
from .fenetres import (
    DECLENCHEURS,
    FENETRE_DEBUT_TOUR,
    FENETRE_FIN_TOUR,
    FENETRES,
    Declencheur,
    declencher,
)

__all__ = [
    # drapeaux
    "identite_pokemon",
    "est_premier_tour_du_joueur_qui_commence",
    "est_premier_tour_du_joueur_actif",
    "pokemon_entre_ce_tour",
    "marquer_energie_posee",
    "marquer_supporter_joue",
    "marquer_retraite_faite",
    "marquer_entree_en_jeu",
    # fenêtres
    "FENETRE_DEBUT_TOUR",
    "FENETRE_FIN_TOUR",
    "FENETRES",
    "Declencheur",
    "DECLENCHEURS",
    "declencher",
]
