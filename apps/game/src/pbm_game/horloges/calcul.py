"""Le **calcul** des horloges — fonctions pures sur :class:`EtatHorloges`, du temps en entrée.

Module **pur** (aucune E/S, aucune horloge système) : partout, ``maintenant`` est un ``float``
(secondes depuis l'époque) fourni par l'appelant. Rien ici ne décompte « tout seul » — le temps
restant est **recalculé** à partir de l'instant fourni et des horodatages portés par l'état. C'est
ce qui fait tenir la reprise après un F5 : on relit l'état, on redonne l'instant courant, on obtient
exactement le même temps restant qu'avant la coupure (risque nommé du lot ``j-timer``).

Invariant central : **un seul compteur tourne à la fois** (le tour du joueur actif, ou une décision
en attente). Toute bascule *débite* le temps écoulé du budget du joueur qui comptait, puis démarre
un compteur neuf. Une pause **gèle** le compteur (le temps ne court plus) ; la reprise **décale**
son instant de départ de la durée gelée, pour que la pause ne consomme rien.
"""

from __future__ import annotations

from dataclasses import replace

from .modele import (
    CAUSE_BUDGET,
    GENRE_DECISION,
    GENRE_TOUR,
    CompteurActif,
    ConfigHorloges,
    EtatHorloges,
)


def demarrer(
    config: ConfigHorloges,
    joueurs: tuple[str, str],
    joueur_actif: str,
    maintenant: float,
) -> EtatHorloges:
    """Crée l'état d'horloges d'une partie neuve : plein budget chacun, tour du premier joueur.

    ``joueurs`` sont les deux identifiants (ordre indifférent) ; ``joueur_actif`` est celui dont le
    tour commence (R-4.7). Son compteur « tour » démarre à ``maintenant``.
    """
    a, b = joueurs
    if a == b:
        raise ValueError("demarrer : les deux joueurs doivent être distincts.")
    if joueur_actif not in (a, b):
        raise ValueError(f"demarrer : « {joueur_actif} » n'est pas un des joueurs {joueurs}.")
    budgets = {a: config.par_joueur_s, b: config.par_joueur_s}
    return EtatHorloges(
        config=config,
        budgets_s=budgets,
        actif=CompteurActif(joueur=joueur_actif, genre=GENRE_TOUR, depuis=maintenant),
    )


def _fin_comptage(etat: EtatHorloges, maintenant: float) -> float:
    """L'instant où s'arrête le comptage courant : ``pause_depuis`` si gelé, sinon ``maintenant``.

    Pendant une pause, le temps ne court plus : on fige l'écoulé à l'instant où la pause a commencé.
    """
    if etat.pause_depuis is not None:
        return etat.pause_depuis
    return maintenant


def ecoule(etat: EtatHorloges, maintenant: float) -> float:
    """Le temps écoulé (secondes, ≥ 0) sur le compteur actif, pause déduite. 0 si rien ne court."""
    if etat.actif is None:
        return 0.0
    return max(0.0, _fin_comptage(etat, maintenant) - etat.actif.depuis)


def _debiter(etat: EtatHorloges, maintenant: float) -> EtatHorloges:
    """Retranche l'écoulé courant du budget du joueur qui comptait (borné à 0), compteur arrêté.

    Point commun à toutes les bascules : on « encaisse » le temps passé avant de démarrer autre
    chose. Borné à 0 — un budget ne devient jamais négatif (l'expiration, elle, est détectée par
    :func:`premiere_echeance` avant d'en arriver là).
    """
    if etat.actif is None:
        return etat
    passe = ecoule(etat, maintenant)
    jid = etat.actif.joueur
    budgets = dict(etat.budgets_s)
    budgets[jid] = max(0.0, budgets.get(jid, 0.0) - passe)
    return replace(etat, budgets_s=budgets, actif=None)


