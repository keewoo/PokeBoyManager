"""`pbm_game.journal` — le **journal d'actions** : une partie est sa suite de coups.

Paquet **pur** (aucune E/S, ni HTTP, ni base, ni React) livré par le lot
``j-journal-actions``. Il porte le principe « tout est rejouable » du jalon J1 : une
partie est un **état initial**, une **graine** et un **journal d'actions numéroté** ;
rejouer le journal redonne exactement le même état.

* :mod:`~pbm_game.journal.modele` — :class:`Action`, :class:`Evenement`, :class:`Entree`,
  :class:`Partie`, :class:`Instantane` et le format versionné (:data:`JOURNAL_VERSION`) ;
* :mod:`~pbm_game.journal.empreinte` — :func:`empreinte` d'un état (divergence au coup près) ;
* :mod:`~pbm_game.journal.transitions` — :func:`appliquer` ``(etat, action, rng)`` →
  ``(etat, evenements)``, :func:`jouer`, :func:`partie_neuve` et le :data:`REGISTRE` des
  transitions mécaniques (mélange, pioche, phases) ;
* :mod:`~pbm_game.journal.rejeu` — :func:`rejouer`, :func:`compacter`, :func:`reprendre`
  (instantané + queue) et :class:`RejeuDivergent` ;
* :mod:`~pbm_game.journal.serialisation` — ``*_vers_json`` / ``*_depuis_json`` (round-trip exact) ;
* :mod:`~pbm_game.journal.debogage` — :func:`decrire_entree` : une entrée lisible par un
  humain, identifiants de cartes résolus en noms.

Format pour une réimplémentation indépendante : ``docs/jeu/JOURNAL.md``.
"""

from __future__ import annotations

from .debogage import decrire_entree, decrire_journal, resoudre_id
from .empreinte import empreinte
from .modele import (
    ACTION_ABANDONNER,
    ACTION_ATTACHER_ENERGIE,
    ACTION_AVANCER_PHASE,
    ACTION_CHECKUP,
    ACTION_DEBUT_TOUR,
    ACTION_DECLARER_ATTAQUE,
    ACTION_ECHANGE_FORCE,
    ACTION_MELANGER_PIOCHE,
    ACTION_PIOCHER,
    ACTION_PROMOUVOIR,
    ACTION_RETRAITE,
    AUTEUR_SYSTEME,
    EVT_ATTAQUE_DECLAREE,
    EVT_CARTES_PIOCHEES,
    EVT_CONFUSION,
    EVT_DEGATS,
    EVT_ECHANGE_FORCE,
    EVT_EFFET_EXPIRE,
    EVT_ENERGIE_ATTACHEE,
    EVT_ETAT_CHECKUP,
    EVT_KO,
    EVT_PARTIE_TERMINEE,
    EVT_PHASE_AVANCEE,
    EVT_PIOCHE_MELANGEE,
    EVT_PROMOTION,
    EVT_PROMOTION_REQUISE,
    EVT_RETRAITE,
    EVT_TOUR_COMMENCE,
    JOURNAL_VERSION,
    RAISON_ABANDON,
    RAISON_DERNIERE_RECOMPENSE,
    RAISON_PIOCHE_IMPOSSIBLE,
    RAISON_PLUS_DE_POKEMON,
    Action,
    Entree,
    Evenement,
    Instantane,
    Partie,
)
from .rejeu import (
    RejeuDivergent,
    compacter,
    rejouer,
    reprendre,
    reprendre_partie,
)
from .serialisation import (
    action_depuis_json,
    action_vers_json,
    entree_depuis_json,
    entree_vers_json,
    evenement_depuis_json,
    evenement_vers_json,
    instantane_depuis_json,
    instantane_vers_json,
    partie_depuis_json,
    partie_vers_json,
)
from .transitions import REGISTRE, appliquer, jouer, partie_neuve

__all__ = [
    # format / version
    "JOURNAL_VERSION",
    "AUTEUR_SYSTEME",
    "RAISON_ABANDON",
    "RAISON_DERNIERE_RECOMPENSE",
    "RAISON_PIOCHE_IMPOSSIBLE",
    "RAISON_PLUS_DE_POKEMON",
    # modèle
    "Action",
    "Evenement",
    "Entree",
    "Partie",
    "Instantane",
    # types d'action / d'événement
    "ACTION_MELANGER_PIOCHE",
    "ACTION_PIOCHER",
    "ACTION_AVANCER_PHASE",
    "ACTION_ATTACHER_ENERGIE",
    "ACTION_ABANDONNER",
    "ACTION_DEBUT_TOUR",
    "ACTION_DECLARER_ATTAQUE",
    "ACTION_RETRAITE",
    "ACTION_PROMOUVOIR",
    "ACTION_ECHANGE_FORCE",
    "ACTION_CHECKUP",
    "EVT_PIOCHE_MELANGEE",
    "EVT_CARTES_PIOCHEES",
    "EVT_PHASE_AVANCEE",
    "EVT_TOUR_COMMENCE",
    "EVT_ATTAQUE_DECLAREE",
    "EVT_ENERGIE_ATTACHEE",
    "EVT_CONFUSION",
    "EVT_DEGATS",
    "EVT_PARTIE_TERMINEE",
    "EVT_RETRAITE",
    "EVT_PROMOTION",
    "EVT_ECHANGE_FORCE",
    "EVT_ETAT_CHECKUP",
    "EVT_EFFET_EXPIRE",
    "EVT_KO",
    "EVT_PROMOTION_REQUISE",
    # application
    "appliquer",
    "jouer",
    "partie_neuve",
    "REGISTRE",
    # empreinte
    "empreinte",
    # rejeu / compaction
    "rejouer",
    "compacter",
    "reprendre",
    "reprendre_partie",
    "RejeuDivergent",
    # sérialisation
    "action_vers_json",
    "action_depuis_json",
    "evenement_vers_json",
    "evenement_depuis_json",
    "entree_vers_json",
    "entree_depuis_json",
    "partie_vers_json",
    "partie_depuis_json",
    "instantane_vers_json",
    "instantane_depuis_json",
    # débogage
    "decrire_entree",
    "decrire_journal",
    "resoudre_id",
]
