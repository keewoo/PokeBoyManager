"""Table des invitations à jouer : game_invitations

Lot `j-invitations` — inviter quelqu'un de précis (par pseudo) ou fabriquer un lien à usage unique,
plutôt que de chercher un inconnu dans la file. Le jeton d'un lien n'est stocké que haché
(``token_hash``, unique) ; les decks annoncés sont en ``SET NULL`` (supprimer un deck n'efface pas
l'invitation) ; ``statut`` porte le cycle de vie (envoyee → acceptee / refusee / annulee / expiree),
dont le caractère à usage unique du lien découle (un lien accepté n'est plus « envoyee »).

Revision ID: b9d4e2a7c1f0
Revises: e4c9a1f20d83
Create Date: 2026-10-02

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b9d4e2a7c1f0"
down_revision = "e4c9a1f20d83"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "game_invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mode", sa.String(length=8), nullable=False),
        sa.Column("statut", sa.String(length=16), nullable=False),
        sa.Column("inviter_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invitee_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("inviter_deck_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("invitee_deck_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["inviter_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invitee_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["inviter_deck_id"], ["decks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["invitee_deck_id"], ["decks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_game_invitations_token_hash"),
    )
    op.create_index("ix_game_invitations_statut", "game_invitations", ["statut"])
    op.create_index("ix_game_invitations_inviter_user_id", "game_invitations", ["inviter_user_id"])
    op.create_index("ix_game_invitations_invitee_user_id", "game_invitations", ["invitee_user_id"])
    op.create_index("ix_game_invitations_expires_at", "game_invitations", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_game_invitations_expires_at", table_name="game_invitations")
    op.drop_index("ix_game_invitations_invitee_user_id", table_name="game_invitations")
    op.drop_index("ix_game_invitations_inviter_user_id", table_name="game_invitations")
    op.drop_index("ix_game_invitations_statut", table_name="game_invitations")
    op.drop_table("game_invitations")
