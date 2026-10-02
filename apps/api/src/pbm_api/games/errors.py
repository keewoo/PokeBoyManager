"""Erreurs du service de parties — chacune dit *pourquoi*, jamais un repli silencieux.

Le service lève ces exceptions ; la couche HTTP (router) les traduit en statuts. Aucune ne tue une
cause en silence : une carte non jouable nomme les cartes, un conflit de numéro nomme le numéro.
"""

from __future__ import annotations


class GameError(Exception):
    """Base des erreurs du service de parties."""


class CartesNonJouables(GameError):
    """Une partie est refusée à la création car un deck porte une ou plusieurs cartes non scriptées.

    Un effet non implémenté n'est jamais approximé (D9) : plutôt que de jouer une carte de travers,
    le jeu refuse la partie **en nommant les cartes** et la raison de chaque refus. `cartes` est la
    liste des `(nom_ou_ref, raison)`.
    """

    def __init__(self, cartes: list[tuple[str, str]]) -> None:
        self.cartes = cartes
        details = " ; ".join(f"« {nom} » : {raison}" for nom, raison in cartes)
        super().__init__(
            f"{len(cartes)} carte(s) non jouable(s), partie refusée (D9) : {details}"
        )


class PartieIntrouvable(GameError):
    """La partie demandée n'existe pas, ou l'utilisateur n'y participe pas (→ 404, pas 403).

    On ne distingue pas « n'existe pas » de « pas la vôtre » : révéler l'existence d'une partie
    d'autrui serait une fuite (même choix que les decks, `pbm_api.decks`).
    """


class ConflitNumero(GameError):
    """Le numéro d'action demandé ne suit pas l'état courant de la partie (→ 409).

    Porte le `numero_attendu` (celui demandé) et le `numero_courant` (le prochain réellement
    attendu). Deux cas : un trou (numéro trop grand) ou un numéro déjà joué par une **autre** action
    (idempotence impossible — ce n'est pas le même coup rejoué).
    """

    def __init__(self, numero_attendu: int, numero_courant: int, detail: str) -> None:
        self.numero_attendu = numero_attendu
        self.numero_courant = numero_courant
        super().__init__(
            f"Conflit de numéro d'action : demandé {numero_attendu}, la partie en est à "
            f"{numero_courant} — {detail}."
        )


class ActionRefusee(GameError):
    """Le moteur a refusé l'action (règle non tenue, coup illégal) — le message cite la règle.

    Le serveur fait autorité : une action impossible n'est pas appliquée « au mieux », elle est
    refusée avec la raison que le moteur a produite (→ 422).
    """


class PartieNonActive(GameError):
    """Action demandée sur une partie qui n'est plus en cours (terminée ou expirée) (→ 409)."""
