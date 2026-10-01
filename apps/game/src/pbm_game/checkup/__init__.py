"""`pbm_game.checkup` — le **Pokémon Checkup** : la phase entre les deux tours (R-12).

Paquet **pur** (aucune E/S, ni HTTP, ni base, ni React) livré par le lot ``j-checkup``. Il
porte la **phase ordonnée** où se résolvent, dans un ordre fixé par le corpus (jamais « dans
l'ordre où le code a été écrit ») : les états spéciaux de chaque Actif (R-12.2), l'expiration
journalisée des effets « jusqu'à la fin de ce tour » (R-12.5), puis les K.O. qui en découlent
hors attaque (R-12.4) — récompenses (R-13) et promotion demandée au bon joueur (R-8.7), banc
vide = défaite (R-8.9/R-14.1).

* :mod:`~pbm_game.checkup.resolution` — :func:`resoudre_checkup` (la phase de bout en bout) et
  la transition ``checkup`` (:func:`appliquer_checkup`), enregistrée dans le ``REGISTRE`` du
  journal **à l'import** — c'est pourquoi ``pbm_game`` importe ce paquet à son chargement.

La phase s'appuie sur les primitives **partagées** de mise K.O. (:mod:`pbm_game.combat.ko`),
pour que le code de K.O. ne vive pas uniquement dans la résolution d'attaque.
"""

from __future__ import annotations

from .resolution import (
    BRULURE_DEGATS,
    POISON_DEGATS,
    appliquer_checkup,
    resoudre_checkup,
)

__all__ = [
    "POISON_DEGATS",
    "BRULURE_DEGATS",
    "resoudre_checkup",
    "appliquer_checkup",
]
