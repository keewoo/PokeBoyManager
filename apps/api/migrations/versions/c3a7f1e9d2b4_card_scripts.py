"""Registre des scripts d'effet : table card_scripts

Lot `j-effets-catalogue-compilation` — le pont entre le catalogue (des textes d'effet) et le moteur
(des scripts DSL). Un script n'est pas écrit par carte mais **par texte d'effet**, repéré par
l'empreinte SHA-256 de sa forme normalisée (`text_fingerprint`, unique) : des centaines de cartes
partageant le même effet sont couvertes par une seule ligne. Le statut (`scripte` / `non_supporte` /
`a_revoir`) décide si la carte qui porte ce texte est jouable (D9 : un texte sans script lisible
bloque la carte, jamais un effet neutre deviné).

Additive et isolée : une seule table neuve, aucun impact sur l'existant. La descente la supprime.

Revision ID: c3a7f1e9d2b4
Revises: b2c3d4e5f6a7
Create Date: 2026-10-04

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c3a7f1e9d2b4"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "card_scripts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # Empreinte SHA-256 (hex) du texte d'effet normalisé — la clé de regroupement, unique.
        sa.Column("text_fingerprint", sa.String(length=64), nullable=False),
        # Langue du texte source (métadonnée de traçabilité ; l'appariement passe par l'empreinte).
        sa.Column("lang", sa.String(length=8), nullable=True),
        # Le texte d'effet canonique couvert, gardé brut (relecture, détection d'errata).
        sa.Column("source_text", sa.Text(), nullable=False),
        # Version du langage d'effets dans laquelle le script est écrit.
        sa.Column("dsl_version", sa.Integer(), nullable=False),
        # Le programme DSL (dict JSON), NULL quand le statut est « non supporté ».
        sa.Column("script", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # scripte / non_supporte / a_revoir.
        sa.Column("statut", sa.String(length=16), nullable=False),
        sa.Column("author", sa.String(length=128), nullable=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        # Cas de test associés (liste d'identifiants).
        sa.Column("tests", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # Le « pourquoi » d'un non_supporte, ou une note de relecture / trace d'errata.
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("text_fingerprint", name="uq_card_scripts_fingerprint"),
    )
    op.create_index("ix_card_scripts_statut", "card_scripts", ["statut"])


def downgrade() -> None:
    op.drop_index("ix_card_scripts_statut", table_name="card_scripts")
    op.drop_table("card_scripts")
