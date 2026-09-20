-- Import HEBDOMADAIRE du catalogue + présence en tournoi en PROD, SANS rien recalculer.
--     sudo -u postgres psql -d pokeboy_prod -f infra/fleet/import_weekly.sql
-- Prérequis : bundle extrait dans /tmp/pbm-import/ (dossier 755, fichiers 644), quatre fichiers
-- TOUJOURS présents (l'orchestrateur crée un fichier vide si une source l'est) :
--     sets.tsv  cards.tsv  card_names.tsv  tournament.tsv
--
-- CATALOGUE = INSERT SEULEMENT (jamais d'UPDATE) : on ne touche PAS au catalogue déjà chargé
-- (garde-fou de la mission). Seules les extensions/cartes/noms NOUVEAUX sont insérés ; les lignes
-- existantes sont laissées telles quelles. Rapprochement par tcgdex_id (UUID différents entre bases).
-- TOURNOI = upsert par carte (snapshot rafraîchi chaque semaine, une ligne par carte).
\set ON_ERROR_STOP on
\timing on
BEGIN;

-- ---- Extensions (insert-only) --------------------------------------------------------------
CREATE TEMP TABLE _sets_in (
    tcgdex_id text, code text, name text, series text, release_date date,
    total_cards int, symbol_url text, logo_url text
) ON COMMIT DROP;
\copy _sets_in FROM '/tmp/pbm-import/sets.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '')

INSERT INTO sets (id, code, name, series, release_date, total_cards, symbol_url, logo_url,
                  created_at, updated_at, tcgdex_id)
SELECT gen_random_uuid(), s.code, s.name, s.series, s.release_date, s.total_cards,
       s.symbol_url, s.logo_url, now(), now(), s.tcgdex_id
FROM _sets_in s
WHERE NOT EXISTS (SELECT 1 FROM sets ps WHERE ps.tcgdex_id = s.tcgdex_id)
  AND NOT EXISTS (SELECT 1 FROM sets ps WHERE ps.code = s.code);

-- ---- Cartes (insert-only, set résolu par tcgdex_id) ----------------------------------------
CREATE TEMP TABLE _cards_in (
    tcgdex_id text, set_tcgdex_id text, number text, name text, rarity text, supertype text,
    hp int, image_url text, illustrator text, attacks jsonb, abilities jsonb,
    legal_standard boolean, legal_expanded boolean, ptcg_id text, weaknesses jsonb,
    resistances jsonb, retreat_cost int, rule_marker text, variants jsonb
) ON COMMIT DROP;
\copy _cards_in FROM '/tmp/pbm-import/cards.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '')

INSERT INTO cards (id, set_id, number, name, rarity, supertype, hp, image_url, created_at,
                   updated_at, illustrator, attacks, abilities, legal_standard, legal_expanded,
                   tcgdex_id, ptcg_id, weaknesses, resistances, retreat_cost, rule_marker, variants)
SELECT gen_random_uuid(), ps.id, i.number, i.name, i.rarity, i.supertype, i.hp, i.image_url,
       now(), now(), i.illustrator, i.attacks, i.abilities, i.legal_standard, i.legal_expanded,
       i.tcgdex_id, i.ptcg_id, i.weaknesses, i.resistances, i.retreat_cost, i.rule_marker, i.variants
FROM _cards_in i
JOIN sets ps ON ps.tcgdex_id = i.set_tcgdex_id
WHERE NOT EXISTS (SELECT 1 FROM cards pc WHERE pc.tcgdex_id = i.tcgdex_id)
  AND NOT EXISTS (SELECT 1 FROM cards pc WHERE pc.set_id = ps.id AND pc.number = i.number);

-- ---- Noms localisés (insert-only) ----------------------------------------------------------
CREATE TEMP TABLE _names_in (card_tcgdex_id text, language text, name text) ON COMMIT DROP;
\copy _names_in FROM '/tmp/pbm-import/card_names.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '')

INSERT INTO card_names (id, card_id, language, name)
SELECT gen_random_uuid(), pc.id, i.language, i.name
FROM _names_in i
JOIN cards pc ON pc.tcgdex_id = i.card_tcgdex_id
WHERE NOT EXISTS (
    SELECT 1 FROM card_names cn WHERE cn.card_id = pc.id AND cn.language = i.language
);

-- ---- Présence en tournoi (upsert par carte) ------------------------------------------------
CREATE TEMP TABLE _tourn_in (
    card_tcgdex_id text, status text, source_url text, decks jsonb, checked_at timestamp
) ON COMMIT DROP;
\copy _tourn_in FROM '/tmp/pbm-import/tournament.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '')

INSERT INTO card_tournament_presence (id, card_id, status, source_url, decks, checked_at)
SELECT gen_random_uuid(), pc.id, i.status::tournament_presence_status, i.source_url,
       i.decks, i.checked_at
FROM _tourn_in i
JOIN cards pc ON pc.tcgdex_id = i.card_tcgdex_id
ON CONFLICT (card_id) DO UPDATE SET status = EXCLUDED.status,
                                    source_url = EXCLUDED.source_url,
                                    decks = EXCLUDED.decks,
                                    checked_at = EXCLUDED.checked_at;

-- Rareté (vue matérialisée) : de nouvelles cartes changent les groupes de rareté par extension.
REFRESH MATERIALIZED VIEW card_value_rank;

COMMIT;

\echo '--- verification post-import hebdo ---'
SELECT (SELECT count(*) FROM sets) AS sets_total,
       (SELECT count(*) FROM cards) AS cards_total,
       (SELECT count(*) FROM card_names) AS card_names_total,
       (SELECT count(*) FROM card_tournament_presence) AS tournament_total;
