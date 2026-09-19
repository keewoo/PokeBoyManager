# Lot `v0-monorepo` — Monorepo, environnement local Docker et CI

> Prompt GÉNÉRÉ depuis `docs/roadmap/roadmap.json` par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Suivi : `docs/roadmap/ROADMAP.html` (onglets Roadmap et Maquette) · processus : `docs/roadmap/PROCESSUS.md`.

**P0** · piste Fondations & livraison · couloir **DA1** — API, comptes & données (**devAI**) · prévu du 22 sept. au 23 sept. · jalon **MVP en UAT** · taille M · complexité 3/5 · difficulté 2/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur devAI**. Lance `hostname -s` :

- **Mac-mini-de-keewoo (hostname -s)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier v0-monorepo`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur devAI :

```bash
ssh devai 'cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-v0-monorepo -b roadmap/v0-monorepo origin/main && mkdir -p ~/dev/logs'
```

3. Lance le lot autonome : `ssh devai 'cd ~/dev/wt-v0-monorepo && nohup claude -p --dangerously-skip-permissions < prompts/v0-monorepo.md > ~/dev/logs/v0-monorepo.log 2>&1 &'` (toutes les sorties redirigées : ssh rend la main).
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/v0-monorepo` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 7 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy`. Travaille dans ton **worktree** `../wt-v0-monorepo`, branche `roadmap/v0-monorepo` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier v0-monorepo
python3 docs/roadmap/suivi.py demarrer v0-monorepo --machine "$(hostname -s)" --branche roadmap/v0-monorepo
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut v0-monorepo attente_validation --motif "<raisons>"`, section 7, dernier message `ATTENTE VALIDATION — v0-monorepo — <raisons>`.
- Tu n'accordes **jamais** toi-même une dérogation.

## 1. Cadre — relire avant d'agir

| Document | Pourquoi |
|---|---|
| `CLAUDE.md` | règles du dépôt, commandes, conventions |
| `docs/ARCHITECTURE.md` | stack, données, coffre de clés, reconnaissance |
| `docs/roadmap/PROCESSUS.md` | suivi, garde-fou, clôture |
| `docs/roadmap/ROADMAP.html` — onglet **Maquette** | l'écran à reproduire (front) |
| `BACKLOG.md` | l'état des autres lots |
| `~/.claude/CLAUDE.md` de la machine | règles de la flotte (construire ≠ servir, Python 3.12, WSL) |

Le cadre l'emporte sur ce prompt : en cas de contradiction, passe en `attente_validation` avec la contradiction en motif.

## 2. Contexte

**Gain.** Un `docker compose up` donne Postgres, Redis, MinIO et Mailpit ; chaque push est testé.

**Fonctionnalités.** Squelette `apps/web` (Next.js) et `apps/api` (FastAPI, `/health`), client TypeScript généré depuis l'OpenAPI.

**Tenants — ce qu'il faut avant.** D1 (stack validée).

**Aboutissants — ce que ça ouvre.** Tous les lots de code.

**Dépend de :**
- aucune

**Décision D1** (avant le 22 sept.) : Valider la stack : Next.js + FastAPI + PostgreSQL 16 + Redis/arq, monorepo pnpm + uv. — lis la décision prise dans `etat.json` (`decisions_prises`) et applique-la à la lettre.

## 3. Mission

1. Créer `apps/web` (Next.js 15, TypeScript strict, Tailwind 4, ESLint, Vitest) et `apps/api` (FastAPI, uv, ruff, pytest, `/health`).
2. `docker-compose.yml` : postgres:16 (extensions `pg_trgm`, `unaccent`), redis:7, minio, mailpit ; `.env.example` sans aucun secret réel.
3. Script `pnpm gen:api` : OpenAPI de l'API → `packages/api-client` (openapi-typescript).
4. GitHub Actions : lint + tests web et api en parallèle, services Postgres/Redis, badge dans le README.
5. `CLAUDE.md` racine à jour : commandes, conventions, règles de la flotte.

## 4. Risques & pièges

Dérive de versions entre machines : épingler Node, pnpm, Python 3.12 et les images Docker.

## 5. Livrables — définition de « fini »

- `docker compose up` fonctionnel
- CI verte sur `main`
- `/health` répond 200
- CI GitHub Actions verte sur la PR (elle fait foi, pas une suite verte sur une machine).
- Aucun secret dans le dépôt, les journaux ou les sorties.

## 6. Tests exigés

- Un test qui **échoue sans** ton changement et passe avec.
- Route utilisateur → test d'accès croisé (l'utilisateur B reçoit 404 sur les objets de A).
- Front → conformité à l'écran de la maquette (capture jointe au compte rendu).
- Suites complètes lancées sur la flotte (`fleet-run` depuis le Mac, ou directement sur la machine), jamais sur le Mac de JF.

## 7. Clôture — obligatoire

Grille de tâches du lot :
- `dev` — Développement
- `tests` — Tests (unitaires, API, e2e)
- `securite` — Contrôle sécurité (isolation, secrets)
- `maquette` — Conforme à la maquette (sans objet : socle technique)
- `doc_tech` — Doc technique (CLAUDE.md, docs/)
- `release_uat` — Livré en UAT (preuve) (sans objet : socle technique)
- `release_prod` — Livré en PROD (preuve) (sans objet : socle technique)
- `backlog` — BACKLOG.md et état à jour
- `compte_rendu` — Compte rendu dans le suivi

```bash
python3 docs/roadmap/suivi.py tache v0-monorepo <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu v0-monorepo --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut v0-monorepo <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "v0-monorepo: …" && git push -u origin roadmap/v0-monorepo && gh pr create --fill
```

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

