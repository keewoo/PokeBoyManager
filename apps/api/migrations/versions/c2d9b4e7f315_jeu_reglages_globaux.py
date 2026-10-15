"""Réglages **globaux** du jeu : la table que JF pose à la main (lot ``j-classement-prive``, DJ6).

Une table de deux colonnes utiles — ``cle`` et ``valeur`` — et **aucune ligne semée**. L'absence de
ligne est l'état normal d'un réglage jamais touché : la lecture rend alors son défaut déclaré dans
:mod:`pbm_api.jeu.reglages`. Semer les défauts en base aurait figé ici une valeur que le code croit
encore pouvoir changer, et il aurait fallu une migration pour corriger un défaut.

**Pourquoi clé/valeur.** DJ6 annonce deux options activables par JF — le classement privé (ce lot)
et les badges (`j-profil-jeu`) — et le jeu en aura d'autres. Une colonne par réglage aurait coûté
une migration par booléen ; le prix habituel du motif clé/valeur (« on peut écrire n'importe quoi »)
est payé dans le code, par un registre de clés déclarées qui refuse le reste.

**Pourquoi une table et pas une variable d'environnement.** Parce que le critère d'acceptation du
lot dit « la désactivation est un réglage, pas un déploiement » : une variable d'environnement
demande d'éditer le fichier d'environnement du serveur *et* de redémarrer les conteneurs. Ici, une
commande d'administration suffit, sans interrompre une partie en cours.

Revision ID: c2d9b4e7f315
Revises: b8f3c5d7e914
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c2d9b4e7f315"
down_revision: str | Sequence[str] | None = "b8f3c5d7e914"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "jeu_reglages",
        sa.Column("cle", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("valeur", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    # Redescendre efface les réglages posés : le classement repart donc éteint (son défaut), ce qui
    # est le comportement le moins surprenant — jamais « actif » par accident.
    op.drop_table("jeu_reglages")
