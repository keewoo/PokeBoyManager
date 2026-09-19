# Lot `v0-schema` — Modèle de données PostgreSQL v1 et migrations Alembic

> Prompt GÉNÉRÉ depuis `docs/roadmap/roadmap.json` par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Suivi : `docs/roadmap/ROADMAP.html` (onglets Roadmap et Maquette) · processus : `docs/roadmap/PROCESSUS.md`.

**P0** · piste Fondations & livraison · couloir **DA1** — API, comptes & données (**devAI**) · prévu du 24 sept. au 25 sept. · jalon **MVP en UAT** · taille M · complexité 3/5 · difficulté 2/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur devAI**. Lance `hostname -s` :

- **Mac-mini-de-keewoo (hostname -s)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier v0-schema`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur devAI :

```bash
ssh devai 'cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-v0-schema -b roadmap/v0-schema origin/main && mkdir -p ~/dev/logs'
```

3. Lance le lot autonome : `ssh devai 'cd ~/dev/wt-v0-schema && nohup claude -p --dangerously-skip-permissions < prompts/v0-schema.md > ~/dev/logs/v0-schema.log 2>&1 &'` (toutes les sorties redirigées : ssh rend la main).
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/v0-schema` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 7 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy`. Travaille dans ton **worktree** `../wt-v0-schema`, branche `roadmap/v0-schema` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier v0-schema
python3 docs/roadmap/suivi.py demarrer v0-schema --machine "$(hostname -s)" --branche roadmap/v0-schema
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut v0-schema attente_validation --motif "<raisons>"`, section 7, dernier message `ATTENTE VALIDATION — v0-schema — <raisons>`.
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

**Gain.** Toutes les fonctionnalités partagent un schéma pensé une fois : comptes, catalogue, prix, photos, détections, collection.

**Fonctionnalités.** —

**Tenants — ce qu'il faut avant.** Monorepo en place.

**Aboutissants — ce que ça ouvre.** Comptes, catalogue, reconnaissance et collection.

**Dépend de :**
- `v0-monorepo` — Monorepo, environnement local Docker et CI

## 3. Mission

1. Tables : `users`, `sessions`, `email_tokens`, `ai_credentials` (chiffrées), `sets`, `cards` (+ `card_names` par langue), `card_prices_daily` (carte, source, variante, jour, devise, bas/moyen/tendance), `uploads`, `detections` (bbox, recadrage, candidats JSON, statut), `collection_items`, `card_insights` (anecdotes, étude en jeu, cache partagé), `jobs`.
2. Index : trigram sur les noms, `(set_id, number)`, `(card_id, day)` ; toutes les tables utilisateur portent `user_id` avec clé étrangère et index.
3. Migration Alembic initiale + données de démonstration (un utilisateur, trois extensions, neuf cartes).
4. Schéma dessiné (Mermaid) dans `docs/ARCHITECTURE.md`.

## 4. Risques & pièges

Distinguer la **carte du catalogue** (`cards`) de l'**exemplaire possédé** (`collection_items` : état, langue, prix d'achat, photo) ; l'historique de prix doit rester léger (une ligne par carte, source et jour).

## 5. Livrables — définition de « fini »

- migration 0001 jouée en CI
- seed de démonstration
- schéma documenté
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
- `maquette` — Conforme à la maquette (sans objet : schéma)
- `doc_tech` — Doc technique (CLAUDE.md, docs/)
- `release_uat` — Livré en UAT (preuve) (sans objet : joué avec v1-uat)
- `release_prod` — Livré en PROD (preuve) (sans objet : joué avec v5-prod)
- `backlog` — BACKLOG.md et état à jour
- `compte_rendu` — Compte rendu dans le suivi

```bash
python3 docs/roadmap/suivi.py tache v0-schema <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu v0-schema --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut v0-schema <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "v0-schema: …" && git push -u origin roadmap/v0-schema && gh pr create --fill
```

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

