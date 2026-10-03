"""Adversaire IA : siège IA, budget par partie, et commentaire d'affichage au journal.

Lot ``j-adversaire-ia`` (jalon J4, DJ7) — l'IA du joueur comme partenaire d'entraînement :

* ``game_players.adversaire_ia`` (bool) — ce siège est tenu par l'**IA du joueur** (sa clé joue) ;
  ``bot_niveau`` sert alors de **repli** quand l'IA échoue. Faux pour un bot pur ou un humain ;
* ``games.ia_appels`` / ``games.ia_tokens`` (int) — compteur de **budget** (plafond
  ``pbm_api.games.adversaire_ia.MAX_APPELS_PAR_PARTIE``) et total de jetons (base du **coût estimé
  affiché**). Sur la partie (et non en mémoire) pour survivre au fil des coups et à un F5 ;
* ``game_events.commentaire`` (str) — métadonnée d'**affichage** d'un coup : l'explication de l'IA
  qui a joué, ou la note de repli du bot. C'est une trace (jalon J4 « la partie laisse une trace »),
  pas un événement du moteur : elle ne participe pas au rejeu. ``NULL`` pour un coup ordinaire.

Toutes les colonnes ont une valeur par défaut serveur : la migration est sûre sur une base peuplée
(les parties existantes deviennent « bot pur, sans IA », ce qu'elles sont).

Revision ID: a1b2c3d4e5f6
Revises: f1c0b07a1d02
Create Date: 2026-10-03
"""

import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "f1c0b07a1d02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "game_players",
        sa.Column(
            "adversaire_ia", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.add_column(
        "games",
        sa.Column("ia_appels", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "games",
        sa.Column("ia_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "game_events",
        sa.Column("commentaire", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("game_events", "commentaire")
    op.drop_column("games", "ia_tokens")
    op.drop_column("games", "ia_appels")
    op.drop_column("game_players", "adversaire_ia")
