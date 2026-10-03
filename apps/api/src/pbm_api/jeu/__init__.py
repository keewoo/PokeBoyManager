"""`pbm_api.jeu` — le pont entre le **catalogue** (base) et le **moteur de jeu** pur (``pbm_game``).

Le moteur ``pbm_game`` ne connaît ni base ni HTTP (principe du jalon J1) : il reçoit des
**descripteurs** déjà extraits du catalogue. Ce paquet est l'adaptateur qui lit une carte du
catalogue et fabrique le :class:`~pbm_game.cartes.modele.DefinitionCarte` que le moteur consomme —
c'est ici, et pas dans le moteur, que vit la **connaissance des colonnes du catalogue** (attacks,
weaknesses, resistances, retreat_cost, prize_marker…).
"""

from __future__ import annotations

from pbm_api.jeu.catalogue import definition_depuis_card, definition_energie_depuis_card

__all__ = ["definition_depuis_card", "definition_energie_depuis_card"]
