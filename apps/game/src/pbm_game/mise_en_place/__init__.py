"""`pbm_game.mise_en_place` — la **mise en place** d'une partie (R-4), avant le premier tour.

Paquet **pur** (aucune E/S), comme tout ``pbm_game``. Il porte la mécanique de R-4, dans l'ordre
du livret officiel (R-1.1) :

* **R-4.1** — mélange des deux decks et pioche de sept cartes ;
* **R-4.4 / R-4.6** — boucle de **mulligan** : une main d'ouverture sans Pokémon de base est
  **révélée**, remélangée, et le joueur repioche ; si **les deux** joueurs sont sans base, les deux
  recommencent **sans carte bonus** ;
* **R-4.5 / R-16.9** — pour chaque mulligan qu'un joueur prend **seul**, l'adversaire a droit à
  **une carte bonus** (comptée ici, piochée à la révélation) ;
* **R-4.2 / R-3.2** — placement de l'Actif (1 Pokémon de base, obligatoire) et du banc (≤ 5 bases),
  **face cachée** : le choix vit dans :class:`~pbm_game.mise_en_place.modele.MiseEnPlace`, jamais
  dans l'Actif/banc publics, tant que la **révélation simultanée** n'a pas eu lieu ;
* **R-4.3 / R-3.4** — six récompenses posées face cachée à la révélation.

Deux transitions, enregistrées dans le ``REGISTRE`` du journal à l'import de ce paquet (comme
``banc``, ``cartes`` et ``checkup``) :

* ``mise_en_place_initiale`` (système) — mélange, pioche de sept, boucle de mulligan : tout ce qui
  est **déterministe à partir de la graine** (aucun choix de joueur), fait d'un coup ;
* ``placer_mise_en_place`` (joueur) — chaque joueur place son Actif et son banc face cachée ; quand
  **les deux** ont placé, la même transition résout la **révélation simultanée** (actif/banc
  deviennent publics, six récompenses posées, cartes bonus piochées), et la partie commence.

``pbm_game`` importe ``mise_en_place`` à son chargement pour garantir cet enregistrement.
"""

from __future__ import annotations

from . import transitions as _transitions  # noqa: F401  (import pour effet d'enregistrement)
from .modele import (
    BANC_MAX,
    MAIN_INITIALE,
    RECOMPENSES,
    MiseEnPlace,
    PlacementCache,
    mise_en_place_depuis_json,
    mise_en_place_vers_json,
)

__all__ = [
    "BANC_MAX",
    "MAIN_INITIALE",
    "RECOMPENSES",
    "MiseEnPlace",
    "PlacementCache",
    "mise_en_place_depuis_json",
    "mise_en_place_vers_json",
]
