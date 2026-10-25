-- Export des fiches `card_insights` d'une base (référence chimera OU PROD) vers le TSV attendu par
-- `import_insights.sql` — lot `pbm-insights-ciblage-large`. Symétrique de l'import : clé
-- `cards.tcgdex_id`, mêmes colonnes/ordre, FORMAT csv tab. Sert à re-dériver le bundle depuis une
-- base qui détient déjà les fiches (reprise, réplication vers l'autre base). `anecdotes_en` n'est
-- pas exporté (non produit par ce lot).
--   docker exec -i pbm-shared-postgres-1 psql -U pbm -d pbm_catalogue_ref \
--     -f infra/fleet/export_insights.sql > insights.tsv
COPY (
    SELECT c.tcgdex_id, i.anecdotes, i.in_game_study, i.source_model,
           i.generated_at, i.cached_until,
           i.game_study_source_model, i.game_study_generated_at, i.game_study_cached_until
    FROM card_insights i
    JOIN cards c ON c.id = i.card_id
    WHERE c.tcgdex_id IS NOT NULL
    ORDER BY c.tcgdex_id
) TO STDOUT WITH (FORMAT csv, DELIMITER E'\t', NULL '');
