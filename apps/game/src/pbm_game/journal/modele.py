"""Structures du **journal d'actions** — une partie *est* sa suite de coups.

Ce module est **pur** : aucune entrée/sortie, aucune dépendance à HTTP, à une base de
données ou à React, comme tout le moteur ``pbm_game`` (principe du jalon J1).

Principe porté ici — « **tout est rejouable** » : une partie n'est pas une photo de son
plateau, c'est un **état initial**, une **graine d'aléatoire** et un **journal d'actions
numéroté**. Rejouer le journal redonne exactement le même état (voir :mod:`.rejeu`). La
forme sérialisée est **versionnée** (:data:`JOURNAL_VERSION`) : relire un journal produit
sous une version inconnue est refusé, jamais replié en silence.

Ce qui est enregistré, par entrée (:class:`Entree`) : ce qui a été **DEMANDÉ**
(l':class:`Action`), ce que le moteur en a **FAIT** (les :class:`Evenement`), qui l'a
demandé, quand, et l'**empreinte** de l'état résultant — jamais une photo du plateau
(c'est le piège que ce lot évite : journaliser l'état, c'est perdre la divergence au coup
près et laisser le replay mentir).

Format documenté pour une réimplémentation indépendante : ``docs/jeu/JOURNAL.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..state.modele import EtatPartie

# Version du schéma du journal : toute évolution INCOMPATIBLE de la forme sérialisée
# (champ d'une entrée, forme d'une action, d'un événement, d'un instantané) l'incrémente.
# ``partie_depuis_json`` refuse une version inconnue (jamais de repli silencieux).
JOURNAL_VERSION = 1

#: Auteur d'une action non imputable à un joueur (mise en place, Checkup automatique).
#: Les actions d'un joueur portent son identifiant ; celles-ci portent cette constante.
AUTEUR_SYSTEME = "systeme"

# --- Types d'action reconnus (ce que porte ``Action.type``) ------------------
# Un type absent de ce catalogue est REFUSÉ à l'application (D9 : un effet non
# implémenté n'est jamais approximé). Les lots de résolution (attaques, Dresseurs,
# talents) en ajoutent, chacun scripté et testé.
ACTION_MELANGER_PIOCHE = "melanger_pioche"
ACTION_PIOCHER = "piocher"
ACTION_AVANCER_PHASE = "avancer_phase"
#: Abandon de la partie (R-14.3) : action légale d'un joueur, à tout moment, sans aucune
#: donnée de carte. Ajoutée par le lot ``j-actions-legales`` (elle est purement mécanique,
#: comme la pioche et l'avancée de phase).
ACTION_ABANDONNER = "abandonner"

# --- Types d'événement (ce que PRODUIT le moteur) ----------------------------
EVT_PIOCHE_MELANGEE = "pioche_melangee"
EVT_CARTES_PIOCHEES = "cartes_piochees"
EVT_PHASE_AVANCEE = "phase_avancee"
EVT_TOUR_COMMENCE = "tour_commence"
#: La partie se termine (R-14.6) : l'événement porte vainqueur, raison et, pour l'abandon,
#: le joueur qui a abandonné. Produit par la transition ``abandonner`` (lot j-actions-legales).
EVT_PARTIE_TERMINEE = "partie_terminee"

#: Raison de fin pour un abandon (R-14.3), portée par ``EtatPartie.raison_fin`` et par
#: l'événement :data:`EVT_PARTIE_TERMINEE`.
RAISON_ABANDON = "abandon"


@dataclass(frozen=True)
class Action:
    """Ce qu'un acteur **demande** au moteur — autosuffisant et sérialisable.

    * ``type`` — un type reconnu (voir les constantes ``ACTION_*``) ; un type inconnu est
      refusé à l'application, jamais approximé (D9) ;
    * ``auteur`` — l'identifiant du joueur qui demande, ou :data:`AUTEUR_SYSTEME` ;
    * ``params`` — les paramètres de l'action, en valeurs **JSON natives** uniquement
      (``str``/``int``/``bool``/``list``/``dict``/``None``), pour que l'entrée se
      sérialise et se rejoue sans surprise.
    """

    type: str
    auteur: str
    params: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Evenement:
    """Ce que le moteur **a fait** en réponse à une action — fait observable et journalisé.

    ``type`` est un des ``EVT_*`` ; ``donnees`` porte les détails (valeurs JSON natives).
    Les événements sont la trace de ce qui a changé : rejouer l'action les reproduit à
    l'identique, ce que :func:`.rejeu.rejouer` contrôle.
    """

    type: str
    donnees: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Entree:
    """Une entrée du journal — **numérotée**, append-only, autosuffisante.

    * ``numero`` — rang dans le journal (0-based), la suite 0, 1, 2… sans trou ;
    * ``auteur`` — qui a demandé l'action (recopié de ``action.auteur`` pour la lecture) ;
    * ``action`` — ce qui a été demandé ;
    * ``evenements`` — ce que le moteur en a fait, dans l'ordre ;
    * ``horodatage`` — quand, en chaîne ISO fournie par l'appelant. Le moteur est **pur**
      et n'appelle aucune horloge : l'horodatage est une **donnée d'entrée**, pas une
      sortie — le rejeu le relit, il ne le recalcule jamais ;
    * ``empreinte`` — l'empreinte de l'état **après** ce coup (voir :func:`.empreinte`).
      Une divergence se détecte ainsi **au coup près**, pas à la fin de la partie.
    """

    numero: int
    auteur: str
    action: Action
    evenements: tuple[Evenement, ...]
    horodatage: str
    empreinte: str


@dataclass(frozen=True)
class Partie:
    """Une partie **persistée** : état initial + graine + journal. La source de vérité.

    L'état courant n'est qu'un **cache** reconstructible : il se recalcule en rejouant le
    journal depuis ``etat_initial`` sous ``graine`` (:func:`.rejeu.rejouer`). C'est cette
    forme-là qu'on stocke, pas une photo du plateau.

    * ``etat_initial`` — l'état au coup 0, avant toute action ;
    * ``graine`` — la graine d'aléatoire **en hexadécimal** (le moteur est pur : il ne la
      fabrique pas, l'appelant la tire et la lui passe) ;
    * ``entrees`` — le journal, dans l'ordre ;
    * ``journal_version`` — version du schéma du journal.
    """

    etat_initial: EtatPartie
    graine: str
    entrees: tuple[Entree, ...] = ()
    journal_version: int = JOURNAL_VERSION


@dataclass(frozen=True)
class Instantane:
    """Un **instantané** de compaction : l'état à un point du journal, pour ne pas tout rejouer.

    Reprendre une partie de 400 coups ne doit pas coûter 400 applications : on garde un
    instantané périodique + la **queue** des entrées postérieures, et on ne rejoue que la
    queue (:func:`.rejeu.reprendre`). L'instantané est un **cache**, jamais la source de
    vérité (qui reste le journal).

    * ``numero_entrees`` — combien d'entrées du journal ont été appliquées pour arriver là
      (donc l'état après ``entrees[:numero_entrees]``) ;
    * ``etat`` — l'état à ce point ;
    * ``rng_etat`` — l'état sérialisé du :class:`~pbm_game.rng.Rng` à ce point (graine,
      compteurs, journal des tirages), pour reprendre les tirages sans décalage ;
    * ``empreinte`` — l'empreinte de ``etat`` (contrôle de cohérence de l'instantané) ;
    * ``journal_version`` — version du schéma.
    """

    numero_entrees: int
    etat: EtatPartie
    rng_etat: dict
    empreinte: str
    journal_version: int = JOURNAL_VERSION