def basculer(
    etat: EtatHorloges, joueur: str, maintenant: float, *, genre: str = GENRE_TOUR
) -> EtatHorloges:
    """Clôt le compteur courant (débite son écoulé) et démarre un compteur neuf pour ``joueur``.

    Utilisée au **changement de tour** (``genre=tour``, nouveau joueur actif) et pour revenir au
    tour après une décision. Le budget du joueur qui comptait est débité ; celui qui prend la main
    repart sur une horloge courte neuve, mais garde son budget total (plafond dur).
    """
    if joueur not in etat.budgets_s:
        raise ValueError(f"basculer : « {joueur} » n'a pas de budget (joueurs connus : "
                         f"{sorted(etat.budgets_s)}).")
    base = _debiter(etat, maintenant)
    return replace(base, actif=CompteurActif(joueur=joueur, genre=genre, depuis=maintenant))


def poser_decision(etat: EtatHorloges, destinataire: str, maintenant: float) -> EtatHorloges:
    """Une **demande** vient d'être posée : le compteur passe à « décision » pour son destinataire.

    Le destinataire peut être l'adversaire du joueur actif (DJ4 « y compris hors de son tour ») : on
    débite le temps que le joueur actif venait de passer, et on démarre l'horloge de décision pour
    celui qui doit trancher. Le tour reprendra, horloge courte neuve, une fois la demande levée.
    """
    return basculer(etat, destinataire, maintenant, genre=GENRE_DECISION)


def lever_decision(etat: EtatHorloges, joueur_actif: str, maintenant: float) -> EtatHorloges:
    """Une demande vient d'être **résolue** : le compteur revient au tour du joueur actif.

    L'horloge de décision est débitée du temps passé à décider ; le joueur actif reprend son tour
    sur une horloge courte neuve (l'interruption pour la décision adverse ne mange pas son tour,
    le budget total, lui, a bien été débité — le plafond dur reste honnête).
    """
    return basculer(etat, joueur_actif, maintenant, genre=GENRE_TOUR)


def arreter(etat: EtatHorloges, maintenant: float) -> EtatHorloges:
    """Arrête tout comptage (partie terminée) après avoir débité le temps du compteur courant."""
    return _debiter(etat, maintenant)


def pause(etat: EtatHorloges, joueur: str, maintenant: float) -> EtatHorloges:
    """Gèle les horloges : un joueur s'est déconnecté. Idempotent (une pause en cours ne bouge pas).

    On n'avance pas ``pause_depuis`` si une pause court déjà : la grâce se compte depuis la
    **première** déconnexion, pas depuis la dernière trame perdue.
    """
    if etat.pause_depuis is not None:
        return etat
    return replace(etat, pause_depuis=maintenant, pause_joueur=joueur)


def reprendre(etat: EtatHorloges, maintenant: float) -> EtatHorloges:
    """Lève la pause : le compteur reprend **là où il s'était gelé** (la pause n'a rien consommé).

    On décale l'instant de départ du compteur de la durée gelée : ainsi ``ecoule`` après la reprise
    exclut exactement le temps passé en pause. Sans effet si aucune pause ne court.
    """
    if etat.pause_depuis is None:
        return etat
    duree = max(0.0, maintenant - etat.pause_depuis)
    actif = etat.actif
    if actif is not None:
        actif = replace(actif, depuis=actif.depuis + duree)
    return replace(etat, actif=actif, pause_depuis=None, pause_joueur=None)


def pause_restante(etat: EtatHorloges, maintenant: float) -> float | None:
    """Secondes de grâce restantes avant la fin de la pause de déconnexion (``None`` hors pause).

    Peut être négative si la grâce est dépassée (l'appelant décide alors de reprendre) ;
    on ne la borne pas à 0 pour que l'extérieur distingue « encore en grâce » de « grâce dépassée ».
    """
    if etat.pause_depuis is None:
        return None
    return etat.config.pause_deconnexion_s - (maintenant - etat.pause_depuis)


