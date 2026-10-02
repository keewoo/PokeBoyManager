"""Le **vocabulaire fermé** du langage d'effets — la seule source de vérité.

Module **pur** (aucune E/S), comme tout ``pbm_game``. Il ne porte que des *constantes* : les
noms de primitives, de zones, de propriétaires, de catégories de carte et de conditions que le
langage reconnaît. Tout le reste du DSL (modèle, chargement, schéma, sélection, primitives,
interprète) importe d'ici — et l'outil de dépouillement (``apps/game/tools/classer_dsl.py``)
aussi, pour qu'il n'existe **jamais** deux listes à tenir en phase.

**Pourquoi une liste fermée (D9).** Un effet qui ne s'exprime pas avec ce vocabulaire est
déclaré *non supporté* à la construction du deck — il n'est pas approximé par une primitive
« code libre » qui exécuterait n'importe quoi. C'est le piège central que la fiche du lot nomme :
la primitive fourre-tout apparaît au bout de trois jours, et à partir de là plus rien n'est
vérifiable ni générable. Elle n'existe pas ici, et le test de couverture
(``test_dsl_couverture``) **mord** si on tente de la réintroduire sous un autre nom.

Les primitives, sélecteurs et conditions ont été dégagés d'un dépouillement de **500 textes
d'effet réels** du catalogue (``apps/game/tools/classer_dsl.py`` →
``tests/donnees/echantillon_500_dsl.json``). Le détail de chaque mot vit dans ``docs/jeu/DSL.md``.
"""

from __future__ import annotations

# --- Version du langage -------------------------------------------------------
#: Version du schéma du langage d'effets. Toute évolution **incompatible** de la forme d'un
#: script (nom de primitive retiré, paramètre devenu obligatoire, sémantique changée) l'incrémente.
#: ``charger_programme`` refuse une version **future** (jamais de repli silencieux) et garde la
#: lecture des versions passées (critère d'acceptation n°4 : un script v1 reste lisible en v2).
DSL_VERSION = 1

#: La plus **ancienne** version de script encore lisible par l'interprète courant. Tant qu'elle
#: vaut 1, tout script v1…DSL_VERSION se charge ; relever ce plancher (abandonner une vieille
#: version) est un choix explicite, tracé, jamais un oubli.
DSL_VERSION_MIN = 1

# --- Les primitives (ce qu'une carte sait FAIRE) ------------------------------
# Un verbe par ligne, nommé en français, tel qu'il apparaît dans le texte des cartes. Chaque
# primitive a sa fonction pure dans ``primitives.py`` et son entrée dans ``docs/jeu/DSL.md``.
OP_PIOCHER = "piocher"  # « Piochez N cartes. »
OP_CHERCHER = "chercher"  # « Cherchez dans votre deck … » (pioche → une destination)
OP_DEFAUSSER = "defausser"  # « Défaussez … »
OP_ATTACHER = "attacher"  # « Attachez cette carte Énergie à … »
OP_DEPLACER = "deplacer"  # « Déplacez une énergie / des dégâts de … vers … »
OP_SOIGNER = "soigner"  # « Soignez N dégâts de … » (retire des compteurs)
OP_POSER_COMPTEURS = "poser_compteurs"  # « Placez N compteurs de dégâts sur … »
OP_INFLIGER_DEGATS = "infliger_degats"  # « … inflige N dégâts à … » (dégâts d'effet)
OP_MELANGER = "melanger"  # « Mélangez votre deck. »
OP_REVELER = "reveler"  # « Montrez … à votre adversaire. »
OP_REGARDER = "regarder"  # « Regardez les N cartes du dessus de votre deck. »
OP_CHOISIR = "choisir"  # « Choisissez 1 de vos Pokémon … » (point de décision)
OP_PILE_OU_FACE = "pile_ou_face"  # « Lancez une pièce. Si c'est face, … »
OP_CHANGER_ACTIF = "changer_actif"  # « Changez votre Pokémon Actif … » (échange forcé)
OP_POSER_ETAT = "poser_etat"  # « … est maintenant Empoisonné / Endormi / … »
OP_RETIRER_ETAT = "retirer_etat"  # « … n'est plus Empoisonné / Confus / … »
OP_EMPECHER = "empecher"  # « … ne peut pas attaquer / jouer de Supporter … » (pose un verrou)
OP_ANNULER = "annuler"  # « Prévenez tous les dégâts … » (annule un effet en cours)

#: Les primitives reconnues. Fermée (D9) : un ``op`` hors de cet ensemble est **refusé** au
#: chargement, jamais deviné. Il n'y a **pas** de primitive « code libre ».
OPS: frozenset[str] = frozenset(
    {
        OP_PIOCHER,
        OP_CHERCHER,
        OP_DEFAUSSER,
        OP_ATTACHER,
        OP_DEPLACER,
        OP_SOIGNER,
        OP_POSER_COMPTEURS,
        OP_INFLIGER_DEGATS,
        OP_MELANGER,
        OP_REVELER,
        OP_REGARDER,
        OP_CHOISIR,
        OP_PILE_OU_FACE,
        OP_CHANGER_ACTIF,
        OP_POSER_ETAT,
        OP_RETIRER_ETAT,
        OP_EMPECHER,
        OP_ANNULER,
    }
)

# --- Les structures de contrôle (ce qui ENCHAÎNE les primitives) --------------
#: Répéter une séquence d'effets N fois (« pour chaque … », « N fois »).
CTRL_REPETER = "repeter"
#: Brancher selon une condition (« si c'est face… », « si votre adversaire a… »).
CTRL_SI = "si"

