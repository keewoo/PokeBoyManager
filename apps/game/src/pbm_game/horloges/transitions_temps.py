"""Transitions journalisées des **expirations d'horloge** — ``fin_tour`` et ``defaite_temps``.

Module **pur**. L'extérieur (le service, lot ``j-timer``) tient le temps et décide *quand* une
horloge expire ; mais l'**effet** d'une expiration est un **coup journalisé** comme les autres
(« tout est rejouable »), pour que la partie survive à un F5 et que l'anti-triche puisse rejouer.
On enregistre ces transitions dans le ``REGISTRE`` du journal **à l'import** — le même motif que
``pbm_game.banc``, ``pbm_game.cartes`` et ``pbm_game.demandes`` — sans que le noyau des transitions
dépende de ce module (pas de cycle).

Deux actions, qui incarnent les deux actions par défaut nommées par DJ4 (la troisième, la *réponse
par défaut d'une demande*, est déjà portée par ``pbm_game.demandes`` via ``expirer_demande``) :

* :data:`~pbm_game.journal.modele.ACTION_FIN_TOUR` — l'horloge **par tour** a expiré : le joueur
  actif n'a pas fini son tour à temps → on **termine son tour** (entrée en Checkup, R-5.8/R-12.1),
  sans déclarer d'attaque. Le tour suivant s'ouvrira par la mécanique habituelle (le service
  Checkup puis début de tour, comme après une attaque) ;
* :data:`~pbm_game.journal.modele.ACTION_DEFAITE_TEMPS` — le **budget total** d'un joueur épuisé :
  aucune action par défaut n'a de sens → **défaite au temps** (R-14.6,
  :data:`~pbm_game.journal.modele.RAISON_TEMPS_ECOULE`). Terminale, comme l'abandon.

Une expiration **produit toujours un coup journalisé, jamais un blocage** (critère d'acceptation).
"""

from __future__ import annotations

from dataclasses import replace

from ..journal.modele import (
    ACTION_DEFAITE_TEMPS,
    ACTION_FIN_TOUR,
    AUTEUR_SYSTEME,
    EVT_FIN_TOUR,
    EVT_PARTIE_TERMINEE,
    EVT_PHASE_AVANCEE,
    RAISON_TEMPS_ECOULE,
    Action,
    Evenement,
)
from ..journal.transitions import REGISTRE
from ..rng import Rng
from ..state.modele import PHASE_ATTAQUE, PHASE_CHECKUP, PHASE_PRINCIPALE, EtatPartie
from ..tour.fenetres import FENETRE_FIN_TOUR, declencher


def _autre_joueur(etat: EtatPartie, jid: str) -> str:
    """L'identifiant de l'autre joueur, ou ``ValueError`` si ``jid`` n'est pas de la partie."""
    a, b = etat.joueurs[0].id, etat.joueurs[1].id
    if jid == a:
        return b
    if jid == b:
        return a
    raise ValueError(f"Joueur « {jid} » absent de la partie.")


