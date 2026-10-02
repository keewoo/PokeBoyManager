"""fusion des têtes alembic : game_access (D11) + effets de carte / sous-type Dresseur

Les lots `j-file-attente` (`d2b7f1a4c9e0`, `users.game_access`) et `cat-textes-effets`
(`f3b8d1c6a927`, texte d'effet + sous-type Dresseur) ont été développés en parallèle à partir du
même parent (`c5f1a9e3b7d0`), créant **deux têtes alembic**. `alembic upgrade head` refuse alors
d'agir (« Multiple head revisions are present »).

Cette migration les **réunit** : les deux parents sont additifs et indépendants (une colonne sur
`users`, des colonnes sur `cards`), elle n'a donc **aucune** opération de schéma propre — elle ne
fait que relier le graphe pour qu'il n'ait plus qu'une tête. Rejouable, sans effet sur les données.

Revision ID: e4c9a1f20d83
Revises: d2b7f1a4c9e0, f3b8d1c6a927
Create Date: 2026-10-02

"""

from collections.abc import Sequence

revision: str = "e4c9a1f20d83"
down_revision: str | Sequence[str] | None = ("d2b7f1a4c9e0", "f3b8d1c6a927")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Aucune opération : cette migration ne fait que réunir deux têtes additives."""


def downgrade() -> None:
    """Aucune opération : la descente rouvre simplement les deux branches parentes."""
