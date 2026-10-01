"""fix marqueur stades (un stade ordinaire n'est jamais un marqueur de règle)

Corrige en base le défaut constaté en PROD le 01/10/2026 (release `20261001-234045`) : **564**
cartes portaient `cards.rule_marker` = `Stage1` / `Stage2` (sans espace). L'import ne reconnaissait
comme stades ordinaires que `stage 1` / `stage 2` (ancien `ORDINARY_STAGES`), si bien que `Stage1`/
`Stage2` étaient recopiés dans `rule_marker` puis classés `inconnu` par `normalized_prize_marker` —
la fiche « En jeu » affichait « Récompenses non déterminées », et `decks/stats.py` les comptait à
tort comme cartes à Rule Box. Le catalogue de chimera ne portait pas ces valeurs, d'où le trou dans
la preuve du lot `fix-marqueur-recompenses`.

Le correctif de code (lot `fix-marqueur-stades`) normalise désormais les stades sans casse NI
espaces/tirets (`pbm_api.catalog.prize_marker.is_ordinary_stage`), partagé par l'import et par la
classification. Cette migration remet les **données existantes** en cohérence, via la **même**
fonction pure (`corrected_stage_row`) : pour toute ligne dont `rule_marker` est un stade ordinaire,
`rule_marker` repasse à NULL et `prize_marker` est recalculé sur le `rule_marker` vidé. Elle ne
touche à **rien d'autre** — une vraie Rule Box (`VMAX`, `ex`, `GX`…) est laissée intacte.

Additive et rejouable : un second passage ne trouve plus aucune ligne à stade ordinaire dans
`rule_marker` (la première l'a vidé) — donc zéro mise à jour, résultat identique. S'applique sans
intervention à la prochaine livraison PROD.

Revision ID: a3f9c2e5b1d4
Revises: e7c2a9f14b63
Create Date: 2026-10-02

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from pbm_api.catalog.prize_marker import corrected_stage_row

revision: str = "a3f9c2e5b1d4"
down_revision: str | Sequence[str] | None = "e7c2a9f14b63"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BACKFILL_CHUNK = 500


def upgrade() -> None:
    bind = op.get_bind()
    cards = sa.table(
        "cards",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String),
        sa.column("supertype", sa.String),
        sa.column("rule_marker", sa.String),
        sa.column("prize_marker", sa.String),
    )

    # Seules les lignes qui ont un `rule_marker` peuvent porter un stade ordinaire mal rangé.
    rows = bind.execute(
        sa.select(cards.c.id, cards.c.name, cards.c.supertype, cards.c.rule_marker).where(
            cards.c.rule_marker.isnot(None)
        )
    ).fetchall()

    # Regroupe les id par `prize_marker` recalculé (le `rule_marker` corrigé est toujours NULL) :
    # une poignée d'UPDATE — un par marqueur, par tranches — au lieu d'un par ligne.
    ids_by_prize: dict[str | None, list] = {}
    for row in rows:
        correction = corrected_stage_row(
            name=row.name, supertype=row.supertype, rule_marker=row.rule_marker
        )
        if correction is None:  # pas un stade ordinaire → on n'y touche pas.
            continue
        _, prize = correction
        ids_by_prize.setdefault(prize, []).append(row.id)

    for prize, ids in ids_by_prize.items():
        for start in range(0, len(ids), _BACKFILL_CHUNK):
            chunk = ids[start : start + _BACKFILL_CHUNK]
            bind.execute(
                cards.update()
                .where(cards.c.id.in_(chunk))
                .values(rule_marker=None, prize_marker=prize)
            )


def downgrade() -> None:
    # Correction de données **non réversible** : le libellé de stade brut (`Stage1` vs `stage 1`…)
    # n'est pas reconstituable depuis un `rule_marker` NULL. No-op EXPLICITE — jamais un repli
    # silencieux —, la migration étant additive et rejouable, pas annulable.
    pass
