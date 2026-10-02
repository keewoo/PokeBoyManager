"""`pbm_game.cartes` — les cartes jouables depuis le catalogue (Pokémon et Énergies).

Paquet **pur** (aucune E/S). Il porte :

* :mod:`~pbm_game.cartes.modele` — :class:`~pbm_game.cartes.modele.DefinitionCarte` et
  :class:`~pbm_game.cartes.modele.AttaqueDef`, la **forme** des caractéristiques d'une carte
  Pokémon (stade, PV, type, faiblesse, résistance, coût de retraite, marqueur de règle,
  attaques) que le service extrait du catalogue — jamais écrite en dur dans le moteur (D9) ;
* :mod:`~pbm_game.cartes.energie` — :class:`~pbm_game.cartes.energie.DefinitionEnergie` (lot
  ``j-cartes-energies``) : la **capacité** d'une carte Énergie — ce qu'elle **fournit** (types
  et quantités, R-9.2) et les **effets** qu'une spéciale apporte, empilables sur la pile
  d'effets. La distinction « de base / spéciale » (légalité, D10) reste au service des decks ;
* :mod:`~pbm_game.cartes.transitions` — les transitions **poser** et **evoluer** (R-5.3, R-7),
  enregistrées dans le ``REGISTRE`` du journal à l'import de ce paquet.

Importer ``pbm_game.cartes`` **enregistre** les transitions : ``pbm_game`` le fait à son
chargement, comme pour ``banc`` et ``checkup``.
"""

from __future__ import annotations

from . import transitions as _transitions  # noqa: F401  (import pour effet d'enregistrement)
from .energie import (
    DefinitionEnergie,
    EffetEnergie,
    definition_energie_depuis_dict,
)
from .modele import (
    STADE_1,
    STADE_2,
    STADE_BASE,
    STADES,
    STADES_EVOLUTION,
    AttaqueDef,
    DefinitionCarte,
    definition_depuis_dict,
    definition_vers_dict,
)

__all__ = [
    "STADE_BASE",
    "STADE_1",
    "STADE_2",
    "STADES",
    "STADES_EVOLUTION",
    "AttaqueDef",
    "DefinitionCarte",
    "definition_depuis_dict",
    "definition_vers_dict",
    "EffetEnergie",
    "DefinitionEnergie",
    "definition_energie_depuis_dict",
]
