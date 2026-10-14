"""jeu_notifications : le canal de notification du jeu et ses réglages (`j-notifications-jeu`).

Un jeu à deux où personne ne sait que l'autre attend ne se joue pas. Deux tables :

* ``game_notifications`` — une notification destinée à un compte. ``game_id`` est **nullable** (une
  invitation reçue n'a pas encore de partie) et en **CASCADE** : une notification sans sa partie n'a
  plus rien à dire, « c'est ton tour » sur une partie purgée serait un mensonge ;
* ``notification_reglages`` — une ligne par compte, **créée à la première modification**. Son
  absence vaut les défauts du code (``pbm_api.notifications.regles``), donc aucun compte n'a besoin
  d'une ligne pour être correctement notifié. Les ``server_default`` posés ici ne sont là que pour
  qu'une ligne insérée sans tous ses champs reste cohérente avec ces défauts.

Les deux index de ``game_notifications`` ne sont pas décoratifs : ``(user_id, lue_at)`` sert la
lecture de tous les écrans (« mes non lues »), et ``(user_id, game_id, genre)`` sert le **plafond
par partie**, compté à chaque émission — sans lui, chaque notification coûterait un balayage.

Revision ID: d8e5a3c6b2f1
Revises: b7d4e2f8a1c3
Create Date: 2026-10-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision = "d8e5a3c6b2f1"
down_revision = "b7d4e2f8a1c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "game_notifications",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("genre", sa.String(32), nullable=False),
        sa.Column(
            "game_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("games.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("donnees", JSONB, nullable=False, server_default="{}"),
        sa.Column("silencieuse", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lue_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_game_notifications_user_id", "game_notifications", ["user_id"])
    op.create_index("ix_game_notifications_game_id", "game_notifications", ["game_id"])
    op.create_index("ix_game_notifications_created_at", "game_notifications", ["created_at"])
    op.create_index("ix_game_notifications_user_lue", "game_notifications", ["user_id", "lue_at"])
    op.create_index(
        "ix_game_notifications_user_game_genre",
        "game_notifications",
        ["user_id", "game_id", "genre"],
    )

    op.create_table(
        "notification_reglages",
        sa.Column(
            "user_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("genres_desactives", JSONB, nullable=False, server_default="[]"),
        sa.Column("silence_actif", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("silence_debut", sa.Time(), nullable=False, server_default="21:00:00"),
        sa.Column("silence_fin", sa.Time(), nullable=False, server_default="07:00:00"),
        sa.Column("fuseau", sa.String(64), nullable=False, server_default="Europe/Paris"),
        sa.Column(
            "relais_email_invitation", sa.Boolean(), nullable=False, server_default="true"
        ),
        sa.Column("relais_push", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("notification_reglages")
    op.drop_index("ix_game_notifications_user_game_genre", table_name="game_notifications")
    op.drop_index("ix_game_notifications_user_lue", table_name="game_notifications")
    op.drop_index("ix_game_notifications_created_at", table_name="game_notifications")
    op.drop_index("ix_game_notifications_game_id", table_name="game_notifications")
    op.drop_index("ix_game_notifications_user_id", table_name="game_notifications")
    op.drop_table("game_notifications")
