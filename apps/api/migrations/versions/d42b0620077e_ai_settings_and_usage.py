"""ai settings and usage

Revision ID: d42b0620077e
Revises: 5e0d551b788e
Create Date: 2026-09-19 21:03:27.298807

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd42b0620077e'
down_revision: str | Sequence[str] | None = '8565c4640de8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Le type `ai_provider` existe déjà (migration 5e0d551b788e, colonne `ai_credentials.provider`) :
# `create_type=False` évite un second `CREATE TYPE ai_provider` qui échouerait avec
# `DuplicateObjectError`, ici comme dans `downgrade()` où `drop_type=False` laisse le type en
# place tant que `ai_credentials` l'utilise encore.
AI_PROVIDER_ENUM = postgresql.ENUM(
    'anthropic', 'gemini', 'openai', name='ai_provider', create_type=False
)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('ai_usage_monthly',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('provider', AI_PROVIDER_ENUM, nullable=False),
    sa.Column('period', sa.Date(), nullable=False),
    sa.Column('calls_count', sa.Integer(), nullable=False),
    sa.Column('tokens_count', sa.Integer(), nullable=False),
    sa.Column('estimated_cost_eur', sa.Numeric(precision=10, scale=4), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'provider', 'period', name='uq_ai_usage_monthly_user_provider_period')
    )
    op.create_index(op.f('ix_ai_usage_monthly_user_id'), 'ai_usage_monthly', ['user_id'], unique=False)
    op.add_column('users', sa.Column('ai_default_provider', AI_PROVIDER_ENUM, nullable=True))
    op.add_column('users', sa.Column('ai_default_model', sa.String(length=128), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'ai_default_model')
    op.drop_column('users', 'ai_default_provider')
    op.drop_index(op.f('ix_ai_usage_monthly_user_id'), table_name='ai_usage_monthly')
    op.drop_table('ai_usage_monthly')
