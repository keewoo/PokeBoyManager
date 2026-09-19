# Compte rendu — `v0-monorepo`

Session autonome (`claude -p`) sur chimera, worktree `~/dev/wt-pbm-v0-monorepo`, branche
`roadmap/v0-monorepo`. Exécuté sous le régime décrit dans le CONTEXTE D'EXÉCUTION du prompt
(sections A/P/0/7 du prompt de lot remplacées) : pas de `suivi.py`, pas d'écriture dans
`etat.json`/`ROADMAP.html`/`BACKLOG.md`/`prompts/`, fusion directe vers `origin/main`
(dépôt relais local, pas GitHub).

## Résumé

Socle technique livré : monorepo pnpm + uv, `apps/web` (Next.js 15), `apps/api` (FastAPI,
`/health`), `docker-compose.yml` (Postgres 16, Redis 7, MinIO, Mailpit) avec les ports par
défaut de l'infra partagée `pbm-shared`, client TypeScript généré depuis l'OpenAPI
(`packages/api-client`), CI GitHub Actions (lint + tests web/api en parallèle), `CLAUDE.md`
racine mis à jour.

## Livrables

- `apps/web` — Next.js 15.5, React 19, TypeScript strict, Tailwind 4, ESLint (flat config),
  Vitest + Testing Library. Page d'accueil minimale (pas de maquette à ce stade — tâche
  `maquette` sans objet, socle technique).
- `apps/api` — FastAPI 0.141, Python 3.12 via uv, route `GET /health` → `{"status": "ok"}`,
  configuration par variables d'environnement (`pbm_api.config.Settings` : `DATABASE_URL`,
  `REDIS_URL`, `S3_*`, `SMTP_*`), ruff, pytest.
- `packages/api-client` — script `pnpm gen:api` : exporte l'OpenAPI de `apps/api` (sans lancer
  de serveur, via `app.openapi()`) puis génère `src/schema.d.ts` avec `openapi-typescript`.
  Schéma généré et commité (régénérer après tout changement de route API).
- `docker-compose.yml` + `.env.example` — Postgres 16 (`pg_trgm`, `unaccent` via
  `infra/postgres/init/01-extensions.sql`), Redis 7, MinIO (image `quay.io/minio/minio` —
  voir écart ci-dessous), Mailpit. Ports par défaut = ceux de l'infra partagée
  (55432/56379/59000/59001/51025/58025), surchargeables par variables d'environnement.
- `.github/workflows/ci.yml` — deux jobs parallèles (`web`, `api`), services Postgres/Redis
  pour le job `api`, badge ajouté au `README.md`.
- `CLAUDE.md` racine — structure du monorepo, commandes, variables d'environnement, rappel
  des règles de flotte.

## Preuves (commandes lancées, résultats)

```
$ cd apps/api && uv run ruff check .
All checks passed!

$ cd apps/api && uv run pytest -q
2 passed in 0.25-0.27s

$ pnpm --filter @pbm/web lint
$ eslint .          (exit 0, aucune sortie)

$ pnpm --filter @pbm/web type-check
$ tsc --noEmit      (exit 0, aucune sortie)

$ pnpm --filter @pbm/web test
✓ src/__tests__/config.test.ts (2 tests)
Test Files  1 passed (1) · Tests  2 passed (2)

$ pnpm --filter @pbm/web build
✓ Compiled successfully · Route / → 123 B, First Load JS 102 kB (build de prod complet)
```

Preuve « le test échoue sans le changement, passe avec » (§6) — capturée par mutation
temporaire puis restauration, sur les deux piles :

- web : `getApiBaseUrl()` — la valeur de repli changée de `http://localhost:8000` à
  `http://localhost:9999` fait échouer `src/__tests__/config.test.ts` avec
  `Expected: "http://localhost:8000" / Received: "http://localhost:9999"` ; restaurée, la
  suite repasse au vert (2 passed).
- api : `HealthResponse(status="ok")` changé en `status="broken"` fait échouer
  `tests/test_health.py::test_health_returns_ok` avec
  `AssertionError: assert {'status': 'broken'} == {'status': 'ok'}` ; restauré, `2 passed`.

Stack Docker validée en conditions réelles (`docker compose -p pbm-mono up -d`, ports par
défaut, puis `down -v`) :

```
$ docker compose -p pbm-mono ps
pbm-mono-mailpit-1    healthy   0.0.0.0:51025->1025, 0.0.0.0:58025->8025
pbm-mono-minio-1      healthy   0.0.0.0:59000->9000, 0.0.0.0:59001->9001
pbm-mono-postgres-1   healthy   0.0.0.0:55432->5432
pbm-mono-redis-1      healthy   0.0.0.0:56379->6379

$ docker compose -p pbm-mono exec -T postgres psql -U pbm -d pbm -c "\dx"
pg_trgm, unaccent, plpgsql  (3 rows)

$ docker compose -p pbm-mono exec -T redis redis-cli ping
PONG

$ curl -sf http://localhost:59000/minio/health/live -w "%{http_code}"
200

$ curl -sf http://localhost:58025/api/v1/info -w "%{http_code}"
200

$ uv run uvicorn pbm_api.main:app --port 18000 &  puis  curl -sf http://localhost:18000/health
{"status":"ok"}  status:200
```

