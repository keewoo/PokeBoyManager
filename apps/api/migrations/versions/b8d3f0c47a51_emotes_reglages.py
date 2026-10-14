"""Réglage d'emotes en jeu (lot `j-echanges-emotes`, jalon J4, décision DJ10).

Une table, une colonne utile : ``jeu_emote_reglages.recevoir_emotes``. C'est **tout** ce que les
emotes écrivent en base — les emotes elles-mêmes ne sont jamais persistées (critère du lot : « ne
rien conserver au-delà de la partie »), elles ne traversent que le canal temps réel en mémoire.

Ligne créée à la première modification seulement (même convention que ``jeu_rendu_reglages``) :
son absence vaut le défaut DJ10, « j'échange des emotes ».

Revision ID: b8d3f0c47a51
Revises: e2a7b4c1d6f9
Create Date: 2026-10-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision = "b8d3f0c47a51"
down_revision = "e2a7b4c1d6f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jeu_emote_reglages",
        sa.Column(
            "user_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "recevoir_emotes", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("jeu_emote_reglages")
