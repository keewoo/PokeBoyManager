"""Décor d'arène choisi par le joueur (lot ``j-arene-decors``).

Une seule colonne, ``jeu_confort_reglages.decor``, **nullable sans valeur par défaut**.

Le ``NULL`` est la partie importante : il ne veut pas dire « pas encore renseigné », il veut dire
« laisse le jeu choisir d'après mon deck » — c'est le réglage par défaut, et le seul moyen de le
distinguer d'un joueur qui a explicitement demandé le décor ``arene``. Poser un ``server_default``
rendrait le thème automatique inatteignable pour tous les comptes existants, en silence.

Le décor est rangé avec les réglages de confort plutôt que dans une table à lui : c'est la même
sorte de réglage (il ne change aucune règle, seulement ce qu'on voit, et il doit suivre le compte
d'un appareil à l'autre), et une table d'une colonne pour un compte aurait coûté une jointure à
chaque chargement de partie.

Revision ID: b8f3c5d7e914
Revises: a7e4c2b9d518
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8f3c5d7e914"
down_revision: str | Sequence[str] | None = "a7e4c2b9d518"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "jeu_confort_reglages",
        sa.Column("decor", sa.String(length=24), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("jeu_confort_reglages", "decor")
