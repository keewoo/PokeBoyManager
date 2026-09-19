"""identity: first/last name, birth date, terms acceptance, forced password change

Revision ID: 328aef94ea58
Revises: 054d503ae627
Create Date: 2026-09-19 22:43:10.164796

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '328aef94ea58'
down_revision: str | Sequence[str] | None = '054d503ae627'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('first_name', sa.String(length=100), nullable=True))
    op.add_column('users', sa.Column('last_name', sa.String(length=100), nullable=False))
    op.add_column('users', sa.Column('birth_date', sa.Date(), nullable=False))
    op.add_column('users', sa.Column('terms_version', sa.String(length=32), nullable=False))
    op.add_column('users', sa.Column('terms_accepted_at', sa.DateTime(), nullable=False))
    op.add_column(
        'users',
        sa.Column('must_change_password', sa.Boolean(), server_default='false', nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'must_change_password')
    op.drop_column('users', 'terms_accepted_at')
    op.drop_column('users', 'terms_version')
    op.drop_column('users', 'birth_date')
    op.drop_column('users', 'last_name')
    op.drop_column('users', 'first_name')
