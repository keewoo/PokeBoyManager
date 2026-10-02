"""Schémas Pydantic des réponses de la fiche carte (`pbm_api.cards.service`) : détail,
historique de prix, exemplaires possédés, et carte vedette de l'accueil visiteur."""

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from pbm_api.models.catalog import PriceVariant


class CardSetOut(BaseModel):
    """Extension à laquelle appartient la carte, telle qu'affichée dans l'en-tête de fiche."""

    id: uuid.UUID
    name: str
    code: str
    series: str | None
    release_date: date | None
    total_cards: int | None
    logo_url: str | None


class CardRankingOut(BaseModel):
    """Position de la carte dans le classement par rareté et son centile de valeur
    (`pbm_api.ranking.service.card_value_rank`)."""

    rarity_rank: int | None
    rarity_group_size: int | None
    value_percentile: float | None


class OwnedCollectionRankOut(BaseModel):
    """Rang de l'exemplaire le plus valorisé de l'utilisateur parmi les cartes de sa collection
    dont le prix est connu."""

    position: int | None
    total_priced: int


class CardDetailResponse(BaseModel):
    """Fiche complète d'une carte : catalogue, prix par variante, classement et, si
    l'utilisateur en possède un exemplaire, son rang dans sa collection."""

    id: uuid.UUID
    name: str
    number: str
    rarity: str | None
    supertype: str | None
    # Type élémentaire normalisé (code du jeu : "grass", "fire"...) ou `None` — sert au visuel
    # de remplacement quand `has_image` est faux (lot `pbm-carte-remplacement`).
    element_type: str | None
    hp: int | None
    has_image: bool
    illustrator: str | None
    set: CardSetOut
    prices_eur: dict[PriceVariant, Decimal | None]
    ranking: CardRankingOut
    owned_count: int
    collection_rank: OwnedCollectionRankOut | None


class PriceHistoryPoint(BaseModel):
    """Un point de l'historique de prix : le prix de référence en EUR pour un jour donné."""

    day: date
    price_eur: Decimal


class PriceHistoryResponse(BaseModel):
    """Historique de prix d'une carte pour une variante et une période donnée, servi à
    l'onglet Valeur de la fiche."""

    card_id: uuid.UUID
    variant: PriceVariant
    points: list[PriceHistoryPoint]


class MyCardItemOut(BaseModel):
    """Un exemplaire possédé de la carte, pour l'onglet « Mes exemplaires » de la fiche."""

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


class FeaturedCardOut(BaseModel):
    """Neuf du tableau de démonstration de l'accueil visiteur (mission `pbm-front-accueil`,
    point 1) — jamais de prix ni de rareté ici : de vraies données, mais pas une fiche
    complète, la route est publique (pas de session)."""

    id: uuid.UUID
    name: str
    number: str
    set_name: str
