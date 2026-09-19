"""data exports

Revision ID: 2e56ba32d5ed
Revises: 11f10f8c0f40
Create Date: 2026-09-19 22:30:06.421059

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '2e56ba32d5ed'
down_revision: str | Sequence[str] | None = '7fc6cd5efc72'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('data_exports',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('status', sa.Enum('queued', 'running', 'succeeded', 'failed', name='export_status'), nullable=False),
    sa.Column('storage_key', sa.String(length=512), nullable=True),
    sa.Column('token_hash', sa.String(length=128), nullable=True),
    sa.Column('expires_at', sa.DateTime(), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    op.create_index(op.f('ix_data_exports_user_id'), 'data_exports', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_data_exports_user_id'), table_name='data_exports')
    op.drop_table('data_exports')
    # `export_status` est un type distinct de `job_status` (v. `pbm_api.models.jobs.DataExport`,
    # même énumération Python, deux types Postgres) : le supprimer ici ne touche pas `job_status`.
    sa.Enum(name='export_status').drop(op.get_bind(), checkfirst=True)
