import uuid
from decimal import Decimal

from pydantic import BaseModel, Field


class CreateWishlistItemRequest(BaseModel):
    card_id: uuid.UUID
    target_price_eur: Decimal | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=280)


class UpdateWishlistItemRequest(BaseModel):
    """Mise à jour partielle (`exclude_unset=True` côté service), même convention que
    `pbm_api.collection.schemas.UpdateCollectionItemRequest` : envoyer seulement le champ à
    corriger, jamais reposer le reste."""

    target_price_eur: Decimal | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=280)


class WishlistItemResponse(BaseModel):
    id: uuid.UUID
    card_id: uuid.UUID
    set_id: uuid.UUID
    card_name: str
    card_number: str
    set_name: str
    set_code: str
    rarity: str | None
    target_price_eur: Decimal | None
    note: str | None
    # Tendance Cardmarket/TCGplayer du jour pour la variante normale (`pbm_api.pricing.valuation.
    # reference_price_eur`) — jamais lié à un exemplaire précis, un vœu n'en possède aucun.
    current_price_eur: Decimal | None
    # Vrai quand un prix courant est connu et ne dépasse pas le prix cible — jamais calculé sans
    # prix cible (`None` dans ce cas, pas `False` : la question n'a pas de réponse tant qu'aucun
    # seuil n'a été fixé).
    target_reached: bool | None


class WishlistListResponse(BaseModel):
    items: list[WishlistItemResponse]
