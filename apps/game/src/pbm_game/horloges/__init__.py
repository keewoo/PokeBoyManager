"""Horloges d'une partie (lot ``j-timer``) — temps par tour, par joueur, par décision.

Paquet **pur** (aucune E/S, aucune horloge système), comme tout ``pbm_game`` :

* :mod:`pbm_game.horloges.modele` — les structures sérialisables (:class:`ConfigHorloges`,
  :class:`EtatHorloges`) : une horloge est une **donnée** portée par la partie, jamais un minuteur ;
* :mod:`pbm_game.horloges.calcul` — les fonctions pures de décompte, bascule, pause/reprise et
  détection d'expiration, toutes recalculant le temps restant depuis un instant fourni ;
* :mod:`pbm_game.horloges.transitions_temps` — les coups journalisés des expirations (``fin_tour``,
  ``defaite_temps``), enregistrés dans le ``REGISTRE`` du journal **à l'import** de ce paquet.

Importer ``pbm_game.horloges`` suffit donc à rendre ces transitions reconnues par
``pbm_game.journal.appliquer`` (c'est pourquoi ``pbm_game.__init__`` l'importe pour effet).
"""

from __future__ import annotations

# Import pour effet d'enregistrement : ``transitions_temps`` branche ``fin_tour`` /
# ``defaite_temps``
# dans le ``REGISTRE`` du journal dès que ce paquet est importé (motif banc/cartes/demandes).
from . import transitions_temps as _transitions_temps  # noqa: F401,E402
from .calcul import (
    arreter,
    basculer,
    demarrer,
    ecoule,
    lever_decision,
    pause,
    pause_expiree,
    pause_restante,
    poser_decision,
    premiere_echeance,
    reprendre,
    restant,
)
from .modele import (
    CAUSE_BUDGET,
    CAUSE_DECISION,
    CAUSE_TOUR,
    GENRE_DECISION,
    GENRE_TOUR,
    CompteurActif,
    ConfigHorloges,
    EtatHorloges,
)

__all__ = [
    "ConfigHorloges",
    "EtatHorloges",
    "CompteurActif",
    "GENRE_TOUR",
    "GENRE_DECISION",
    "CAUSE_TOUR",
    "CAUSE_DECISION",
    "CAUSE_BUDGET",
    "demarrer",
    "ecoule",
    "basculer",
    "poser_decision",
    "lever_decision",
    "arreter",
    "pause",
    "reprendre",
    "pause_restante",
    "pause_expiree",
    "restant",
    "premiere_echeance",
]
