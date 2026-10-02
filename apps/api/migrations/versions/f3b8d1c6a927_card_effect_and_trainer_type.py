"""card effect text + trainer sub-type (chantier des effets du jeu)

Ajoute deux colonnes additives à `cards`, préalable aux lots d'effets du jeu (`j-effets-dsl`,
`j-cartes-objets`/`-supporters`/`-stades`/`-outils`, `j-cartes-energies`) :

- `effect` (texte) : le texte d'effet/règle de la carte (TCGdex `effect`). Jusqu'ici non stocké —
  2 766 des 2 873 Dresseurs n'avaient ni `abilities` ni `attacks`, donc aucun texte scriptable
  (constat du lot `j-effets-architecture`, 02/10/2026). Porté par les Dresseurs et les Énergies
  spéciales ; `None` pour les Pokémon et les Énergies de base.
- `trainer_type` : le sous-type de Dresseur (TCGdex `trainerType` : "Objet"/"Supporter"/"Stade"/
  "Outil"/"Machine Technique" en français, équivalents anglais via le repli). `None` hors Dresseur.

Toutes deux renseignées par `catalog/import_service.py`. Rien à rétro-remplir ici : le remplissage
se fait par la voie normale de l'import (re-upsert idempotent de chaque carte).

Revision ID: f3b8d1c6a927
Revises: c5f1a9e3b7d0
Create Date: 2026-10-02

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f3b8d1c6a927"
down_revision: str | Sequence[str] | None = "c5f1a9e3b7d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("cards", sa.Column("effect", sa.Text(), nullable=True))
    op.add_column("cards", sa.Column("trainer_type", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("cards", "trainer_type")
    op.drop_column("cards", "effect")
