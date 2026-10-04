"""Schémas Pydantic de la **file de demandes** « je voudrais jouer cette carte » (lot
`j-effets-couverture-outil`). Côté joueur uniquement : signaler une carte, suivre sa progression.
L'agrégation pour la priorisation du chantier reste une donnée d'exploitation, jamais exposée en
HTTP (un joueur ne voit pas ce que les autres demandent)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CardPlayRequestCreate(BaseModel):
    """Le joueur signale une carte qu'il veut jouer, avec un mot libre facultatif."""

    card_id: uuid.UUID
    note: str | None = Field(default=None, max_length=500)


class CardPlayRequestOut(BaseModel):
    """Une demande du joueur, avec sa progression : le statut posé ET la jouabilité courante.

    `jouable_maintenant` est recalculé à la lecture contre le registre `card_scripts` : une carte
    peut être devenue jouable sans qu'on ait repassé son statut à la main — le joueur voit alors
    que sa demande est satisfaite même si le statut n'a pas encore été mis à jour."""

    id: uuid.UUID
    card_id: uuid.UUID
    card_name: str
    statut: str  # "en_attente" | "scriptee" | "refusee"
    note: str | None
    jouable_maintenant: bool
    created_at: datetime
    updated_at: datetime


class CardPlayRequestsResponse(BaseModel):
    """Les demandes du joueur courant (jamais celles d'un autre)."""

    requests: list[CardPlayRequestOut]
