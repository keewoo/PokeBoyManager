-- Export hebdo des extensions (base de référence, chimera) — clé de rapprochement = tcgdex_id.
-- docker exec pbm-shared-postgres-1 psql -U pbm -d pbm_catalogue_ref -f infra/fleet/export_sets.sql > sets.tsv
COPY (
    SELECT tcgdex_id, code, name, series, release_date, total_cards, symbol_url, logo_url
    FROM sets
    WHERE tcgdex_id IS NOT NULL
) TO STDOUT WITH (FORMAT csv, DELIMITER E'\t', NULL '');
