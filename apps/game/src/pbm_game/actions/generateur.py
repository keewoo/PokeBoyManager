"""Générateur d'actions légales et validation motivée — le cœur du lot.

Module **pur** (aucune E/S, ni HTTP, ni base, ni React), comme tout ``pbm_game``.

Deux fonctions publiques :

* :func:`actions_legales` ``(etat, joueur)`` — la liste **exhaustive** des coups que
  ``joueur`` peut jouer dans ``etat``, chacun avec son étiquette lisible et ses cibles
  valides (calculées depuis l'état, jamais depuis l'interface) ;
* :func:`valider` ``(etat, action)`` — soit l'accord, soit un **refus motivé** par une
  règle ``R-x.y`` du corpus (``docs/jeu/REGLES.md``). Toute action passe par là, y compris
  celles venues du serveur.

**Une seule source de vérité : la liste.** :func:`valider` vérifie l'**appartenance** d'une
action à ``actions_legales`` (recalculée depuis l'état qui fait autorité) ; il ne redérive
jamais la légalité par un second chemin. Dédoubler « je liste » et « je valide » les ferait
diverger : c'est le piège que ce lot évite (voir sa fiche). Un test de cohérence
(``test_actions_legales.py``) garde cet équivalent pour toujours.

**Périmètre au palier 4 (ce lot).** Le moteur ne connaît **pas encore** les données de
carte (type, coût, attaques, évolutions) : elles arrivent avec ``j-cartes-pokemon`` et les
lots de résolution (``j-degats-resolution``, ``j-retraite-banc``…). Ce lot livre donc le
**cadre** — représentation d'un coup, registre de familles, liste/validation — et les
familles qui ne demandent **aucune** donnée de carte :

* **avancer la phase / terminer le tour** (R-5.1) — pour le joueur actif ;
* **abandonner** (R-14.3) — pour tout joueur, à tout moment.

Les familles dépendantes du catalogue (poser un Pokémon, faire évoluer, attacher une
énergie, jouer un Dresseur, battre en retraite, déclarer une attaque) ne sont **pas
approximées** (D9) : chaque lot de résolution enregistre sa :class:`Famille` dans
:data:`FAMILLES_DEFAUT` quand il dispose du catalogue, exactement comme les transitions
s'enregistrent dans ``journal.transitions.REGISTRE``.

Règles de référence servies : **R-5.1** (déroulé d'un tour), **R-14.3** (abandon),
**R-14.6** (partie terminée figée), **R-4.1 / R-5.2** (le mélange et la pioche de début de
tour ne sont pas des coups libres de joueur), **R-15.12** (D9 : effet non implémenté).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..journal.modele import (
    ACTION_ABANDONNER,
    ACTION_AVANCER_PHASE,
    ACTION_MELANGER_PIOCHE,
    ACTION_PIOCHER,
    Action,
)
from ..journal.transitions import REGISTRE
from ..state.modele import PHASE_CHECKUP, EtatPartie
from .modele import ActionLegale, Verdict, refus


def _ids_joueurs(etat: EtatPartie) -> frozenset[str]:
    return frozenset(j.id for j in etat.joueurs)


class Famille(ABC):
    """Une **famille d'actions** : elle sait les énumérer et expliquer un refus.

    Chaque famille est l'unique propriétaire d'un (ou plusieurs) ``Action.type``. Les lots
    de résolution en ajoutent — c'est le point d'extension du moteur côté actions.
    """

    #: Clé stable de la famille (pour l'ordre déterministe de la liste et le débogage).
    nom: str

    @abstractmethod
    def gouverne(self, action: Action) -> bool:
        """Vrai si ce ``action.type`` appartient à cette famille."""

    @abstractmethod
    def generer(self, etat: EtatPartie, joueur: str) -> list[ActionLegale]:
        """Les coups légaux de cette famille pour ``joueur`` (partie supposée vivante).

        ``actions_legales`` garantit que ``etat`` n'est pas terminé avant d'appeler ceci
        (R-14.6) : une famille n'a pas à re-vérifier la fin de partie.
        """

    @abstractmethod
    def refuser(self, etat: EtatPartie, action: Action) -> Verdict:
        """Explique pourquoi ``action`` — que cette famille gouverne — n'est pas légale.

        Appelée par :func:`valider` **uniquement** quand l'action n'appartient pas à
        ``generer`` : elle cite la règle qui bloque. Elle ne décide pas de la légalité
        (c'est ``generer``), elle la **motive**.
        """


class FamilleAvancerPhase(Famille):
    """Avancer la phase / terminer le tour (R-5.1) — réservé au joueur actif."""

    nom = "avancer_phase"

    def gouverne(self, action: Action) -> bool:
        return action.type == ACTION_AVANCER_PHASE

    def generer(self, etat: EtatPartie, joueur: str) -> list[ActionLegale]:
        if joueur != etat.tour.joueur_actif:
            return []
        if etat.tour.phase == PHASE_CHECKUP:
            etiquette = "Terminer le tour"
        else:
            etiquette = "Passer à la phase suivante"
        return [ActionLegale(action=Action(ACTION_AVANCER_PHASE, joueur), etiquette=etiquette)]

    def refuser(self, etat: EtatPartie, action: Action) -> Verdict:
        if action.auteur != etat.tour.joueur_actif:
            return refus(
                "R-5.1",
                f"Ce n'est pas le tour de « {action.auteur} » : "
                f"le tour est à « {etat.tour.joueur_actif} ».",
            )
        if action.params:
            return refus("R-5.1", "« avancer_phase » ne prend aucun paramètre.")
        # Joueur actif, sans paramètre, partie vivante : ce coup EST légal, donc valider
        # ne nous appelle pas. Garde-fou honnête si l'invariant venait à casser.
        return refus("R-5.1", "Avancer la phase n'est pas possible dans cet état.")


class FamilleAbandonner(Famille):
    """Abandonner la partie (R-14.3) — pour tout joueur, à tout moment d'une partie vivante."""

    nom = "abandonner"

    def gouverne(self, action: Action) -> bool:
        return action.type == ACTION_ABANDONNER

    def generer(self, etat: EtatPartie, joueur: str) -> list[ActionLegale]:
        if joueur not in _ids_joueurs(etat):
            return []
        return [
            ActionLegale(action=Action(ACTION_ABANDONNER, joueur), etiquette="Abandonner la partie")
        ]

    def refuser(self, etat: EtatPartie, action: Action) -> Verdict:
        if action.auteur not in _ids_joueurs(etat):
            return refus(
                "R-14.3",
                f"« {action.auteur} » n'est pas un joueur de cette partie : "
                "seul un joueur peut abandonner.",
            )
        if action.params:
            return refus("R-14.3", "« abandonner » ne prend aucun paramètre.")
        return refus("R-14.3", "L'abandon n'est pas possible dans cet état.")


#: Les familles actives au palier 4. **Source unique** de ce qui est jouable : les lots de
#: résolution y ajoutent leur :class:`Famille` quand ils disposent du catalogue (D9). L'ordre
#: fixe l'ordre d'affichage de la liste (déterministe).
FAMILLES_DEFAUT: tuple[Famille, ...] = (FamilleAvancerPhase(), FamilleAbandonner())


def actions_legales(
    etat: EtatPartie, joueur: str, familles: tuple[Famille, ...] = FAMILLES_DEFAUT
) -> tuple[ActionLegale, ...]:
    """La liste exhaustive des coups que ``joueur`` peut jouer dans ``etat``.

    Une partie terminée est figée (R-14.6) : elle ne rend **aucun** coup. ``familles``
    n'est à passer que pour composer un sous-ensemble ou injecter une famille de test ;
    par défaut c'est :data:`FAMILLES_DEFAUT`, la source de vérité.
    """
    if etat.terminee:
        return ()
    coups: list[ActionLegale] = []
    for famille in familles:
        coups.extend(famille.generer(etat, joueur))
    return tuple(coups)


def _refus_type_non_gouverne(action: Action) -> Verdict:
    """Refus d'un type d'action qu'aucune famille ne gouverne, avec la règle qui l'explique.

    * ``piocher`` — la pioche de début de tour est **automatique** (R-5.2), pas un coup libre ;
    * ``melanger_pioche`` — le mélange appartient à la **mise en place** (R-4.1) ;
    * tout autre type (inconnu du moteur, ou pas encore scripté comme coup jouable) — **D9**
      (R-15.12) : un effet non implémenté n'est jamais approximé.
    """
    if action.type == ACTION_PIOCHER:
        return refus(
            "R-5.2",
            "La pioche de début de tour est automatique, pas un coup libre du joueur.",
        )
    if action.type == ACTION_MELANGER_PIOCHE:
        return refus(
            "R-4.1",
            "Le mélange du deck appartient à la mise en place, pas à un coup de joueur.",
        )
    connu = action.type in REGISTRE
    detail = "pas encore un coup jouable" if connu else f"type d'action inconnu : « {action.type} »"
    return refus(
        "R-15.12",
        f"{detail} — un effet non implémenté n'est jamais approximé (D9).",
    )


def valider(
    etat: EtatPartie, action: Action, familles: tuple[Famille, ...] = FAMILLES_DEFAUT
) -> Verdict:
    """Valide ``action`` contre ``etat`` : accord, ou refus motivé par une règle citée.

    Vérifie l'**appartenance** de ``action`` à :func:`actions_legales` recalculée depuis
    l'état qui fait autorité (une seule source de vérité). Un refus porte toujours une
    règle ``R-x.y`` — jamais un refus muet.
    """
    if not isinstance(action, Action):
        raise TypeError(f"valider attend une Action, reçu {type(action).__name__}.")
    if etat.terminee:
        return refus("R-14.6", "La partie est terminée : elle refuse toute action (R-14.6).")
    for famille in familles:
        if famille.gouverne(action):
            legales = famille.generer(etat, action.auteur)
            if any(coup.action == action for coup in legales):
                return Verdict(accepte=True)
            return famille.refuser(etat, action)
    return _refus_type_non_gouverne(action)


__all__ = [
    "Famille",
    "FamilleAvancerPhase",
    "FamilleAbandonner",
    "FAMILLES_DEFAUT",
    "actions_legales",
    "valider",
]
