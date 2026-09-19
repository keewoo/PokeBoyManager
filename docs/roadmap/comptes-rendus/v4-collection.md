# Compte rendu — `v4-collection`

Session autonome (`claude -p`) sur chimera, worktree `~/dev/wt-pbm-v4-collection`, branche
`roadmap/v4-collection`. Exécuté sous le régime décrit dans le CONTEXTE D'EXÉCUTION du prompt
(sections A/P/0/7 du prompt de lot remplacées) : pas de `suivi.py`, pas d'écriture dans
`etat.json`/`ROADMAP.html`/`BACKLOG.md`/`prompts/`, fusion directe vers `origin/main` (dépôt
relais local, pas GitHub).

## Résumé

Page collection : grille filtrable/triable/paginée avec agrégats de valeur, ajout manuel d'une
carte sans photo, mesure de performance à 5 000 exemplaires. `GET /me/collection` (filtres
extension/série/rareté/type/langue/variante/état/valeur min-max/date d'ajout/doublons/
contrefaçons, tri, pagination par curseur, agrégats — nombre, valeur totale, variation 7/30 j) ;
`GET /me/collection/facets` (valeurs de filtre disponibles, scopées à l'utilisateur) ; `POST
/me/collection` (ajout manuel, recherche catalogue) ; `PATCH`/`DELETE /me/collection/{item}`.
Front `/collection` : panneau de filtres (tiroir sur mobile), recherche + tri, grille de cartes,
pagination « Charger plus », état dans l'URL (partageable, retour arrière fonctionnel).

Risque nommé par la mission — 5 000 exemplaires en moins de 300 ms — confirmé réel en mesurant :
la première version (une requête de prix par exemplaire, héritée du lot `v4-ranking`) répondait
en ~500 ms. Deux optimisations mesurées ramènent la médiane à ~230-265 ms (voir « Choix
techniques »).

## Livrables

- `apps/api/src/pbm_api/collection/` (nouveau module) :
  - `service.py` — `list_collection` (filtres SQL bon marché + valorisation en masse + tri/
    pagination en mémoire), `get_facets`, `create_manual_items`, `update_item`, `delete_item`.
  - `schemas.py` — `CollectionListItem/Aggregates/Response`, `CollectionFacets`,
    `Create/UpdateCollectionItemRequest`.
  - `errors.py` — `CollectionItemNotFoundError` (jamais un 403 : pas de fuite d'existence).
- `apps/api/src/pbm_api/routers/collection.py` — étendu : `GET`/`POST /me/collection`, `GET
  /me/collection/facets`, `PATCH`/`DELETE /me/collection/{item_id}` ; route de détail existante
  (`GET /me/collection/{item_id}`, lot `v4-ranking`) inchangée.
- `apps/api/src/pbm_api/pricing/valuation.py` — `bulk_item_values`, `bulk_item_values_multi`,
  `bulk_reference_prices_eur[_multi]`, `_bulk_latest_prices[_multi]` (voir « Choix
  techniques ») ; `collection_value` corrigé pour utiliser `bulk_item_values` (même N+1 que
  celui visé par ce lot, présent depuis `v2-prix`).
- `apps/api/scripts/measure_collection_performance.py` — sème 5 000 exemplaires (50 extensions
  × 100 cartes, 80 % valorisées) et mesure `GET /me/collection` en conditions HTTP réelles
  (`ASGITransport`) sur 5 scénarios, transaction annulée en fin de script.
- `apps/api/tests/test_collection_routes.py` (nouveau, 19 tests) — voir « Tests ».
- `apps/web/src/lib/api/collection.ts` — client HTTP typé (liste, facettes, création,
  suppression).
- `apps/web/src/app/collection/` :
  - `page.tsx` — `Suspense` (requis par `useSearchParams` côté client, Next 15).
  - `collection-view.tsx` — état/filtres/tri/pagination synchronisés avec l'URL, agrégats,
    grille, tiroir de filtres mobile.
  - `collection-filters.tsx` — panneau de filtres (checkboxes par facette, plage de valeur,
    plage de dates, doublons/contrefaçons).
  - `manual-add-form.tsx` — recherche catalogue (réutilise `searchCatalog`, `v2-recherche`),
    langue/variante/quantité/état/prix d'achat.
- `apps/web/src/__tests__/collection-view.test.tsx` (nouveau, 5 tests) — voir « Tests ».
- `docs/roadmap/comptes-rendus/captures/v4-collection-{grille,filtree,ajout-manuel}.png` —
  captures réelles (navigateur, pas la maquette JS), voir « Conformité à la maquette ».
- Base/préfixe dédiés créés sur `pbm-shared` : `pbm_v4_collection` (dev), `pbm_v4_collection_test`
  (tests) — pas de bucket S3 ni de préfixe Redis nécessaires (ce lot n'ajoute ni stockage ni
  file). `apps/api/.env` non versionné.

## Tests

```
$ cd apps/api && uv run ruff check .
All checks passed!

$ TZ=Europe/Paris TEST_DATABASE_URL=postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v4_collection_test \
  uv run pytest -q
459 passed, 2 failed in ~70s
```

Les 2 échecs (`tests/test_catalogue_seed.py::test_seed_export_then_restore_into_empty_database`
et `::test_seed_import_is_idempotent`) sont **préexistants, sans rapport avec ce lot** :
`pg_dump: command not found` — le client PostgreSQL n'est pas installé sur chimera (seul le
serveur, dans le conteneur Docker partagé, l'est). Déjà documenté par `v3-validation` (son
compte rendu) et `v2-catalogue-complet` ; vérifié que le décompte de préexistants (440, mesuré
avant tout changement de ce lot) plus les 19 nouveaux (`test_collection_routes.py`) correspond
bien à 459. Sans effet attendu en CI GitHub Actions (`ubuntu-latest` fournit `pg_dump`).

- `tests/test_collection_routes.py` (19 tests, nouveaux) — **échouent tous sans ce lot** (`GET
  /me/collection` en liste, `/facets`, `POST`, `PATCH`, `DELETE` n'existaient pas) et passent une
  fois branchés :
  - Liste : items + valeur + agrégats ; **variation 30 j en pourcentage** (50 % pour 20→30 €,
    jamais un pourcentage inventé) ; filtres langue/variante, plage de valeur, recherche sur le
    nom localisé (`CardName`), tri par défaut (valeur décroissante), pagination par curseur
    (page de 2 puis 1, aucun doublon/oubli entre les deux pages), doublons, contrefaçons (valeur
    neutralisée à `0`).
  - **Test d'accès croisé** (mission section 6) : la collection de B n'apparaît jamais dans la
    liste de A (`test_list_collection_is_isolated_by_user`) ; `PATCH`/`DELETE` sur l'exemplaire
    d'un autre utilisateur → 404, jamais 403 (pas de fuite d'existence).
  - Facettes scopées à l'utilisateur (celles de B n'apparaissent pas chez A).
  - Ajout manuel : quantité multiple, CSRF obligatoire (403 sans jeton), 404 sur `card_id`
    inconnu.
  - `PATCH` partiel : seuls les champs envoyés changent (`exclude_unset`).
- `pricing/valuation.py` : tests existants (`test_valuation.py`, `test_ranking.py`) toujours
  verts après le passage de `collection_value` sur `bulk_item_values` — non-régression du calcul
  de valeur (même résultat, juste moins de requêtes SQL).

### Test de charge (mission point 4)

```
$ cd apps/api && TZ=Europe/Paris uv run python scripts/measure_collection_performance.py
Semis de 5000 exemplaires...
  défaut (tri valeur, page 1): {min_ms: 232.9, median_ms: 264.2, max_ms: 299.1, mean_ms: 265.6}
  recherche:                   {min_ms: 29.6,  median_ms: 31.7,  max_ms: 73.8,  mean_ms: 36.1}
  filtre valeur min:           {min_ms: 229.9, median_ms: 236.2, max_ms: 276.5, mean_ms: 246.5}
  tri date d'ajout:            {min_ms: 226.4, median_ms: 235.9, max_ms: 273.4, mean_ms: 245.0}
  tri variation 30 j:          {min_ms: 223.8, median_ms: 232.4, max_ms: 272.3, mean_ms: 243.1}
Objectif tenu : médiane sous 300 ms pour tous les scénarios.
```

Objectif jugé sur la **médiane de 9 requêtes**, pas le maximum d'un échantillon aussi petit :
chimera est une machine partagée avec d'autres lots en cours (`~/.claude/CLAUDE.md`), un pic
isolé (jusqu'à ~300 ms observé une fois sur 9) reflète la contention de la machine à l'instant T,
pas le temps de réponse réel du chemin de code — mesuré en le reproduisant plusieurs fois de
suite (médiane stable entre 230 et 265 ms à chaque run). Le script imprime aussi min/mean/max
pour ne rien cacher ; reproductible avec `uv run python
scripts/measure_collection_performance.py` depuis `apps/api`.

```
$ pnpm --filter @pbm/web lint && pnpm --filter @pbm/web type-check && pnpm --filter @pbm/web build
✓ eslint . (aucune erreur)
✓ tsc --noEmit (aucune erreur)
✓ next build — /collection généré (route statique, 5,25 kB)

$ pnpm --filter @pbm/web test
70 passed   # 65 préexistants + 5 nouveaux (collection-view.test.tsx)
```

- `collection-view.test.tsx` (5 tests, nouveaux) — affiche cartes/valeur/filtres depuis les
  facettes ; état vide dédié (collection réellement vide) distinct du message « aucune carte ne
  correspond à ces filtres » (filtre actif, ensemble vide) ; coche un filtre de rareté → l'URL
  reçoit `?rarity=rare` ; « Charger plus » ajoute la page suivante sans dupliquer/perdre
  d'exemplaire.
  - Piège rencontré en écrivant ce test : le mock usuel `useSearchParams: () =>
    new URLSearchParams(searchParamsValue)` (repris de `connexion.test.tsx`) reconstruit un
    objet à *chaque rendu* — le vrai `useSearchParams` de Next.js renvoie une référence stable
    tant que l'URL ne change pas réellement. `CollectionView` s'appuie sur cette stabilité
    (`useMemo`/`useEffect` sur `searchParams`) : le mock non stable provoquait une boucle de
    rendu propre au test (le composant refetchait à l'infini, jamais stable le temps qu'un
    `findByText` le capture). Corrigé en mettant en cache l'instance tant que la valeur de test
    ne change pas — **aucun changement côté code applicatif**, uniquement le double de test.

### Conformité à la maquette (mission section 6)

Pas de Playwright ici (voir « Écarts au plan ») : conformité vérifiée avec un navigateur réel
(Chromium headless via Playwright, pas la maquette JS de `ROADMAP.html`) contre les serveurs de
développement réels (API + Postgres/Redis/MinIO/Mailpit partagés), session authentifiée par
inscription/vérification/connexion réelles, collection semée à la main (5 cartes variées + 1
doublon), captures dans `docs/roadmap/comptes-rendus/captures/` :

- `v4-collection-grille.png` — grille par défaut : en-tête (nombre de cartes, valeur totale,
  variations 7/30 j), boutons « Ajouter une carte »/« Ajouter des photos », panneau de filtres
  complet (Extension/Série/Rareté/Type/Langue/Variante/État estimé/Valeur/Date d'ajout/Autres),
  barre recherche + tri, tuiles carte (image/nom/extension·numéro/valeur/badge doublon).
- `v4-collection-filtree.png` — coche « rare » : 3 cartes sur 7, agrégats recalculés, la case
  reste cochée. URL passée à `router.replace("/collection?rarity=rare")`, vérifiée.
- `v4-collection-ajout-manuel.png` — recherche « Dracaufeu » → candidat catalogue trouvé →
  ajout → grille passée de 7 à 8 cartes, valeur totale mise à jour (322,95 €), nouvelle carte
  correctement signalée « doublon » (deuxième Dracaufeu ex de la collection).

Les images des cartes n'apparaissent pas dans les captures (icône d'image cassée) : `GET
/img/cards/{id}` (lot `v1-byok`/`images`, hors périmètre de ce lot) ne pose pas d'en-tête
`Cross-Origin-Resource-Policy`, ce que ce Chromium précis bloque en `ERR_BLOCKED_BY_ORB` pour une
image chargée depuis une autre origine (`localhost:3000` → `localhost:8000`). Préexistant et
partagé par tout le site (même endpoint déjà utilisé par `/ajouter/validation`), pas introduit
ici — signalé pour le lot propriétaire de `routers/images.py`.

Aucun secret dans le dépôt, les journaux ou les sorties : aucune clé IA impliquée dans ce lot ;
`apps/api/.env` (base dédiée) non versionné ; l'utilisateur et les cartes de démonstration créés
pour les captures vivent uniquement dans `pbm_v4_collection` (base de dev, pas la base de test),
jamais commités.

## Choix techniques faits (autonomes, dans le cadre de `docs/ARCHITECTURE.md`)

- **Performance à 5 000 exemplaires — deux optimisations mesurées, dans cet ordre** :
  1. Colonnes explicites plutôt que les entités ORM `Card`/`Set` complètes dans la requête
     principale de `list_collection` : `Card` porte plusieurs colonnes JSONB (attaques,
     capacités, faiblesses, résistances, variantes) inutiles à une grille et coûteuses à décoder
     à 5 000 lignes. Mesuré : requête principale ramenée de ~170-230 ms à ~20-30 ms sur le jeu de
     5 000 (voir historique de mesures dans les commits).
  2. `bulk_item_values`/`bulk_reference_prices_eur` (une poignée de requêtes de prix au total,
     jamais une par exemplaire — c'était le N+1 d'origine, hérité de `v4-ranking` et présent
     aussi dans `collection_value`), puis fusion cardmarket+tcgplayer en une seule requête
     `DISTINCT ON` (colonnes explicites, pas l'entité `CardPriceDaily`), puis fusion des 3
     fenêtres de date (aujourd'hui/-7 j/-30 j, nécessaires aux agrégats + au tri par variation)
     en une seule requête `UNION ALL` de sous-requêtes `DISTINCT ON` (`bulk_item_values_multi`) —
     un aller-retour SQL de prix au lieu de six. Mesuré : ~500 ms → ~230-265 ms (médiane) sur le
     jeu de 5 000.
  - Reste un choix assumé plutôt qu'une optimisation supplémentaire : le filtre de valeur
    (`value_min`/`value_max`), le tri et la pagination s'appliquent **en mémoire**, après avoir
    chargé en une requête tout le sous-ensemble filtré par les critères « bon marché » (catalogue,
    langue, variante, état, dates). La valeur d'un exemplaire n'est stockée nulle part (calculée
    à la demande, comme `item_value`) : il n'existe pas de colonne SQL sur laquelle trier/filtrer
    par valeur sans la recalculer d'une façon ou d'une autre. À l'échelle visée par la mission
    (5 000), c'est plus simple et plus rapide qu'une matérialisation ; documenté comme risque
    « à surveiller au-delà » en « Reste à faire », pas résolu par prudence prématurée.
- **`value_change_30d_pct` ajouté à `CollectionListItem`** (en plus de `value_change_30d_eur`,
  déjà exposé) : la maquette n'affiche la variation qu'en pourcentage (fonction `delta()` de
  `ROADMAP.html`) et le composant partagé `apps/web/src/components/value-delta.tsx` (posé par le
  lot design-system, jusqu'ici utilisé seulement dans la page `/design`) attend un nombre. Calculé
  côté serveur (`None` si la valeur de référence 30 j est inconnue ou nulle — jamais un
  pourcentage inventé), pour ne pas dupliquer ce calcul côté client ni risquer un écart
  d'arrondi entre front et back.
- **`rarity-badge.tsx`/`condition-badge.tsx` (même lot design-system) délibérément NON
  réutilisés dans la grille.** Leurs types (`RarityTier` : 6 valeurs kebab-case françaises ;
  `ConditionGrade` : 6 valeurs) sont un taxonomie fixe, non nulle, pensée pour la maquette — le
  catalogue réel (TCGdex, `Card.rarity`) porte des dizaines de libellés distincts selon
  l'extension et l'ère (« Rare Holo », « Illustration Rare », « Hyper Rare », etc., texte libre
  non normalisé) et `condition_grade` suit le barème de
  `pbm_api.pricing.valuation.CONDITION_MULTIPLIERS` (`mint`/`near_mint`/`excellent`/`good`/
  `light_played`/`played`/`poor`, `None` accepté). Aucune fonction de normalisation catalogue →
  taxonomie fixe n'existe dans le dépôt (`apps/web/src/app/design/page.tsx`, seul consommateur
  actuel, n'utilise que des données d'exemple câblées en dur). Inventer cette correspondance
  ici aurait été une décision de taxonomie hors du périmètre de ce lot, avec un risque réel
  d'afficher un libellé faux (ex. classer à tort une rareté récente en « secrète » ou une carte
  jouée en « mint »). La grille affiche donc `rarity`/`card_type`/`condition_grade` en texte
  brut (déjà filtrable/recherchable) plutôt que par ces badges ; `ValueDelta` (qui ne dépend
  d'aucune taxonomie, juste d'un nombre) reste réutilisé. Reporté en « Reste à faire ».
- **Curseur de pagination = id du dernier exemplaire de la page, pas un jeton composite.** Le
  jeu filtré est déjà chargé et trié en mémoire (choix ci-dessus) : retrouver la position du
  curseur, c'est chercher l'id dans la liste triée. Un exemplaire supprimé entre deux pages
  (curseur introuvable) redémarre silencieusement au début plutôt que d'échouer — dégradation
  documentée dans le code, jamais un 500 pour un cas aussi bénin.
- **Doublon = même `card_id`, toutes langues/variantes confondues**, calculé sur la collection
  entière de l'utilisateur (pas sur le sous-ensemble filtré) : correspond à la question qu'un
  collectionneur se pose (« j'ai déjà cette carte ? »), pas à une définition technique plus
  étroite (même langue+variante). Une requête `GROUP BY card_id HAVING COUNT(*) > 1` dédiée,
  jamais recalculée à partir du jeu déjà chargé (qui peut être un sous-ensemble filtré).
- **Aucune quantité sur `CollectionItem`** (cohérent avec le modèle posé par `v3-validation`) :
  l'ajout manuel de N exemplaires crée N lignes, comme `confirm_detection`. `PATCH` reste donc
  un exemplaire à la fois — pas de champ « quantité » à corriger après coup.
- **Facettes (`GET /me/collection/facets`) scopées à l'utilisateur, pas au catalogue entier** :
  une extension que l'utilisateur ne possède pas n'encombre pas son panneau de filtres. Coût
  d'une requête dédiée (`GROUP BY` implicite via `DISTINCT`-like en Python après un seul
  `SELECT`) acceptable : appelée une fois par ouverture de page, pas par requête de liste.
- **Devise fixée à EUR pour toute la liste et les agrégats** (pas de paramètre `currency`
  contrairement à `GET /me/collection/{item}`, qui l'exposait déjà) : simplification assumée —
  la maquette n'affiche que des €, et `User.preferred_currency` (lot `v2-prix`) n'est câblé nulle
  part côté affichage aujourd'hui. Signalé en « Reste à faire » plutôt que devinée.

## Écarts au plan

- **Pas de suite Playwright pour ce lot** (contrairement à `v3-validation`, qui en a une) :
  l'environnement Chromium de chimera reste cassé pour les lots qui n'ouvrent pas eux-mêmes une
  session interactive (`chrome-headless-shell` sans `libnspr4`/`libnss3`/`libasound2`, pas de
  `sudo` disponible). `v3-validation` avait déjà documenté et contourné ce point avec des `.deb`
  extraits sous `/tmp/pw-libs/extracted` (`LD_LIBRARY_PATH`) — **ce chemin `/tmp` a survécu** et a
  été réutilisé ici pour produire les 3 captures manuelles (voir « Conformité à la maquette »),
  mais aucune spec Playwright durable (`apps/web/e2e/*.spec.ts`) n'a été écrite : la preuve de
  conformité de ce lot est donc une capture ponctuelle plus les tests Vitest/pytest, pas un test
  e2e rejouable par la CI. Toujours pas corrigé à la racine (`sudo apt-get install -y libnspr4
  libnss3 libasound2`, hors de portée sans les droits qui manquent).
- **`value_change_30d_pct` ajouté après coup** (deuxième commit backend), pas dans la même passe
  que le reste de l'API : découvert en comparant la grille rendue à la maquette (celle-ci
  n'affiche qu'un pourcentage) après avoir déjà posé `value_change_30d_eur` seul — corrigé plutôt
  que laissé approximatif.

## Reste à faire (pour les lots suivants)

- Normaliser `Card.rarity`/`condition_grade` vers les taxonomies fixes de
  `rarity-badge.tsx`/`condition-badge.tsx` (design-system) si un lot futur (fiche carte,
  tableau de bord) veut réellement les utiliser — décision de taxonomie qui touche le catalogue
  entier, pas seulement la collection.
- Corriger l'environnement Playwright de chimera à la racine (`sudo apt-get install -y libnspr4
  libnss3 libasound2`) — déjà signalé par `v3-validation`, toujours vrai.
- `Cross-Origin-Resource-Policy` manquant sur `GET /img/cards/{id}` (`routers/images.py`) :
  bloque le chargement d'image par certains navigateurs/outils en cross-origin (`ERR_BLOCKED_BY_
  ORB`), visible sur mes captures et déjà latent sur `/ajouter/validation`. Hors périmètre de ce
  lot (pas le propriétaire du module images).
- Si la collection dépasse largement 5 000-10 000 exemplaires pour un même utilisateur, le choix
  assumé « filtre de valeur/tri/pagination en mémoire après un chargement complet » (voir « Choix
  techniques ») cessera d'être trivialement rapide — à surveiller, pas un problème mesuré
  aujourd'hui (mission bornée à 5 000).
- Paramètre `currency` non exposé sur `GET /me/collection` (contrairement à la route de détail
  existante) : à ajouter si `User.preferred_currency` devient un jour affiché ailleurs que dans
  les paramètres du compte.
- Aucune UI d'édition/suppression d'un exemplaire depuis la grille (l'API `PATCH`/`DELETE`
  existe et est testée, mais la maquette ne montre l'édition que sur la fiche carte — lot
  `v4-fiche`, pas encore construit, actuellement un état vide `EmptyState` sur `/carte/[id]`).
  Volontaire, pour rester conforme à la maquette plutôt que d'anticiper cet écran.

## Décisions provisoires utilisées

D7 (stockage S3 en dev) : sans objet, ce lot n'ajoute ni stockage ni fichier. D2/D8 hors
périmètre, confirmé (aucun déploiement, aucune tâche `release_uat`/`release_prod` traitée).
