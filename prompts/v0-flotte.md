# Lot `v0-flotte` — Équiper la flotte pour PokeBoyManager (clones, clés de dépôt, fleet-run)

> Prompt GÉNÉRÉ depuis `docs/roadmap/roadmap.json` par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Suivi : `docs/roadmap/ROADMAP.html` (onglets Roadmap et Maquette) · processus : `docs/roadmap/PROCESSUS.md`.

**P0** · piste Fondations & livraison · couloir **DA2** — Livraison & infra (seul à déployer) (**devAI**) · prévu du 21 sept. au 22 sept. · jalon **MVP en UAT** · taille S · complexité 2/5 · difficulté 2/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur devAI**. Lance `hostname -s` :

- **Mac-mini-de-keewoo (hostname -s)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier v0-flotte`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur devAI :

```bash
ssh devai 'cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-v0-flotte -b roadmap/v0-flotte origin/main && mkdir -p ~/dev/logs'
```

3. Lance le lot autonome : `ssh devai 'cd ~/dev/wt-v0-flotte && nohup claude -p --dangerously-skip-permissions < prompts/v0-flotte.md > ~/dev/logs/v0-flotte.log 2>&1 &'` (toutes les sorties redirigées : ssh rend la main).
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/v0-flotte` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 7 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy`. Travaille dans ton **worktree** `../wt-v0-flotte`, branche `roadmap/v0-flotte` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier v0-flotte
python3 docs/roadmap/suivi.py demarrer v0-flotte --machine "$(hostname -s)" --branche roadmap/v0-flotte
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut v0-flotte attente_validation --motif "<raisons>"`, section 7, dernier message `ATTENTE VALIDATION — v0-flotte — <raisons>`.
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

**Gain.** Sans clone ni clé d'écriture sur devAI et chimera, les six couloirs n'existent pas.

**Fonctionnalités.** —

**Tenants — ce qu'il faut avant.** Dépôt GitHub créé (fait) ; accès SSH devai/chimera.

**Aboutissants — ce que ça ouvre.** Tous les lots peuvent démarrer sur la bonne machine.

**Dépend de :**
- aucune

## 3. Mission

1. devAI : cloner `git@github.com:keewoo/PokeBoyManager.git` dans `~/dev/pokeboy`, vérifier `uv` (Python 3.12) et Node 24.
2. chimera (WSL `Ubuntu-24.04`, utilisateur `upgreg`) : clone dans `~/dev/pokeboy`, clé de dépôt en écriture dédiée (JF l'ajoute dans GitHub → Deploy keys).
3. Étendre le mécanisme de lots de chimera (`~/dev/lots/launch-lot.sh`, `status-lot.sh`) au dépôt `~/dev/pokeboy` : un lot = un worktree `~/dev/wt-<id>`, journal `~/dev/logs/<id>.log`, lancé côté Windows.
4. Vérifier `fleet-run` depuis le Mac sur un script témoin, et Docker (colima sur devAI, Docker de la WSL sur chimera).
5. Lot témoin : un commit poussé depuis chaque machine sur une branche `chore/flotte`.

## 4. Risques & pièges

Clé de dépôt limitée à `keewoo/PokeBoyManager` ; WSL de chimera qui s'arrête quand plus aucun `wsl.exe` n'est ouvert ; ne jamais cloner sous `C:\fleet-ci` (rsync `--delete`).

## 5. Livrables — définition de « fini »

- clone sur devAI et chimera
- un commit poussé depuis chaque machine
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
- `securite` — Contrôle sécurité (isolation, secrets) (sans objet : outillage)
- `maquette` — Conforme à la maquette (sans objet : outillage)
- `doc_tech` — Doc technique (CLAUDE.md, docs/)
- `release_uat` — Recette locale sur chimera (sans objet : outillage)
- `release_prod` — Livré en PROD (preuve) (sans objet : outillage)
- `backlog` — BACKLOG.md et état à jour
- `compte_rendu` — Compte rendu dans le suivi

```bash
python3 docs/roadmap/suivi.py tache v0-flotte <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu v0-flotte --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut v0-flotte <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "v0-flotte: …" && git push -u origin roadmap/v0-flotte && gh pr create --fill
```

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

