"""`pbm_game.effets.dsl` — le **langage d'effets** : décrire ce qu'une carte fait, sans code.

Lot ``j-effets-dsl`` (jalon J2). Module **pur** (aucune E/S), comme tout ``pbm_game``.

Dix mille cartes ne s'écrivent pas en dix mille fonctions Python. Un **langage déclaratif**
rend les cartes lisibles, relisibles, testables, et écrivables par une IA sous contrôle. Un
*script d'effet* est une donnée (JSON) : une version, et une liste d'**instructions** —
primitives (piocher, chercher, défausser, attacher, soigner, pile ou face, poser un état…) et
structures de contrôle (``si``, ``repeter``). Chaque instruction cible des cartes via un
**sélecteur** (« mon Actif », « un Pokémon de base de ma pioche », « une carte Objet de ma
défausse »).

Le langage se pose **au-dessus de la pile d'effets** (:mod:`pbm_game.effets.pile`) :
:func:`compiler_en_effet` emballe un script en
:class:`~pbm_game.effets.pile.EffetEnAttente`, et :func:`resolveur_dsl` le résout. Il n'y a
**pas** de primitive « code libre » (D9) : une carte qui ne s'exprime pas avec le vocabulaire
fermé (:mod:`pbm_game.effets.dsl.vocabulaire`) est déclarée *non supportée* à la construction du
deck, jamais jouée de travers. Un script est **chargé et validé** (:func:`charger_programme`)
avant toute exécution — un script non conforme est refusé **là**, pas en pleine partie.

Le détail de chaque primitive, sélecteur et condition vit dans ``docs/jeu/DSL.md``.
"""

from __future__ import annotations

from .chargement import ProgrammeInvalide, charger_programme
from .contexte import ContexteEffet
from .interprete import (
    EVT_COUT_IMPAYABLE,
    EVT_DSL_CHOIX,
    EVT_DSL_PILE,
    EVT_DSL_PRIMITIVE,
    TYPE_EFFET_DSL,
    ResultatProgramme,
    StrategieChoix,
    compiler_en_effet,
    executer_programme,
    registre_dsl,
    resolveur_dsl,
    strategie_canonique,
)
from .modele import Condition, Instruction, Programme, Selecteur
from .vocabulaire import (
    CONDITIONS,
    CONTROLES,
    DSL_VERSION,
    INSTRUCTIONS,
    OPS,
    ZONES,
)

__all__ = [
    "charger_programme",
    "ProgrammeInvalide",
    "Programme",
    "Instruction",
    "Selecteur",
    "Condition",
    "ContexteEffet",
    "ResultatProgramme",
    "StrategieChoix",
    "strategie_canonique",
    "executer_programme",
    "compiler_en_effet",
    "resolveur_dsl",
    "registre_dsl",
    "TYPE_EFFET_DSL",
    "EVT_DSL_PRIMITIVE",
    "EVT_DSL_CHOIX",
    "EVT_DSL_PILE",
    "EVT_COUT_IMPAYABLE",
    "DSL_VERSION",
    "OPS",
    "CONTROLES",
    "INSTRUCTIONS",
    "ZONES",
    "CONDITIONS",
]
