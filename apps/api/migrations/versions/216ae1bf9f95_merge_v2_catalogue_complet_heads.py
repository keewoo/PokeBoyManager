"""merge v2-catalogue-complet heads

Revision ID: 216ae1bf9f95
Revises: 066f6a4397cb, 5310390bc9a5
Create Date: 2026-09-19 23:52:17.529064

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '216ae1bf9f95'
down_revision: Union[str, Sequence[str], None] = ('066f6a4397cb', '5310390bc9a5')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
