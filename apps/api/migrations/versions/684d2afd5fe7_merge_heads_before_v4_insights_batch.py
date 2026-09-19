"""merge heads before v4-insights-batch

Revision ID: 684d2afd5fe7
Revises: 216ae1bf9f95, d27e4efd0255
Create Date: 2026-09-20 00:08:21.016316

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '684d2afd5fe7'
down_revision: Union[str, Sequence[str], None] = ('216ae1bf9f95', 'd27e4efd0255')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
