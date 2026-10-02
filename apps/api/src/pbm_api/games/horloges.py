"""Adaptateur des **horloges** d'une partie (lot ``j-timer``) — entre le moteur pur et le service.

Le décompte, la bascule, la pause et la détection d'expiration vivent dans le moteur pur
(:mod:`pbm_game.horloges`) : ce module n'est qu'une **couche de traduction** qui porte le temps
(l'instant courant du serveur), lit/écrit la forme JSON stockée dans la colonne ``games.horloges``,
et décide **quelle action par défaut** journaliser à une expiration. Il n'a **aucune** dépendance à
la base ni à HTTP : le service (:mod:`pbm_api.games.service`) l'appelle sous verrou et persiste le
résultat ; c'est ce qui le rend testable sans base.

Les durées viennent de la **configuration** (variables d'environnement, :func:`config_horloges`) et
sont figées dans l'état de **chaque** partie à sa création : les changer côté serveur ne touche pas
une partie en vol, et aucune durée n'est codée en dur dans le moteur (critère d'acceptation du lot).
"""

from __future__ import annotations

from pbm_game.horloges import (
    CAUSE_BUDGET,
    CAUSE_DECISION,
    CAUSE_TOUR,
    GENRE_TOUR,
    ConfigHorloges,
    EtatHorloges,
    arreter,
    basculer,
    demarrer,
    lever_decision,
    pause,
    pause_expiree,
    poser_decision,
    premiere_echeance,
    reprendre,
    restant,
)
from pbm_game.journal.modele import (
    ACTION_DEFAITE_TEMPS,
    ACTION_EXPIRER_DEMANDE,
    ACTION_FIN_TOUR,
)
from pbm_game.state.modele import PHASE_CHECKUP, EtatPartie


def config_horloges(settings) -> ConfigHorloges:
    """Construit la :class:`ConfigHorloges` depuis la configuration (``settings``), DJ4 par défaut.

    Les cinq durées sont des réglages d'environnement : les modifier ne demande pas de redéployer le
    moteur, seulement de relancer l'API (les parties déjà lancées gardent leur config figée).
    """
    return ConfigHorloges(
        par_tour_s=settings.horloge_par_tour_s,
        par_joueur_s=settings.horloge_par_joueur_s,
        par_decision_s=settings.horloge_par_decision_s,
        tolerance_reseau_s=settings.horloge_tolerance_reseau_s,
        pause_deconnexion_s=settings.horloge_pause_deconnexion_s,
    )


def etat_initial_json(config: ConfigHorloges, etat: EtatPartie, maintenant_ts: float) -> dict:
    """Forme JSON des horloges d'une partie neuve : plein budget, tour du joueur actif."""
    joueurs = (etat.joueurs[0].id, etat.joueurs[1].id)
    return demarrer(config, joueurs, etat.tour.joueur_actif, maintenant_ts).en_json()


def transition_json(
    horloges_json: dict, etat_avant: EtatPartie, etat_apres: EtatPartie, maintenant_ts: float
) -> dict:
    """Met à jour les horloges après un coup, d'après la **transition d'état** observée.

    Un coup appliqué par un joueur prouve qu'il est connecté : si une pause de déconnexion courait,
    on la **lève** d'abord. Puis, selon ce qui a changé entre ``etat_avant`` et ``etat_apres`` :

    * partie **terminée** → on arrête tout comptage (le temps ne court plus) ;
    * une **demande** vient d'apparaître → l'horloge passe à « décision » pour son destinataire
      (éventuellement l'adversaire — DJ4) ;
    * une **demande** vient de disparaître → le compteur revient au tour du joueur actif ;
    * le **joueur actif a changé** (changement de tour) → bascule vers le tour du nouveau joueur ;
    * le tour **entre en Checkup** (fin de tour) → on **arrête** le comptage : pendant le Checkup,
      entre les deux tours, personne ne « réfléchit » (et ça évite qu'une horloge de tour ré-expire
      sur une phase où « fin de tour » serait illégale). Le comptage repart au tour suivant, quand
      le joueur actif change ;
    * sinon, le compteur courant continue (rien à faire).
    """
    h = EtatHorloges.depuis_json(horloges_json)
    if h.en_pause:
        h = reprendre(h, maintenant_ts)
    if etat_apres.terminee:
        h = arreter(h, maintenant_ts)
    elif etat_avant.resolution is None and etat_apres.resolution is not None:
        h = poser_decision(h, etat_apres.resolution.demande.destinataire, maintenant_ts)
    elif etat_avant.resolution is not None and etat_apres.resolution is None:
        h = lever_decision(h, etat_apres.tour.joueur_actif, maintenant_ts)
    elif etat_avant.tour.joueur_actif != etat_apres.tour.joueur_actif:
        h = basculer(h, etat_apres.tour.joueur_actif, maintenant_ts, genre=GENRE_TOUR)
    elif etat_apres.tour.phase == PHASE_CHECKUP and etat_avant.tour.phase != PHASE_CHECKUP:
        h = arreter(h, maintenant_ts)
    return h.en_json()


