"""Clôtures **forcées** d'une partie — ``deserter`` et ``expirer_inactivite`` (lot
``j-deconnexion-abandon``).

Module **pur**. Comme pour les expirations d'horloge (:mod:`pbm_game.horloges.transitions_temps`),
l'extérieur (le service de parties) décide *quand* clore — il tient le temps, les déconnexions et le
balayage ; mais l'**effet** d'une clôture est un **coup journalisé** comme les autres (« tout est
rejouable »), pour que la fin survive à un F5 et que l'historique porte son motif. On enregistre ces
transitions dans le ``REGISTRE`` du journal **à l'import** — motif ``banc``/``cartes``/``demandes``/
``horloges`` — sans que le noyau des transitions dépende de ce module (pas de cycle).

Deux clôtures, qui prolongent l'abandon volontaire (R-14.3, ``abandonner``) pour les deux cas que ce
lot distingue (« leurs conséquences ne sont pas les mêmes ») :

* :data:`~pbm_game.journal.modele.ACTION_DESERTER` — un joueur déconnecté n'est pas revenu avant la
  fin de son délai de grâce : **forfait**. ``params["joueur"]`` nomme le déserteur, l'adversaire
  gagne, raison :data:`~pbm_game.journal.modele.RAISON_DESERTION`. Terminale, comme l'abandon et la
  défaite au temps ;
* :data:`~pbm_game.journal.modele.ACTION_EXPIRER_INACTIVITE` — une partie fantôme (plus personne ne
  joue) close par le balayage périodique : **aucun vainqueur** (``vainqueur=None``), raison
  :data:`~pbm_game.journal.modele.RAISON_INACTIVITE`. Ce n'est pas une fin méritée mais un ménage —
  mais il est **journalisé** : « aucune partie ne reste suspendue », et jamais un nettoyage muet
  (risque nommé du lot).

Une clôture **produit toujours un coup journalisé, jamais un effacement silencieux** (critère
d'acceptation : « chaque clôture automatique porte son motif dans le journal et dans
l'historique »).
"""

from __future__ import annotations

from dataclasses import replace

from .journal.modele import (
    ACTION_DESERTER,
    ACTION_EXPIRER_INACTIVITE,
    AUTEUR_SYSTEME,
    EVT_PARTIE_TERMINEE,
    RAISON_DESERTION,
    RAISON_INACTIVITE,
    Action,
    Evenement,
)
from .journal.transitions import REGISTRE
from .rng import Rng
from .state.modele import EtatPartie


def _autre_joueur(etat: EtatPartie, jid: str) -> str:
    """L'identifiant de l'autre joueur, ou ``ValueError`` si ``jid`` n'est pas de la partie."""
    a, b = etat.joueurs[0].id, etat.joueurs[1].id
    if jid == a:
        return b
    if jid == b:
        return a
    raise ValueError(f"Joueur « {jid} » absent de la partie.")


def _deserter(
    etat: EtatPartie, action: Action, rng: Rng
) -> tuple[EtatPartie, list[Evenement]]:
    """Désertion : le joueur déconnecté qui n'est pas revenu **perd par forfait** (R-14.6).

    Action **système** : son ``auteur`` doit être :data:`AUTEUR_SYSTEME` (un délai de grâce expire,
    ce n'est pas un coup de joueur), et ``params["joueur"]`` nomme le **déserteur** (celui qui ne
    revient pas). L'adversaire devient vainqueur, raison :data:`RAISON_DESERTION`. Refuse une partie
    déjà terminée (R-14.6) et un déserteur qui n'est pas de la partie (``_autre_joueur`` lève alors)
    — jamais de repli silencieux. Permise même pendant une demande en cours (comme l'abandon et la
    défaite au temps) : un joueur peut déserter pendant que l'adversaire décide.
    """
    if etat.terminee:
        raise ValueError(
            "Partie terminée : plus aucune action, la désertion comprise (R-14.6)."
        )
    if action.auteur != AUTEUR_SYSTEME:
        raise ValueError(
            f"« deserter » est une action système : auteur attendu « {AUTEUR_SYSTEME} », "
            f"reçu « {action.auteur} »."
        )
    deserteur = action.params.get("joueur")
    if not isinstance(deserteur, str) or not deserteur:
        raise ValueError("« deserter » : « params.joueur » (le déserteur) est requis.")
    gagnant = _autre_joueur(etat, deserteur)  # lève si « deserteur » n'est pas un joueur
    etat2 = replace(etat, terminee=True, vainqueur=gagnant, raison_fin=RAISON_DESERTION)
    evt = Evenement(
        EVT_PARTIE_TERMINEE,
        {"vainqueur": gagnant, "raison": RAISON_DESERTION, "deserteur": deserteur},
    )
    return etat2, [evt]


def _expirer_inactivite(
    etat: EtatPartie, action: Action, rng: Rng
) -> tuple[EtatPartie, list[Evenement]]:
    """Clôture d'une partie fantôme pour inactivité : **aucun vainqueur** (R-14.6, ménage).

    Action **système** (le balayage périodique) : son ``auteur`` doit être :data:`AUTEUR_SYSTEME`.
    Plus personne ne joue depuis le plafond configuré ; on ne désigne donc **aucun** vainqueur
    (``vainqueur=None``), raison :data:`RAISON_INACTIVITE`. Refuse une partie déjà terminée
    (R-14.6). La clôture est **journalisée** (jamais un effacement muet) : l'historique a son motif.
    """
    if etat.terminee:
        raise ValueError(
            "Partie terminée : plus aucune action, l'expiration pour inactivité comprise (R-14.6)."
        )
    if action.auteur != AUTEUR_SYSTEME:
        raise ValueError(
            f"« expirer_inactivite » est une action système : auteur attendu « {AUTEUR_SYSTEME} », "
            f"reçu « {action.auteur} »."
        )
    etat2 = replace(etat, terminee=True, vainqueur=None, raison_fin=RAISON_INACTIVITE)
    evt = Evenement(
        EVT_PARTIE_TERMINEE,
        {"vainqueur": None, "raison": RAISON_INACTIVITE},
    )
    return etat2, [evt]


# Enregistrement dans le ``REGISTRE`` du journal, à l'import (motif banc/cartes/demandes/horloges).
REGISTRE[ACTION_DESERTER] = _deserter
REGISTRE[ACTION_EXPIRER_INACTIVITE] = _expirer_inactivite


__all__ = ["_deserter", "_expirer_inactivite"]
