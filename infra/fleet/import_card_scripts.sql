-- Import en PROD des scripts d'effet ADMIS écrits par l'assistance IA (lot `ia-scripts-passe`, DJ8),
-- SANS rien recalculer et SANS redéploiement de code.
--   sudo -u postgres psql -d pokeboy_prod -f infra/fleet/import_card_scripts.sql
-- Prérequis : card_scripts.tsv déposé dans /tmp/pbm-import/ (dossier 755, fichier 644), produit par
-- `infra/fleet/export_card_scripts.sql` sur la base de travail de la flotte.
--
-- INSERT SEULEMENT (jamais d'UPDATE) : on n'écrase AUCUN script déjà présent en PROD — un script
-- validé à la main ou importé antérieurement reste intact. Rapprochement par `text_fingerprint`
-- (l'empreinte du texte d'effet, identique entre bases). La contrainte `ck_card_scripts_scripte_gate`
-- refuse en base tout « scripte » sans programme + date de validation + tests verts : un TSV abîmé
-- est rejeté par la base, jamais joué « au mieux » (D9/DJ8).
--
-- ⚠️ L'ORDRE des colonnes suit EXACTEMENT celui de `export_card_scripts.sql` (contrat du TSV).
\set ON_ERROR_STOP on
\timing on
BEGIN;

CREATE TEMP TABLE _scripts_in (
    text_fingerprint text, lang text, source_text text, dsl_version int, script jsonb,
    statut text, author text, validated_at timestamptz, tests jsonb, notes text,
    review_tests_ok boolean, review_contradicteur text, famille text, confidence text,
    cost_eur numeric
) ON COMMIT DROP;
\copy _scripts_in FROM '/tmp/pbm-import/card_scripts.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '')

INSERT INTO card_scripts (id, text_fingerprint, lang, source_text, dsl_version, script, statut,
                          author, validated_at, tests, notes, review_tests_ok,
                          review_contradicteur, famille, confidence, cost_eur,
                          created_at, updated_at)
SELECT gen_random_uuid(), i.text_fingerprint, i.lang, i.source_text, i.dsl_version, i.script,
       i.statut, i.author, i.validated_at, i.tests, i.notes, i.review_tests_ok,
       i.review_contradicteur, i.famille, i.confidence, i.cost_eur, now(), now()
FROM _scripts_in i
WHERE NOT EXISTS (
    SELECT 1 FROM card_scripts cs WHERE cs.text_fingerprint = i.text_fingerprint
);

COMMIT;

\echo '--- verification post-import card_scripts ---'
SELECT statut, count(*) FROM card_scripts GROUP BY statut ORDER BY statut;
