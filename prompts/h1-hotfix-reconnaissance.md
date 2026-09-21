# Lot `h1-hotfix-reconnaissance` — La reconnaissance échouait : schéma JSON refusé par Anthropic

> Prompt GÉNÉRÉ depuis `docs/roadmap/roadmap.json` par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Suivi : `docs/roadmap/ROADMAP.html` (onglets Roadmap et Maquette) · processus : `docs/roadmap/PROCESSUS.md`.

**P0** · piste Fondations & livraison · couloir **DA2** — Livraison & infra (seul à déployer) (**devAI**) · prévu du 20 sept. au 20 sept. · jalon **MVP en UAT** · taille S · complexité 3/5 · difficulté 4/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur devAI**. Lance `hostname -s` :

- **Mac-mini-de-keewoo (hostname -s)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier h1-hotfix-reconnaissance`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur devAI :

```bash
ssh devai 'cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-h1-hotfix-reconnaissance -b roadmap/h1-hotfix-reconnaissance origin/main && mkdir -p ~/dev/logs'
```

3. Lance le lot autonome : `ssh devai 'cd ~/dev/wt-h1-hotfix-reconnaissance && nohup claude -p --dangerously-skip-permissions < prompts/h1-hotfix-reconnaissance.md > ~/dev/logs/h1-hotfix-reconnaissance.log 2>&1 &'` (toutes les sorties redirigées : ssh rend la main).
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/h1-hotfix-reconnaissance` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 7 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy`. Travaille dans ton **worktree** `../wt-h1-hotfix-reconnaissance`, branche `roadmap/h1-hotfix-reconnaissance` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier h1-hotfix-reconnaissance
python3 docs/roadmap/suivi.py demarrer h1-hotfix-reconnaissance --machine "$(hostname -s)" --branche roadmap/h1-hotfix-reconnaissance
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut h1-hotfix-reconnaissance attente_validation --motif "<raisons>"`, section 7, dernier message `ATTENTE VALIDATION — h1-hotfix-reconnaissance — <raisons>`.
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

**Gain.** Sans ce correctif, le cœur du produit ne marchait pas en production : chaque photo finissait en « erreur 400 » invisible.

**Fonctionnalités.** Reconnaissance rétablie ; l'erreur du fournisseur remonte à l'écran et dans le suivi du job.

**Tenants — ce qu'il faut avant.** Envoi de photos, coffre de clés.

**Aboutissants — ce que ça ouvre.** Parcours de validation.

**Dépend de :**
- aucune

## 3. Mission

1. (livré) Schéma nettoyé, erreur rendue visible, preuve de bout en bout en PROD.

## 4. Risques & pièges

Diagnostiqué contre l'API réelle : les contraintes Pydantic (`minimum`, `maxLength`…) laissées dans le schéma ne sont pas acceptées.

## 5. Livrables — définition de « fini »

- job de reconnaissance réussi en PROD
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
- `maquette` — Conforme à la maquette (sans objet : back-end)
- `doc_tech` — Doc technique (CLAUDE.md, docs/)
- `release_uat` — Recette locale sur chimera
- `release_prod` — Livré en PROD (preuve)
- `backlog` — BACKLOG.md et état à jour
- `compte_rendu` — Compte rendu dans le suivi

```bash
python3 docs/roadmap/suivi.py tache h1-hotfix-reconnaissance <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu h1-hotfix-reconnaissance --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut h1-hotfix-reconnaissance <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "h1-hotfix-reconnaissance: …" && git push -u origin roadmap/h1-hotfix-reconnaissance && gh pr create --fill
```

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

