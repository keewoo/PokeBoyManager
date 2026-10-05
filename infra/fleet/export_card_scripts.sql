-- Export des scripts d'effet ADMIS (statut « scripte ») depuis la base de travail de la flotte,
-- pour import en PROD SANS redéploiement de code (lot `ia-scripts-passe`, décision DJ8).
--   docker exec pbm-shared-postgres-1 psql -U pbm -d <base_de_travail> -f infra/fleet/export_card_scripts.sql > card_scripts.tsv
--
-- La clé d'une ligne est l'EMPREINTE du texte d'effet (text_fingerprint), indépendante des UUID de
-- cartes : une même empreinte désigne le même effet dans toutes les bases (chimera comme PROD). On
-- n'exporte QUE les « scripte » (jouables) — les `a_revoir`/`non_supporte` restent sur la base de
-- travail, ils ne rendent aucune carte jouable en PROD.
--
-- ⚠️ L'ORDRE des colonnes est le contrat avec `import_card_scripts.sql` (table temporaire
-- `_scripts_in`) : toute colonne ajoutée ici doit l'être au MÊME rang là-bas. `script` et `tests`
-- sont du JSONB sérialisé tel quel (round-trip sûr en FORMAT csv). NULL SQL -> champ vide (NULL '').
COPY (
    SELECT text_fingerprint, lang, source_text, dsl_version, script, statut, author,
           validated_at, tests, notes, review_tests_ok, review_contradicteur, famille,
           confidence, cost_eur
    FROM card_scripts
    WHERE statut = 'scripte'
    ORDER BY text_fingerprint
) TO STDOUT WITH (FORMAT csv, DELIMITER E'\t', NULL '');
