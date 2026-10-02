"""Table de la machine de lancement d'une partie : game_launches

Lot `j-lancement-partie` — entre le salon d'attente (`j-invitations`) et la partie en cours
(`j-partie-service`), l'étape « qui commence » : choix du deck, prêt des deux camps, et la
graine, pile ou face R-4.7, choix du gagnant (ou défaut), bascule en partie. Un lancement
par invitation (``invitation_id`` unique) ; la graine est le secret commit-reveal (révélée en fin de
partie seulement) ; ``game_id`` pointe la partie créée. Decks et partie en ``SET NULL`` (les
supprimer n'efface pas la trace du lancement) ; invitation en ``CASCADE`` (le lancement n'a aucun
sens sans elle).

Revision ID: c7e2b1a9f4d3
Revises: b9d4e2a7c1f0
Create Date: 2026-10-02

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c7e2b1a9f4d3"
down_revision = "b9d4e2a7c1f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "game_launches",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invitation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("statut", sa.String(length=16), nullable=False),
        sa.Column("inviter_deck_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("invitee_deck_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("inviter_pret", sa.Boolean(), nullable=False),
        sa.Column("invitee_pret", sa.Boolean(), nullable=False),
        sa.Column("graine", sa.String(length=128), nullable=True),
        sa.Column("engagement", sa.String(length=64), nullable=True),
        sa.Column("tirage", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("tirage_gagnant_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("choix_commencer", sa.Boolean(), nullable=True),
        sa.Column("premier_joueur_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("choix_expire_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["invitation_id"], ["game_invitations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["inviter_deck_id"], ["decks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["invitee_deck_id"], ["decks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tirage_gagnant_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["premier_joueur_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invitation_id", name="uq_game_launches_invitation"),
        sa.UniqueConstraint("game_id", name="uq_game_launches_game"),
    )
    op.create_index("ix_game_launches_invitation_id", "game_launches", ["invitation_id"])
    op.create_index("ix_game_launches_statut", "game_launches", ["statut"])


def downgrade() -> None:
    op.drop_index("ix_game_launches_statut", table_name="game_launches")
    op.drop_index("ix_game_launches_invitation_id", table_name="game_launches")
    op.drop_table("game_launches")
