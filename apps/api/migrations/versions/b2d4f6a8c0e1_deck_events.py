"""deck events (collection sync alerts + history)

Revision ID: b2d4f6a8c0e1
Revises: f4a1c8d0b7e2
Create Date: 2026-09-22 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b2d4f6a8c0e1"
down_revision: str | Sequence[str] | None = "f4a1c8d0b7e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "deck_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("deck_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=16), nullable=False),
        # SET NULL : l'historique survit si la carte disparaissait du catalogue.
        sa.Column("card_id", sa.UUID(), nullable=True),
        sa.Column("card_name", sa.String(length=255), nullable=False),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["card_id"], ["cards.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["deck_id"], ["decks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_deck_events_card_id", "deck_events", ["card_id"], unique=False)
    op.create_index("ix_deck_events_deck_id", "deck_events", ["deck_id"], unique=False)
    op.create_index("ix_deck_events_user_id", "deck_events", ["user_id"], unique=False)
    # Requête de l'en-tête : « mes alertes non lues » du plus récent au plus ancien.
    op.create_index(
        "ix_deck_events_user_unread", "deck_events", ["user_id", "read_at"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_deck_events_user_unread", table_name="deck_events")
    op.drop_index("ix_deck_events_user_id", table_name="deck_events")
    op.drop_index("ix_deck_events_deck_id", table_name="deck_events")
    op.drop_index("ix_deck_events_card_id", table_name="deck_events")
    op.drop_table("deck_events")
