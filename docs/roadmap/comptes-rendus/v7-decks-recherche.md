# Compte rendu — `v7-decks-recherche`

**Recherche de cartes du constructeur : trouver une carte en trois secondes.**
Back-end (le couloir CH5 marque `maquette` « sans objet : back-end »). Branche
`roadmap/v7-decks-recherche`, base `github/main` (`ce5cb05`).

## Résumé

Deux routes du constructeur de deck, dans `pbm_api.routers.decks` (service
`pbm_api.decks.card_search`) :

- `GET /me/decks/cards` — cherche dans le **catalogue** (~22 000 cartes, pas la collection),
  chaque carte annotée pour l'utilisateur de la session du nombre **possédé** (`owned_count`,
  `is_duplicate`) et **déjà dans le deck édité** (`in_deck_count`, si `deck_id` fourni). Filtres
  cumulables (nom FR/EN accent-insensible **ou** numéro, extension, type, rareté, PV, « mes
  cartes », doublons), tri (valeur/nom/numéro/date d'ajout), pagination **par curseur keyset**.
- `GET /me/decks/cards/facets` — valeurs de filtre à l'échelle du catalogue + compteurs
  possédées/doublons propres à l'utilisateur.

## Livrables

- `apps/api/src/pbm_api/decks/card_search.py` — service (recherche, keyset, facettes).
- `apps/api/src/pbm_api/decks/schemas.py` — `DeckCardSearchItem/Response/Facets/FacetSet`.
- `apps/api/src/pbm_api/routers/decks.py` — routes `/cards` et `/cards/facets`, déclarées **avant**
  `/{deck_id}` (sinon « cards » serait parsé comme un UUID → 422).
- `apps/api/migrations/versions/f4a1c8d0b7e2_deck_card_search_indexes.py` — fonction
  `pbm_immutable_unaccent` + index trigram fonctionnels (noms FR/EN), btree
  (type/rareté/PV), composé `collection_items(user_id, card_id)`.
- `apps/api/tests/test_deck_card_search_routes.py` — 11 tests (filtres, comptes de possession,
  pagination curseur, facettes, accès croisé).
- `apps/api/scripts/measure_deck_card_search_performance.py` — mesure de perf (mission point 2).
- `CLAUDE.md` — section « Recherche de cartes du constructeur ».

## Preuves

- **ruff** : `All checks passed!` (sur tout `apps/api`).
- **pytest ciblé** : 41 passés (`test_deck_card_search_routes` (11) + `test_deck_routes` +
  `test_collection_routes`), sans régression.
- **pytest complet** : 645 passés, 2 échecs sur
  `test_catalogue_seed.py::{export_then_restore, import_is_idempotent}`. Localement sur chimera
  ils tombent sur `pg_dump: command not found` (client Postgres absent de la WSL).

  ⚠️ **Correction du 22/09 — ces deux échecs n'étaient PAS « sans rapport avec ce lot ».** La CI
  GitHub, qui a `pg_dump`, les a rejoués et ils ont échoué pour une autre raison, causée par ce
  lot : `pg_restore: COPY failed for table "cards": ERROR: text search dictionary "unaccent" does
  not exist` (run 35598181314, `api — lint, tests`). `pg_restore` ouvre sa session avec
  `search_path` vide ; le corps de `pbm_immutable_unaccent` résolvait `'unaccent'::regdictionary`
  **à l'appel**, et l'index trigram fonctionnel — maintenu pendant le COPY — faisait donc échouer
  la restauration du catalogue. Corrigé en qualifiant le schéma dans le corps de la fonction
  (`public.unaccent('public.unaccent'::regdictionary, $1)`), ce qui ne change pas l'expression
  indexée. **La leçon** : un échec local dû à un outil manquant ne dit rien de ce que fera la CI —
  tant qu'elle n'a pas tourné, « sans rapport avec ce lot » est une hypothèse, pas une preuve.
- **migration** : `alembic upgrade head` atteint `f4a1c8d0b7e2` (tête unique).
- **Perf (mission point 2, p95 < 150 ms sur 22 000 cartes / 5 000 exemplaires)** : **objectif
  tenu**, p95 par scénario (chimera, tables ANALYZE — cf. ci-dessous ;
  `var/deck-card-search-performance.json`) :

  | Scénario | p95 (ms) |
  |---|---|
  | page par défaut (tri nom) | 79 |
  | recherche par nom (sous-chaîne large « Carte 10 » ≈ 2 000 cartes) | 140 |
  | recherche par numéro | 33 |
  | filtre type + rareté | 39 |
  | filtre PV | 43 |
  | tri par valeur (page 1) | 70 |
  | seulement mes cartes | 47 |
  | doublons | 21 |
  | annoté du deck courant (deck_id) | 83 |
  | pagination 10 pages au curseur (total) | 691 (~69 ms/page) |

  ⚠️ **Le script `ANALYZE` les tables semées avant de mesurer** : sans cela (premier tir), le
  filtre type+rareté montait à **5,3 s** et le filtre PV à **1,1 s** — plans à boucles imbriquées
  sur des estimations fausses, artefact d'insertions en masse jamais analysées. En production les
  tables le sont toujours (autovacuum) ; la mesure sans ANALYZE ne reflète aucun régime réel. Avec
  ANALYZE, ces deux filtres tombent à 39/43 ms. La leçon (index seuls ≠ perf sans statistiques) est
  documentée dans le script et ici.
- **CI GitHub** : <URL PR / statut à compléter au push>.

## Décisions & conception

- **Cherche le catalogue, pas la collection.** Le constructeur propose toutes les cartes du jeu ;
  la collection ne sert qu'aux annotations `owned_count`/`in_deck_count`. C'est l'inverse de
  `v4-collection` (qui liste les exemplaires). L'isolation porte donc sur ces annotations
  (toujours `user.id`) et sur `deck_id` (propriété contrôlée → 404, jamais 403).
- **`deck_cards`/`collection_items` référencent le catalogue** (héritage `v7-decks-api`, D10) :
  la possession est un **compte**, pas une jointure d'appartenance — une Énergie de base est
  proposable sans être possédée.
- **Valeur = `card_value_rank`** (vue matérialisée `v4-ranking`), pas un calcul de prix par
  requête (« job lourd = job bridé »). Sur des cartes semées en test la vue n'est pas rafraîchie
  → `value_eur` NULL → le tri par valeur retombe sur `card_id` ; l'ORDRE réel par valeur est
  vérifié par le script de mesure (qui rafraîchit la vue).
- **Perf en SQL, pas en mémoire.** Contrairement à `v4-collection` (qui charge les ≤ 5 000
  exemplaires d'un utilisateur), la base est ici le catalogue entier : filtrage + tri + keyset
  poussés en SQL, index posés par la migration, jamais de chargement complet par requête. Curseur
  **keyset** (clé de tri + `card_id`, `null_rank` mettant les valeurs manquantes en dernier dans
  les deux sens) plutôt qu'OFFSET, qui relirait 20 000 lignes à la page 400.
- **Recherche accent-insensible indexée.** `unaccent(text)` n'est que STABLE (non indexable) ;
  `pbm_immutable_unaccent` fige le dictionnaire → IMMUTABLE → index trigram fonctionnel. La même
  expression est appliquée des deux côtés (colonne et motif) : correction garantie, index utilisé.

## Écarts au plan (signalés, pas tus)

- **Front reporté à `v7-decks-ui`.** La navigation clavier (mission point 3 : flèches / Entrée /
  Échap) et la conformité à la maquette (section 6, front) appartiennent au constructeur
  `v7-decks-ui` (couloir CH5), seul lot qui monte l'écran de recherche — il n'existe encore aucun
  écran de deck dans `apps/web`. La « définition de fini » (section 5) et la grille (`maquette`
  « sans objet : back-end ») cadrent ce lot en back-end ; la route est conçue pour l'ajout clavier
  (elle rend déjà `owned_count`/`in_deck_count`, aucun aller-retour de plus). Report explicite, pas
  un repli silencieux.
- **« Coût d'attaque » comme critère écarté.** Cité au contexte (Fonctionnalités), absent du point
  1 et de la définition de « fini ». Il porte sur `attacks` (JSONB) et exigerait un index dédié
  pour tenir les 150 ms — à traiter avec `v7-decks-ui` si le besoin se confirme, pas bricolé ici
  au prix de la cible de performance.
- **Tri par numéro = tri textuel** (`Card.number`, comme `v4-collection`), pas numérique
  (`TG05`/`SV107` n'ont pas d'ordre numérique unique).

## Reste à faire (autres lots)

- `v7-decks-ui` : l'écran de recherche/constructeur qui consomme ces routes (clavier, maquette).
- Éventuel filtre « coût d'attaque » avec son index si le produit le demande.