Aucun secret dans le dépôt : `git ls-files | grep -E '^\.env$'` → vide ; recherche de motifs
de clé (`sk-ant`, `sk-proj`, `AKIA`, `BEGIN … PRIVATE KEY`) sur `apps/`, `packages/`,
`docker-compose.yml`, `.env.example` → aucun résultat.

## Choix techniques faits (autonomes, dans le cadre de `docs/ARCHITECTURE.md`)

- **`apps/web` scaffoldé à la main** plutôt que via `create-next-app` (pas d'invite
  interactive possible en session `-p` ; contrôle exact des versions et du contenu).
- **`apps/api` sans SQLAlchemy/Alembic/asyncpg** à ce stade : le modèle de données est le
  périmètre du lot `v0-schema` (aucune dépendance déclarée ici, `docs/roadmap/roadmap.json`
  confirme que `v0-schema` est un lot distinct). `Settings.database_url` est prête (format
  `postgresql+asyncpg://…`) pour que ce lot n'ait qu'à ajouter les paquets et le moteur.
- **Image MinIO `quay.io/minio/minio`** au lieu de `minio/minio` (Docker Hub) : le pull de
  `minio/minio:latest` échoue avec *pull access denied* (image retirée/restreinte côté
  Docker Hub) ; `quay.io/minio/minio:latest` est le miroir officiel qui fonctionne, vérifié
  ci-dessus (conteneur `healthy`).
- **`packages/api-client` génère le schéma sans serveur HTTP** (`app.openapi()` exporté
  directement par un script Python) plutôt que de dépendre d'un `apps/api` démarré : plus
  fiable en CI et en local, aucune dépendance réseau.
- **Client généré commité** (`packages/api-client/src/schema.d.ts`), pas seulement généré à
  la volée : les lots suivants (front) peuvent l'importer immédiatement ; `pnpm gen:api` est
  à relancer après tout changement de route API (documenté dans `CLAUDE.md`).
- **`allowBuilds` dans `pnpm-workspace.yaml`** (`esbuild`, `unrs-resolver` → `true`) : pnpm
  12 bloque par défaut les scripts postinstall des dépendances tierces ; ces deux paquets
  sont des outils de build standard (esbuild pour Vite/Vitest, unrs-resolver pour la
  résolution TypeScript d'ESLint), approuvés explicitement plutôt qu'ignorés en silence.

## Écarts au plan

- **Tâche `maquette` non traitée** : sans objet pour ce lot (socle technique, aucune page
  fonctionnelle) — cohérent avec la grille de clôture du prompt qui la marque déjà « sans
  objet » pour `v0-monorepo`.
- **Test d'accès croisé (§6) non applicable** : aucune route utilisateur, aucune session,
  aucun modèle de données dans ce lot (`GET /health` est public, sans `user_id`). Le test
  d'accès croisé s'appliquera aux premières routes authentifiées (`v1-auth` et suivants).
- **`fleet-run` non utilisé** : conformément au CONTEXTE D'EXÉCUTION, les suites tournent
  « ici même sur chimera » — c'est ce qui a été fait (pas de délégation à `fleet-run`).
- **Aucune clé IA réelle utilisée** (conforme aux consignes) : rien dans ce lot n'appelle un
  fournisseur IA, donc aucun script d'essai manuel à prévoir ici (sera pertinent à partir de
  `v3-ia-providers`).

## Reste à faire (pour les lots suivants)

- Modèle de données PostgreSQL + Alembic (`v0-schema`).
- Design system / squelette de pages conforme à la maquette (`v0-design-system`).
- Authentification, sessions, premier `user_id` et donc premier test d'accès croisé réel
  (`v1-auth`).
- Brancher `packages/api-client` dans `apps/web` une fois qu'il y a des appels API réels à
  typer côté front.
- CI GitHub Actions écrite et validée localement (syntaxe YAML vérifiée) mais **pas encore
  exécutée sur GitHub** — le pilote la déclenchera au push vers GitHub, conformément au
  CONTEXTE D'EXÉCUTION (« elle tournera quand le pilote poussera »).

## Décisions provisoires utilisées

D1 (stack), D3, D4, D5, D6, D7 — telles que rappelées dans le CONTEXTE D'EXÉCUTION du prompt.
Aucune décision supplémentaire nécessaire pour ce lot (D2/D8 hors périmètre, confirmé).
