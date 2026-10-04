-- Rétro-remplissage PROD des colonnes du catalogue AJOUTÉES APRÈS le premier chargement.
--     sudo -u postgres psql -d pokeboy_prod -f infra/fleet/backfill_cards.sql
-- Prérequis : le MÊME bundle que l'import hebdo, décompressé dans /tmp/pbm-import/ (cards.tsv).
--
-- POURQUOI CE GESTE EXISTE (lot `cat-stades`, 04/10/2026). `import_weekly.sql` est INSERT-ONLY :
-- il n'a jamais touché aux cartes DÉJÀ chargées. Or six colonnes (energy_type, element_type,
-- stage, prize_marker, trainer_type, effect) n'ont été ajoutées à la chaîne que le 02/10/2026
-- (lot `cat-textes-effets`). Toutes les cartes entrées AVANT cette date sont donc restées à
-- `NULL` sur ces colonnes, et n'ont jamais été rattrapées. En jeu, une carte sans `stage` ou sans
-- `prize_marker` est **bloquée** par `pbm_api.jeu.catalogue.definition_depuis_card` (R-7 / R-13.4,
-- « on ne devine pas ») : c'est la cause mesurée des très rares cartes jouables en PROD. Ce script
-- rattrape ces cartes à partir de la base de référence (via le bundle), sans rien recalculer.
--
-- SÛRETÉ. Rapprochement par `tcgdex_id` (clé stable entre bases, les UUID diffèrent). On ne
-- remplit QUE ce qui est `NULL` côté PROD et renseigné côté référence (`COALESCE` + garde dans le
-- WHERE) : une valeur déjà posée en PROD n'est JAMAIS écrasée, et une colonne légitimement vide
-- (un Pokémon sans `effect`, une carte sans `stage` dans aucune langue) reste vide. Idempotent :
-- un second passage ne change plus rien. Ne touche pas aux cartes absentes du bundle.
\set ON_ERROR_STOP on
\timing on
BEGIN;

CREATE TEMP TABLE _cards_in (
    tcgdex_id text, set_tcgdex_id text, number text, name text, rarity text, supertype text,
    hp int, image_url text, illustrator text, attacks jsonb, abilities jsonb,
    legal_standard boolean, legal_expanded boolean, ptcg_id text, weaknesses jsonb,
    resistances jsonb, retreat_cost int, rule_marker text, variants jsonb,
    energy_type text, element_type text, stage text, prize_marker text, trainer_type text,
    effect text
) ON COMMIT DROP;
\copy _cards_in FROM '/tmp/pbm-import/cards.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '')

\echo '--- AVANT backfill (Pokémon) ---'
SELECT count(*) FILTER (WHERE stage IS NULL)        AS stage_null,
       count(*) FILTER (WHERE prize_marker IS NULL) AS prize_marker_null,
       count(*) FILTER (WHERE element_type IS NULL) AS element_type_null
FROM cards WHERE supertype IN ('Pokémon', 'Pokemon');

UPDATE cards pc SET
    stage        = COALESCE(pc.stage,        i.stage),
    prize_marker = COALESCE(pc.prize_marker, i.prize_marker),
    element_type = COALESCE(pc.element_type, i.element_type),
    energy_type  = COALESCE(pc.energy_type,  i.energy_type),
    trainer_type = COALESCE(pc.trainer_type, i.trainer_type),
    effect       = COALESCE(pc.effect,       i.effect),
    updated_at   = now()
FROM _cards_in i
WHERE pc.tcgdex_id = i.tcgdex_id
  AND (   (pc.stage        IS NULL AND i.stage        IS NOT NULL)
       OR (pc.prize_marker IS NULL AND i.prize_marker IS NOT NULL)
       OR (pc.element_type IS NULL AND i.element_type IS NOT NULL)
       OR (pc.energy_type  IS NULL AND i.energy_type  IS NOT NULL)
       OR (pc.trainer_type IS NULL AND i.trainer_type IS NOT NULL)
       OR (pc.effect       IS NULL AND i.effect       IS NOT NULL) );

\echo '--- APRES backfill (Pokémon) ---'
SELECT count(*) FILTER (WHERE stage IS NULL)        AS stage_null,
       count(*) FILTER (WHERE prize_marker IS NULL) AS prize_marker_null,
       count(*) FILTER (WHERE element_type IS NULL) AS element_type_null
FROM cards WHERE supertype IN ('Pokémon', 'Pokemon');

COMMIT;
