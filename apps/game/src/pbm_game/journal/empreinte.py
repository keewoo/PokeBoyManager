"""Empreinte d'un état de partie — une divergence se détecte **au coup près**.

Pur : ``str``/``bytes`` en entrée et en sortie, aucune E/S (ni fichier, ni réseau). On
réutilise la sérialisation **déterministe** de l'état (:func:`~pbm_game.state.vers_json`,
qui trie déjà les ensembles) et on en prend une empreinte SHA-256 sur une forme JSON
**canonique** (clés triées, séparateurs compacts) : deux états égaux donnent la même
empreinte, deux états différents des empreintes différentes.

L'empreinte porte sur l'**état de jeu** (``EtatPartie``) seul — pas sur l'aléatoire :
une divergence d'aléatoire se voit, elle, dans le journal de tirages du
:class:`~pbm_game.rng.Rng` et son vérificateur commit-reveal. Les deux contrôles sont
complémentaires : l'un garde l'état, l'autre garde le hasard.
"""

from __future__ import annotations

import hashlib
import json

from ..state.modele import EtatPartie
from ..state.serialisation import vers_json


def empreinte(etat: EtatPartie) -> str:
    """L'empreinte SHA-256 (hex) de ``etat``, stable et déterministe.

    La forme canonique est ``json.dumps(..., sort_keys=True, separators=(",", ":"))`` du
    JSON déjà déterministe de l'état : aucun flottant, aucun ensemble non trié ne peut
    rendre deux empreintes d'un même état différentes.
    """
    canonique = json.dumps(
        vers_json(etat),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonique.encode("utf-8")).hexdigest()
