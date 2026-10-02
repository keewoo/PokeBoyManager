# Lot `h1-ci-stockage-s3` — La CI retrouve son stockage S3 : MinIO remplacé par SeaweedFS

> Prompt GÉNÉRÉ depuis `docs/roadmap/roadmap.json` par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Suivi : `docs/roadmap/ROADMAP.html` (onglets Roadmap et Maquette) · processus : `docs/roadmap/PROCESSUS.md`.

**P0** · piste Fondations & livraison · couloir **DA2** — Livraison & infra (seul à déployer) (**devAI**) · prévu du 1 oct. au 1 oct. · jalon **MVP en UAT** · taille S · complexité 2/5 · difficulté 2/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur devAI**. Lance `hostname -s` :

- **Mac-mini-de-keewoo (hostname -s)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier h1-ci-stockage-s3`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur devAI :

```bash
ssh devai 'cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-h1-ci-stockage-s3 -b roadmap/h1-ci-stockage-s3 origin/main && mkdir -p ~/dev/logs'
```

3. Lance le lot autonome : `ssh devai 'cd ~/dev/wt-h1-ci-stockage-s3 && nohup claude -p --dangerously-skip-permissions < prompts/h1-ci-stockage-s3.md > ~/dev/logs/h1-ci-stockage-s3.log 2>&1 &'` (toutes les sorties redirigées : ssh rend la main).
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/h1-ci-stockage-s3` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 7 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy`. Travaille dans ton **worktree** `../wt-h1-ci-stockage-s3`, branche `roadmap/h1-ci-stockage-s3` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier h1-ci-stockage-s3
python3 docs/roadmap/suivi.py demarrer h1-ci-stockage-s3 --machine "$(hostname -s)" --branche roadmap/h1-ci-stockage-s3
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut h1-ci-stockage-s3 attente_validation --motif "<raisons>"`, section 7, dernier message `ATTENTE VALIDATION — h1-ci-stockage-s3 — <raisons>`.
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

## 1 bis. Le dépôt est graphifié — interroge le graphe avant de lire dix fichiers

Le code, la documentation et les schémas de ce dépôt sont indexés par **Graphify**. Dans ton worktree, `graphify-out/` n'existe pas encore (il n'est pas versionné) : construis-le, puis pose tes questions au graphe.

```bash
export PATH=$HOME/.local/bin:$PATH   # sur la flotte, graphify vit là
graphify update .                     # ~5-25 s, sans LLM
graphify query "<ta question>"      # qui appelle quoi, où vit telle règle
graphify explain "<symbole>"        # un nœud et ses voisins
graphify affected "<symbole>"       # ce qui dépend de ce que tu vas modifier
```

Si le serveur MCP `graphify` est chargé dans ta session, `query_graph`, `get_neighbors` et `shortest_path` font la même chose. Le graphe **oriente**, il ne prouve pas : ouvre le fichier réel avant d'affirmer qu'une ligne existe. Mode d'emploi : `docs/CODE.md` § « Chercher dans le dépôt ».

## 2. Contexte

**Gain.** MinIO n'est plus distribué en image (quay.io répond 401, le dépôt Docker Hub a disparu) : depuis le 01/10, les jobs api et e2e échouent avant le premier test, quel que soit le commit. Sans CI, plus rien ne peut être déclaré fini.

**Fonctionnalités.** Remplacer le serveur S3 de la CI et du docker-compose de dev par une image maintenue, épinglée, qui se comporte comme MinIO sur tout ce que le produit utilise : bucket créé à la volée, objets, codes NoSuchKey/404, URL présignées SigV2 avec Content-Type signé, et CORS ouvert pour le dépôt direct du navigateur.

**Tenants — ce qu'il faut avant.** CI GitHub Actions, docker-compose de dev, stockage objet.

**Aboutissants — ce que ça ouvre.** CI de nouveau verte ; tous les lots suivants retrouvent leur verdict.

**Dépend de :**
- aucune

## 3. Mission

1. Mesurer les candidats contre la même sonde que MinIO, MinIO compris comme référence.
2. Remplacer MinIO dans la CI (jobs api et e2e) et dans docker-compose.yml, image épinglée.
3. Garder la sonde dans le dépôt pour revalider tout futur remplaçant.
4. Mettre à jour les fiches et les commentaires qui nomment MinIO comme serveur courant.

## 4. Risques & pièges

Un remplaçant qui accepte tout (signatures non vérifiées) laisserait passer des tests qui ne prouvent plus rien ; un remplaçant sans CORS casserait l'e2e d'envoi de photo. La PROD n'est pas concernée : elle stocke les photos sur disque (D7).

## 5. Livrables — définition de « fini »

- CI verte sur la branche du lot puis sur main
- apps/api/scripts/sonde_s3.py et son verdict par candidat dans le compte rendu
- CI GitHub Actions verte sur la PR (elle fait foi, pas une suite verte sur une machine).
- Aucun secret dans le dépôt, les journaux ou les sorties.
- **Code documenté** : chaque module, fonction et classe publique ajouté ou modifié a sa docstring (Python) ou son `/** … */` (TypeScript), en français, qui dit le pourquoi — `docs/CODE.md` § « Documenter le code ».
- **Graphe à jour** : après la fusion dans `main`, `graphify update .` sur le clone qui suit `main` (un graphe en retard fait mentir les lots suivants).

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
- `maquette` — Conforme à la maquette (sans objet : infrastructure de test)
- `doc_tech` — Doc technique (CLAUDE.md, docs/)
- `release_uat` — Recette locale sur chimera
- `release_prod` — Livré en PROD (preuve) (sans objet : la PROD stocke sur disque (D7), rien n'y change)
- `backlog` — BACKLOG.md et état à jour
- `compte_rendu` — Compte rendu dans le suivi

```bash
python3 docs/roadmap/suivi.py tache h1-ci-stockage-s3 <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu h1-ci-stockage-s3 --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut h1-ci-stockage-s3 <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "h1-ci-stockage-s3: …" && git push -u origin roadmap/h1-ci-stockage-s3
bash scripts/ouvrir-pr.sh roadmap/h1-ci-stockage-s3   # ouvre la PR, ou echoue en disant pourquoi
```

**La PR n'est pas optionnelle** : sans elle, la CI ne tourne pas sur ton travail, et c'est la CI qui fait foi. Si `ouvrir-pr.sh` sort en erreur, tu NE conclus PAS que c'est sans importance : tu nommes le manque dans ton compte rendu et dans ton dernier message.

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

