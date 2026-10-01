"""`pbm_game.banc` — le Pokémon Actif **change de place** : retraite, promotion, échange forcé.

Paquet **pur** (aucune E/S, ni HTTP, ni base, ni React) livré par le lot ``j-retraite-banc``.
Il mécanise le geste défensif du jeu et distingue **trois mouvements** aux règles différentes
(R-8), que l'on aurait tort de confondre :

* :func:`~pbm_game.banc.mouvements.battre_en_retraite` — **volontaire** (R-8.2/R-8.3/R-8.4) :
  défausser une énergie par symbole du coût (au choix du joueur), une fois par tour, interdit
  sous Sommeil ou Paralysie ;
* :func:`~pbm_game.banc.mouvements.promouvoir` — **obligatoire** après un K.O. (R-8.7), **banc
  vide = défaite** (R-8.9/R-14.1) ;
* :func:`~pbm_game.banc.mouvements.echange_force` — provoqué par un **effet** (R-8.8) : sans coût
  ni consommation de la retraite du tour, autorisé même sous état (R-16.12).

Toutes trois passent par le **passage au banc** (R-8.6) : le Pokémon qui descend perd ses états
spéciaux et les effets d'attaque, mais garde énergies, Outil, compteurs et pile d'évolutions.

Les trois sont des **transitions journalisées** (rejouables) : leurs gestionnaires
(``appliquer_*``) s'enregistrent eux-mêmes dans le ``REGISTRE`` du journal au chargement de
:mod:`pbm_game.banc.mouvements` (``pbm_game`` importe ce paquet pour le garantir).
"""

from __future__ import annotations

from .mouvements import (
    appliquer_echange_force,
    appliquer_promotion,
    appliquer_retraite,
    battre_en_retraite,
    echange_force,
    promouvoir,
)

__all__ = [
    "battre_en_retraite",
    "promouvoir",
    "echange_force",
    "appliquer_retraite",
    "appliquer_promotion",
    "appliquer_echange_force",
]
