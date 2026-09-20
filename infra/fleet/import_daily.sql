-- Import du bundle quotidien (prix + taux) en PROD, SANS rien recalculer : COPY dans des tables
-- temporaires puis upsert. Lancé sur kailo-srv par l'orchestrateur devAI (lot `pbm-jobs-flotte`) :
--     sudo -u postgres psql -d pokeboy_prod -f infra/fleet/import_daily.sql
-- Prérequis : le bundle a été extrait dans /tmp/pbm-import/ (dossier 755, fichiers 644) :
--     /tmp/pbm-import/prices.tsv   /tmp/pbm-import/rates.tsv
-- (chemin FIXE : `\copy` n'interpole pas les variables psql — vérifié sur PROD 20/09/2026).
-- Le job reste COURT et local : aucune requête réseau, aucun scraping. Jointure sur cards.tcgdex_id.
\set ON_ERROR_STOP on
\timing on
BEGIN;

-- ---- Taux de change (clé métier day+currency) ----------------------------------------------
CREATE TEMP TABLE _rates_in (day date, currency text, rate numeric) ON COMMIT DROP;
\copy _rates_in FROM '/tmp/pbm-import/rates.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '')

INSERT INTO exchange_rates_daily (id, day, currency, rate, created_at)
SELECT gen_random_uuid(), day, currency, rate, now()
FROM _rates_in
ON CONFLICT ON CONSTRAINT uq_exchange_rates_daily_day_currency
DO UPDATE SET rate = EXCLUDED.rate;

-- ---- Prix du jour (jointure tcgdex_id -> card_id) ------------------------------------------
CREATE TEMP TABLE _prices_in (
    tcgdex_id text, source text, variant text, day date, currency text,
    price_low numeric, price_mid numeric, price_trend numeric
) ON COMMIT DROP;
\copy _prices_in FROM '/tmp/pbm-import/prices.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '')

-- Traçabilité honnête AVANT écriture : combien de lignes reçues, combien sans carte en PROD.
\echo '--- diagnostic import prix ---'
SELECT
    (SELECT count(*) FROM _prices_in) AS prix_recus,
    (SELECT count(*) FROM _prices_in i LEFT JOIN cards c ON c.tcgdex_id = i.tcgdex_id
        WHERE c.id IS NULL) AS lignes_sans_carte_en_prod;

INSERT INTO card_prices_daily
    (id, card_id, source, variant, day, currency, price_low, price_mid, price_trend, created_at)
SELECT gen_random_uuid(), c.id, i.source::price_source, i.variant::price_variant,
       i.day, i.currency, i.price_low, i.price_mid, i.price_trend, now()
FROM _prices_in i
JOIN cards c ON c.tcgdex_id = i.tcgdex_id
ON CONFLICT ON CONSTRAINT uq_card_prices_daily_unique_point
DO UPDATE SET currency = EXCLUDED.currency,
             price_low = EXCLUDED.price_low,
             price_mid = EXCLUDED.price_mid,
             price_trend = EXCLUDED.price_trend;

-- Rang de valeur (vue matérialisée lue par la fiche, mission `v4-ranking`) : rafraîchie sur des
-- données DÉJÀ importées, pas un recalcul réseau. Léger — mesuré, voir docs/infra/JOBS-LOURDS.md.
REFRESH MATERIALIZED VIEW card_value_rank;

COMMIT;

-- ---- Preuve : ce qui est réellement présent pour aujourd'hui -------------------------------
\echo '--- verification post-import ---'
SELECT
    count(*) AS prix_du_jour_en_prod,
    count(DISTINCT card_id) AS cartes_distinctes
FROM card_prices_daily
WHERE day = current_date;
