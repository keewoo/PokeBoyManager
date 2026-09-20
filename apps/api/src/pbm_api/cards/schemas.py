import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from pbm_api.models.catalog import PriceVariant


class CardSetOut(BaseModel):
    id: uuid.UUID
    name: str
    code: str
    series: str | None
    release_date: date | None
    total_cards: int | None
    logo_url: str | None


class CardRankingOut(BaseModel):
    rarity_rank: int | None
    rarity_group_size: int | None
    value_percentile: float | None


class OwnedCollectionRankOut(BaseModel):
    position: int | None
    total_priced: int


class CardDetailResponse(BaseModel):
    id: uuid.UUID
    name: str
    number: str
    rarity: str | None
    supertype: str | None
    hp: int | None
    has_image: bool
    illustrator: str | None
    set: CardSetOut
    prices_eur: dict[PriceVariant, Decimal | None]
    ranking: CardRankingOut
    owned_count: int
    collection_rank: OwnedCollectionRankOut | None


class PriceHistoryPoint(BaseModel):
    day: date
    price_eur: Decimal


class PriceHistoryResponse(BaseModel):
    card_id: uuid.UUID
    variant: PriceVariant
    points: list[PriceHistoryPoint]


class MyCardItemOut(BaseModel):
    id: uuid.UUID
    language: str
    variant: PriceVariant
    condition_grade: str | None
    counterfeit_suspected: bool
    purchase_price: Decimal | None
    purchase_currency: str | None
    # Converti au taux du jour d'acquisition (jamais celui du jour de lecture : ce qui a été
    # payé ne change pas avec le temps) — `None` si aucun prix d'achat, ou si le taux de ce
    # jour-là n'a jamais été relevé (jamais un taux inventé). Permet la plus-value de l'en-tête
    # de fiche (`value_eur - purchase_price_eur`) sans dépendre d'un second aller-retour serveur.
    purchase_price_eur: Decimal | None
    acquired_at: date | None
    value_eur: Decimal | None
    has_photo: bool
    # Détail brut de `Detection.condition_assessment` (mission `v3-etat`) : centrage/coins/
    # bords/surface — `None` pour un exemplaire ajouté manuellement (aucune détection liée),
    # même choix de forme que `DetectionResponse.condition` (`pbm_api.uploads.schemas`).
    condition_detail: dict | None
