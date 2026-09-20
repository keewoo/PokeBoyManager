-- Export des relevés de prix du DERNIER jour présent, sur la base de référence (chimera).
-- Lancé via : docker exec pbm-shared-postgres-1 psql -U pbm -d pbm_catalogue_ref \
--               -f infra/fleet/export_prices.sql > prices.tsv
-- Clé de jointure = cards.tcgdex_id (STABLE entre bases : les UUID de `cards.id` diffèrent entre
-- pbm_catalogue_ref et pokeboy_prod, seeds indépendants). Les cartes sans tcgdex_id ne peuvent
-- être rapprochées en PROD : exclues ici, comptées par le manifeste de l'orchestrateur (jamais
-- avalées en silence). TSV (FORMAT csv, séparateur TAB) pour un round-trip JSONB/guillemets sûr.
COPY (
    SELECT c.tcgdex_id, p.source, p.variant, p.day, p.currency,
           p.price_low, p.price_mid, p.price_trend
    FROM card_prices_daily p
    JOIN cards c ON c.id = p.card_id
    WHERE p.day = (SELECT max(day) FROM card_prices_daily)
      AND c.tcgdex_id IS NOT NULL
) TO STDOUT WITH (FORMAT csv, DELIMITER E'\t', NULL '');
