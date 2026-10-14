"""jeu_rendu_carte : ma photo ou l'image officielle sur le plateau (`j-rendu-carte`).

Trois écritures, un par niveau de la décision DJ5 :

* ``jeu_rendu_reglages`` — une ligne par compte, **créée à la première modification**. Son absence
  vaut les défauts du code (``pbm_api.jeu.rendu.ReglagesRendu``) : aucun compte n'a besoin d'une
  ligne pour jouer avec ses photos, qui est le défaut. Les ``server_default`` posés ici ne sont là
  que pour qu'une ligne insérée sans tous ses champs reste cohérente avec ces défauts ;
* ``decks.rendu_cartes`` — la préférence **du deck**, volontairement **nullable sans
  ``server_default``** : nul signifie « suit le réglage global du compte », pas « photo ». Poser un
  défaut ici figerait les decks existants et rendrait le réglage global sans effet sur eux ;
* ``collection_items.jeu_image_key`` / ``jeu_qualite`` — la **variante de jeu** d'une photo (celle
  qu'on sert vraiment : 44 Ko contre 178 Ko pour l'originale 630×880, soit 0,86 Mo au lieu de
  3,5 Mo pour un plateau de vingt cartes) et sa note de qualité. Les deux sont nulles pour tout le
  corpus existant : la variante est produite à l'ouverture du deck ou à la première demande de la
  photo, jamais par cette migration (une migration ne décode pas vingt mille images).

Aucune donnée n'est réécrite, aucune valeur par défaut n'est appliquée aux lignes existantes : le
retour arrière rend donc exactement l'état d'avant.

Revision ID: a1f7c3d9e5b2
Revises: d8e5a3c6b2f1
Create Date: 2026-10-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision = "a1f7c3d9e5b2"
down_revision = "d8e5a3c6b2f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jeu_rendu_reglages",
        sa.Column(
            "user_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("rendu_defaut", sa.String(16), nullable=False, server_default="photo"),
        sa.Column(
            "jamais_montrer_mes_photos",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.add_column("decks", sa.Column("rendu_cartes", sa.String(16), nullable=True))
    op.add_column("collection_items", sa.Column("jeu_image_key", sa.String(512), nullable=True))
    op.add_column("collection_items", sa.Column("jeu_qualite", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("collection_items", "jeu_qualite")
    op.drop_column("collection_items", "jeu_image_key")
    op.drop_column("decks", "rendu_cartes")
    op.drop_table("jeu_rendu_reglages")
