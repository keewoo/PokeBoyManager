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

from ..combat.cout import EVT_COUT_PAYE
from ..effets.dsl.interprete import EVT_COUT_IMPAYABLE, EVT_DSL_PILE
from ..effets.pile import EVT_EFFET_RESOLU, EVT_EFFET_SANS_CIBLE
from ..effets.verrous import EVT_VERROU_LEVE, EVT_VERROU_POSE
from ..journal.modele import (
    EVT_ATTAQUE_DECLAREE,
    EVT_CARTES_PIOCHEES,
    EVT_CONFUSION,
    EVT_DEGATS,
    EVT_ECHANGE_FORCE,
    EVT_EFFET_EXPIRE,
    EVT_ENERGIE_ATTACHEE,
    EVT_ETAT_CHECKUP,
    EVT_EVOLUTION,
    EVT_FIN_TOUR,
    EVT_KO,
    EVT_MAIN_REVELEE,
    EVT_MISE_EN_PLACE_PRETE,
    EVT_MISE_EN_PLACE_REVELEE,
    EVT_MULLIGAN,
    EVT_OBJET_JOUE,
    EVT_PARTIE_TERMINEE,
    EVT_PHASE_AVANCEE,
    EVT_PIOCHE_MELANGEE,
    EVT_PLACEMENT_CACHE,
    EVT_POKEMON_POSE,
    EVT_PROMOTION,
    EVT_PROMOTION_REQUISE,
    EVT_RETRAITE,
    EVT_STADE_JOUE,
    EVT_SUPPORTER_JOUE,
    EVT_TALENT_ACTIVE,
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


def _main_revelee(evt: Evenement, pour: str, jetonneur: Jetonneur | None) -> Evenement:
    """Main d'ouverture révélée après un mulligan (R-4.4) : l'adversaire voit **quelles** cartes
    (leurs ``ref``), jamais leurs ``instance_id``.

    R-4.4 tranche que la main d'un mulligan est **révélée à l'adversaire** — c'est le seul moment où
    une main est publique. L'adversaire a donc droit aux **identités** (``ref``), qui lui suffisent
    pour constater l'absence de Pokémon de base ; il n'a pas droit aux ``instance_id``, que la règle
    ne mentionne pas. Or ces cartes repartent aussitôt dans la pioche (zone cachée) : leur laisser
    l'``instance_id`` donnerait un **repère de suivi** d'une carte qui redevient secrète — on
    choisit donc le moins révélateur (D-visibilité) et on retire l'``instance_id`` pour
    l'adversaire. Le propriétaire, lui, voit sa propre main en entier (il la connaît déjà). Le
    journal moteur, à part, garde la trace complète avec ``instance_id`` (exigence « le contenu
    révélé est journalisé »).
    """
    joueur = evt.donnees.get("joueur")
    if pour == joueur:
        return evt
    cartes = evt.donnees.get("cartes", [])
    cartes_publiques = [{"ref": c["ref"]} for c in cartes]
    donnees = {**evt.donnees, "cartes": cartes_publiques}
    return Evenement(evt.type, donnees)


#: Registre des projecteurs, par type d'événement. **Tout** type produit par le moteur y figure :
#: un type absent est refusé par :func:`projeter_evenement` (jamais diffusé brut), et le test de
#: parité ``test_parite_evenements_projecteurs`` casse en CI si un ``EVT_*`` du moteur n'y est pas.
#: Les événements qui n'exposent que de l'information publique pointent sur :func:`_public` ; ceux
#: qui portent une information cachée (la pioche, la main révélée d'un mulligan) ont leur projecteur
#: dédié.
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
    # Mise en place (lots j-initialisation / j-coups-joueur) et horloges (lot j-timer) : les sept
    # types qui manquaient au registre et faisaient répondre 500 à POST /actions (fix-projection).
    EVT_ENERGIE_ATTACHEE: _public,  # R-5.4 : attacher une énergie est un geste public
    EVT_PLACEMENT_CACHE: _public,  # R-4.2 : ne porte que le joueur, jamais le contenu face cachée
    EVT_MULLIGAN: _public,  # R-4.5 : numéro de mulligan et carte bonus, aucune identité de carte
    EVT_MAIN_REVELEE: _main_revelee,  # R-4.4 : refs révélés à l'adversaire, instance_id retirés
    EVT_MISE_EN_PLACE_PRETE: _public,  # R-4.5 : résumé public (mulligans, bonus par joueur)
    EVT_MISE_EN_PLACE_REVELEE: _public,  # R-4.2/R-4.3 : Actif et banc rendus publics (refs)
    EVT_FIN_TOUR: _public,  # R-5.8 : fin de tour, joueur et phase quittée — aucun secret
    EVT_OBJET_JOUE: _public,  # R-5.5 : Objet joué — nom et Actifs changés, tout est public
    EVT_SUPPORTER_JOUE: _public,  # R-5.5 : Supporter joué — nom et Actifs changés, tout est public
    EVT_STADE_JOUE: _public,  # R-3.5 : Stade joué — zone partagée publique, aucun secret
    EVT_TALENT_ACTIVE: _public,  # R-5 : talent activé — nom, Pokémon et Actifs changés, tout public
    # Combat et effets (lots j-attaque / effets de carte) : ces types **ne portent que de
    # l'information publique** — cartes en jeu, énergies attachées (publiques), pile ou face.
    # Le reste du système d'effets (demandes, choix, primitives) peut porter des identités cachées :
    # il est tenu HORS de ce registre, voir DIFFERES_SYSTEME_EFFETS dans le test de parité.
    EVT_COUT_PAYE: _public,  # R-9.2 : coût payé par des énergies attachées (donc publiques)
    EVT_EFFET_RESOLU: _public,  # source (carte en jeu) + règle — aucun secret
    EVT_EFFET_SANS_CIBLE: _public,  # effet sans cible : source + raison, aucun secret
    EVT_VERROU_POSE: _public,  # R-12 : verrou posé par une carte (nom, portée, source publique)
    EVT_VERROU_LEVE: _public,  # R-12.5 : verrou expiré — aucun secret
    EVT_DSL_PILE: _public,  # pile ou face : nombre de pièces et de faces, public par nature
    EVT_COUT_IMPAYABLE: _public,  # un coût d'effet n'a pas pu être payé — fait public
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
