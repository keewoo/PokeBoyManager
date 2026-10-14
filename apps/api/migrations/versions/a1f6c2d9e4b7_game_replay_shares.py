"""game_replay_shares : à qui le replay d'une partie est ouvert (lot `j-replay`).

Le replay d'une partie finie est visible de ses deux joueurs de droit (leurs sièges le disent
déjà, dans ``game_players``). Cette table porte le cas **au-delà** : un joueur ouvre le replay à
un compte invité nommément, et c'est cette ligne — pas un jeton dans une URL — qui fait le droit.
Un compte absent de cette table et des sièges reçoit 404 sur le replay.

L'unicité ``(game_id, user_id)`` rend l'ouverture **idempotente** : deux clics sur « partager »
ne fabriquent pas deux droits dont on ne retirerait qu'un.

Revision ID: a1f6c2d9e4b7
Revises: c9d4e7a1b3f8
Create Date: 2026-10-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision = "a1f6c2d9e4b7"
down_revision = "c9d4e7a1b3f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "game_replay_shares",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "game_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("games.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_by_user_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("game_id", "user_id", name="uq_game_replay_shares_game_user"),
    )
    # Deux lectures : « ce replay est-il ouvert à ce compte ? » (le contrôle d'accès, à chaque
    # page de replay) et « que m'a-t-on partagé ? ». D'où un index par partie et un par compte.
    op.create_index(
        "ix_game_replay_shares_game_id", "game_replay_shares", ["game_id"]
    )
    op.create_index(
        "ix_game_replay_shares_user_id", "game_replay_shares", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_game_replay_shares_user_id", table_name="game_replay_shares")
    op.drop_index("ix_game_replay_shares_game_id", table_name="game_replay_shares")
    op.drop_table("game_replay_shares")
