"""rename_cards_rule_suffix_to_rule_marker

Revision ID: 5310390bc9a5
Revises: b671eb503fa3
Create Date: 2026-09-19 21:44:54.464286

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5310390bc9a5'
down_revision: Union[str, Sequence[str], None] = 'b671eb503fa3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """`rule_suffix` ne couvrait que TCGdex `suffix` (ex, GX) — VMAX/VSTAR y sont portées par
    `stage`, pas `suffix` (constaté en direct le 2026-09-19, voir compte rendu). `rule_marker`
    reflète la valeur réellement calculée (`suffix` sinon `stage` s'il n'est pas une étape
    d'évolution ordinaire)."""
    op.alter_column("cards", "rule_suffix", new_column_name="rule_marker")


def downgrade() -> None:
    op.alter_column("cards", "rule_marker", new_column_name="rule_suffix")
