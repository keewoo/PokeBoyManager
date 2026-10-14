"""Normalisation des **motifs** d'incident — pur, sans entrée/sortie, testable seul.

Un compteur « actions refusées par motif » ne vaut que si le motif appartient à un vocabulaire
**fermé** : agréger sur un message libre produit autant de motifs que de refus, et ne signale donc
jamais rien. Le moteur, lui, cite toujours la règle qui motive son refus
(:class:`pbm_game.actions.modele.Verdict` — un identifiant ``R-x.y`` du corpus
``docs/jeu/REGLES.md``), et le service la recopie dans le message (« … (R-3.5) ») : **la règle est
le motif**. Une hausse sur ``R-3.5`` nomme la règle qui casse, pas un symptôme.

C'est aussi ce qui garantit qu'aucun motif ne transporte de donnée d'utilisateur : la forme est
reconnue par une expression régulière bornée, jamais recopiée du message.
"""

from __future__ import annotations

import re

#: Une règle du corpus : ``R-`` puis au moins deux nombres séparés par des points (``R-3.5``,
#: ``R-13.1.2``). Bornée en longueur par construction — elle sert de clé de métrique.
_REGLE = re.compile(r"\bR-\d{1,3}(?:\.\d{1,3}){1,3}\b")

#: Motif d'un refus dont le message ne cite aucune règle. Ce n'est pas un repli silencieux : c'est
#: un signal en soi — tout refus **doit** citer sa règle (``pbm_game.actions.modele.refus``), donc
#: un compteur non nul ici désigne un chemin de refus à corriger.
MOTIF_SANS_REGLE = "sans-regle"

#: Motif d'une partie refusée faute de carte scriptée (D9) — cause unique, vocabulaire d'un mot.
MOTIF_CARTE_NON_SCRIPTEE = "carte_non_scriptee"

#: Longueur maximale du détail conservé (colonne ``jeu_incidents.detail``).
DETAIL_MAX = 480


def motif_de_refus(message: str | None) -> str:
    """La règle citée par un refus du moteur, ou :data:`MOTIF_SANS_REGLE`.

    On prend la **première** règle rencontrée : le service compose ``« <message> (R-x.y) »`` et un
    message d'explication peut lui-même citer une règle voisine ; la première est celle du refus.
    """
    trouve = _REGLE.search(message or "")
    return trouve.group(0) if trouve else MOTIF_SANS_REGLE


def motif_d_erreur(exc: BaseException) -> str:
    """Le motif d'une erreur de moteur : le **nom de la classe** d'exception, jamais son message.

    Le message d'une exception peut contenir des valeurs de la partie (identifiants de cartes,
    de joueurs) : il n'a rien à faire dans une clé d'agrégation. Le nom de classe, lui, regroupe
    les occurrences d'un même bug — ``KeyError`` d'un côté, ``TypeError`` de l'autre.
    """
    return type(exc).__name__[:64]


def detail_borne(texte: str | None) -> str | None:
    """Tronque un détail à :data:`DETAIL_MAX` caractères, en le signalant par un « … ».

    Le détail sert au diagnostic humain, jamais à l'agrégation : on le garde lisible et borné
    plutôt que de laisser un message de moteur dépasser la colonne (et faire échouer l'écriture
    de la trace — une supervision qui tombe sur l'incident qu'elle devait tracer).
    """
    if texte is None:
        return None
    texte = texte.strip()
    if not texte:
        return None
    if len(texte) <= DETAIL_MAX:
        return texte
    return texte[: DETAIL_MAX - 1] + "…"


__all__ = [
    "DETAIL_MAX",
    "MOTIF_CARTE_NON_SCRIPTEE",
    "MOTIF_SANS_REGLE",
    "detail_borne",
    "motif_d_erreur",
    "motif_de_refus",
]
