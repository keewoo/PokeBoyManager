"""users.game_access (droit d'accès au jeu — « compte invité », D11)

Ajoute `users.game_access` : le droit d'accès au jeu. L'inscription est libre (D8), mais le jeu est
réservé aux **comptes invités** (D11) — un compte ordinaire ne voit **rien** du jeu (toutes ses
routes répondent 404). Le droit est posé et retiré hors ligne par l'administration
(`pbm_api.admin set-game-access <email> on|off`), jamais par une route HTTP.

Additive et rejouable : colonne booléenne NOT NULL avec valeur serveur `false`. Tous les comptes
existants deviennent donc « sans accès au jeu » à la livraison — l'état voulu : le jeu s'ouvre
compte par compte. S'applique sans intervention à la prochaine livraison.

Revision ID: d2b7f1a4c9e0
Revises: c5f1a9e3b7d0
Create Date: 2026-10-02

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d2b7f1a4c9e0"
down_revision: str | Sequence[str] | None = "c5f1a9e3b7d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "game_access",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "game_access")
