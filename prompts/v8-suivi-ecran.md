# Lot `v8-suivi-ecran` — Où en est mon échange

> Prompt GÉNÉRÉ depuis `docs/roadmap/roadmap.json` par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Suivi : `docs/roadmap/ROADMAP.html` (onglets Roadmap et Maquette) · processus : `docs/roadmap/PROCESSUS.md`.

**P1** · piste Échanges entre collectionneurs · couloir **CH6** — Échanges — écrans, appariement & messagerie (**chimera**) · prévu du 15 févr. au 19 févr. · jalon **En ligne** · taille M · complexité 2/5 · difficulté 2/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur chimera**. Lance `hostname -s` :

- **Chimaera (dans la WSL)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier v8-suivi-ecran`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur chimera :

```bash
ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- bash -lc "cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-v8-suivi-ecran -b roadmap/v8-suivi-ecran origin/main && mkdir -p ~/dev/logs"'
```

3. Lance le lot autonome : par le mécanisme de lots de chimera (`~/dev/lots/launch-lot.sh`, étendu au dépôt `~/dev/pokeboy` par le lot `v0-flotte`), **lancé côté Windows** — un `nohup` interne à la WSL meurt avec la session. Journal : `~/dev/logs/v8-suivi-ecran.log`.
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/v8-suivi-ecran` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 7 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy (WSL Ubuntu-24.04, utilisateur upgreg)`. Travaille dans ton **worktree** `../wt-v8-suivi-ecran`, branche `roadmap/v8-suivi-ecran` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier v8-suivi-ecran
python3 docs/roadmap/suivi.py demarrer v8-suivi-ecran --machine "$(hostname -s)" --branche roadmap/v8-suivi-ecran
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut v8-suivi-ecran attente_validation --motif "<raisons>"`, section 7, dernier message `ATTENTE VALIDATION — v8-suivi-ecran — <raisons>`.
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

**Gain.** Un échange dure une semaine et traverse quatre étapes : sans écran qui le dit, l'utilisateur s'inquiète ou oublie — et dans les deux cas il n'envoie pas.

**Fonctionnalités.** Liste « mes échanges » par état ; frise des étapes avec les dates réelles et la prochaine échéance ; action attendue mise en avant (« à toi d'envoyer », « confirme la réception ») ; notifications et e-mails de relance ; ouverture d'un litige depuis l'écran, sans aller la chercher.

**Tenants — ce qu'il faut avant.** Expédition, offre, notifications.

**Aboutissants — ce que ça ouvre.** Taux d'aboutissement des échanges.

**Dépend de :**
- `v8-expedition` — Envoyer, suivre, recevoir

## 3. Mission

1. Écran « mes échanges » et frise d'étapes, avec l'action attendue en évidence.
2. Notifications et e-mails branchés sur les relances serveur, une par étape.
3. Ouverture de litige accessible depuis l'écran de suivi.
4. Tests d'écran : échange à chaque étape, échange en retard, échange en litige, affichage sur téléphone.

## 4. Risques & pièges

La notification est le produit ici : trop, elle est coupée ; trop peu, l'échange meurt. Une seule relance par étape, plus un récapitulatif. L'écran doit rester lisible sur un téléphone (PWA, v6-pwa), c'est là qu'il sera consulté.

## 5. Livrables — définition de « fini »

- écran de suivi complet sur téléphone et ordinateur
- relances branchées et limitées
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
- `maquette` — Conforme à la maquette
- `doc_tech` — Doc technique (CLAUDE.md, docs/)
- `release_uat` — Recette locale sur chimera
- `release_prod` — Livré en PROD (preuve)
- `backlog` — BACKLOG.md et état à jour
- `compte_rendu` — Compte rendu dans le suivi

```bash
python3 docs/roadmap/suivi.py tache v8-suivi-ecran <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu v8-suivi-ecran --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut v8-suivi-ecran <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "v8-suivi-ecran: …" && git push -u origin roadmap/v8-suivi-ecran
bash scripts/ouvrir-pr.sh roadmap/v8-suivi-ecran   # ouvre la PR, ou echoue en disant pourquoi
```

**La PR n'est pas optionnelle** : sans elle, la CI ne tourne pas sur ton travail, et c'est la CI qui fait foi. Si `ouvrir-pr.sh` sort en erreur, tu NE conclus PAS que c'est sans importance : tu nommes le manque dans ton compte rendu et dans ton dernier message.

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

