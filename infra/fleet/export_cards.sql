-- Export hebdo des cartes (base de référence, chimera). set_tcgdex_id = clé pour retrouver le set
-- en PROD (les UUID diffèrent). JSONB (attacks/abilities/weaknesses/resistances/variants) sérialisé
-- tel quel, round-trip sûr en FORMAT csv. NULL SQL -> champ vide (NULL '').
-- docker exec pbm-shared-postgres-1 psql -U pbm -d pbm_catalogue_ref -f infra/fleet/export_cards.sql > cards.tsv
--
-- ⚠️ L'ORDRE des colonnes est le contrat avec `import_weekly.sql` (table temporaire `_cards_in`) :
-- toute colonne ajoutée ici doit l'être au MÊME rang là-bas. Les six dernières (energy_type,
-- element_type, stage, prize_marker, trainer_type, effect) ont été ajoutées le 02/10/2026 (lot
-- `cat-textes-effets`) : jusque-là la chaîne les perdait en silence alors que le modèle les porte.
COPY (
    SELECT c.tcgdex_id, s.tcgdex_id AS set_tcgdex_id, c.number, c.name, c.rarity, c.supertype,
           c.hp, c.image_url, c.illustrator, c.attacks, c.abilities, c.legal_standard,
           c.legal_expanded, c.ptcg_id, c.weaknesses, c.resistances, c.retreat_cost,
           c.rule_marker, c.variants,
           c.energy_type, c.element_type, c.stage, c.prize_marker, c.trainer_type, c.effect
    FROM cards c
    JOIN sets s ON s.id = c.set_id
    WHERE c.tcgdex_id IS NOT NULL AND s.tcgdex_id IS NOT NULL
) TO STDOUT WITH (FORMAT csv, DELIMITER E'\t', NULL '');
