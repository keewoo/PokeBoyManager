"""`pbm_game.state` — l'état d'une partie : zones, attachements, compteurs, vues par joueur.

Paquet **pur** (aucune E/S, ni HTTP, ni base, ni React) livré par le lot ``j-modele-etat``.
Il porte la **forme** de l'état et sa séparation information publique / information cachée ;
il n'expose aucune méthode de mutation — toute mutation passera par une action journalisée
(lots suivants), pour que la partie reste rejouable.

* :mod:`~pbm_game.state.modele` — les dataclasses figées (``EtatPartie``, ``Joueur``,
  ``PokemonEnJeu``, ``Tour``, ``Carte``) et les constantes de règle ;
* :mod:`~pbm_game.state.serialisation` — ``vers_json`` / ``depuis_json`` (round-trip exact) ;
* :mod:`~pbm_game.state.projection` — ``vue(etat, joueur)`` : ce qu'un joueur a le droit
  de savoir, sans fuite d'information cachée ;
* :mod:`~pbm_game.state.invariants` — ``verifier`` / ``assert_invariants``.
"""

from __future__ import annotations

from .invariants import (
    InvariantViole,
    assert_invariants,
    total_cartes_joueur,
    toutes_les_cartes,
    verifier,
)
from .modele import (
    BRULE,
    CONFUS,
    EMPOISONNE,
    ENDORMI,
    ETATS_MARQUEUR,
    ETATS_ORIENTATION,
    ETATS_SPECIAUX,
    ORIENTATION_NORMALE,
    PARALYSE,
    PHASE_ATTAQUE,
    PHASE_CHECKUP,
    PHASE_PIOCHE,
    PHASE_PRINCIPALE,
    PHASES,
    RAISON_EGALITE,
    SCHEMA_VERSION,
    Carte,
    EtatPartie,
    Joueur,
    PokemonEnJeu,
    Tour,
    carte_active,
    orientation,
)
from .projection import vue
from .serialisation import depuis_json, vers_json

__all__ = [
    # modèle
    "SCHEMA_VERSION",
    "Carte",
    "PokemonEnJeu",
    "Joueur",
    "Tour",
    "EtatPartie",
    "orientation",
    "carte_active",
    # constantes d'état / de tour
    "ENDORMI",
    "BRULE",
    "CONFUS",
    "PARALYSE",
    "EMPOISONNE",
    "ETATS_SPECIAUX",
    "ETATS_ORIENTATION",
    "ETATS_MARQUEUR",
    "ORIENTATION_NORMALE",
    "PHASE_PIOCHE",
    "PHASE_PRINCIPALE",
    "PHASE_ATTAQUE",
    "PHASE_CHECKUP",
    "PHASES",
    "RAISON_EGALITE",
    # sérialisation
    "vers_json",
    "depuis_json",
    # projection
    "vue",
    # invariants
    "verifier",
    "assert_invariants",
    "toutes_les_cartes",
    "total_cartes_joueur",
    "InvariantViole",
]