def restant_json(horloges_json: dict | None, maintenant_ts: float) -> dict | None:
    """Le temps restant affichable (vérité serveur), ou ``None`` si la partie n'a pas d'horloges.

    Renvoyé dans les charges temps réel : le client en fait une estimation, recalée à chaque
    événement (c'est ce qui garde l'écran à moins de deux secondes de la vérité serveur).
    """
    if horloges_json is None:
        return None
    return restant(EtatHorloges.depuis_json(horloges_json), maintenant_ts)


def pause_json(horloges_json: dict, joueur: str, maintenant_ts: float) -> dict:
    """Gèle les horloges (déconnexion de ``joueur``) et renvoie la forme JSON mise à jour."""
    return pause(EtatHorloges.depuis_json(horloges_json), joueur, maintenant_ts).en_json()


def reprendre_json(horloges_json: dict, maintenant_ts: float) -> dict:
    """Lève la pause (reconnexion) et renvoie la forme JSON mise à jour."""
    return reprendre(EtatHorloges.depuis_json(horloges_json), maintenant_ts).en_json()


def pause_a_expire(horloges_json: dict, maintenant_ts: float) -> bool:
    """Vrai si une pause de déconnexion court et que sa durée de grâce est dépassée."""
    return pause_expiree(EtatHorloges.depuis_json(horloges_json), maintenant_ts)


def action_par_defaut(horloges_json: dict, maintenant_ts: float) -> tuple[str, dict] | None:
    """L'action par défaut à journaliser à une expiration : ``(type, params)``, ou ``None``.

    Traduit la cause d'expiration (:func:`pbm_game.horloges.premiere_echeance`) en l'un des trois
    coups par défaut nommés par DJ4 — tous **système** (``auteur`` posé par le service) :

    * cause **décision** → :data:`~pbm_game.journal.modele.ACTION_EXPIRER_DEMANDE` (réponse par
      défaut de la demande en cours) ;
    * cause **tour** → :data:`~pbm_game.journal.modele.ACTION_FIN_TOUR` (fin du tour actif) ;
    * cause **budget** → :data:`~pbm_game.journal.modele.ACTION_DEFAITE_TEMPS` (défaite au temps),
      ``params["joueur"]`` nommant le perdant.

    Ne décide rien pendant une pause (les horloges sont gelées) : renvoie ``None``.
    """
    h = EtatHorloges.depuis_json(horloges_json)
    echeance = premiere_echeance(h, maintenant_ts)
    if echeance is None:
        return None
    joueur, cause = echeance
    if cause == CAUSE_DECISION:
        return (ACTION_EXPIRER_DEMANDE, {})
    if cause == CAUSE_TOUR:
        return (ACTION_FIN_TOUR, {})
    if cause == CAUSE_BUDGET:
        return (ACTION_DEFAITE_TEMPS, {"joueur": joueur})
    raise ValueError(f"Cause d'expiration inconnue : {cause!r}.")  # pragma: no cover


__all__ = [
    "config_horloges",
    "etat_initial_json",
    "transition_json",
    "restant_json",
    "pause_json",
    "reprendre_json",
    "pause_a_expire",
    "action_par_defaut",
]
