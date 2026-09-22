"""card element_type (visuel de remplacement)

Ajoute `cards.element_type` : le type élémentaire du Pokémon, normalisé au code du jeu
("grass", "fire"...), utilisé par le visuel de remplacement des cartes sans image officielle
(lot `pbm-carte-remplacement`). Distinct de `energy_type` ("Normal"/"Special" des Énergies).

Revision ID: c3a7e1f4d820
Revises: 23a3f88da88d
Create Date: 2026-09-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3a7e1f4d820"
down_revision: str | Sequence[str] | None = "23a3f88da88d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("cards", sa.Column("element_type", sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column("cards", "element_type")
