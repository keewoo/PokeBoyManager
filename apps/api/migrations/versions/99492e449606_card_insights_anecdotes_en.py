"""card insights anecdotes en

Revision ID: 99492e449606
Revises: 684d2afd5fe7
Create Date: 2026-09-20 00:08:36.145153

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '99492e449606'
down_revision: Union[str, Sequence[str], None] = '684d2afd5fe7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Note : l'autogénération détecte aussi une dérive préexistante et sans rapport sur
    # `card_insight_reports.created_at` (timezone) — laissée de côté, hors périmètre de ce lot.
    op.add_column('card_insights', sa.Column('anecdotes_en', postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('card_insights', 'anecdotes_en')
