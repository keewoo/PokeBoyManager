"""fusion wishlist_items et deck_format

Revision ID: 23a3f88da88d
Revises: 9cf1c808d8f6, a4e9c1d7b3f5
Create Date: 2026-09-22 09:44:23.239181

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '23a3f88da88d'
down_revision: Union[str, Sequence[str], None] = ('9cf1c808d8f6', 'a4e9c1d7b3f5')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
