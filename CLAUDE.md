# CLAUDE.md — PokeBoyManager

## Ce qu'est le projet
Espace privé (compte e-mail + mot de passe) : photos de cartes Pokémon → reconnaissance par l'IA
**de l'utilisateur** (clé Claude, Gemini ou OpenAI déposée dans son profil) → collection filtrable,
valeur dans le temps, fiche carte (image officielle, état estimé, anecdotes sourcées, étude en jeu).

## Le plan fait foi
- `docs/roadmap/roadmap.json` : le plan (lots, dépendances, décisions). Seule source.
- `docs/roadmap/etat.json` : l'état réel, écrit **uniquement** par `docs/roadmap/suivi.py`.
- `BACKLOG.md`, `prompts/*.md`, `docs/roadmap/ROADMAP.html` sont **générés** (`python3 docs/roadmap/suivi.py build`) — ne jamais les éditer à la main.
- Chaque lot démarre par `suivi.py verifier <id>` : code 2 = ordre non tenu → on s'arrête et on demande à JF.

## Règles
- Un lot = un worktree `../wt-<id>`, une branche `roadmap/<id>`, une PR. Jamais `git stash`, jamais `git add -A`.
- Python **3.12** (`UV_PYTHON=3.12`), Node 24. La CI GitHub Actions fait foi.
- Toute route utilisateur filtre par `user_id` issu de la session ; test d'accès croisé obligatoire.
- Les clés IA ne sont **jamais** renvoyées, journalisées ni écrites en clair (chiffrement AES-256-GCM, clé maître hors base).
- Aucun secret dans le dépôt (`.env` ignoré, `.env.example` sans valeur réelle).
- Le front reproduit la maquette (onglet « Maquette du site » de `ROADMAP.html`) ; identité propre, pas de logo officiel Pokémon.
- Construire sur chimera, déployer par devAI ; jamais de build ni de déploiement depuis le Mac de JF.
- Un repli silencieux (`|| true`, `except: pass`, `2>/dev/null` sur un chemin nominal) est interdit : un relevé de prix vide ou un lot sans compte rendu est une panne.

## Monorepo — structure et commandes

```
apps/web            Next.js 15 (App Router), TypeScript strict, Tailwind 4, ESLint, Vitest
apps/api             FastAPI, Python 3.12, uv, ruff, pytest — /health
packages/api-client  Client TypeScript généré depuis l'OpenAPI de apps/api (openapi-typescript)
infra/postgres/init  Scripts d'initialisation (extensions pg_trgm, unaccent)
docker-compose.yml   Postgres 16, Redis 7, MinIO, Mailpit — ports par défaut = infra partagée de la flotte
```

Versions épinglées : Node 24, pnpm 12.4.2 (`packageManager` dans `package.json`), Python 3.12,
uv (voir `uv.lock` dans `apps/api`) ; images Docker à tag majeur fixe (`postgres:16-alpine`,
`redis:7-alpine`).

```bash
# Infra locale (Postgres, Redis, MinIO, Mailpit)
cp .env.example .env   # optionnel : les valeurs par défaut suffisent
docker compose up -d
docker compose down -v # arrêt + purge des volumes

# Front — apps/web
pnpm install
pnpm --filter @pbm/web dev          # http://localhost:3000
pnpm --filter @pbm/web lint
pnpm --filter @pbm/web type-check
pnpm --filter @pbm/web test
pnpm --filter @pbm/web build

# API — apps/api
cd apps/api
uv sync
uv run uvicorn pbm_api.main:app --reload   # http://localhost:8000/health
uv run ruff check .
uv run pytest -q

# Client TypeScript généré depuis l'OpenAPI (à relancer après tout changement de schéma API)
pnpm gen:api
```

## Configuration par variables d'environnement

`apps/api` lit sa configuration via `pbm_api.config.Settings` (pydantic-settings, fichier `.env`
optionnel) : `DATABASE_URL`, `REDIS_URL`, `S3_ENDPOINT_URL`/`S3_ACCESS_KEY`/`S3_SECRET_KEY`/
`S3_BUCKET`/`S3_REGION`, `SMTP_HOST`/`SMTP_PORT`/`SMTP_USER`/`SMTP_PASSWORD`/`SMTP_FROM`. Chaque
lot pointe sa propre base/bucket/préfixe — ne jamais réutiliser ceux d'un autre lot sur l'infra
partagée (`pbm-shared`). `apps/web` lit `NEXT_PUBLIC_API_URL` (défaut `http://localhost:8000`).

## Règles de la flotte applicables ici (résumé de `~/.claude/CLAUDE.md`)

- On construit sur chimera (32 Go, 16 threads) et on ne construit jamais sur la machine qui sert.
- Le réseau de chimera plafonne à ~250 Ko/s : éviter les téléchargements/images Docker inutiles.
- Session autonome (`claude -p`) : jamais de `git stash`, jamais `git add -A`, commits ciblés,
  compte rendu obligatoire même en cas d'échec ou de blocage.
