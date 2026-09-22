# Code — conventions, commandes, tests

> **À lire avant d'écrire du code.** Ce qui vaut pour tout le dépôt : structure du monorepo,
> commandes, versions, git, tests et définition du « fini ».
> Ce qui n'est pas ici : le comportement métier (`docs/ARCHITECTURE.md`), l'écran
> (`docs/UI-UX.md`), la mise en ligne (`docs/LIVRAISON.md`), les services tiers (`docs/PLUGINS.md`).
> Tous les chemins sont donnés **depuis la racine du dépôt**.

## Versions — non négociables

| | Version | Pourquoi |
|---|---|---|
| Python | **3.12** (`UV_PYTHON=3.12`) | c'est ce que la PROD exécute et ce que teste la CI ; cinq versions ont déjà cohabité ailleurs et la garde de livraison validait un interpréteur que personne n'exécutait |
| Node | **24** | épinglé par `packageManager` dans `package.json` |
| pnpm | **12.4.2** | idem |
| Images Docker | tag majeur fixe (`postgres:16-alpine`, `redis:7-alpine`) | une image flottante rend un build non reproductible |

**La CI GitHub Actions fait foi.** Un test vert en local ne vaut pas livraison : l'environnement
local agrège des dépendances que la CI isole. Un échec local qui n'apparaît pas en CI se compare
avant d'être corrigé.

## Git — un lot, un worktree, une branche, une PR

- Un lot = un worktree `../wt-<id>`, une branche `roadmap/<id>`, une PR.
- **Jamais `git stash`** : il remise l'arbre entier, y compris le travail des autres sessions Claude
  qui tournent sur ce poste.
- **Jamais `git add -A`** : on ajoute les fichiers qu'on a écrits, nommément.
- Les fichiers générés (`BACKLOG.md`, `prompts/*.md`, `docs/roadmap/ROADMAP.html`,
  `docs/roadmap/jeu/BACKLOG-JEU.md`, `docs/roadmap/jeu/jeu.json`) se commitent **avec leurs sources**,
  jamais seuls et jamais édités à la main.

## Ce qui est interdit dans le code

- **Un repli silencieux** — `|| true`, `except: pass`, `2>/dev/null` sur un chemin nominal, une
  branche attendue « ignorée ». Un relevé de prix vide, un lot sans compte rendu, une carte sans
  script : ce sont des **pannes**, pas des cas normaux. Quand on écrit un repli, on écrit dans le
  même geste ce qui le rendra visible.
- **Un secret dans le dépôt** : `.env` est ignoré, `.env.example` ne contient aucune valeur réelle.
  Les clés IA ne sont jamais renvoyées par une route, jamais journalisées, jamais écrites en clair.
- **Une route sans filtre `user_id`** : toute route utilisateur filtre par l'identifiant issu de la
  session, et son test d'accès croisé est obligatoire (voir `docs/SECURITE.md`).

## Chercher dans le dépôt : le graphe avant le grep

Le dépôt est indexé par **Graphify** (`.mcp.json`, serveur `graphify`) — la taille du jour se lit
avec `graph_stats`, pas dans cette phrase : elle changerait à chaque commit. Avant de relire dix fichiers pour comprendre qui appelle quoi, pose la question au graphe
(`query_graph`, `get_neighbors`, `shortest_path`, `god_nodes`). Il se reconstruit par
`graphify update .` en ~25 s (~5 s sur devAI). Détail et limites : `docs/PLUGINS.md`.

### Le graphe suit `main` — procédure

Le graphe décrit un état du code. Dès que `main` bouge, il ment. **Trois moments l'imposent, et
aucun ne se reporte au lendemain :**

| Quand | Quoi |
|---|---|
| après un `git commit` **sur `main`** | `graphify update .` |
| après un `git pull` / `git merge` qui apporte du code sur `main` | `graphify update .` |
| après la fusion de la PR d'un lot | `graphify update .` sur le clone où l'on travaille |

```bash
# le geste complet, à faire d'un bloc
git add <fichiers nommés> && git commit -m "…" && graphify update .
```

Sur une branche de lot, rafraîchir n'est utile que si l'on va interroger le graphe : c'est `main`
qui fait foi. **Le graphe ne se versionne pas** (`graphify-out/` est dans `.gitignore`) : chaque
clone tient le sien, et chaque machine paie ses 5 à 25 secondes.

Une règle écrite ne force rien toute seule : si le graphe d'un clone retarde, le premier agent qui
s'en aperçoit le reconstruit **avant** de répondre, il ne travaille pas sur des réponses fausses.

## Définition du « fini » pour un lot

