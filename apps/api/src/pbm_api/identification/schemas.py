"""Schéma d'extraction par carte (mission `v3-identification` point 1).

Un seul appel `AIProvider.extract` par carte, dès le premier tir (principe cadre, voir
`docs/ARCHITECTURE.md` § « la base sait, l'IA reconnaît ») : ce schéma ne demande au modèle que
ce que le catalogue ne sait pas déjà déduire d'une photo (nom, numéro, extension, langue, PV,
variante) — jamais une information que le rapprochement catalogue pourrait retrouver seul.
"""

from enum import StrEnum

from pydantic import BaseModel, Field


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
