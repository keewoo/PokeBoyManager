"""Structures d'état d'une partie — dataclasses **figées** et sérialisables.

Ce module est **pur** : aucune entrée/sortie, aucune dépendance à HTTP, à une base
de données ou à React, comme tout le moteur ``pbm_game`` (principe du jalon J1).

Les structures sont ``frozen`` et n'exposent **aucune** méthode de mutation (« piocher »,
« attacher »…) : toute mutation doit passer par une action journalisée (lots suivants),
sinon la rejouabilité est perdue dès le premier raccourci. Ce qui vit ici, c'est la
**forme** de l'état, sa séparation information publique / information cachée, et les
constantes de règle qui la structurent.

Règles de référence structurées ici (``docs/jeu/REGLES.md``) :

* **R-3.1** — chaque joueur a : pioche, main, 1 Actif, banc, défausse, 6 récompenses ;
* **R-3.2** — banc ≤ 5 ;
* **R-3.3** — exactement 1 Actif tant que le joueur a au moins un Pokémon en jeu ;
* **R-3.4** — 6 récompenses face cachée ;
* **R-3.5** — un seul Stade en jeu, partagé par les deux joueurs ;
* **R-3.6** — un Pokémon en jeu porte : pile d'évolutions, énergies, ≤ 1 Outil,
  compteurs de dégâts, états spéciaux, orientation ;
* **R-3.7** — au plus 1 Outil par Pokémon ;
* **R-5.1 / R-5.4 / R-5.5 / R-5.6** — le tour porte son numéro, sa phase et les drapeaux
  « énergie posée », « supporter joué », « retraite faite » ;
* **R-10.4** — les dégâts se comptent en **compteurs**, jamais en PV soustraits ;
* **R-11.1 / R-11.8** — les cinq états spéciaux et la matrice d'orientation ;
* **R-14.6** — une partie terminée est figée et porte vainqueur + raison.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Importé **seulement** pour l'annotation de ``EtatPartie.resolution`` : jamais au runtime, pour
    # que ``state.modele`` reste une feuille sans dépendance au paquet ``demandes`` (pas de cycle).
    from ..demandes.moteur import ResolutionEnCours

# Version du schéma d'état : toute évolution incompatible de la forme sérialisée
# l'incrémente. ``depuis_json`` refuse une version inconnue (jamais de repli silencieux).
# v3 (lot ``j-effets-choix``) : ajout de ``EtatPartie.resolution`` — la demande de décision en
# cours et la pile d'effets suspendue, pour qu'une partie se mette en pause en attendant un joueur.
SCHEMA_VERSION = 3

# --- États spéciaux (R-11.1) -------------------------------------------------
ENDORMI = "endormi"
BRULE = "brule"
CONFUS = "confus"
PARALYSE = "paralyse"
EMPOISONNE = "empoisonne"

#: Les cinq états spéciaux du corpus (R-11.1).
ETATS_SPECIAUX: frozenset[str] = frozenset({ENDORMI, BRULE, CONFUS, PARALYSE, EMPOISONNE})

#: États qui **orientent** la carte : un seul des trois à la fois (R-11.8).
ETATS_ORIENTATION: frozenset[str] = frozenset({ENDORMI, CONFUS, PARALYSE})

#: États à **marqueur** : cumulables entre eux et avec l'orientation en cours (R-11.8).
ETATS_MARQUEUR: frozenset[str] = frozenset({BRULE, EMPOISONNE})

# Orientation physique de la carte, manifestation de l'état d'orientation (R-11.3/5/6/8).
ORIENTATION_NORMALE = "normale"

# --- Phases d'un tour (R-5.1, R-12) ------------------------------------------
PHASE_PIOCHE = "pioche"
PHASE_PRINCIPALE = "principale"
PHASE_ATTAQUE = "attaque"
PHASE_CHECKUP = "checkup"

#: Phases reconnues d'un tour. ``pioche`` → ``principale`` → ``attaque`` (R-5.1),
#: ``checkup`` = phase entre les deux tours (R-12.1).
PHASES: frozenset[str] = frozenset({PHASE_PIOCHE, PHASE_PRINCIPALE, PHASE_ATTAQUE, PHASE_CHECKUP})

# Raison de fin réservée à l'égalité (R-14.4) : vainqueur ``None`` + cette raison.
RAISON_EGALITE = "egalite"


@dataclass(frozen=True)
class Carte:
    """Un exemplaire de carte dans la partie.

    ``instance_id`` identifie **l'exemplaire** (unique dans toute la partie) ; ``ref``
    identifie **ce que la carte est** (référence catalogue). Les deux sont de
    l'information **cachée** quand la carte est dans une zone cachée (pioche, main
    adverse, récompenses) : la projection ``vue`` ne les laisse jamais fuir.
    """

    instance_id: str
    ref: str


@dataclass(frozen=True)
class PokemonEnJeu:
    """Un Pokémon en jeu (Actif ou banc) et tout ce qu'il porte (R-3.6).

    ``cartes`` est la **pile d'évolutions**, du bas (Pokémon de base, index 0) vers le
    haut (évolution courante, dernier élément). ``compteurs_degats`` compte en
    **compteurs**, jamais en PV soustraits (R-10.4). ``etats_speciaux`` porte les états
    de R-11 ; l'**orientation** en est dérivée (voir :func:`orientation`) plutôt que
    stockée en double, pour qu'elle ne puisse pas désynchroniser.
    """

    cartes: tuple[Carte, ...]
    energies: tuple[Carte, ...] = ()
    outil: Carte | None = None
    compteurs_degats: int = 0
    etats_speciaux: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class Joueur:
    """Un joueur et ses zones (R-3.1).

    Séparation stricte public / caché :

    * ``pioche`` — liste **ordonnée** ; l'ordre est de l'information cachée (anti-triche) ;
    * ``main`` — **privée** (visible de son seul propriétaire) ;
    * ``recompenses`` — **face cachée** (R-3.4), inconnues même de leur propriétaire ;
    * ``defausse`` et ``zone_perdue`` — **publiques** (face visible) ;
    * ``actif`` / ``banc`` — **publics** (les Pokémon en jeu sont visibles des deux joueurs).
    """

    id: str
    pioche: tuple[Carte, ...] = ()
    main: tuple[Carte, ...] = ()
    actif: PokemonEnJeu | None = None
    banc: tuple[PokemonEnJeu, ...] = ()
    defausse: tuple[Carte, ...] = ()
    recompenses: tuple[Carte, ...] = ()
    zone_perdue: tuple[Carte, ...] = ()


@dataclass(frozen=True)
class Tour:
    """L'état du tour courant (R-5).

    ``joueur_actif`` : identifiant du joueur dont c'est le tour. ``numero`` : numéro de
    tour (1-based). ``phase`` ∈ :data:`PHASES`. Les trois drapeaux portent les « une
    seule fois par tour » : énergie attachée (R-5.4), Supporter joué (R-5.5), retraite
    faite (R-5.6).

    ``entres_en_jeu_ce_tour`` : identités (``instance_id`` de la **carte de base**, qui ne
    change pas à l'évolution) des Pokémon **entrés en jeu pendant CE tour**. Sert la règle
    R-7.3 — on ne peut pas faire évoluer un Pokémon le tour où il est entré en jeu. Comme
    les drapeaux, cet ensemble est **remis à vide** à chaque nouveau tour (un tour neuf naît
    sans historique) : toute cette information est donc portée par l'état, donc sérialisée,
    donc reprise après un F5.

    **Convention de numérotation (invariant du moteur)** : le tour 1 est celui du joueur
    **qui commence** (R-4.7) ; les tours alternent ensuite. Le premier tour de chaque joueur
    est donc : numéro 1 pour celui qui commence, numéro 2 pour l'autre. Les règles du premier
    tour (R-6.*) se dérivent de ce seul numéro (voir :mod:`pbm_game.tour.drapeaux`).
    """

    joueur_actif: str
    numero: int
    phase: str
    energie_posee: bool = False
    supporter_joue: bool = False
    retraite_faite: bool = False
    entres_en_jeu_ce_tour: frozenset[str] = field(default_factory=frozenset)
    #: Identités (``instance_id`` de carte de base) des Pokémon qui ont **évolué** ce tour —
    #: pour R-7.4 (pas deux évolutions du même Pokémon dans le même tour). Distinct de
    #: ``entres_en_jeu_ce_tour`` (R-7.3, pose) : une évolution ne rend pas le Pokémon « nouveau
    #: en jeu » pour l'attaque ou la retraite, seulement pour une seconde évolution. Remis à
    #: vide à chaque tour neuf, comme les drapeaux — donc sérialisé, donc repris après un F5.
    evolues_ce_tour: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class EtatPartie:
    """L'état complet d'une partie — l'objet que toute la suite manipule.

    ``joueurs`` : exactement deux. ``stade`` : le Stade **unique** en jeu, partagé par
    les deux joueurs (R-3.5) ; ``stade_proprietaire`` nomme qui l'a posé (pour sa
    défausse). Une partie **terminée** est figée (R-14.6) : ``terminee`` vrai,
    ``vainqueur`` = l'id du gagnant (ou ``None`` pour une égalité, R-14.4),
    ``raison_fin`` le motif.

    ``resolution`` : une **demande de décision en cours** (lot ``j-effets-choix``), ou ``None``
    quand aucune n'attend. Quand elle n'est pas ``None``, la partie est **en pause** : un joueur —
    éventuellement l'adversaire — doit trancher un choix avant que la résolution d'un effet ne
    reprenne. C'est une donnée (type ``pbm_game.demandes.moteur.ResolutionEnCours``), pas une
    attente de code : elle est sérialisée avec l'état, donc une partie interrompue au milieu d'une
    demande **reprend exactement à cette demande**. Annotée en chaîne (``from __future__``) pour ne
    pas importer le paquet ``demandes`` ici — ``state.modele`` reste une feuille sans dépendance.
    """

    joueurs: tuple[Joueur, Joueur]
    tour: Tour
    schema_version: int = SCHEMA_VERSION
    stade: Carte | None = None
    stade_proprietaire: str | None = None
    terminee: bool = False
    vainqueur: str | None = None
    raison_fin: str | None = None
    resolution: ResolutionEnCours | None = None


def orientation(pokemon: PokemonEnJeu) -> str:
    """L'orientation d'un Pokémon, dérivée de son état d'orientation (R-11.8).

    Renvoie :data:`ENDORMI`, :data:`CONFUS` ou :data:`PARALYSE` si l'un est présent,
    sinon :data:`ORIENTATION_NORMALE`. Lève ``ValueError`` si **plusieurs** états
    d'orientation coexistent — c'est une incohérence que R-11.8 interdit (un seul à la
    fois), jamais un cas à trancher en silence.
    """
    presents = sorted(pokemon.etats_speciaux & ETATS_ORIENTATION)
    if len(presents) > 1:
        raise ValueError(
            f"Orientation ambiguë : {presents} coexistent, or R-11.8 n'en permet qu'un seul."
        )
    return presents[0] if presents else ORIENTATION_NORMALE


def carte_active(pokemon: PokemonEnJeu) -> Carte:
    """La carte du sommet de la pile d'évolutions — l'évolution courante (R-3.6, R-7.1)."""
    if not pokemon.cartes:
        raise ValueError("Un Pokémon en jeu a toujours au moins une carte dans sa pile.")
    return pokemon.cartes[-1]