def _fin_tour(
    etat: EtatPartie, action: Action, rng: Rng
) -> tuple[EtatPartie, list[Evenement]]:
    """Termine le tour du joueur actif (horloge par tour expirée) : entrée en Checkup (R-5.8).

    Action **système** (le temps est tenu dehors) ou coup volontaire du joueur actif : l'``auteur``
    doit être :data:`AUTEUR_SYSTEME` ou le joueur actif lui-même. Elle **termine le tour** sans
    déclarer d'attaque, exactement comme ``declarer_attaque`` mène au Checkup — une seule porte vers
    la fin du tour. Elle ne résout pas le Pokémon Checkup (poison, brûlure : action ``checkup``
    séparée, qui a besoin du catalogue) ni n'ouvre le tour suivant : c'est la mécanique habituelle
    qui enchaîne, la partie n'est jamais figée.

    Refuse une partie terminée (R-14.6) et une phase hors des phases jouables (R-5.1) : on ne
    « termine » pas un tour pas encore commencé (phase de pioche) ni un Checkup déjà en cours.
    """
    if etat.terminee:
        raise ValueError("Partie terminée : aucun tour ne se termine (R-14.6).")
    jid = etat.tour.joueur_actif
    if action.auteur not in (AUTEUR_SYSTEME, jid):
        raise ValueError(
            f"« {action.auteur} » ne peut pas terminer le tour de « {jid} » : seul le joueur "
            f"actif ou le système (à l'expiration de l'horloge) le peut (R-5.7)."
        )
    if etat.tour.phase not in (PHASE_PRINCIPALE, PHASE_ATTAQUE):
        raise ValueError(
            f"Fin de tour hors d'une phase jouable (phase : {etat.tour.phase!r}, R-5.1) : "
            "le tour n'a pas commencé, ou le Checkup est déjà atteint."
        )
    # Entrée en Checkup (R-12.1) + fenêtre « fin de tour » (vide au jalon J1), comme pour une
    # attaque déclarée — une seule porte vers la fin du tour.
    de = etat.tour.phase
    etat2 = replace(etat, tour=replace(etat.tour, phase=PHASE_CHECKUP))
    evenements = [
        Evenement(EVT_FIN_TOUR, {"joueur": jid, "de": de}),
        Evenement(
            EVT_PHASE_AVANCEE,
            {"de": de, "vers": PHASE_CHECKUP, "numero": etat2.tour.numero, "joueur_actif": jid},
        ),
    ]
    etat2, evts_fenetre = declencher(etat2, FENETRE_FIN_TOUR, rng)
    evenements.extend(evts_fenetre)
    return etat2, evenements


def _defaite_temps(
    etat: EtatPartie, action: Action, rng: Rng
) -> tuple[EtatPartie, list[Evenement]]:
    """Défaite au temps (budget total épuisé) : la partie se termine, l'adversaire gagne (R-14.6).

    Action **système** : son ``auteur`` doit être :data:`AUTEUR_SYSTEME` (une horloge expire, ce
    n'est pas un coup de joueur), et ``params["joueur"]`` nomme le **perdant** (celui dont le budget
    est épuisé). L'adversaire devient vainqueur, raison :data:`RAISON_TEMPS_ECOULE`. Refuse une
    partie déjà terminée (R-14.6) et un perdant qui n'est pas de la partie (jamais de repli
    silencieux). Permise même pendant une demande en cours (comme l'abandon) : un budget peut
    s'épuiser pendant que l'adversaire décide.
    """
    if etat.terminee:
        raise ValueError(
            "Partie terminée : plus aucune action, la défaite au temps comprise (R-14.6)."
        )
    if action.auteur != AUTEUR_SYSTEME:
        raise ValueError(
            f"« defaite_temps » est une action système : auteur attendu « {AUTEUR_SYSTEME} », "
            f"reçu « {action.auteur} »."
        )
    perdant = action.params.get("joueur")
    if not isinstance(perdant, str) or not perdant:
        raise ValueError("« defaite_temps » : « params.joueur » (le perdant) est requis.")
    gagnant = _autre_joueur(etat, perdant)  # lève si « perdant » n'est pas un joueur
    etat2 = replace(etat, terminee=True, vainqueur=gagnant, raison_fin=RAISON_TEMPS_ECOULE)
    evt = Evenement(
        EVT_PARTIE_TERMINEE,
        {"vainqueur": gagnant, "raison": RAISON_TEMPS_ECOULE, "perdant": perdant},
    )
    return etat2, [evt]


# Enregistrement dans le ``REGISTRE`` du journal, à l'import (motif banc/cartes/demandes).
REGISTRE[ACTION_FIN_TOUR] = _fin_tour
REGISTRE[ACTION_DEFAITE_TEMPS] = _defaite_temps


__all__ = ["_fin_tour", "_defaite_temps"]
