-- Export des taux de change BCE du dernier jour publié (base de référence, chimera).
-- docker exec pbm-shared-postgres-1 psql -U pbm -d pbm_catalogue_ref -f infra/fleet/export_rates.sql > rates.tsv
-- Pas de FK ni d'UUID à traduire : la clé métier (day, currency) suffit à l'upsert côté PROD.
COPY (
    SELECT day, currency, rate
    FROM exchange_rates_daily
    WHERE day = (SELECT max(day) FROM exchange_rates_daily)
) TO STDOUT WITH (FORMAT csv, DELIMITER E'\t', NULL '');
