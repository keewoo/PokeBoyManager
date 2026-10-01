"""card prize_marker (marqueur de règle normalisé pour la règle des Prix)

Ajoute `cards.prize_marker` : le marqueur de règle **normalisé** (vocabulaire du moteur
`pbm_game.combat.fin.MARQUEUR_RECOMPENSES`) d'où se déduit le nombre de récompenses d'une carte
K.O. (R-13.3/R-13.7). Jusqu'ici ce nombre se devinait du **suffixe du nom**, qui range mal une
Méga-Évolution Pokémon ex (finit par « ex », donne 3) ou une TAG TEAM (finit par « GX », donne 3).

Non destructive et rejouable : ajoute une colonne *nullable* et **remplit les cartes existantes**
dans la migration elle-même, via la **même** fonction pure que l'import
(`pbm_api.catalog.prize_marker.normalized_prize_marker`) — une seule logique de classification.
Les cartes hors Pokémon (Dresseur, Énergie) gardent `prize_marker` NULL (la règle ne les concerne
pas). S'applique donc sans intervention à la prochaine livraison PROD.

Revision ID: e7c2a9f14b63
Revises: b2d4f6a8c0e1
Create Date: 2026-10-01

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from pbm_api.catalog.prize_marker import normalized_prize_marker

revision: str = "e7c2a9f14b63"
down_revision: str | Sequence[str] | None = "b2d4f6a8c0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BACKFILL_CHUNK = 500


def upgrade() -> None:
    op.add_column("cards", sa.Column("prize_marker", sa.String(length=16), nullable=True))

    bind = op.get_bind()
    cards = sa.table(
        "cards",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String),
        sa.column("supertype", sa.String),
        sa.column("rule_marker", sa.String),
        sa.column("prize_marker", sa.String),
    )

    rows = bind.execute(
        sa.select(cards.c.id, cards.c.name, cards.c.supertype, cards.c.rule_marker)
    ).fetchall()

    # Regroupe les id par marqueur calculé : une poignée d'UPDATE (un par marqueur, par tranches)
    # au lieu de dizaines de milliers. Les cartes hors Pokémon rendent None → laissées à NULL.
    ids_by_marker: dict[str, list] = {}
    for row in rows:
        marker = normalized_prize_marker(
            name=row.name, supertype=row.supertype, rule_marker=row.rule_marker
        )
        if marker is None:
            continue
        ids_by_marker.setdefault(marker, []).append(row.id)

    for marker, ids in ids_by_marker.items():
        for start in range(0, len(ids), _BACKFILL_CHUNK):
            chunk = ids[start : start + _BACKFILL_CHUNK]
            bind.execute(
                cards.update().where(cards.c.id.in_(chunk)).values(prize_marker=marker)
            )


def downgrade() -> None:
    op.drop_column("cards", "prize_marker")
