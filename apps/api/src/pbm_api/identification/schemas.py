"""Schéma d'extraction par carte (mission `v3-identification` point 1, étendu par `v3-etat`).

Un seul appel `AIProvider.extract` par carte, dès le premier tir (principe cadre, voir
`docs/ARCHITECTURE.md` § « la base sait, l'IA reconnaît ») : ce schéma ne demande au modèle que
ce que le catalogue ne sait pas déjà déduire d'une photo (nom, numéro, extension, langue, PV,
variante) — jamais une information que le rapprochement catalogue pourrait retrouver seul. Les
champs `*_wear`/`counterfeit_*` (lot `v3-etat`) suivent le même principe côté état de
l'exemplaire : coins, bords et surface ne se mesurent pas par OpenCV comme le centrage
(`pbm_api.state.centering`), ils sont demandés au modèle dans ce même appel plutôt que d'en
ajouter un second (« un seul appel IA par carte, dès le premier tir »).
"""

from enum import StrEnum

from pydantic import BaseModel, Field

from pbm_api.state.grades import ConditionGrade


class CardVariantGuess(StrEnum):
    """Variante visuelle telle que perçue sur la photo — un indice pour la validation humaine
    (lot `v3-validation`), pas encore la variante retenue en collection (`PriceVariant`,
    `pbm_api.models.catalog`) : une énumération distincte évite de faire dépendre ce schéma d'un
    type Postgres partagé avec la tarification, et couvre des cas que l'IA peut décrire mais
    qu'aucune variante de prix ne modélise encore (full art, gold)."""

    normal = "normal"
    holo = "holo"
    reverse_holo = "reverse_holo"
    first_edition = "first_edition"
    full_art = "full_art"
    gold = "gold"
    other = "other"


class CardExtraction(BaseModel):
    """Sortie structurée demandée au fournisseur IA pour une carte déjà recadrée et redressée
    (630×880 px, `pbm_api.detection.geometry`). Un champ de confiance (0..1) accompagne chaque
    valeur lue, y compris quand elle est absente (`None` + confiance à 0) — c'est ce que
    `pbm_api.identification.reconciliation` pondère pour décider si un candidat catalogue est
    présélectionné."""

    name: str | None = None
    name_confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    number: str | None = None
    number_confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    total: int | None = None
    total_confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    set_code: str | None = None
    set_code_confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    language: str | None = None
    language_confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    hp: int | None = None
    hp_confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    card_type: str | None = None
    card_type_confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    variant: CardVariantGuess | None = None
    variant_confidence: float = Field(ge=0.0, le=1.0, default=0.0)

    # État de l'exemplaire (mission `v3-etat` point 1) : un palier par défaut, pas une mesure —
    # la confiance doit chuter (jamais être maquillée) quand la photo ne permet pas de juger
    # (pochette/toploader, reflet) ; voir `pbm_api.state.centering` pour le centrage, mesuré par
    # OpenCV plutôt que demandé ici.
    corner_wear: ConditionGrade | None = None
    corner_wear_confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    corner_wear_note: str | None = None
    edge_wear: ConditionGrade | None = None
    edge_wear_confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    edge_wear_note: str | None = None
    surface_wear: ConditionGrade | None = None
    surface_wear_confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    surface_wear_note: str | None = None

    # Indices de contrefaçon (mission point 3) : police, couleurs, format du numéro incohérents
    # avec une carte officielle — jamais un simple "je ne reconnais pas cette carte" (ça, c'est
    # le rôle du rapprochement catalogue, `pbm_api.identification.reconciliation`).
    counterfeit_suspected: bool = False
    counterfeit_confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    counterfeit_reason: str | None = None


class CardBottomReading(BaseModel):
    """Seconde passe ciblée sur le bas de la carte (lot `pbm-parcours-validation`, mission point
    4) : quand le premier appel n'a pas lu de numéro fiable, une image AGRANDIE de la seule bande
    inférieure est renvoyée au modèle pour lire numéro / total / code d'extension — qui y sont
    imprimés en tout petit, souvent illisibles sur le recadrage entier. Schéma volontairement
    réduit à ces trois champs : le reste (nom, état, contrefaçon) est déjà connu du premier
    appel, jamais redemandé (le principe « un seul appel par carte » cède ici sur les seules
    cartes dont le numéro manque — arbitrage JF 20/09/2026, comme le secours vision)."""

    number: str | None = None
    number_confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    total: int | None = None
    total_confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    set_code: str | None = None
    set_code_confidence: float = Field(ge=0.0, le=1.0, default=0.0)


class IdentificationCandidate(BaseModel):
    """Un candidat du catalogue, classé (mission point 2) — forme stockée dans
    `Detection.candidates` (JSONB, liste de ces objets, au plus trois)."""

    card_id: str
    set_id: str
    name: str
    number: str
    set_name: str
    set_code: str
    catalog_score: float
    combined_score: float
    preselected: bool