def pause_expiree(etat: EtatHorloges, maintenant: float) -> bool:
    """Vrai si une pause court **et** que sa durée de grâce est dépassée (il faut reprendre)."""
    reste = pause_restante(etat, maintenant)
    return reste is not None and reste <= 0.0


def restant(etat: EtatHorloges, maintenant: float) -> dict:
    """Le temps restant **affichable**, recalculé à ``maintenant`` — la vérité serveur du moment.

    Renvoie un mapping prêt pour la projection vers le client (qui n'en fait qu'une estimation,
    corrigée à chaque événement) :

    * ``maintenant`` — l'instant serveur du calcul (le client en déduit sa dérive locale) ;
    * ``en_pause`` / ``pause_joueur`` / ``pause_restant_s`` — l'état de la pause de déconnexion ;
    * ``joueurs`` — par joueur : ``budget_s`` (budget total restant), ``genre`` (``tour`` /
      ``decision`` / ``None`` s'il ne compte pas) et ``horloge_s`` (restant sur l'horloge courte, ou
      ``None``). Les valeurs courtes peuvent descendre légèrement sous 0 dans la tolérance réseau
      avant que l'expiration ne se déclenche — on ne les borne pas, pour un affichage honnête.
    """
    passe = ecoule(etat, maintenant)
    joueurs: dict[str, dict] = {}
    for jid, budget in etat.budgets_s.items():
        compte_lui = etat.actif is not None and etat.actif.joueur == jid
        passe_lui = passe if compte_lui else 0.0
        info: dict = {"budget_s": max(0.0, budget - passe_lui), "genre": None, "horloge_s": None}
        if compte_lui:
            genre = etat.actif.genre
            info["genre"] = genre
            info["horloge_s"] = etat.config.limite(genre) - passe
        joueurs[jid] = info
    return {
        "maintenant": maintenant,
        "en_pause": etat.en_pause,
        "pause_joueur": etat.pause_joueur,
        "pause_restant_s": pause_restante(etat, maintenant),
        "joueurs": joueurs,
    }


def premiere_echeance(etat: EtatHorloges, maintenant: float) -> tuple[str, str] | None:
    """La première expiration atteinte à ``maintenant`` : ``(joueur, cause)``, ou ``None``.

    ``cause`` ∈ {``tour``, ``decision``, ``budget``}. Une horloge n'expire qu'**au-delà** de sa
    limite plus la tolérance réseau (la latence ne fait pas perdre un tour). Pendant une pause, rien
    n'expire (les horloges sont gelées) : on renvoie ``None`` — la fin de la grâce de pause est une
    affaire distincte (:func:`pause_expiree`).

    Le **budget total** est vérifié en premier : s'il est épuisé, c'est une défaite au temps (DJ4),
    qui prime sur l'horloge courte. Sinon, l'horloge courte (tour ou décision) expire
    selon le genre du compteur. Comme la limite courte (90 s / 30 s) est bien inférieure au budget
    (25 min), c'est normalement elle qui tombe d'abord ; le budget ne tranche que lorsqu'un joueur a
    cumulé tout son temps sur la partie.
    """
    if etat.actif is None or etat.en_pause:
        return None
    passe = ecoule(etat, maintenant)
    jid = etat.actif.joueur
    tol = etat.config.tolerance_reseau_s
    budget = etat.budgets_s.get(jid, 0.0)
    # Budget épuisé (tolérance comprise) → défaite au temps (prime, DJ4).
    if passe >= budget + tol:
        return (jid, CAUSE_BUDGET)
    # Horloge courte dépassée (tolérance comprise) → cause = genre du compteur (tour / decision).
    limite = etat.config.limite(etat.actif.genre)
    if passe >= limite + tol:
        return (jid, etat.actif.genre)
    return None


__all__ = [
    "demarrer",
    "ecoule",
    "basculer",
    "poser_decision",
    "lever_decision",
    "arreter",
    "pause",
    "reprendre",
    "pause_restante",
    "pause_expiree",
    "restant",
    "premiere_echeance",
]