1. `python3 docs/roadmap/suivi.py verifier <id>` passe **avant** la première ligne de code
   (code 2 = ordre non tenu → on s'arrête et on demande à JF).
2. Les tests du lot sont verts **en CI**, pas seulement en local.
3. Le compte rendu est écrit dans `docs/roadmap/comptes-rendus/<id>.md`.
4. Ce que le lot a changé de durable est reporté dans la fiche concernée de `docs/` — pas empilé
   dans `CLAUDE.md` (voir `CLAUDE.md` § « Où écrire quoi »).
5. **Le graphe est à jour avec `main`** : `graphify update .` après la fusion. Un lot livré qui
   laisse le graphe en arrière fait mentir toutes les sessions suivantes.

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

## Parcours e2e complet (lot `v5-e2e`)

`apps/web/e2e/parcours-complet.spec.ts` — inscription → vérification (Mailpit) → clé IA
(simulée) → envoi de la photo de référence 3×3 → validation → collection filtrée → fiche carte.
Contrairement à `validation.spec.ts`/`card-detail.spec.ts` (résultat semé directement en base,
aucune clé IA réelle sur chimera), ce lot fait tourner le **vrai** pipeline de bout en bout : un
vrai fichier envoyé par le navigateur, une vraie détection OpenCV, une vraie identification +
rapprochement catalogue — seul l'aller-retour réseau vers le fournisseur IA est remplacé.

`pbm_api.ai.simulated_provider.SimulatedProvider` (drapeau `AI_SIMULATED_PROVIDER`, faux par
défaut, jamais en UAT/PROD) bascule `pbm_api.ai.factory.create_provider` dessus quel que soit le
fournisseur demandé — un seul point de fabrication, comme la mission `v3-ia-providers` le
prévoyait déjà. Il ne simule que `CardExtraction` (identification/état) en servant les neuf
cartes de `pbm_api.seed.DEMO_CARDS` ; tout autre schéma (repli LLM de la détection, insights,
étude en jeu) lève une erreur explicite plutôt qu'une réponse inventée. Faire tourner le vrai
pipeline exige un worker arq réel : troisième entrée `webServer` de `playwright.config.ts`
(`uv run arq pbm_api.worker.WorkerSettings`, même base/redis que l'API) — jusqu'ici aucune spec
n'en avait besoin, le résultat de reconnaissance étant toujours semé directement.

Photo de référence : `apps/api/scripts/generate_e2e_reference_photo.py` écrit un classeur 3×3
propre (`pbm_api.detection.synthetic.make_binder_grid(glare=False)`) — OpenCV seul suffit à
détecter les neuf cartes, aucun repli LLM n'est donc exercé. Catalogue : idempotent comme
`pbm_api.seed` lui-même, `apps/api/scripts/seed_e2e_reference_catalog.py` sème aussi un
historique de prix minimal et rafraîchit `card_value_rank` (sinon le classement de la fiche
resterait vide pour des cartes fraîchement créées). En le relançant, un bogue latent de
`pbm_api.seed.seed()` a été trouvé et corrigé : `User` exige `last_name`/`birth_date`/
`terms_version`/`terms_accepted_at` depuis `v1-identite`, postérieur à ce module qui n'avait
jamais été rejoué depuis.

**Écart assumé** : les neuf recadrages du classeur synthétique sont visuellement indiscernables
(`pbm_api.detection.synthetic.draw_card` est pensé pour la géométrie de détection, pas pour
l'identification — même couleur, même cercle, quelle que soit la carte). Leur empreinte
perceptuelle est donc identique, et `identification_cache` (une vraie fonctionnalité de
production, pas un artefact de la simulation) résout les huit détections suivantes sans
repasser par le fournisseur simulé après le premier appel : les neuf exemplaires confirmés sont
neuf « Sarmuraï » (doublons), pas neuf cartes distinctes. Une diversité réelle demanderait des
photos distinctes, indisponibles sur chimera (même contrainte que `v3-detection`). Le filtre de
collection est quand même exercé dans les deux sens (une recherche qui trouve, une qui ne trouve
rien) ; la fiche carte n'est vérifiée que sur ses onglets Valeur/État/Mes exemplaires — Histoire/
En jeu appelleraient un vrai wiki + la clé IA (schémas que `SimulatedProvider` ne simule pas),
déjà couverts sans réseau par `card-detail.spec.ts`.

Test d'accès croisé propre à ce lot : un second utilisateur reçoit 404 sur `GET /uploads/{id}` et
`GET /uploads/{id}/detections` de l'envoi réel du premier — isolation déjà couverte ailleurs sur
un résultat *semé*, jamais encore sur un envoi/détections produits par le vrai pipeline.

**Deux bogues trouvés en étant la première spec à exercer un vrai envoi de photo par le
navigateur** (les e2e précédentes sèment leur résultat directement en base) :
- La CSP `connect-src` du lot `v5-securite` (`apps/web/src/middleware.ts`) n'autorisait que
  `'self'` et l'origine de l'API — pas celle du stockage objet. Avec `STORAGE_BACKEND=s3` (MinIO
  en dev/CI), le navigateur dépose la photo brute par un `PUT` direct vers cette origine
  (présignée, `pbm_api.s3.ObjectStorage.presign_put`) : la CSP le bloquait, et **tout envoi de
  photo échouait silencieusement** (page affichant « L'envoi a échoué. », rien dans les journaux
  serveur puisque la requête n'atteint jamais l'API). Corrigé par `NEXT_PUBLIC_UPLOAD_ORIGIN`
  (voir plus haut) ajoutée à `connect-src` quand elle est définie.
- `/auth/register` est limité en débit par IP depuis `v5-securite`
  (`LOGIN_RATE_LIMIT_MAX_ATTEMPTS`/`_WINDOW_SECONDS`, un compteur Redis partagé avec `/auth/
  login`/`/auth/forgot`). Toutes les specs e2e tournent depuis la même IP contre la même
  instance API : `auth`+`validation`+`card-detail`+`parcours-complet` totalisaient déjà 5
  inscriptions dans une CI qui repart de zéro — pile à la limite par défaut (5), sans marge pour
  la moindre reprise (`retries: 1` en CI). `playwright.config.ts` relève `LOGIN_RATE_LIMIT_MAX_
  ATTEMPTS` pour cette seule instance e2e (jamais en UAT/PROD) ; le second utilisateur du test
  d'accès croisé de ce lot est en plus seedé directement en base
  (`scripts/seed_e2e_second_user.py`) plutôt que par `/auth/register`, pour ne pas alourdir ce
  compteur partagé.
