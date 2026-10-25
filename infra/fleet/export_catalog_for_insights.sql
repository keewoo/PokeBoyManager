-- Export du catalogue pour la génération des fiches (lot `pbm-insights-ciblage-large`).
-- Produit UN tableau JSON (une entrée par carte) avec tout ce dont
-- `scripts/generate_large_insights.py` a besoin : identité, données de jeu (attaques, talents,
-- légalités, PV, retraite, faiblesses/résistances, marqueur ex/V/VMAX), nom EN pour Bulbapedia,
-- infos d'extension (nom/série/date pour la priorité « récence ») et un proxy de valeur (prix)
-- pour la priorité « plus chères ». `tcgdex_id` est la clé de jointure vers la PROD (jamais l'UUID).
--   docker exec -i pbm-shared-postgres-1 psql -U pbm -d pbm_catalogue_ref -tA \
--     -f infra/fleet/export_catalog_for_insights.sql | gzip -c > catalog_full.json.gz
SELECT json_agg(t) FROM (
  SELECT
    c.tcgdex_id, s.tcgdex_id AS set_tcgdex_id,
    c.name, c.number, c.supertype, c.hp, c.rule_marker, c.retreat_cost,
    c.attacks, c.abilities, c.weaknesses, c.resistances,
    c.legal_standard, c.legal_expanded,
    (SELECT cn.name FROM card_names cn WHERE cn.card_id = c.id AND cn.language = 'en' LIMIT 1)
        AS en_name,
    s.name AS set_name, s.series AS set_series, s.release_date AS set_release_date,
    -- Proxy de valeur : plus fort prix relevé sur 90 jours (toutes sources/devises confondues —
    -- ordonnancement grossier de la priorité « plus chères », documenté comme tel dans le lot).
    (SELECT max(coalesce(p.price_trend, p.price_mid, p.price_low))
       FROM card_prices_daily p
      WHERE p.card_id = c.id AND p.day >= current_date - interval '90 days') AS value_proxy
  FROM cards c
  JOIN sets s ON s.id = c.set_id
  WHERE c.tcgdex_id IS NOT NULL AND s.tcgdex_id IS NOT NULL
  ORDER BY c.tcgdex_id
) t;
