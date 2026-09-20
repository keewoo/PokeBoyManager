-- Export hebdo de la présence en tournoi (base de référence, chimera). card_tcgdex_id = clé de la
-- carte ; `decks` est du JSONB affiché tel quel côté fiche (jamais réinterprété). Snapshot par
-- carte : l'import PROD fait un upsert (une carte = une ligne, se rafraîchit chaque semaine).
-- docker exec pbm-shared-postgres-1 psql -U pbm -d pbm_catalogue_ref -f infra/fleet/export_tournament.sql > tournament.tsv
COPY (
    SELECT c.tcgdex_id AS card_tcgdex_id, t.status, t.source_url, t.decks, t.checked_at
    FROM card_tournament_presence t
    JOIN cards c ON c.id = t.card_id
    WHERE c.tcgdex_id IS NOT NULL
) TO STDOUT WITH (FORMAT csv, DELIMITER E'\t', NULL '');
