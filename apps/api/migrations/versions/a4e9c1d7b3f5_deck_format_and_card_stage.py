"""deck format and card stage (lot v7-decks-legalite)

Revision ID: a4e9c1d7b3f5
Revises: d1c7a3f0b2e4
Create Date: 2026-09-21 17:20:00.000000

`cards.stage` : stade d'évolution TCGdex (sert au « au moins un Pokémon de base » de la légalité
des decks). `decks.format` : format de jeu choisi par le joueur (Standard / Étendu / Illimité),
`server_default 'standard'` pour rétro-remplir les decks créés par `v7-decks-api`.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a4e9c1d7b3f5'
down_revision: str | Sequence[str] | None = 'd1c7a3f0b2e4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('cards', sa.Column('stage', sa.String(length=32), nullable=True))
    op.add_column(
        'decks',
        sa.Column('format', sa.String(length=16), nullable=False, server_default='standard'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('decks', 'format')
    op.drop_column('cards', 'stage')
