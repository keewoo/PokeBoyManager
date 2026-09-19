"""merge heads before v3-identification-visuelle

Revision ID: 5cd5353f33b8
Revises: 99492e449606, f950b86db322
Create Date: 2026-09-20 00:42:58.864854

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5cd5353f33b8'
down_revision: Union[str, Sequence[str], None] = ('99492e449606', 'f950b86db322')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
