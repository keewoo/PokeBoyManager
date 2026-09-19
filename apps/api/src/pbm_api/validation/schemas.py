"""Schémas de l'écran de validation (lot `v3-validation`) : confirmer/rejeter une détection,
tout ajouter d'un coup. `Detection.status` (`pbm_api.models.collection.DetectionStatus`) porte
l'état ; ces requêtes/réponses ne font que l'exposer côté HTTP.
"""

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from pbm_api.models.catalog import PriceVariant
from pbm_api.models.collection import DetectionStatus


class ConfirmDetectionRequest(BaseModel):
    card_id: uuid.UUID
    language: str = Field("fr", min_length=2, max_length=8)
    variant: PriceVariant = PriceVariant.normal
    # Nombre d'exemplaires identiques ajoutés d'un coup (ex: plusieurs exemplaires de la même
    # carte sur une même photo) — `CollectionItem` n'a pas de colonne quantité, une ligne par
    # exemplaire : `confirm` en crée `quantity`.
    quantity: int = Field(1, ge=1, le=20)
    condition_grade: str | None = Field(None, max_length=32)
    purchase_price: Decimal | None = Field(None, ge=0)
    purchase_currency: str | None = Field(None, min_length=3, max_length=3)
    acquired_at: date | None = None


class ConfirmDetectionResponse(BaseModel):
    detection_id: uuid.UUID
    status: DetectionStatus
    collection_item_ids: list[uuid.UUID]


class RejectDetectionResponse(BaseModel):
    detection_id: uuid.UUID
    status: DetectionStatus


class ConfirmAllResponse(BaseModel):
    upload_id: uuid.UUID
    # Détections confirmées avec leur candidat présélectionné (score > `PRESELECTION_THRESHOLD`),
    # langue "fr", variante normale, un exemplaire, aucun prix — corrigeables ensuite depuis la
    # collection. Le reste (aucun candidat présélectionné, déjà traitée) reste `pending` et va
    # dans `skipped` : jamais ajouté à la collection sans un choix, même implicite.
    confirmed: list[uuid.UUID]
    skipped: list[uuid.UUID]
