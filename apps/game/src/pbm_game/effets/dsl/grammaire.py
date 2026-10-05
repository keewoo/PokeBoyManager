"""La **grammaire documentée** du langage d'effets — le schéma *par primitive*, et des exemples
prouvés, pour le prompt d'assistance IA.

Module **pur** (aucune E/S), comme tout ``pbm_game``. Il ne porte que des *données* : pour chaque
instruction du langage, ses **arguments requis et facultatifs**, un **exemple valide**, et une note
sémantique ; et une poignée d'**exemples complets** (texte → script → essais) qui *passent*
réellement la porte de vérification.

**Pourquoi ce module existe (lot ``ia-scripts-passe-2``).** Le premier passage d'assistance IA a
produit **0 script admissible sur 97** : le prompt listait les *noms* des primitives
(``grammaire_dsl``) mais pas, pour chacune, ses arguments — le modèle inventait des clés ou en
oubliait (``piocher`` sans ``nombre``), et le chargeur strict (:mod:`.chargement`) les refusait à
raison. Et faute d'exemple complet, les **cas de test** écrits par le modèle ne collaient pas au
format d'état exact du moteur. Ce module comble les deux trous, **sans recopier** le langage à la
main :

* :data:`SPEC_OPS` dérive ses « arguments requis » des **constantes du moteur**
  (:data:`~pbm_game.effets.dsl.chargement.OPS_CIBLE_REQUISE`, ``OPS_SOURCE_REQUISE``,
  ``OPS_NOMBRE_REQUIS``, :data:`~pbm_game.state.modele.ETATS_SPECIAUX`,
  :data:`~pbm_game.effets.verrous.VERROUS`, ``PORTEES_VERROU``). Un test de cohérence
  (``apps/game/tests/test_grammaire_dsl.py``) **mord** si le moteur gagne, perd ou change une
  primitive sans que cette grammaire suive : chaque exemple est rechargé par ``charger_programme``,
  et le retrait de chaque argument déclaré « requis » doit faire échouer le chargement.
* :data:`EXEMPLES_AMORCE` sont des exemples **validés** (chacun passe
  :func:`~pbm_game.effets.dsl.essais.verifier_script` dans le même test) — ils amorcent le prompt
  même quand ``card_scripts`` est vide, et montrent le format d'état d'un essai qui *passe*.

Le rendu en texte (ce que le prompt cite) vit dans
:func:`pbm_api.jeu.scripts.assistance.gabarit.grammaire_dsl` : ce module-ci ne fait que tenir la
donnée, au plus près du moteur qu'elle décrit.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...state.modele import ETATS_SPECIAUX
from ..verrous import PORTEES_VERROU, VERROUS
from .vocabulaire import (
    CTRL_REPETER,
    CTRL_SI,
    INSTRUCTIONS,
    OP_ANNULER,
    OP_ATTACHER,
    OP_CHANGER_ACTIF,
    OP_CHERCHER,
    OP_CHOISIR,
    OP_DEFAUSSER,
    OP_DEPLACER,
    OP_EMPECHER,
    OP_INFLIGER_DEGATS,
    OP_MELANGER,
    OP_PILE_OU_FACE,
    OP_PIOCHER,
    OP_POSER_COMPTEURS,
    OP_POSER_ETAT,
    OP_REGARDER,
    OP_RETIRER_ETAT,
    OP_REVELER,
    OP_SOIGNER,
)


@dataclass(frozen=True)
class SpecOp:
    """La fiche d'une instruction : ce qu'elle fait, ses arguments, un exemple, une note.

    * ``resume`` — une phrase : ce que l'instruction fait, dans les termes des cartes ;
    * ``requis`` — les clés **obligatoires** ; retirer l'une d'elles de ``exemple`` doit faire
      échouer :func:`~pbm_game.effets.dsl.chargement.charger_programme` (le test anti-dérive) ;
    * ``optionnels`` — les clés acceptées mais non obligatoires ;
    * ``exemple`` — une instruction **valide** (se charge seule, emballée dans un programme) ;
    * ``note`` — le piège à éviter, surtout l'unité d'un ``nombre`` (marqueurs vs PV).
    """

    resume: str
    requis: tuple[str, ...]
    optionnels: tuple[str, ...]
    exemple: dict
    note: str = ""


#: Le schéma, instruction par instruction. **Toutes** les instructions du langage y figurent
#: (``set(SPEC_OPS) == INSTRUCTIONS``, garanti par test) : primitives (:data:`.vocabulaire.OPS`) et
#: structures de contrôle (:data:`.vocabulaire.CONTROLES`). Les « requis » reflètent exactement la
#: porte de :mod:`.chargement` — c'est elle qui tranche, ce module ne fait que la décrire.
SPEC_OPS: dict[str, SpecOp] = {
    OP_PIOCHER: SpecOp(
        resume="Piocher N cartes du dessus de la pioche vers la main.",
        requis=("nombre",),
        optionnels=("cible",),
        exemple={"op": "piocher", "nombre": 2},
        note="« nombre » = cartes. « Votre adversaire pioche N » : "
        'cible={"zone":"pioche","proprietaire":"adversaire"}.',
    ),
    OP_CHERCHER: SpecOp(
        resume="Chercher des cartes dans une zone (la pioche) et les mettre en main.",
        requis=("cible",),
        optionnels=(),
        exemple={
            "op": "chercher",
            "cible": {"zone": "pioche", "categorie": "pokemon", "nombre": 1},
        },
        note="« cible » décrit QUOI chercher (zone, catégorie, stade, nombre). Les cartes "
        "trouvées rejoignent la main.",
    ),
    OP_DEFAUSSER: SpecOp(
        resume="Défausser les cartes désignées vers la défausse de leur propriétaire.",
        requis=("cible",),
        optionnels=(),
        exemple={"op": "defausser", "cible": {"zone": "main", "proprietaire": "moi", "nombre": 1}},
        note="",
    ),
    OP_ATTACHER: SpecOp(
        resume="Attacher une carte (Énergie ou Outil) depuis une zone à un Pokémon.",
        requis=("source", "cible"),
        optionnels=(),
        exemple={
            "op": "attacher",
            "source": {"zone": "defausse", "categorie": "energie", "nombre": 1},
            "cible": {"zone": "actif", "proprietaire": "moi"},
        },
        note="« source » = la carte à attacher (categorie energie|outil) ; « cible » = le Pokémon "
        "destination.",
    ),
    OP_DEPLACER: SpecOp(
        resume="Déplacer N énergies d'un Pokémon vers un autre, ou vers la défausse (coût).",
        requis=("source", "cible"),
        optionnels=("nombre",),
        exemple={
            "op": "deplacer",
            "source": {"zone": "banc", "proprietaire": "moi", "nombre": 1},
            "cible": {"zone": "actif", "proprietaire": "moi"},
            "nombre": 1,
        },
        note="« source » = Pokémon d'origine ; « cible » = Pokémon destination, ou "
        '{"zone":"defausse"} pour défausser l\'énergie. « nombre » = énergies déplacées.',
    ),
    OP_SOIGNER: SpecOp(
        resume="Retirer des compteurs de dégâts d'un Pokémon.",
        requis=("cible",),
        optionnels=("nombre",),
        exemple={"op": "soigner", "cible": {"zone": "actif", "proprietaire": "moi"}, "nombre": 3},
        note="⚠️ « nombre » = MARQUEURS (1 marqueur = 10 PV). « Soignez 30 dégâts » → nombre:3, "
        "jamais 30. Sans « nombre » : soigne tout.",
    ),
    OP_POSER_COMPTEURS: SpecOp(
        resume="Placer N marqueurs de dégâts sur un Pokémon (sans faiblesse/résistance).",
        requis=("cible", "nombre"),
        optionnels=(),
        exemple={
            "op": "poser_compteurs",
            "cible": {"zone": "actif", "proprietaire": "adversaire"},
            "nombre": 2,
        },
        note="⚠️ « nombre » = MARQUEURS (1 marqueur = 10 PV). « Placez 2 marqueurs » → nombre:2 "
        "(= 20 PV de dégâts).",
    ),
    OP_INFLIGER_DEGATS: SpecOp(
        resume="Infliger N dégâts d'effet directs à un Pokémon.",
        requis=("cible", "nombre"),
        optionnels=(),
        exemple={
            "op": "infliger_degats",
            "cible": {"zone": "actif", "proprietaire": "adversaire"},
            "nombre": 20,
        },
        note="⚠️ « nombre » = DÉGÂTS en PV, multiple de 10. « inflige 20 dégâts » → nombre:20.",
    ),
    OP_MELANGER: SpecOp(
        resume="Mélanger une zone de cartes (par défaut sa pioche).",
        requis=(),
        optionnels=("cible",),
        exemple={"op": "melanger", "cible": {"zone": "pioche", "proprietaire": "moi"}},
        note='Sans « cible » : mélange sa pioche. cible={"zone":"main"} : remet la main dans le '
        "deck puis mélange.",
    ),
    OP_REVELER: SpecOp(
        resume="Montrer des cartes à l'adversaire (sans les déplacer).",
        requis=("cible",),
        optionnels=(),
        exemple={"op": "reveler", "cible": {"zone": "main", "proprietaire": "adversaire"}},
        note="",
    ),
    OP_REGARDER: SpecOp(
        resume="Regarder des cartes d'une zone ordonnée (information privée).",
        requis=("cible",),
        optionnels=(),
        exemple={
            "op": "regarder",
            "cible": {"zone": "pioche", "proprietaire": "moi", "nombre": 3, "position": "dessus"},
        },
        note="« position » (dessus/dessous) dit d'où l'on regarde dans une zone ordonnée.",
    ),
    OP_CHOISIR: SpecOp(
        resume="Ouvrir un point de décision : choisir N cibles parmi des options, puis agir.",
        requis=("cible",),
        optionnels=("nombre", "alors"),
        exemple={
            "op": "choisir",
            "cible": {"zone": "en_jeu", "proprietaire": "moi", "nombre": 1},
            "alors": [{"op": "soigner", "nombre": 2}],
        },
        note="« cible » = les OPTIONS ; « nombre » = combien choisir ; « alors » agit sur les "
        "choisis — ses primitives n'ont alors PAS besoin de « cible ».",
    ),
    OP_PILE_OU_FACE: SpecOp(
        resume="Lancer une ou des pièces, et brancher selon le résultat.",
        requis=("alors",),
        optionnels=("nombre", "sinon", "jusqu_a_echec"),
        exemple={"op": "pile_ou_face", "nombre": 1, "alors": [{"op": "piocher", "nombre": 1}]},
        note="« alors » est joué une fois PAR FACE ; « sinon » une seule fois si pile. « nombre » "
        "= pièces (défaut 1) ; « jusqu_a_echec »:true = jusqu'à obtenir pile.",
    ),
    OP_CHANGER_ACTIF: SpecOp(
        resume="Échanger l'Actif contre un Pokémon de Banc (échange forcé, sans coût).",
        requis=("cible",),
        optionnels=(),
        exemple={
            "op": "changer_actif",
            "cible": {"zone": "banc", "proprietaire": "adversaire", "nombre": 1},
        },
        note="« cible » = un Pokémon de BANC (zone:banc). proprietaire:adversaire = l'appât ; "
        "proprietaire:moi = un changement de son côté.",
    ),
    OP_POSER_ETAT: SpecOp(
        resume="Infliger un état spécial à un Pokémon.",
        requis=("cible", "etat"),
        optionnels=(),
        exemple={
            "op": "poser_etat",
            "cible": {"zone": "actif", "proprietaire": "adversaire"},
            "etat": "empoisonne",
        },
        note=f"« etat » ∈ {{{', '.join(sorted(ETATS_SPECIAUX))}}}.",
    ),
    OP_RETIRER_ETAT: SpecOp(
        resume="Retirer un état spécial d'un Pokémon (ou tous).",
        requis=("cible",),
        optionnels=("etat",),
        exemple={
            "op": "retirer_etat",
            "cible": {"zone": "actif", "proprietaire": "moi"},
            "etat": "confus",
        },
        note="Sans « etat » : retire TOUS les états.",
    ),
    OP_EMPECHER: SpecOp(
        resume="Poser un verrou (interdire une action) pour une portée donnée.",
        requis=("verrou", "portee"),
        optionnels=("cible",),
        exemple={
            "op": "empecher",
            "verrou": "ne_peut_attaquer",
            "portee": "prochain_tour",
            "cible": {"zone": "actif", "proprietaire": "adversaire"},
        },
        note=f"« verrou » ∈ {{{', '.join(sorted(VERROUS))}}} ; "
        f"« portee » ∈ {{{', '.join(sorted(PORTEES_VERROU))}}}.",
    ),
    OP_ANNULER: SpecOp(
        resume="Prévenir tous les dégâts (en coût ou en réaction).",
        requis=(),
        optionnels=(),
        exemple={"op": "annuler"},
        note="Lève le drapeau « dégâts annulés » que la résolution de combat lit.",
    ),
    CTRL_REPETER: SpecOp(
        resume="Répéter une séquence N fois, ou une fois par cible d'une source.",
        requis=("nombre", "alors"),
        optionnels=("source",),
        exemple={"op": "repeter", "nombre": 2, "alors": [{"op": "piocher", "nombre": 1}]},
        note="« nombre » (fixe) OU « source » (« pour chaque … ») ; « alors » = le corps répété.",
    ),
    CTRL_SI: SpecOp(
        resume="Brancher selon une condition.",
        requis=("condition", "alors"),
        optionnels=("sinon",),
        exemple={
            "op": "si",
            "condition": {"type": "resultat_pile", "attendu": "face"},
            "alors": [{"op": "piocher", "nombre": 1}],
        },
        note="« condition » obligatoire ; au moins une branche « alors » ou « sinon ».",
    ),
}


# --- Exemples complets, validés (texte → script → essais qui passent) ---------------------------
#
# Chaque entrée passe :func:`pbm_game.effets.dsl.essais.verifier_script` (test anti-dérive) : le
# script se charge, il a au moins un essai, et chaque essai est vert (attendu tenu ET cartes
# conservées). Ils servent deux buts : amorcer le prompt quand ``card_scripts`` est vide (le modèle
# calque une forme qui marche, pas une grammaire seule), et montrer le **format exact d'un essai**
# (état de départ concis, contexte par défaut alice/bob, attendu partiel sur l'état final).
#
# Format d'un essai (cf. :mod:`pbm_game.effets.dsl.essais` et ``docs/jeu/CAS-EXECUTABLES.md``) : un
# Pokémon = {pv, recompenses, degats (en PV), etats, energies, cartes, outil} ; un joueur =
# {actif, banc, pioche, main, defausse, recompenses, zone_perdue (des entiers)} ; l'« attendu » ne
# vérifie QUE les champs qu'il nomme (assertions partielles).

EXEMPLES_AMORCE: tuple[dict, ...] = (
    {
        "source_text": "Piochez 2 cartes.",
        "script": {"version": 1, "effets": [{"op": "piocher", "nombre": 2}]},
        "essais": [
            {
                "nom": "pioche 2",
                "etat": {
                    "alice": {"actif": {"pv": 60, "recompenses": 1}, "pioche": 5, "main": 0},
                    "bob": {"actif": {"pv": 60, "recompenses": 1}},
                },
                "attendu": {"etat": {"alice": {"pioche": 3, "main": 2}}},
            }
        ],
    },
    {
        "source_text": "Soignez 30 dégâts d'un de vos Pokémon.",
        "script": {
            "version": 1,
            "effets": [
                {
                    "op": "choisir",
                    "cible": {"zone": "en_jeu", "proprietaire": "moi", "nombre": 1},
                    "alors": [{"op": "soigner", "nombre": 3}],
                }
            ],
        },
        "essais": [
            {
                "nom": "soigne 30 (= 3 marqueurs)",
                "etat": {
                    "alice": {"actif": {"pv": 60, "recompenses": 1, "degats": 30}},
                    "bob": {"actif": {"pv": 60, "recompenses": 1}},
                },
                "attendu": {"etat": {"alice": {"actif": {"degats": 0}}}},
            }
        ],
    },
    {
        "source_text": "Placez 2 marqueurs de dégâts sur le Pokémon Actif de votre adversaire.",
        "script": {
            "version": 1,
            "effets": [
                {
                    "op": "poser_compteurs",
                    "cible": {"zone": "actif", "proprietaire": "adversaire"},
                    "nombre": 2,
                }
            ],
        },
        "essais": [
            {
                "nom": "2 marqueurs = 20 PV",
                "etat": {
                    "alice": {"actif": {"pv": 60, "recompenses": 1}},
                    "bob": {"actif": {"pv": 60, "recompenses": 1}},
                },
                "attendu": {"etat": {"bob": {"actif": {"degats": 20}}}},
            }
        ],
    },
    {
        "source_text": "Le Pokémon Actif de votre adversaire est maintenant Empoisonné.",
        "script": {
            "version": 1,
            "effets": [
                {
                    "op": "poser_etat",
                    "cible": {"zone": "actif", "proprietaire": "adversaire"},
                    "etat": "empoisonne",
                }
            ],
        },
        "essais": [
            {
                "nom": "empoisonne l'Actif adverse",
                "etat": {
                    "alice": {"actif": {"pv": 60, "recompenses": 1}},
                    "bob": {"actif": {"pv": 60, "recompenses": 1}},
                },
                "attendu": {"etat": {"bob": {"actif": {"etats": ["empoisonne"]}}}},
            }
        ],
    },
    {
        "source_text": "Lancez une pièce. Si c'est face, piochez une carte.",
        "script": {
            "version": 1,
            "effets": [
                {"op": "pile_ou_face", "nombre": 1, "alors": [{"op": "piocher", "nombre": 1}]}
            ],
        },
        "essais": [
            {
                "nom": "face → pioche 1",
                "etat": {
                    "alice": {"actif": {"pv": 60, "recompenses": 1}, "pioche": 5, "main": 0},
                    "bob": {"actif": {"pv": 60, "recompenses": 1}},
                },
                "tirages": [{"flux": "dsl:pile:alice", "resultat": "face"}],
                "attendu": {"etat": {"alice": {"pioche": 4, "main": 1}}},
            }
        ],
    },
    {
        "source_text": "Changez un des Pokémon de Banc de votre adversaire par son Pokémon Actif.",
        "script": {
            "version": 1,
            "effets": [
                {
                    "op": "choisir",
                    "cible": {"zone": "banc", "proprietaire": "adversaire", "nombre": 1},
                    "alors": [{"op": "changer_actif"}],
                }
            ],
        },
        "essais": [
            {
                "nom": "appât : un Pokémon du banc adverse monte Actif",
                "etat": {
                    "alice": {"actif": {"pv": 60, "recompenses": 1}},
                    "bob": {"actif": {"pv": 60, "recompenses": 1}, "banc": 1},
                },
                "attendu": {"etat": {"bob": {"banc": 1, "actif_present": True}}},
            }
        ],
    },
)


def op_connu(op: str) -> bool:
    """Vrai si ``op`` est une instruction du langage décrite ici (et donc du moteur)."""
    return op in SPEC_OPS


__all__ = [
    "SpecOp",
    "SPEC_OPS",
    "EXEMPLES_AMORCE",
    "op_connu",
    "INSTRUCTIONS",
]
