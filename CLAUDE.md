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
`S3_BUCKET`/`S3_REGION`, `SMTP_HOST`/`SMTP_PORT`/`SMTP_USER`/`SMTP_PASSWORD`/`SMTP_FROM`,
`SECRET_KEY`/`APP_PUBLIC_URL`/`SESSION_COOKIE_NAME`/`CSRF_COOKIE_NAME`/`SESSION_TTL_DAYS`/
`EMAIL_TOKEN_TTL_MINUTES`/`LOGIN_RATE_LIMIT_MAX_ATTEMPTS`/`LOGIN_RATE_LIMIT_WINDOW_SECONDS`
(comptes, lot `v1-auth` — `SECRET_KEY` signe les jetons CSRF, à définir par variable
d'environnement en dehors du dépôt pour tout déploiement), `AI_KEY_ENCRYPTION_KEY` (coffre de
clés IA, lot `v1-byok` — clé maître AES-256 en base64, 32 octets ; chiffre/déchiffre les clés
des utilisateurs, à définir par variable d'environnement hors dépôt pour tout déploiement).
Chaque lot pointe sa propre base/bucket/préfixe — ne jamais réutiliser ceux d'un autre lot sur
l'infra partagée (`pbm-shared`). `apps/web` lit `NEXT_PUBLIC_API_URL` (défaut
`http://localhost:8000`) et `NEXT_PUBLIC_SESSION_COOKIE_NAME` (défaut `pbm_session`, doit
rester alignée avec `SESSION_COOKIE_NAME` côté API : le middleware de garde de route ne lit que
la présence de ce cookie, `apps/web/src/middleware.ts`). `apps/api` accepte les requêtes
cross-origin du front (`CORSMiddleware`, origine = `APP_PUBLIC_URL`, `allow_credentials=True`
pour le cookie de session) — obligatoire dès qu'ils tournent sur des ports/domaines différents.

Pages d'authentification (lot `v1-pages-auth`) : `/inscription`, `/connexion`,
`/mot-de-passe-oublie`, `/verifier?token=…`, `/reinitialiser?token=…` — ces deux derniers
chemins doivent rester alignés avec les liens envoyés par e-mail
(`pbm_api.auth.service.register_user`/`request_password_reset`). e2e Playwright du parcours
inscription → vérification → connexion : `apps/web/e2e/auth.spec.ts` (`pnpm --filter @pbm/web
test:e2e`, nécessite Mailpit ; navigateurs déjà en cache sur chimera).

## Coffre de clés IA (lot `v1-byok`)

Routes (`apps/api/src/pbm_api/routers/ai_keys.py`) : `GET/PUT/DELETE /me/ai-keys[/{provider}]`,
`POST /me/ai-keys/{provider}/test`, `GET/PATCH /me/ai-settings`, `GET /me/ai-usage`. Chiffrement
AES-256-GCM (`pbm_api.security.crypto`, `user_id` en données associées) ; filtre anti-fuite de
clé dans les journaux (`pbm_api.security.log_filter`, installé au démarrage) et dans les
réponses 422 de validation (`pbm_api.security.validation_errors` — le comportement par défaut
de FastAPI renverrait sinon la valeur soumise en clair sur une clé trop courte/longue). Le test
d'une clé
appelle réellement le fournisseur (liste de modèles, coût nul) via `pbm_api.ai.providers.
ProviderKeyTester`, injecté par dépendance FastAPI — remplacé par un double dans les tests
(aucune clé IA réelle disponible sur chimera) ; essai manuel avec une vraie clé :
`uv run python scripts/test_ai_key_manual.py <provider> <clé>` depuis `apps/api`.

## Fournisseurs IA (lot `v3-ia-providers`)

Interface unique `AIProvider.extract(images, schema, prompt) -> (objet validé, usage)`
(`apps/api/src/pbm_api/ai/base.py`) — implémentations `AnthropicProvider`/`OpenAiProvider`/
`GeminiProvider` (`apps/api/src/pbm_api/ai/`), fabriquées par `pbm_api.ai.factory.
create_provider(provider, api_key)`. Sortie structurée native par fournisseur + validation
Pydantic (schéma traduit par `pbm_api.ai.json_schema`, `$ref` repliés) ; une nouvelle tentative
guidée si le JSON ne valide pas. Erreurs normalisées (`pbm_api.ai.errors` :
`InvalidApiKeyError`/`QuotaExceededError`/`ProviderOverloadedError`/`ProviderUnreachableError`/
`ContentRefusedError`), chacune avec un `user_message` prêt à consigner sur un `Job`. Détail :
`docs/ARCHITECTURE.md` § « Fournisseurs IA ». Tests sur réponses enregistrées
(`apps/api/tests/test_ai_providers.py`, `httpx.MockTransport`, aucune clé réelle sur chimera) ;
essai manuel avec une vraie clé : `uv run python scripts/test_ai_extraction_manual.py <provider>
<clé>` depuis `apps/api`.

## Règles de la flotte applicables ici (résumé de `~/.claude/CLAUDE.md`)

- On construit sur chimera (32 Go, 16 threads) et on ne construit jamais sur la machine qui sert.
- Le réseau de chimera plafonne à ~250 Ko/s : éviter les téléchargements/images Docker inutiles.
- Session autonome (`claude -p`) : jamais de `git stash`, jamais `git add -A`, commits ciblés,
  compte rendu obligatoire même en cas d'échec ou de blocage.
