"""`pbm_game.combat` — la **résolution d'attaque** : coût, dégâts, faiblesse, résistance.

Paquet **pur** (aucune E/S, ni HTTP, ni base, ni React) livré par le lot
``j-degats-resolution``. C'est le geste central du jeu, et celui dont le calcul est le plus
souvent faux : l'ordre des opérations entre faiblesse, résistance et modificateurs change le
résultat. On suit donc **à la lettre** l'ordre strict du corpus (``docs/jeu/REGLES.md`` §R-10).

* :mod:`~pbm_game.combat.modele` — les descripteurs : :class:`CoutAttaque`, :class:`Faiblesse`,
  :class:`Resistance`, :class:`Modificateur` (point d'accroche nommé d'une étape), et le
  :class:`ResultatDegats` avec sa trace et son **détail lisible** (R-10.9) ;
* :mod:`~pbm_game.combat.cout` — :func:`cout_satisfait` : l'Actif porte-t-il de quoi payer
  l'attaque (colorés, incolores, énergies multi-unités) ? (R-9.1, R-9.2) ;
* :mod:`~pbm_game.combat.resolution` — :func:`resoudre_degats` (l'ordre strict R-10.1),
  :func:`poser_degats` / :func:`poser_compteurs` (en **compteurs**, jamais en PV — R-10.4) et
  :func:`evenement_degats` (le détail porté par le journal).

**Périmètre au palier 6 (ce lot).** Le moteur ne connaît **pas encore** les données de carte
(type d'une énergie, coût imprimé, faiblesse d'un Pokémon, attaques) : elles arrivent avec
``j-cartes-pokemon`` (que ce lot débloque). Ce lot livre donc le **calcul** et ses crochets ;
il reçoit des **descripteurs** déjà extraits du catalogue et ne devine rien (D9).
"""

from __future__ import annotations

from .cout import cout_satisfait, pool_energies
from .modele import (
    FAIBLESSE_FACTEUR_DEFAUT,
    INCOLORE,
    OP_AJOUT,
    OP_FIXE,
    OP_MULTIPLIE,
    OPERATIONS,
    RESISTANCE_REDUCTION_DEFAUT,
    CoutAttaque,
    EtapeCalcul,
    Faiblesse,
    Modificateur,
    Resistance,
    ResultatDegats,
    modificateur_ajout,
    modificateur_fixe,
    modificateur_multiplie,
)
from .resolution import evenement_degats, poser_compteurs, poser_degats, resoudre_degats

__all__ = [
    # modèle
    "INCOLORE",
    "FAIBLESSE_FACTEUR_DEFAUT",
    "RESISTANCE_REDUCTION_DEFAUT",
    "OP_AJOUT",
    "OP_MULTIPLIE",
    "OP_FIXE",
    "OPERATIONS",
    "CoutAttaque",
    "Faiblesse",
    "Resistance",
    "Modificateur",
    "modificateur_ajout",
    "modificateur_multiplie",
    "modificateur_fixe",
    "EtapeCalcul",
    "ResultatDegats",
    # coût
    "cout_satisfait",
    "pool_energies",
    # résolution
    "resoudre_degats",
    "poser_degats",
    "poser_compteurs",
    "evenement_degats",
]
