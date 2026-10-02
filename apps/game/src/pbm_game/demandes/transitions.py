"""Transitions journalisées des demandes de décision — ``repondre_demande`` et ``expirer_demande``.

Module **pur**. Une réponse de joueur, ou l'expiration d'un délai, sont des **coups journalisés**
comme les autres (« tout est rejouable ») : ce sont des :class:`~pbm_game.journal.modele.Action` qui
reprennent la résolution suspendue portée par l'état. On les enregistre dans le ``REGISTRE`` du
journal **à l'import** — le même motif que ``pbm_game.banc`` et ``pbm_game.cartes`` — pour que
``appliquer`` les reconnaisse dès que ``pbm_game`` est chargé, sans que le noyau des transitions
dépende du paquet ``demandes`` (ce qui formerait un cycle).

Le **registre des résolveurs** (quel effet sait se résoudre) est, lui,
:data:`~pbm_game.demandes.moteur.REGISTRE_EFFETS` — peuplé lui aussi à l'import (le DSL s'y
enregistre via ``pbm_game.__init__``). Reprendre une résolution, c'est re-dérouler la pile suspendue
à travers ce registre, la réponse nouvelle en main.
"""

from __future__ import annotations

from ..journal.modele import (
    ACTION_EXPIRER_DEMANDE,
    ACTION_REPONDRE_DEMANDE,
    AUTEUR_SYSTEME,
    Action,
    Evenement,
)
from ..journal.transitions import REGISTRE
from ..rng import Rng
from ..state.modele import EtatPartie
from .modele import Reponse
from .moteur import expirer, repondre


def _repondre_demande(
    etat: EtatPartie, action: Action, rng: Rng
) -> tuple[EtatPartie, list[Evenement]]:
    """Applique la réponse d'un joueur à la demande en cours (reprend la résolution suspendue).

    ``params`` : ``demande_id`` (celle à laquelle on répond) et ``choix`` (les identifiants
    d'option retenus ; liste vide = abandon d'un effet facultatif). L'``auteur`` **doit** être le
    destinataire de la demande — c'est ici qu'on refuse qu'un joueur réponde à la place de l'autre
    (le serveur fait autorité). Les autres contrôles (ensemble, cardinalité) sont faits par
    :func:`~pbm_game.demandes.moteur.repondre` via la validation du modèle.
    """
    resolution = etat.resolution
    if resolution is None:
        raise ValueError("Aucune demande en cours : « repondre_demande » n'a rien à reprendre.")
    if action.auteur != resolution.demande.destinataire:
        raise ValueError(
            f"« {action.auteur} » ne peut pas répondre à la place de "
            f"« {resolution.demande.destinataire} » (demande « {resolution.demande.id} »)."
        )
    demande_id = action.params.get("demande_id", resolution.demande.id)
    choix = action.params.get("choix", [])
    if not isinstance(choix, list) or not all(isinstance(c, str) for c in choix):
        raise ValueError("« repondre_demande » : « choix » doit être une liste de chaînes.")
    reponse = Reponse(demande_id=demande_id, choix=tuple(choix))
    return repondre(etat, reponse, rng)


def _expirer_demande(
    etat: EtatPartie, action: Action, rng: Rng
) -> tuple[EtatPartie, list[Evenement]]:
    """Applique la réponse par défaut à la demande en cours (le délai a expiré).

    Action **système** : son ``auteur`` doit être :data:`AUTEUR_SYSTEME` (l'extérieur tient
    l'horloge, lot ``j-timer``, pas un joueur). La réponse par défaut est écrite au journal par
    :func:`~pbm_game.demandes.moteur.expirer` (jamais un abandon muet).
    """
    if action.auteur != AUTEUR_SYSTEME:
        raise ValueError(
            f"« expirer_demande » est une action système : auteur attendu « {AUTEUR_SYSTEME} », "
            f"reçu « {action.auteur} »."
        )
    return expirer(etat, rng)


# Enregistrement dans le ``REGISTRE`` du journal, à l'import (motif banc/cartes).
REGISTRE[ACTION_REPONDRE_DEMANDE] = _repondre_demande
REGISTRE[ACTION_EXPIRER_DEMANDE] = _expirer_demande


__all__ = ["_repondre_demande", "_expirer_demande"]
