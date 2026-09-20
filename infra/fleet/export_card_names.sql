-- Export hebdo des noms localisés (base de référence, chimera). card_tcgdex_id = clé de la carte.
-- docker exec pbm-shared-postgres-1 psql -U pbm -d pbm_catalogue_ref -f infra/fleet/export_card_names.sql > card_names.tsv
COPY (
    SELECT c.tcgdex_id AS card_tcgdex_id, n.language, n.name
    FROM card_names n
    JOIN cards c ON c.id = n.card_id
    WHERE c.tcgdex_id IS NOT NULL
) TO STDOUT WITH (FORMAT csv, DELIMITER E'\t', NULL '');