#: Les structures de contrôle reconnues. Comme les primitives, elles sont *exécutées* par
#: l'interprète ; elles vivent dans la même liste d'instructions qu'une primitive.
CONTROLES: frozenset[str] = frozenset({CTRL_REPETER, CTRL_SI})

#: Tout ce qu'une instruction peut être : une primitive **ou** une structure de contrôle.
INSTRUCTIONS: frozenset[str] = OPS | CONTROLES

# --- Les zones (où vivent les cartes, R-3.1) ----------------------------------
ZONE_ACTIF = "actif"
ZONE_BANC = "banc"
ZONE_EN_JEU = "en_jeu"  # Actif + banc (commodité : « 1 de vos Pokémon »)
ZONE_MAIN = "main"
ZONE_PIOCHE = "pioche"
ZONE_DEFAUSSE = "defausse"
ZONE_RECOMPENSES = "recompenses"
ZONE_ZONE_PERDUE = "zone_perdue"
ZONE_STADE = "stade"

#: Les zones reconnues par un sélecteur. Une zone hors liste est refusée (D9).
ZONES: frozenset[str] = frozenset(
    {
        ZONE_ACTIF,
        ZONE_BANC,
        ZONE_EN_JEU,
        ZONE_MAIN,
        ZONE_PIOCHE,
        ZONE_DEFAUSSE,
        ZONE_RECOMPENSES,
        ZONE_ZONE_PERDUE,
        ZONE_STADE,
    }
)

# --- Le propriétaire visé (de qui parle le sélecteur) -------------------------
PROPRIO_MOI = "moi"  # le joueur qui joue l'effet
PROPRIO_ADVERSAIRE = "adversaire"
PROPRIO_LES_DEUX = "les_deux"

PROPRIETAIRES: frozenset[str] = frozenset({PROPRIO_MOI, PROPRIO_ADVERSAIRE, PROPRIO_LES_DEUX})

# --- Les catégories de carte (pour filtrer un sélecteur) ----------------------
CAT_POKEMON = "pokemon"
CAT_ENERGIE = "energie"
CAT_DRESSEUR = "dresseur"
CAT_OUTIL = "outil"

CATEGORIES: frozenset[str] = frozenset({CAT_POKEMON, CAT_ENERGIE, CAT_DRESSEUR, CAT_OUTIL})

# --- D'où l'on prend dans une zone ORDONNÉE (pioche, défausse, zone perdue) ----
# L'ordre d'une zone cachée est de l'information sensible (anti-triche) : « les 7 cartes du
# dessus » ne se confond pas avec « 7 cartes au choix ». La position le dit explicitement.
POSITION_DESSUS = "dessus"
POSITION_DESSOUS = "dessous"
POSITION_AU_CHOIX = "au_choix"  # le joueur (ou la stratégie) choisit lesquelles

POSITIONS: frozenset[str] = frozenset({POSITION_DESSUS, POSITION_DESSOUS, POSITION_AU_CHOIX})

# --- Les conditions (ce qu'un « si » ou un coût teste) ------------------------
#: Le dernier pile ou face est tombé sur face (``{"type": "resultat_pile", "attendu": "face"}``).
COND_RESULTAT_PILE = "resultat_pile"
#: Une zone (via un sélecteur) n'est pas vide (« si votre adversaire a des cartes en main »).
COND_ZONE_NON_VIDE = "zone_non_vide"
#: Un Pokémon porte un état spécial (« si le Pokémon Défenseur est Empoisonné »).
COND_A_ETAT = "a_etat"
#: Un Pokémon porte au moins N compteurs de dégâts.
COND_A_DEGATS = "a_degats"

CONDITIONS: frozenset[str] = frozenset(
    {COND_RESULTAT_PILE, COND_ZONE_NON_VIDE, COND_A_ETAT, COND_A_DEGATS}
)

__all__ = [
    "DSL_VERSION",
    "DSL_VERSION_MIN",
    "OP_PIOCHER",
    "OP_CHERCHER",
    "OP_DEFAUSSER",
    "OP_ATTACHER",
    "OP_DEPLACER",
    "OP_SOIGNER",
    "OP_POSER_COMPTEURS",
    "OP_INFLIGER_DEGATS",
    "OP_MELANGER",
    "OP_REVELER",
    "OP_REGARDER",
    "OP_CHOISIR",
    "OP_PILE_OU_FACE",
    "OP_CHANGER_ACTIF",
    "OP_POSER_ETAT",
    "OP_RETIRER_ETAT",
    "OP_EMPECHER",
    "OP_ANNULER",
    "OPS",
    "CTRL_REPETER",
    "CTRL_SI",
    "CONTROLES",
    "INSTRUCTIONS",
    "ZONE_ACTIF",
    "ZONE_BANC",
    "ZONE_EN_JEU",
    "ZONE_MAIN",
    "ZONE_PIOCHE",
    "ZONE_DEFAUSSE",
    "ZONE_RECOMPENSES",
    "ZONE_ZONE_PERDUE",
    "ZONE_STADE",
    "ZONES",
    "PROPRIO_MOI",
    "PROPRIO_ADVERSAIRE",
    "PROPRIO_LES_DEUX",
    "PROPRIETAIRES",
    "CAT_POKEMON",
    "CAT_ENERGIE",
    "CAT_DRESSEUR",
    "CAT_OUTIL",
    "CATEGORIES",
    "POSITION_DESSUS",
    "POSITION_DESSOUS",
    "POSITION_AU_CHOIX",
    "POSITIONS",
    "COND_RESULTAT_PILE",
    "COND_ZONE_NON_VIDE",
    "COND_A_ETAT",
    "COND_A_DEGATS",
    "CONDITIONS",
]
