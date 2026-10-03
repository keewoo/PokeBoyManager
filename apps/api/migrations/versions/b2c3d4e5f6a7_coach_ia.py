"""Coach IA : conseils par partie et activation du coach par le joueur.

Lot ``j-coach-ia`` (jalon J4, DJ7) — l'IA du joueur comme coach :

* ``games.conseils_utilises`` (int) — compteur de **budget** des conseils demandés dans une partie
  (plafond ``settings.coach_max_conseils``). Sur la partie (et non en mémoire) pour survivre au fil
  des coups et à un F5. ``0`` pour une partie sans conseil (dont toute partie entre deux humains) ;
* ``users.coach_actif`` (bool) — le joueur peut **désactiver** le coach dans son profil. Vrai par
  défaut : le coach est proposé, jamais imposé (il consomme la clé IA du joueur).

Les deux colonnes ont une valeur par défaut serveur : la migration est sûre sur une base peuplée
(les parties existantes gardent 0 conseil, les comptes existants ont le coach actif).

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-10-03
"""

import sqlalchemy as sa
from alembic import op

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "games",
        sa.Column("conseils_utilises", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "users",
        sa.Column("coach_actif", sa.Boolean(), nullable=False, server_default="true"),
    )


def downgrade() -> None:
    op.drop_column("users", "coach_actif")
    op.drop_column("games", "conseils_utilises")
