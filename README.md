# PokeBoyManager

[![CI](https://github.com/keewoo/PokeBoyManager/actions/workflows/ci.yml/badge.svg)](https://github.com/keewoo/PokeBoyManager/actions/workflows/ci.yml)

Espace **privé** de gestion de collection de cartes Pokémon : on photographie ses cartes (une
ou tout un classeur), **sa propre IA** (Claude, Gemini ou OpenAI) les reconnaît, puis on gère
sa collection et on suit la **valeur de chaque carte dans le temps**.

- Roadmap, backlog, prompts de lancement et **maquette cliquable** : [`docs/roadmap/ROADMAP.html`](docs/roadmap/ROADMAP.html) — version publiée : https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy
- Backlog lisible sur GitHub : [`BACKLOG.md`](BACKLOG.md) · un prompt par lot : [`prompts/`](prompts/)
- Architecture et choix techniques : [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- Processus de suivi : [`docs/roadmap/PROCESSUS.md`](docs/roadmap/PROCESSUS.md)

État au 19/09/2026 : socle technique livré (`v0-monorepo`) — monorepo pnpm + uv, `apps/web`
(Next.js 15), `apps/api` (FastAPI, `/health`), `docker-compose.yml` (Postgres, Redis, MinIO,
Mailpit), client TypeScript généré depuis l'OpenAPI, CI GitHub Actions. Aucune fonctionnalité
métier encore.

## Démarrer en local

```bash
cp .env.example .env   # optionnel, les valeurs par défaut suffisent
docker compose up -d   # Postgres 16, Redis 7, MinIO, Mailpit
pnpm install
pnpm --filter @pbm/web dev        # http://localhost:3000
cd apps/api && uv sync && uv run uvicorn pbm_api.main:app --reload   # http://localhost:8000/health
```

> PokeBoyManager n'est pas affilié à Nintendo, Creatures, GAME FREAK ni à The Pokémon Company.
