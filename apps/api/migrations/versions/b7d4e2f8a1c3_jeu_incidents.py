"""jeu_incidents : les incidents du jeu, pour qu'une règle qui casse se VOIE (`j-observabilite-jeu`).

Un coup refusé, une erreur de moteur et une partie refusée faute de carte scriptée (D9) n'existaient
que dans la sortie du serveur : perdus au redémarrage, invisibles sans SSH, incomptables. Cette
table les garde, horodatés et bornés, pour que la sonde et la route ``GET /jeu/metriques`` en
tirent des compteurs — et une alerte.

``game_id`` et ``user_id`` sont en **SET NULL** (et non CASCADE) : la purge des parties mortes ne
doit pas effacer la trace qui sert à expliquer un incident. On perd le lien, jamais le fait.

Revision ID: b7d4e2f8a1c3
Revises: a1f6c2d9e4b7
Create Date: 2026-10-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision = "b7d4e2f8a1c3"
down_revision = "a1f6c2d9e4b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jeu_incidents",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("genre", sa.String(32), nullable=False),
        sa.Column("motif", sa.String(64), nullable=False),
        sa.Column(
            "game_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("games.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("type_action", sa.String(48), nullable=True),
        sa.Column("detail", sa.String(512), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    # Les trois lectures de la supervision : « quoi » (genre), « quelle règle » (motif), et
    # toujours bornées à une fenêtre de temps (created_at). D'où ces trois index, et pas d'autre.
    op.create_index("ix_jeu_incidents_genre", "jeu_incidents", ["genre"])
    op.create_index("ix_jeu_incidents_motif", "jeu_incidents", ["motif"])
    op.create_index("ix_jeu_incidents_created_at", "jeu_incidents", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_jeu_incidents_created_at", table_name="jeu_incidents")
    op.drop_index("ix_jeu_incidents_motif", table_name="jeu_incidents")
    op.drop_index("ix_jeu_incidents_genre", table_name="jeu_incidents")
    op.drop_table("jeu_incidents")
