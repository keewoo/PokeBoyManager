"""jeu_accessibilite : les réglages de confort d'un compte (`j-accessibilite-jeu`).

Une seule table, ``jeu_confort_reglages``, sur le modèle exact de ``jeu_rendu_reglages`` : une ligne
par compte, **créée à la première modification**. Son absence vaut les défauts du code
(``pbm_api.jeu.confort.ReglagesConfort``) — aucun compte n'a besoin d'une ligne pour jouer avec les
animations, un texte normal et les horloges DJ4, qui sont les défauts. Les ``server_default`` posés
ici ne sont là que pour qu'une ligne insérée sans tous ses champs reste cohérente avec ces défauts.

``temps_rallonge`` mérite un mot : il **double les horloges** d'une partie, mais il est lu **au
lancement** seulement (``pbm_api.games.service.creer_partie``), parce qu'une partie fige sa
configuration d'horloges à sa création. Aucune partie en cours n'est donc touchée par cette
migration, ni par un changement de réglage.

Aucune donnée n'est réécrite, aucune ligne n'est créée : le retour arrière rend exactement l'état
d'avant.

Revision ID: c4f1a8b7e2d3
Revises: a1f7c3d9e5b2
Create Date: 2026-10-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision = "c4f1a8b7e2d3"
down_revision = "a1f7c3d9e5b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jeu_confort_reglages",
        sa.Column(
            "user_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("animations", sa.String(16), nullable=False, server_default="completes"),
        sa.Column("taille_texte", sa.String(16), nullable=False, server_default="normale"),
        sa.Column(
            "temps_rallonge", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("jeu_confort_reglages")
