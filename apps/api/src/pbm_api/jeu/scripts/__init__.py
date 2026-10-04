"""`pbm_api.jeu.scripts` — la **compilation du catalogue en cartes jouables** (lot
`j-effets-catalogue-compilation`).

Le pont entre le catalogue (des textes d'effet) et le moteur (des scripts DSL). Un script d'effet
n'est pas écrit par carte mais **par texte** : des centaines de cartes partageant le même effet sont
couvertes par un seul script, repéré par l'**empreinte** de son texte source.

* :mod:`.empreinte` — normalisation et empreinte d'un texte, extraction des effets d'une carte ;
* :mod:`.groupement` — la mesure du regroupement (combien de scripts le partage économise, pur) ;
* :mod:`.depot` — l'accès base au registre `card_scripts` (lire, enregistrer, valider) ;
* :mod:`.chargeur` — résout un deck en scripts validés, refuse (D9) un effet non scripté ;
* :mod:`.errata` — la détection des textes modifiés, qui repasse les scripts concernés « à revoir ».
"""

from __future__ import annotations

from pbm_api.jeu.scripts.chargeur import refus_scripts_cartes, refus_scripts_deck
from pbm_api.jeu.scripts.empreinte import (
    EffetCarte,
    effets_scriptables,
    empreinte_texte,
    normaliser_texte,
)
from pbm_api.jeu.scripts.errata import detecter_errata, empreintes_vivantes
from pbm_api.jeu.scripts.groupement import MesureGroupement, mesurer_groupement

__all__ = [
    "EffetCarte",
    "effets_scriptables",
    "empreinte_texte",
    "normaliser_texte",
    "MesureGroupement",
    "mesurer_groupement",
    "refus_scripts_cartes",
    "refus_scripts_deck",
    "detecter_errata",
    "empreintes_vivantes",
]
