"""card insight reports

Revision ID: 7fc6cd5efc72
Revises: 3221843f145c
Create Date: 2026-09-19 22:16:17.248686

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7fc6cd5efc72'
down_revision: str | Sequence[str] | None = '11f10f8c0f40'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('card_insight_reports',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('card_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['card_id'], ['cards.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('card_id', 'user_id', name='uq_card_insight_reports_card_user')
    )
    op.create_index(op.f('ix_card_insight_reports_card_id'), 'card_insight_reports', ['card_id'], unique=False)
    op.create_index(op.f('ix_card_insight_reports_user_id'), 'card_insight_reports', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_card_insight_reports_user_id'), table_name='card_insight_reports')
    op.drop_index(op.f('ix_card_insight_reports_card_id'), table_name='card_insight_reports')
    op.drop_table('card_insight_reports')
