"""L'**état transitoire** d'une exécution de script, et la **stratégie de choix**.

Module **pur** (aucune E/S). Interpréter un script, c'est faire avancer un état de partie à
travers une liste d'instructions tout en accumulant des événements. :class:`Execution` porte ce
qui vit *le temps d'un script* : l'état courant (réaffecté à chaque primitive), les événements
produits, les verrous posés, et trois éléments transitoires — le résultat du dernier pile ou
face (pour un ``si resultat_pile``), la **sélection** en cours (le « choisis » d'un ``choisir``,
sur lequel agit son corps), et le drapeau « dégâts annulés » (pour ``annuler``).

Le **choix** d'un joueur (``choisir``, et toute position ``au_choix``) passe par une
:data:`StrategieChoix` **injectée** : une fonction pure qui, parmi des candidats, en retient
``nombre``. C'est le point de jonction, assumé et documenté, avec le lot ``j-effets-choix`` : ici
la stratégie par défaut est **déterministe** (:func:`strategie_canonique`) — ce qui rend chaque
primitive testable et le moteur rejouable dès maintenant — et un lot ultérieur la remplacera par
une vraie demande de décision (suspension de la pile). Ce n'est **pas** une approximation d'effet
(D9) : la primitive ``choisir`` est bel et bien implémentée ; c'est la *politique* de décision qui
est branchable, pas l'effet.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from ...rng import Rng
from ...state.modele import EtatPartie
from .contexte import ContexteEffet
from .selection import CibleCarte, CiblePokemon

#: Une **stratégie de choix** : parmi ``candidats``, en retenir ``nombre`` (au plus). Pure.
#: Reçoit le contexte pour qu'une stratégie fine (bot, joueur) décide selon l'état connu.
StrategieChoix = Callable[
    [list["CibleCarte | CiblePokemon"], int, ContexteEffet],
    list["CibleCarte | CiblePokemon"],
]


def _cle_stable(cible: CibleCarte | CiblePokemon) -> tuple:
    """Clé d'ordre **déterministe** d'une cible — pour que le choix canonique soit reproductible."""
    if isinstance(cible, CiblePokemon):
        return (0, cible.joueur, cible.emplacement, cible.identite)
    return (1, cible.joueur, cible.zone, cible.instance_id)


def strategie_canonique(
    candidats: list[CibleCarte | CiblePokemon], nombre: int, ctx: ContexteEffet
) -> list[CibleCarte | CiblePokemon]:
    """La stratégie **par défaut** : prendre les ``nombre`` premiers candidats, en ordre stable.

    Déterministe (donc rejouable et testable) et honnête : elle ne « triche » pas sur l'état caché
    — elle ordonne par une clé stable et tranche. Un lot ultérieur (``j-effets-choix``, bots) en
    injectera une autre sans toucher aux primitives.
    """
    ordonnes = sorted(candidats, key=_cle_stable)
    return ordonnes[: max(0, nombre)]


@dataclass
class Execution:
    """Le contexte **mutable** d'une exécution de script (le temps d'un :func:`executer_programme`).

    ``etat`` est réaffecté par chaque primitive (l'état lui-même reste figé : on remplace la
    référence). ``_budget`` est un garde-fou anti-boucle : un ``repeter`` dérivé d'un compteur
    aberrant s'arrête **bruyamment** plutôt que de tourner sans fin (même esprit que la pile).
    """

    etat: EtatPartie
    ctx: ContexteEffet
    rng: Rng
    strategie: StrategieChoix
    evenements: list = field(default_factory=list)
    verrous: list = field(default_factory=list)
    selection: tuple[CibleCarte | CiblePokemon, ...] | None = None
    dernier_pile: str | None = None
    degats_annules: bool = False
    _budget: int = 100_000

    def consommer(self) -> None:
        """Décompte une instruction exécutée ; lève si le budget est épuisé (boucle probable)."""
        self._budget -= 1
        if self._budget <= 0:
            raise ValueError(
                "Script d'effet : trop d'instructions exécutées — boucle probable, arrêt "
                "bruyant (jamais un silence)."
            )


__all__ = ["Execution", "StrategieChoix", "strategie_canonique"]
