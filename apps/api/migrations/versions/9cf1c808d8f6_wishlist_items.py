"""wishlist items

Revision ID: 9cf1c808d8f6
Revises: d1c7a3f0b2e4
Create Date: 2026-09-21 14:34:44.433813

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '9cf1c808d8f6'
down_revision: str | Sequence[str] | None = 'd1c7a3f0b2e4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'wishlist_items',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('card_id', sa.UUID(), nullable=False),
        sa.Column('target_price_eur', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('note', sa.String(length=280), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['card_id'], ['cards.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'card_id', name='uq_wishlist_items_user_card'),
    )
    op.create_index('ix_wishlist_items_card_id', 'wishlist_items', ['card_id'], unique=False)
    op.create_index('ix_wishlist_items_user_id', 'wishlist_items', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_wishlist_items_user_id', table_name='wishlist_items')
    op.drop_index('ix_wishlist_items_card_id', table_name='wishlist_items')
    op.drop_table('wishlist_items')
