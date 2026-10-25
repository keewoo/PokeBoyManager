-- Import des fiches générées (2 anecdotes FR + règles de jeu) — lot `pbm-insights-ciblage-large`.
-- Le worker de PROD ne génère RIEN : il reçoit un TSV produit sur la flotte (devAI, clé d'Aymeric)
-- et fait COPY dans une table temporaire puis un upsert. Jointure sur `cards.tcgdex_id` (jamais
-- l'UUID : les deux bases sont seedées indépendamment). Aucun appel réseau, aucun appel IA.
--
-- Le même script sert la PROD ET la base de référence chimera — le fichier est déposé au chemin
-- FIXE /tmp/pbm-import/insights.tsv (`\copy` n'interpole pas les variables psql) :
--   PROD    : sudo -u postgres psql -d pokeboy_prod -f infra/fleet/import_insights.sql
--   chimera : docker cp insights.tsv pbm-shared-postgres-1:/tmp/pbm-import/insights.tsv
--             docker exec -i pbm-shared-postgres-1 psql -U pbm -d pbm_catalogue_ref \
--               -f - < infra/fleet/import_insights.sql
-- Colonnes du TSV (FORMAT csv, DELIMITER tab, NULL '') — écrites par generate_large_insights.py :
--   tcgdex_id, anecdotes(jsonb), in_game_study, source_model, generated_at, cached_until,
--   game_study_source_model, game_study_generated_at, game_study_cached_until
-- `anecdotes_en` n'est PAS fourni (français seulement, décision de JF) : l'upsert n'y touche pas.
\set ON_ERROR_STOP on
\timing on
BEGIN;

CREATE TEMP TABLE _insights_in (
    tcgdex_id text,
    anecdotes jsonb,
    in_game_study text,
    source_model text,
    generated_at timestamp,
    cached_until timestamp,
    game_study_source_model text,
    game_study_generated_at timestamp,
    game_study_cached_until timestamp
) ON COMMIT DROP;
\copy _insights_in FROM '/tmp/pbm-import/insights.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '')

-- Traçabilité honnête AVANT écriture : combien reçus, combien sans carte correspondante.
\echo '--- diagnostic import insights ---'
SELECT
    (SELECT count(*) FROM _insights_in) AS fiches_recues,
    (SELECT count(*) FROM _insights_in i LEFT JOIN cards c ON c.tcgdex_id = i.tcgdex_id
        WHERE c.id IS NULL) AS lignes_sans_carte;

INSERT INTO card_insights
    (id, card_id, anecdotes, in_game_study, source_model, generated_at, cached_until,
     game_study_source_model, game_study_generated_at, game_study_cached_until)
SELECT gen_random_uuid(), c.id, i.anecdotes, i.in_game_study, i.source_model,
       i.generated_at, i.cached_until,
       i.game_study_source_model, i.game_study_generated_at, i.game_study_cached_until
FROM _insights_in i
JOIN cards c ON c.tcgdex_id = i.tcgdex_id
ON CONFLICT (card_id) DO UPDATE SET
    anecdotes = EXCLUDED.anecdotes,
    in_game_study = EXCLUDED.in_game_study,
    source_model = EXCLUDED.source_model,
    generated_at = EXCLUDED.generated_at,
    cached_until = EXCLUDED.cached_until,
    game_study_source_model = EXCLUDED.game_study_source_model,
    game_study_generated_at = EXCLUDED.game_study_generated_at,
    game_study_cached_until = EXCLUDED.game_study_cached_until;

COMMIT;

-- Preuve : ce qui est réellement présent après import.
\echo '--- verification post-import ---'
SELECT
    count(*) AS fiches_total,
    count(*) FILTER (WHERE anecdotes IS NOT NULL) AS avec_anecdotes,
    count(*) FILTER (WHERE in_game_study IS NOT NULL) AS avec_regles_de_jeu
FROM card_insights;
