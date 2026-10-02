"""Horloges d'une partie : colonne games.horloges

Lot `j-timer` — les trois horloges (par tour, par joueur, par décision) d'une partie vivent dans
une colonne JSONB `games.horloges`, calculée depuis des horodatages par le moteur pur
`pbm_game.horloges`. C'est une **donnée de la partie**, pas un minuteur en mémoire : elle survit
ainsi à un redémarrage de l'API et à un F5 du client. Nullable : les parties créées avant ce lot
n'en ont pas (le service traite `NULL` comme « pas d'horloges », sans repli silencieux côté calcul).

Revision ID: d4e1f2a3b5c6
Revises: c7e2b1a9f4d3
Create Date: 2026-10-02

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d4e1f2a3b5c6"
down_revision = "c7e2b1a9f4d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "games",
        sa.Column("horloges", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("games", "horloges")
