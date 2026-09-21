"""decks, deck_cards and cards.energy_type

Revision ID: d1c7a3f0b2e4
Revises: 5cd5353f33b8
Create Date: 2026-09-21 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd1c7a3f0b2e4'
down_revision: str | Sequence[str] | None = '5cd5353f33b8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('cards', sa.Column('energy_type', sa.String(length=16), nullable=True))
    op.create_table(
        'decks',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_decks_user_id', 'decks', ['user_id'], unique=False)
    op.create_table(
        'deck_cards',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('deck_id', sa.UUID(), nullable=False),
        sa.Column('card_id', sa.UUID(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['deck_id'], ['decks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['card_id'], ['cards.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('deck_id', 'card_id', name='uq_deck_cards_deck_card'),
    )
    op.create_index('ix_deck_cards_deck_id', 'deck_cards', ['deck_id'], unique=False)
    op.create_index('ix_deck_cards_card_id', 'deck_cards', ['card_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_deck_cards_card_id', table_name='deck_cards')
    op.drop_index('ix_deck_cards_deck_id', table_name='deck_cards')
    op.drop_table('deck_cards')
    op.drop_index('ix_decks_user_id', table_name='decks')
    op.drop_table('decks')
    op.drop_column('cards', 'energy_type')
