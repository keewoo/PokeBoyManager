"""card_value_rank materialized view

Revision ID: 11f10f8c0f40
Revises: d42b0620077e
Create Date: 2026-09-26 09:00:00.000000

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '11f10f8c0f40'
down_revision: str | Sequence[str] | None = 'd42b0620077e'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Mission `v4-ranking` point 1 : percentile de valeur dans l'extension + rang de rareté dans
# l'extension (D6), tous deux "de son extension" — voir le gain du lot : « est-ce une pièce
# maîtresse de ma collection, ET de son extension ? ». Rafraîchie par le job de prix
# (`pbm_api.ranking.service.refresh_card_value_rank`), jamais à la demande (risque documenté :
# recalcul coûteux).
#
# Référence de valeur par carte = tendance Cardmarket (EUR) la plus récente, sinon tendance
# TCGplayer convertie en EUR au taux le plus récent connu (pas nécessairement celui du même
# jour que le relevé — approximation assumée pour un agrégat périodique, contrairement à
# `pricing.valuation.reference_price_eur` qui aligne taux et prix au jour près pour la valeur
# d'un exemplaire) ; le maximum entre variantes sert de valeur représentative de la carte.
# Écrêtage des tendances aberrantes : même règle que `pricing.valuation._sanitize_trend`
# (borne à 3x le prix moyen quand les deux sont connus).
#
# Rang de rareté = DENSE_RANK croissant sur la taille du groupe de cartes partageant la même
# rareté au sein de l'extension (moins de cartes de cette rareté = rang 1 = plus rare) —
# dérivé uniquement du catalogue, aucune échelle de rareté externe à inventer.
_CREATE_VIEW_SQL = """
CREATE MATERIALIZED VIEW card_value_rank AS
WITH latest_cardmarket AS (
    SELECT DISTINCT ON (card_id, variant) card_id, price_mid, price_trend
    FROM card_prices_daily
    WHERE source = 'cardmarket'
    ORDER BY card_id, variant, day DESC
),
latest_tcgplayer AS (
    SELECT DISTINCT ON (card_id, variant) card_id, variant, currency, price_mid, price_trend
    FROM card_prices_daily
    WHERE source = 'tcgplayer'
    ORDER BY card_id, variant, day DESC
),
latest_rate AS (
    SELECT DISTINCT ON (currency) currency, rate
    FROM exchange_rates_daily
    ORDER BY currency, day DESC
),
sanitized AS (
    SELECT card_id,
        CASE
            WHEN price_trend IS NULL OR price_trend <= 0 THEN NULL
            WHEN price_mid IS NOT NULL AND price_mid > 0 AND price_trend > price_mid * 3
                THEN price_mid * 3
            ELSE price_trend
        END AS trend_eur
    FROM latest_cardmarket
    UNION ALL
    SELECT t.card_id,
        (CASE
            WHEN t.price_trend IS NULL OR t.price_trend <= 0 THEN NULL
            WHEN t.price_mid IS NOT NULL AND t.price_mid > 0 AND t.price_trend > t.price_mid * 3
                THEN t.price_mid * 3
            ELSE t.price_trend
        END) / NULLIF(r.rate, 0) AS trend_eur
    FROM latest_tcgplayer t
    LEFT JOIN latest_rate r ON r.currency = t.currency
),
card_reference AS (
    SELECT card_id, MAX(trend_eur) AS reference_price_eur
    FROM sanitized
    WHERE trend_eur IS NOT NULL
    GROUP BY card_id
),
priced_ranked AS (
    SELECT
        cr.card_id,
        cr.reference_price_eur,
        PERCENT_RANK() OVER (
            PARTITION BY c.set_id ORDER BY cr.reference_price_eur
        ) AS value_percentile
    FROM card_reference cr
    JOIN cards c ON c.id = cr.card_id
),
rarity_counts AS (
    SELECT set_id, rarity, COUNT(*) AS rarity_group_size
    FROM cards
    WHERE rarity IS NOT NULL
    GROUP BY set_id, rarity
),
rarity_ranked AS (
    SELECT
        set_id, rarity, rarity_group_size,
        DENSE_RANK() OVER (PARTITION BY set_id ORDER BY rarity_group_size ASC) AS rarity_rank
    FROM rarity_counts
)
SELECT
    c.id AS card_id,
    c.set_id,
    pr.reference_price_eur,
    pr.value_percentile,
    rr.rarity_rank,
    rr.rarity_group_size,
    now() AS refreshed_at
FROM cards c
LEFT JOIN priced_ranked pr ON pr.card_id = c.id
LEFT JOIN rarity_ranked rr ON rr.set_id = c.set_id AND rr.rarity = c.rarity
"""


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(_CREATE_VIEW_SQL)
    # Index unique requis pour un futur `REFRESH MATERIALIZED VIEW CONCURRENTLY` (pas utilisé
    # au premier tir — voir `pbm_api.ranking.service.refresh_card_value_rank` — mais posé tout
    # de suite pour ne pas re-verrouiller la vue en production plus tard).
    op.execute(
        "CREATE UNIQUE INDEX ix_card_value_rank_card_id ON card_value_rank (card_id)"
    )
    op.execute(
        "CREATE INDEX ix_card_value_rank_set_id ON card_value_rank (set_id)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP MATERIALIZED VIEW IF EXISTS card_value_rank")
