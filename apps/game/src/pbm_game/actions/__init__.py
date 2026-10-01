"""`pbm_game.actions` — le **générateur d'actions légales** : ce qui est jouable, et pourquoi.

Paquet **pur** (aucune E/S, ni HTTP, ni base, ni React) livré par le lot
``j-actions-legales``. Il répond à deux questions, et à elles seules il confie les règles
du jeu — l'interface n'a plus à les connaître, elle affiche ce qu'on lui donne :

* :func:`actions_legales` ``(etat, joueur)`` — la liste exhaustive des coups possibles,
  chacun avec ses cibles valides et une étiquette lisible ;
* :func:`valider` ``(etat, action)`` — l'accord, ou un refus motivé par une règle citée
  (``R-14.6 : la partie est terminée``). Toute action y passe, y compris celles du serveur.

**Une seule source de vérité** : la liste. La validation vérifie l'appartenance à cette
liste, jamais une seconde dérivation de la légalité (voir :mod:`.generateur`).

* :mod:`~pbm_game.actions.modele` — :class:`Cible`, :class:`ActionLegale`, :class:`Verdict` ;
* :mod:`~pbm_game.actions.generateur` — :func:`actions_legales`, :func:`valider`, la
  :class:`Famille` et le registre :data:`FAMILLES_DEFAUT` qu'étendent les lots de résolution.

Format et périmètre documentés pour la suite : ``docs/jeu/ACTIONS.md``.
"""

from __future__ import annotations

from .generateur import (
    FAMILLES_DEFAUT,
    Famille,
    FamilleAbandonner,
    FamilleAvancerPhase,
    actions_legales,
    valider,
)
from .modele import (
    ACCORD,
    GENRE_CARTE_MAIN,
    GENRE_JOUEUR,
    GENRE_POKEMON_EN_JEU,
    ActionLegale,
    Cible,
    Verdict,
    refus,
)

__all__ = [
    # modèle
    "Cible",
    "ActionLegale",
    "Verdict",
    "ACCORD",
    "refus",
    "GENRE_JOUEUR",
    "GENRE_POKEMON_EN_JEU",
    "GENRE_CARTE_MAIN",
    # générateur
    "actions_legales",
    "valider",
    "Famille",
    "FamilleAvancerPhase",
    "FamilleAbandonner",
    "FAMILLES_DEFAUT",
]
