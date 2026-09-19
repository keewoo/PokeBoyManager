# Compte rendu — `v0-schema`

Session autonome (`claude -p`) sur chimera, worktree `~/dev/wt-pbm-v0-schema`, branche
`roadmap/v0-schema`. Exécuté sous le régime décrit dans le CONTEXTE D'EXÉCUTION du prompt
(sections A/P/0/7 du prompt de lot remplacées) : pas de `suivi.py`, pas d'écriture dans
`etat.json`/`ROADMAP.html`/`BACKLOG.md`/`prompts/`, fusion directe vers `origin/main`
(dépôt relais local, pas GitHub).

## Résumé

Modèle de données PostgreSQL v1 posé via SQLAlchemy 2 (async) + une migration Alembic
initiale unique, jouée et vérifiée (upgrade / downgrade complet / upgrade) sur la base
dédiée `pbm_v0_schema` et sur `pbm_v0_schema_test`. Seed de démonstration idempotent.
Schéma documenté (Mermaid) dans `docs/ARCHITECTURE.md`. CI mise à jour pour jouer la
migration avant les tests de l'API.

## Livrables

- `apps/api/src/pbm_api/models/` — modèles SQLAlchemy 2 (`Mapped`/`mapped_column`) :
  `users`, `sessions`, `email_tokens`, `ai_credentials` (chiffrées : `encrypted_key` +
  `nonce` en `bytea`, `key_mask` affichable, **aucune colonne en clair**), `sets`, `cards`
  (+ `card_names` par langue), `card_prices_daily`, `card_insights`, `uploads`,
  `detections`, `collection_items`, `jobs`.
