"""`pbm_game.etats` — les cinq **états spéciaux** : pose, cumul, guérison, confusion (R-11).

Paquet **pur** (aucune E/S, ni HTTP, ni base, ni React) livré par le lot ``j-etats-speciaux``.
La *forme* des états (constantes, orientation dérivée) vit dans :mod:`pbm_game.state.modele` et
leur *résolution au Checkup* (pile ou face de réveil/brûlure, compteurs de poison/brûlure dans
l'ordre R-12.2) dans :mod:`pbm_game.checkup`. Ce paquet porte ce qui restait :

* :mod:`~pbm_game.etats.matrice` — :func:`appliquer_etat` (la **matrice de cumul** R-11.8 :
  Endormi/Confus/Paralysé s'orientent et se remplacent, Brûlé/Empoisonné se cumulent),
  :func:`soigner_etats_speciaux` (la guérison de **tous** les états — passage au banc, évolution,
  effet de soin — R-11.9, **une seule porte**) et :func:`etat_bloquant_attaque` (R-11.3/R-11.6) ;
* :mod:`~pbm_game.etats.attaque` — :func:`resoudre_etats_avant_attaque` : le blocage
  Sommeil/Paralysie et le **pile ou face de confusion** à la déclaration d'attaque (R-11.5),
  branché sur la transition ``declarer_attaque``.

Le blocage de la **retraite** sous Sommeil/Paralysie (R-11.10) et la guérison **par passage au
banc** (R-11.9) sont déjà appliqués par :mod:`pbm_game.banc.mouvements` (lot ``j-retraite-banc``),
qui route désormais sa guérison par :func:`soigner_etats_speciaux`.
"""

from __future__ import annotations

from .attaque import CONFUSION_COMPTEURS, resoudre_etats_avant_attaque
from .matrice import appliquer_etat, etat_bloquant_attaque, soigner_etats_speciaux

__all__ = [
    "appliquer_etat",
    "soigner_etats_speciaux",
    "etat_bloquant_attaque",
    "CONFUSION_COMPTEURS",
    "resoudre_etats_avant_attaque",
]
