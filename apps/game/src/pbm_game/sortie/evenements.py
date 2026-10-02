"""Projection des événements par destinataire — lot ``j-autorite-vues``.

Un même coup n'est pas **décrit pareil** aux deux joueurs quand une information est cachée :
quand le joueur actif pioche, lui apprend *quelles* cartes (elles entrent dans sa main, qu'il
voit) ; son adversaire n'apprend que *combien* (R-5.2). Le canal temps réel (lot ``j-temps-reel``)
diffusera donc, pour chaque événement, **une projection par destinataire** — jamais l'événement
brut, qui porte parfois des ``instance_id`` de zones cachées.

Le filtrage est **structurel**, pas « par route » : chaque type d'événement a son projecteur
déclaré dans :data:`PROJECTEURS`. Un type d'événement **inconnu du registre est refusé**
(``ValueError``), jamais laissé passer tel quel — c'est le garde qui fait qu'un futur événement
ajouté sans projecteur **casse bruyamment** au lieu de fuir en silence (D9, « aucun repli
silencieux »). Ajouter un type d'événement, c'est donc décider ce que chaque joueur en voit.
"""

from __future__ import annotations

from collections.abc import Callable

from ..journal.modele import (
    EVT_ATTAQUE_DECLAREE,
    EVT_CARTES_PIOCHEES,
    EVT_CONFUSION,
    EVT_DEGATS,
    EVT_ECHANGE_FORCE,
    EVT_EFFET_EXPIRE,
    EVT_ETAT_CHECKUP,
    EVT_EVOLUTION,
    EVT_KO,
    EVT_PARTIE_TERMINEE,
    EVT_PHASE_AVANCEE,
    EVT_PIOCHE_MELANGEE,
    EVT_POKEMON_POSE,
    EVT_PROMOTION,
    EVT_PROMOTION_REQUISE,
    EVT_RETRAITE,
    EVT_TOUR_COMMENCE,
    Evenement,
)
from .jetons import Jetonneur

#: Un projecteur d'événement : reçoit l'événement, le destinataire et un :class:`Jetonneur`
#: optionnel, et renvoie l'événement **projeté** pour ce destinataire (ses ``donnees`` ne portent
#: que ce que le destinataire a le droit de savoir).
Projecteur = Callable[[Evenement, str, "Jetonneur | None"], Evenement]


def _public(evt: Evenement, pour: str, jetonneur: Jetonneur | None) -> Evenement:
    """Événement **entièrement public** : les deux joueurs le voient à l'identique.

    N'expose que des zones publiques (Actif, banc, défausse, zone perdue, Stade) ou des faits
    publics (phase, pile ou face, dégâts, fin de partie). Renvoyé tel quel — mais il est tout de
    même passé par ce registre, pour qu'aucun événement n'échappe au point de filtrage unique.
    """
    return evt


def _cartes_piochees(evt: Evenement, pour: str, jetonneur: Jetonneur | None) -> Evenement:
    """Pioche (R-5.2) : le **propriétaire** voit les ``instance_id`` tirés (ils sont dans sa main
    qu'il voit) ; l'adversaire n'apprend que le **nombre**, jamais les identités.

    Le nombre est public (tout le monde voit une carte quitter le deck) ; les identités ne le sont
    pas (elles rejoignent une zone — la main — cachée à l'adversaire). On ne remplace pas ici les
    identités par des jetons : une carte en main n'a pas à être désignée par l'adversaire, et un
    jeton serait une information de trop. On les **retire**.
    """
    joueur = evt.donnees.get("joueur")
    if pour == joueur:
        return evt
    donnees = {cle: valeur for cle, valeur in evt.donnees.items() if cle != "instance_ids"}
    return Evenement(evt.type, donnees)


#: Registre des projecteurs, par type d'événement. **Tout** type produit par le moteur y figure :
#: un type absent est refusé par :func:`projeter_evenement` (jamais diffusé brut). Les événements
#: qui n'exposent que de l'information publique pointent sur :func:`_public` ; ceux qui portent une
#: information cachée (aujourd'hui la seule pioche) ont leur projecteur dédié.
PROJECTEURS: dict[str, Projecteur] = {
    EVT_PIOCHE_MELANGEE: _public,
    EVT_CARTES_PIOCHEES: _cartes_piochees,
    EVT_PHASE_AVANCEE: _public,
    EVT_TOUR_COMMENCE: _public,
    EVT_ATTAQUE_DECLAREE: _public,
    EVT_CONFUSION: _public,
    EVT_DEGATS: _public,
    EVT_PARTIE_TERMINEE: _public,
    EVT_RETRAITE: _public,
    EVT_PROMOTION: _public,
    EVT_ECHANGE_FORCE: _public,
    EVT_ETAT_CHECKUP: _public,
    EVT_EFFET_EXPIRE: _public,
    EVT_KO: _public,
    EVT_PROMOTION_REQUISE: _public,
    EVT_POKEMON_POSE: _public,
    EVT_EVOLUTION: _public,
}


def projeter_evenement(
    evt: Evenement, *, pour: str, jetonneur: Jetonneur | None = None
) -> Evenement:
    """Projette ``evt`` pour le destinataire ``pour`` — ce qu'il a le droit d'en savoir.

    Refuse (``ValueError``) un type d'événement absent de :data:`PROJECTEURS` : un événement non
    projeté n'est **jamais** diffusé tel quel, car il pourrait porter une information cachée. C'est
    la garde structurelle du lot — un nouvel événement ajouté sans projecteur échoue ici, au lieu
    de fuir discrètement vers le client.
    """
    projecteur = PROJECTEURS.get(evt.type)
    if projecteur is None:
        raise ValueError(
            f"Événement « {evt.type} » sans projecteur : un événement non projeté ne peut pas "
            f"être diffusé (il pourrait fuir une information cachée). Déclarer son projecteur dans "
            f"PROJECTEURS. Types connus : {sorted(PROJECTEURS)}."
        )
    return projecteur(evt, pour, jetonneur)