- `apps/api/migrations/` — Alembic (template async), `env.py` branché sur
  `pbm_api.config.settings.database_url` (pas de doublon d'URL en dur dans `alembic.ini`).
  Migration unique `5e0d551b788e_initial_schema.py` : crée les 13 tables, les contraintes
  (FK avec `ondelete` explicite, `UNIQUE`), les index (trigram GIN sur `cards.name` et
  `card_names.name`, `(set_id, number)`, `(card_id, day)`, `user_id` sur toutes les tables
  utilisateur), et les extensions `pg_trgm`/`unaccent` (`CREATE EXTENSION IF NOT EXISTS`,
  donc indépendant du script d'init docker-compose — portable en CI). `downgrade()` étendu
  pour aussi supprimer les types ENUM Postgres (l'autogénération Alembic ne le fait pas).
- `apps/api/src/pbm_api/seed.py` — un utilisateur (`demo@pokeboymanager.local`), trois
  extensions (`sv01`, `sv03pt5`, `swsh07`), neuf cartes avec noms FR/EN. Idempotent (upsert
  par clé naturelle), aucune clé IA.
- `apps/api/src/pbm_api/db.py` — moteur async + fabrique de sessions (`async_sessionmaker`).
- `docs/ARCHITECTURE.md` — diagramme Mermaid mis à jour (`email_tokens`, `jobs` ajoutés,
  cardinalités optionnelles corrigées) + pointeurs vers la migration/les modèles/le seed.
- `.github/workflows/ci.yml` — job `api` : ajout d'une étape `uv run alembic upgrade head`
  avant `pytest`, `TEST_DATABASE_URL`/`TZ=Europe/Paris` ajoutés à l'environnement du job.
- `apps/api/pyproject.toml` — dépendances ajoutées : `sqlalchemy`, `alembic`, `asyncpg`,
  `greenlet` ; `uv.lock` régénéré ; `extend-exclude = ["migrations/versions"]` pour ruff
  (fichiers autogénérés par Alembic, non réécrits à la main hormis les deux ajouts documentés
  ci-dessous).
- Bases dédiées créées sur l'infra partagée `pbm-shared` : `pbm_v0_schema` (dev, seedée) et
  `pbm_v0_schema_test` (tests, migrée). `pbm_api.config.Settings` pointe `pbm_v0_schema` /
  bucket `pbm-v0-schema` / préfixe Redis `pbm:v0-schema:` par défaut.

## Preuves (commandes lancées, résultats chiffrés)

```
$ cd apps/api && uv run alembic upgrade head      (sur pbm_v0_schema et pbm_v0_schema_test)
Running upgrade  -> 5e0d551b788e, initial schema

$ uv run alembic check
No new upgrade operations detected.   (modèles == schéma en base, aucun écart)

$ uv run alembic downgrade base   puis   upgrade head   (cycle complet, base pbm_v0_schema)
Running downgrade 5e0d551b788e -> , initial schema
Running upgrade  -> 5e0d551b788e, initial schema
$ psql … "SELECT typname FROM pg_type WHERE typname IN (...)"   → 0 ligne après downgrade
   (les 7 types ENUM sont bien supprimés, pas de résidu)

$ uv run python -m pbm_api.seed   (deux exécutions successives)
$ psql … "SELECT count(*) FROM users/sets/cards/card_names"
1|3|9|18   puis   1|3|9|18   (inchangé : idempotent)

$ TZ=Europe/Paris uv run pytest -q
10 passed in 0.71s-0.94s

$ uv run ruff check .
All checks passed!
```

Preuve « un test échoue sans le changement, passe avec » (§6) — la migration a été annulée
(`alembic downgrade base`) sur `pbm_v0_schema_test`, puis la suite relancée :

```
7 failed, 1 passed in 1.23s
  FAILED test_schema.py::test_all_expected_tables_exist
  FAILED test_schema.py::test_trigram_indexes_exist
  FAILED test_schema.py::test_set_number_and_card_day_indexes_exist
  FAILED test_schema.py::test_card_prices_daily_unique_constraint_enforced
  FAILED test_schema.py::test_user_id_columns_are_foreign_keys_with_index
  FAILED test_schema.py::test_delete_user_cascades_to_collection_items
  FAILED test_cross_user_isolation.py::test_collection_query_scoped_by_user_id_excludes_other_users
  (UndefinedTableError: relation "sets" does not exist)
```

puis `alembic upgrade head` → `10 passed`. Le seul test qui reste vert sans la migration
(`test_ai_credentials_never_store_plaintext_key`) est une assertion sur les colonnes du
modèle Python, indépendante de la base — cohérent, pas un défaut du test.

Simulation du job CI en local (une seule base `pbm_test`, comme le service Postgres GitHub
Actions, sans script d'init docker-compose) :

```
$ createdb pbm_test   puis   DATABASE_URL=…/pbm_test TEST_DATABASE_URL=…/pbm_test \
    uv run alembic upgrade head && uv run pytest -q
Running upgrade  -> 5e0d551b788e, initial schema
10 passed in 0.70s
```
→ confirme que `CREATE EXTENSION IF NOT EXISTS pg_trgm/unaccent` embarqué dans la migration
suffit ; la base pbm_test de simulation a été supprimée après ce test (`DROP DATABASE`).

Aucun secret : aucune clé IA réelle utilisée (seed n'en dépose aucune) ; `ai_credentials` ne
possède aucune colonne texte en clair (vérifié par `test_ai_credentials_never_store_plaintext_key`) ;
recherche de motifs de clé (`sk-ant`, `sk-proj`, `AKIA`, `BEGIN … PRIVATE KEY`) sur les fichiers
ajoutés → aucun résultat.

## Choix techniques faits (autonomes, dans le cadre de `docs/ARCHITECTURE.md`)

- **UUID générés côté Python** (`default=uuid.uuid4`) plutôt que `gen_random_uuid()` côté
  Postgres : évite une dépendance à l'extension `pgcrypto`, cohérent avec un id disponible
  avant le `flush()` (utile pour lier `card` → `card_names` dans le même `commit`).
- **Alembic en mode async** (template `-t async`, `env.py` utilise `async_engine_from_config`
  + `run_sync`) : cohérent avec le reste de l'API (SQLAlchemy 2 async, `asyncpg`) — pas de
  driver de migration séparé (`psycopg2`) à maintenir.
- **`PRICE_VARIANT_ENUM` factorisé en instance partagée** (`catalog.py`) réutilisée par
  `card_prices_daily` et `collection_items` : évite une double définition du type Postgres
  `price_variant` (vérifié sans erreur à l'autogénération et au `upgrade`/`downgrade`).
- **Enums Python en `enum.StrEnum`** (recommandation ruff `UP042`, Python 3.12) plutôt que
  `class X(str, enum.Enum)`.
- **`collection_items.card_id` en `ON DELETE RESTRICT`** (pas `CASCADE`) : une carte du
  catalogue partagé ne doit jamais disparaître silencieusement à cause d'un exemplaire
  utilisateur ; toutes les autres FK vers `users`/`uploads`/`cards` (côté 1) utilisent
  `CASCADE` ou `SET NULL` selon que la ligne dépendante a un sens sans son parent.
- **`downgrade()` étendu à la main** pour supprimer les 7 types ENUM Postgres : Alembic ne
  génère pas ce nettoyage automatiquement, laissant des types orphelins après un
  downgrade — vérifié avant/après (0 type résiduel).
- **Extensions créées dans la migration** (`op.execute('CREATE EXTENSION IF NOT EXISTS …')`)
  en plus du script `infra/postgres/init/01-extensions.sql` : la CI GitHub Actions utilise un
  service Postgres nu (pas de script d'init monté), donc la migration doit être autonome.
- **`ruff` : `migrations/versions` exclu** du lint (code autogénéré par Alembic, seules deux
  lignes y ont été ajoutées à la main — les `CREATE EXTENSION` et le nettoyage des ENUM au
  downgrade) ; le reste du code (modèles, seed, tests, `env.py`) est conforme (`ruff check`
  et `ruff format` appliqués).
- **Test d'accès croisé adapté au niveau données** (voir écart ci-dessous) plutôt qu'au
  niveau HTTP, ce lot ne posant aucune route.

## Écarts au plan

- **§6 « test d'accès croisé » adapté** : ce lot ne crée aucune route HTTP (pas encore
  d'authentification ni d'API de collection — prévu par `v1-auth` et les lots suivants).
  L'équivalent livré (`test_collection_query_scoped_by_user_id_excludes_other_users`) vérifie
  au niveau données qu'une requête filtrée par `user_id` n'expose jamais l'exemplaire d'un
  autre utilisateur. Le vrai test HTTP (404 sur `/api/collection/{id}` pour l'utilisateur B)
  revient au lot qui posera les routes de collection.
- **§6 « Front → conformité à la maquette »** : sans objet, confirmé par la grille de
  clôture du prompt (« sans objet : schéma ») — ce lot ne touche pas `apps/web`.
- **`fleet-run` non utilisé** : conformément au CONTEXTE D'EXÉCUTION, les suites tournent
  « ici même sur chimera ».
- **Aucune clé IA réelle utilisée** (conforme aux consignes) : le seed ne dépose aucune
  ligne dans `ai_credentials` — aucun script d'essai manuel n'était pertinent pour ce lot
  (il le sera pour le lot qui posera le chiffrement AES-256-GCM et l'appel réel aux
  fournisseurs).
- **CI non exécutée sur GitHub** : la mise à jour de `.github/workflows/ci.yml` a été
  validée par une simulation locale équivalente (base Postgres nue, mêmes variables
  d'environnement) ; le pilote la déclenchera au push vers GitHub.

## Reste à faire (pour les lots suivants)

- Authentification (hash du mot de passe, sessions, `email_tokens`) — table posée, logique
  applicative à écrire (`v1-auth` probable).
- Chiffrement AES-256-GCM réel des clés IA (`ai_credentials.encrypted_key`/`nonce`) — colonnes
  posées, service de chiffrement/déchiffrement et clé maître hors base à écrire.
- Import réel du catalogue (TCGdex / Pokémon TCG API) pour remplacer le seed de démonstration.
- Premières routes API (auth, collection) et donc premier test d'accès croisé HTTP réel.
- Worker arq consommant la table `jobs`.

## Décisions provisoires utilisées

D3 (sources de prix gratuites + historique par relevés propres — reflété dans
`card_prices_daily`), D4 (pas de clé IA disponible — `ai_credentials` posée mais vide, seed
sans clé), D5 (SMTP configurable — `email_tokens` prêt pour les envois de vérification/reset),
D6 (les trois classements — `card_prices_daily.source` distingue Cardmarket/TCGplayer), D7
(stockage S3 compatible, conservation jusqu'à suppression — `uploads`/`collection_items`
stockent des `s3_key`, pas de TTL automatique). D2/D8 hors périmètre, confirmé (aucun
déploiement, aucune tâche `release_uat`/`release_prod` traitée).
