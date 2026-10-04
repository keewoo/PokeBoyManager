"""File de demandes « je voudrais jouer cette carte » : table card_play_requests

Lot `j-effets-couverture-outil` — un joueur signale une carte qu'il veut jouer ; chaque demande
nourrit la priorisation du chantier de scriptage (scripter d'abord ce que les joueurs possèdent,
pas ce que personne ne joue). Une ligne par (joueur, carte), unique : une seconde demande met à
jour celle qui existe. Le statut suit le cycle de vie (en_attente / scriptee / refusee).

Additive et isolée : une seule table neuve, deux clés étrangères (`users`, `cards`), aucun impact
sur l'existant. La descente la supprime.

Revision ID: b7d3f1a2c9e4
Revises: c3a7f1e9d2b4
Create Date: 2026-10-04

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b7d3f1a2c9e4"
down_revision = "c3a7f1e9d2b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "card_play_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # Le joueur qui demande la carte (supprimé avec lui — une demande orpheline n'a pas de sens).
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        # La carte demandée (supprimée avec elle du catalogue, cas théorique).
        sa.Column("card_id", postgresql.UUID(as_uuid=True), nullable=False),
        # en_attente / scriptee / refusee.
        sa.Column(
            "statut", sa.String(length=16), nullable=False, server_default="en_attente"
        ),
        # Mot libre du joueur, ou raison d'un refus posée par l'exploitation.
        sa.Column("note", sa.Text(), nullable=True),
        # Date de résolution (passage à scriptee/refusee), NULL tant qu'« en attente ».
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["card_id"], ["cards.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "card_id", name="uq_card_play_requests_user_card"),
    )
    op.create_index("ix_card_play_requests_user_id", "card_play_requests", ["user_id"])
    op.create_index("ix_card_play_requests_card", "card_play_requests", ["card_id"])
    op.create_index("ix_card_play_requests_statut", "card_play_requests", ["statut"])


def downgrade() -> None:
    op.drop_index("ix_card_play_requests_statut", table_name="card_play_requests")
    op.drop_index("ix_card_play_requests_card", table_name="card_play_requests")
    op.drop_index("ix_card_play_requests_user_id", table_name="card_play_requests")
    op.drop_table("card_play_requests")
