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


def _id_cible(cible: CibleCarte | CiblePokemon) -> str:
    """L'identifiant d'option **stable** d'une cible, pour l'exposer dans une demande de décision.

    Une :class:`~pbm_game.effets.dsl.selection.CibleCarte` s'identifie par son ``instance_id`` ; un
    :class:`~pbm_game.effets.dsl.selection.CiblePokemon` par l'``instance_id`` de sa carte de base
    (identité stable à l'évolution) — les mêmes identités que le reste du moteur manipule.
    """
    return cible.identite if isinstance(cible, CiblePokemon) else cible.instance_id


def strategie_demande(
    gestionnaire,
    *,
    destinataire: str,
    regle: str,
    libelle: str = "Choix d'une cible",
    obligatoire: bool = True,
    delai_ms: int | None = None,
):
    """Fabrique une :data:`StrategieChoix` qui transforme chaque ``choisir`` en **demande réelle**.

    C'est le point de jonction, enfin branché, entre le DSL et les demandes de décision : au lieu de
    trancher elle-même (comme :func:`strategie_canonique`), cette stratégie **réclame** le choix au
    :class:`~pbm_game.demandes.gestionnaire.Gestionnaire` (import local pour ne pas coupler le DSL
    paquet ``demandes`` à l'import). Si la décision est déjà connue (reprise), elle renvoie les
    cibles correspondantes ; sinon le gestionnaire lève la suspension, qui remonte jusqu'au moteur.

    Ce n'est **pas** une approximation d'effet (D9) : la primitive ``choisir`` reste exactement ce
    qu'elle était ; seule change la *politique* de décision, qui était déjà conçue pour être
    branchable. ``destinataire`` est le joueur qui tranche (par défaut celui qui joue l'effet ;
    un effet qui fait choisir l'**adversaire** le passera explicitement).
    """
    from ...demandes.modele import CAT_CARTE, CAT_CARTES, DemandeDecision

    def strategie(
        candidats: list[CibleCarte | CiblePokemon], nombre: int, ctx: ContexteEffet
    ) -> list[CibleCarte | CiblePokemon]:
        options = tuple(_id_cible(c) for c in candidats)
        combien = min(max(1, nombre), len(candidats))
        demande = DemandeDecision(
            destinataire=destinataire,
            categorie=CAT_CARTE if combien == 1 else CAT_CARTES,
            source=ctx.source,
            regle=regle or "R-9.3",
            libelle=libelle,
            options=options,
            minimum=combien,
            maximum=combien,
            obligatoire=obligatoire,
            delai_ms=delai_ms,
            temps_restant_ms=delai_ms,
        )
        reponse = gestionnaire.demander(demande)  # lève SuspensionDemande si la décision est neuve
        par_id = {_id_cible(c): c for c in candidats}
        return [par_id[i] for i in reponse.choix]

    return strategie


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
