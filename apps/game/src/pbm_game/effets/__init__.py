"""`pbm_game.effets` — l'**architecture d'effets** qui accueille toutes les cartes.

Lot ``j-effets-architecture`` (jalon J2). Module **pur** (aucune E/S), comme tout le moteur.
Il ne script **aucune** carte (D9) : il livre le *cadre* sur lequel les lots suivants
(``j-effets-dsl``, ``j-cartes-outils``, ``j-cartes-stades``, ``j-cartes-talents``,
``j-cartes-attaques-effets``) brancheront chaque effet, scripté et testé.

Quatre pièces, et un pont vers le socle :

* :mod:`~pbm_game.effets.evenements` — le vocabulaire fermé des **moments de jeu**
  (:class:`~pbm_game.effets.evenements.EvenementJeu`), dérivé d'un dépouillement de 200 cartes
  réelles ;
* :mod:`~pbm_game.effets.pile` — la **pile d'effets** résolue en LIFO
  (:class:`~pbm_game.effets.pile.PileEffets`), chaque résolution journalisée avec sa source ;
* :mod:`~pbm_game.effets.continus` — les **effets continus** comme modificateurs *dérivés* de
  ce qui est en jeu, jamais comme mutations (leur retrait restaure le calcul par construction) ;
* :mod:`~pbm_game.effets.verrous` — les **verrous nommés** et leurs portées (« pas de Supporter
  ce tour », « ce Pokémon ne peut pas attaquer », « les talents sont sans effet ») ;
* :mod:`~pbm_game.effets.bus` — le **bus d'événements** et son pont ``declencheur_fenetre``,
  qui branche la pile sur les fenêtres **existantes** du socle sans en modifier une ligne.

Importer ce paquet n'a **aucun effet de bord** : il n'enregistre rien globalement (ni dans
``REGISTRE``, ni dans ``DECLENCHEURS``), pour que le comportement du socle reste strictement
inchangé tant qu'aucun effet n'est câblé. Le branchement se fait explicitement, par injection.
"""

from __future__ import annotations

from .bus import Bus, Reacteur, declencheur_fenetre
from .continus import (
    FACE_ATTAQUANT,
    FACE_DEFENSEUR,
    EffetContinu,
    RegistreContinus,
    collecter_effets_continus,
    modificateurs_degats,
    seuil_ko,
)
from .evenements import (
    EVENEMENTS_JEU,
    MECANISMES,
    EvenementJeu,
)
from .pile import (
    EffetEnAttente,
    PileEffets,
    RegistreEffets,
    SourceEffet,
    resoudre_pile,
)
from .verrous import (
    VERROUS,
    VERROUS_VIDES,
    JeuDeVerrous,
    Verrou,
)

__all__ = [
    "Bus",
    "Reacteur",
    "declencheur_fenetre",
    "EvenementJeu",
    "EVENEMENTS_JEU",
    "MECANISMES",
    "PileEffets",
    "EffetEnAttente",
    "SourceEffet",
    "RegistreEffets",
    "resoudre_pile",
    "EffetContinu",
    "FACE_ATTAQUANT",
    "FACE_DEFENSEUR",
    "RegistreContinus",
    "collecter_effets_continus",
    "modificateurs_degats",
    "seuil_ko",
    "Verrou",
    "JeuDeVerrous",
    "VERROUS",
    "VERROUS_VIDES",
]
