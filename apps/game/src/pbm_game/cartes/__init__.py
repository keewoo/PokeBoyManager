"""`pbm_game.cartes` — les cartes Pokémon jouables depuis le catalogue (lot ``j-cartes-pokemon``).

Paquet **pur** (aucune E/S). Il porte :

* :mod:`~pbm_game.cartes.modele` — :class:`~pbm_game.cartes.modele.DefinitionCarte` et
  :class:`~pbm_game.cartes.modele.AttaqueDef`, la **forme** des caractéristiques d'une carte
  (stade, PV, type, faiblesse, résistance, coût de retraite, marqueur de règle, attaques) que le
  service extrait du catalogue — jamais écrite en dur dans le moteur (D9) ;
* :mod:`~pbm_game.cartes.transitions` — les transitions **poser** et **evoluer** (R-5.3, R-7),
  enregistrées dans le ``REGISTRE`` du journal à l'import de ce paquet.

Importer ``pbm_game.cartes`` **enregistre** les transitions : ``pbm_game`` le fait à son
chargement, comme pour ``banc`` et ``checkup``.
"""

from __future__ import annotations

from . import transitions as _transitions  # noqa: F401  (import pour effet d'enregistrement)
from .modele import (
    STADE_1,
    STADE_2,
    STADE_BASE,
    STADES,
    STADES_EVOLUTION,
    AttaqueDef,
    DefinitionCarte,
    definition_depuis_dict,
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
]
