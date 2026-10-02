"""Tables de parties de jeu : games, game_players, game_events, game_snapshots

Lot `j-partie-service` — l'enveloppe qui persiste une partie du moteur `pbm_game` : son état
initial, sa graine et son journal d'actions numéroté (append-only). Le journal (`game_events`) et
les instantanés (`game_snapshots`) ne sont **jamais** mis à jour en place : une entrée écrite ne
bouge plus (rejouabilité, anti-triche). La contrainte d'unicité `(game_id, numero)` sur le journal
est le socle de l'idempotence par numéro d'action.

Revision ID: c5f1a9e3b7d0
Revises: a3f9c2e5b1d4
Create Date: 2026-10-02

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c5f1a9e3b7d0"
down_revision = "a3f9c2e5b1d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "games",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("etat_initial", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("graine", sa.String(length=128), nullable=False),
        sa.Column("engagement", sa.String(length=64), nullable=False),
        sa.Column("journal_version", sa.Integer(), nullable=False),
        sa.Column("current_numero", sa.Integer(), nullable=False),
        sa.Column("current_empreinte", sa.String(length=64), nullable=False),
        sa.Column("vainqueur_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("raison_fin", sa.String(length=32), nullable=True),
        sa.Column("last_action_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["vainqueur_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_games_status", "games", ["status"])
    op.create_index("ix_games_expires_at", "games", ["expires_at"])

    op.create_table(
        "game_players",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deck_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("seat", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["deck_id"], ["decks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id", "seat", name="uq_game_players_game_seat"),
        sa.UniqueConstraint("game_id", "user_id", name="uq_game_players_game_user"),
    )
    op.create_index("ix_game_players_game_id", "game_players", ["game_id"])
    op.create_index("ix_game_players_user_id", "game_players", ["user_id"])

    op.create_table(
        "game_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("auteur", sa.String(length=64), nullable=False),
        sa.Column("action", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evenements", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("horodatage", sa.String(length=64), nullable=False),
        sa.Column("empreinte", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id", "numero", name="uq_game_events_game_numero"),
    )
    op.create_index("ix_game_events_game_id", "game_events", ["game_id"])

    op.create_table(
        "game_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("numero_entrees", sa.Integer(), nullable=False),
        sa.Column("etat", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("rng_etat", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("empreinte", sa.String(length=64), nullable=False),
        sa.Column("journal_version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "game_id", "numero_entrees", name="uq_game_snapshots_game_numero_entrees"
        ),
    )
    op.create_index("ix_game_snapshots_game_id", "game_snapshots", ["game_id"])


def downgrade() -> None:
    op.drop_index("ix_game_snapshots_game_id", table_name="game_snapshots")
    op.drop_table("game_snapshots")
    op.drop_index("ix_game_events_game_id", table_name="game_events")
    op.drop_table("game_events")
    op.drop_index("ix_game_players_user_id", table_name="game_players")
    op.drop_index("ix_game_players_game_id", table_name="game_players")
    op.drop_table("game_players")
    op.drop_index("ix_games_expires_at", table_name="games")
    op.drop_index("ix_games_status", table_name="games")
    op.drop_table("games")
