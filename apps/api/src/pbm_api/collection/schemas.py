import uuid
from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field

from pbm_api.models.catalog import PriceVariant


class CollectionSort(StrEnum):
    value_desc = "value_desc"
    value_asc = "value_asc"
    value_change_30d_desc = "value_change_30d_desc"
    value_change_30d_asc = "value_change_30d_asc"
    acquired_at_desc = "acquired_at_desc"
    acquired_at_asc = "acquired_at_asc"
    number_asc = "number_asc"
    name_asc = "name_asc"


class CollectionListItem(BaseModel):
    id: uuid.UUID
    card_id: uuid.UUID
    set_id: uuid.UUID
    card_name: str
    card_number: str
    set_name: str
    set_code: str
    series: str | None
    rarity: str | None
    card_type: str | None
    language: str
    variant: PriceVariant
    condition_grade: str | None
    counterfeit_suspected: bool
    purchase_price: Decimal | None
    purchase_currency: str | None
    acquired_at: date | None
    value_eur: Decimal | None
    value_change_30d_eur: Decimal | None
    value_change_30d_pct: Decimal | None
    is_duplicate: bool


class CollectionAggregates(BaseModel):
    items_total: int
    items_priced: int
    items_missing_price: int
    total_value_eur: Decimal
    value_change_7d_eur: Decimal
    value_change_30d_eur: Decimal


class CollectionListResponse(BaseModel):
    items: list[CollectionListItem]
    next_cursor: str | None
    aggregates: CollectionAggregates


class CollectionFacetSet(BaseModel):
    set_id: uuid.UUID
    name: str
    code: str


class CollectionFacets(BaseModel):
    sets: list[CollectionFacetSet]
    series: list[str]
    rarities: list[str]
    card_types: list[str]
    languages: list[str]
    variants: list[PriceVariant]
    condition_grades: list[str]


class CreateCollectionItemRequest(BaseModel):
    card_id: uuid.UUID
    language: str = Field(default="fr", min_length=2, max_length=8)
    variant: PriceVariant = PriceVariant.normal
    quantity: int = Field(default=1, ge=1, le=50)
    condition_grade: str | None = None
    purchase_price: Decimal | None = Field(default=None, ge=0)
    purchase_currency: str | None = Field(default=None, min_length=3, max_length=3)
    acquired_at: date | None = None


class CreateCollectionItemResponse(BaseModel):
    collection_item_ids: list[uuid.UUID]


class UpdateCollectionItemRequest(BaseModel):
    """Toute mise à jour partielle : seuls les champs effectivement envoyés sont modifiés
    (`exclude_unset=True` côté service) — un client peut donc corriger le seul état estimé sans
    reposer la langue, la variante ou le prix d'achat déjà enregistrés."""

    language: str | None = Field(default=None, min_length=2, max_length=8)
    variant: PriceVariant | None = None
    condition_grade: str | None = None
    counterfeit_suspected: bool | None = None
    purchase_price: Decimal | None = Field(default=None, ge=0)
    purchase_currency: str | None = Field(default=None, min_length=3, max_length=3)
    acquired_at: date | None = None
