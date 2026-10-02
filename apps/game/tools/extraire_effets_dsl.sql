-- Extraction d'un échantillon **déterministe** de 500 textes d'effet du catalogue de référence,
-- pour le dépouillement du langage d'effets (lot j-effets-dsl, outil classer_dsl.py).
--
-- Le texte d'une carte concatène ses effets de talents (abilities), ses effets d'attaque
-- (attacks) et son texte de Dresseur/Énergie (effect) — séparés par « ||| ». On ne retient que
-- les cartes PORTEUSES d'au moins un effet (sinon rien à dépouiller). L'échantillon est
-- déterministe (ORDER BY md5(tcgdex_id)) : relancer donne les mêmes 500 cartes, donc le gel est
-- reproductible. La base de référence est en LECTURE SEULE pour ce lot : aucune écriture ici.
--
-- Usage (sur chimera) :
--   docker exec -i pbm-shared-postgres-1 psql -U pbm -d pbm_catalogue_ref -t -A \
--     -f apps/game/tools/extraire_effets_dsl.sql > brut_500.json
SELECT json_agg(row_to_json(t))
FROM (
  SELECT
    tcgdex_id AS id,
    name,
    supertype,
    trainer_type,
    trim(both ' |' FROM
      concat_ws(' ||| ',
        NULLIF((
          SELECT string_agg(trim(a->>'effect'), ' ||| ')
          FROM jsonb_array_elements(abilities) a
          WHERE jsonb_typeof(abilities) = 'array'
            AND length(trim(coalesce(a->>'effect', ''))) > 0
        ), ''),
        NULLIF((
          SELECT string_agg(trim(a->>'effect'), ' ||| ')
          FROM jsonb_array_elements(attacks) a
          WHERE jsonb_typeof(attacks) = 'array'
            AND length(trim(coalesce(a->>'effect', ''))) > 0
        ), ''),
        NULLIF(trim(coalesce(effect, '')), '')
      )
    ) AS texte
  FROM cards
  WHERE
    (jsonb_typeof(abilities) = 'array' AND EXISTS (
      SELECT 1 FROM jsonb_array_elements(abilities) a
      WHERE length(trim(coalesce(a->>'effect', ''))) > 0))
    OR (jsonb_typeof(attacks) = 'array' AND EXISTS (
      SELECT 1 FROM jsonb_array_elements(attacks) a
      WHERE length(trim(coalesce(a->>'effect', ''))) > 0))
    OR (effect IS NOT NULL AND length(trim(effect)) > 0)
  ORDER BY md5(tcgdex_id)
  LIMIT 500
) t;
