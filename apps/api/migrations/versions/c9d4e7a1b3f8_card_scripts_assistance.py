"""card_scripts : colonnes de revue de l'assistance IA + contrainte de porte (DJ8).

Lot `j-effets-assistance-ia`. Ajoute les colonnes qui portent la preuve de la porte DJ8
(``review_tests_ok``, ``review_contradicteur``, ``famille``, ``confidence``, ``cost_eur``), puis la
contrainte CHECK ``ck_card_scripts_scripte_gate`` qui interdit en base qu'une ligne soit ``scripte``
sans programme, sans date de validation **et** sans tests verts.

Avant d'ajouter la contrainte, on **backfill** ``review_tests_ok = TRUE`` pour les ``scripte``
existants : ils ont été validés (import / validation humaine) avant DJ8, donc ils vouchent leurs
tests — sans ce backfill, la contrainte rejetterait des lignes légitimes déjà en base.

Revision ID: c9d4e7a1b3f8
Revises: b7d3f1a2c9e4
Create Date: 2026-10-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c9d4e7a1b3f8"
down_revision = "b7d3f1a2c9e4"
branch_labels = None
depends_on = None

_CK = "ck_card_scripts_scripte_gate"
_GATE = (
    "statut <> 'scripte' OR "
    "(script IS NOT NULL AND validated_at IS NOT NULL AND review_tests_ok IS TRUE)"
)


def upgrade() -> None:
    op.add_column("card_scripts", sa.Column("review_tests_ok", sa.Boolean(), nullable=True))
    op.add_column("card_scripts", sa.Column("review_contradicteur", sa.String(length=16), nullable=True))
    op.add_column("card_scripts", sa.Column("famille", sa.String(length=32), nullable=True))
    op.add_column("card_scripts", sa.Column("confidence", sa.String(length=8), nullable=True))
    op.add_column("card_scripts", sa.Column("cost_eur", sa.Numeric(precision=10, scale=6), nullable=True))
    # Les scripts déjà validés (avant DJ8) vouchent leurs tests : on le pose avant la contrainte.
    op.execute(
        "UPDATE card_scripts SET review_tests_ok = TRUE "
        "WHERE statut = 'scripte' AND review_tests_ok IS NULL"
    )
    op.create_check_constraint(_CK, "card_scripts", _GATE)


def downgrade() -> None:
    op.drop_constraint(_CK, "card_scripts", type_="check")
    op.drop_column("card_scripts", "cost_eur")
    op.drop_column("card_scripts", "confidence")
    op.drop_column("card_scripts", "famille")
    op.drop_column("card_scripts", "review_contradicteur")
    op.drop_column("card_scripts", "review_tests_ok")
