# Lot `v8-litiges` — Quand ça se passe mal

> Prompt GÉNÉRÉ depuis `docs/roadmap/roadmap.json` par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Suivi : `docs/roadmap/ROADMAP.html` (onglets Roadmap et Maquette) · processus : `docs/roadmap/PROCESSUS.md`.

**P0** · piste Échanges entre collectionneurs · couloir **DA4** — Échanges — règles, transfert & argent (**devAI**) · prévu du 8 févr. au 12 févr. · jalon **En ligne** · taille L · complexité 3/5 · difficulté 4/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur devAI**. Lance `hostname -s` :

- **Mac-mini-de-keewoo (hostname -s)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier v8-litiges`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur devAI :

```bash
ssh devai 'cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-v8-litiges -b roadmap/v8-litiges origin/main && mkdir -p ~/dev/logs'
```

3. Lance le lot autonome : `ssh devai 'cd ~/dev/wt-v8-litiges && nohup claude -p --dangerously-skip-permissions < prompts/v8-litiges.md > ~/dev/logs/v8-litiges.log 2>&1 &'` (toutes les sorties redirigées : ssh rend la main).
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/v8-litiges` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 7 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy`. Travaille dans ton **worktree** `../wt-v8-litiges`, branche `roadmap/v8-litiges` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier v8-litiges
python3 docs/roadmap/suivi.py demarrer v8-litiges --machine "$(hostname -s)" --branche roadmap/v8-litiges
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut v8-litiges attente_validation --motif "<raisons>"`, section 7, dernier message `ATTENTE VALIDATION — v8-litiges — <raisons>`.
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

**Gain.** Un dispositif d'échange ne se juge pas sur les échanges qui marchent : il se juge sur ce qu'il fait le jour où une carte n'arrive pas.

**Fonctionnalités.** Ouverture d'un litige par l'une des parties dans une fenêtre définie ; dossier constitué automatiquement (offre figée, valeurs archivées, photos d'emballage, suivi, fil de discussion) ; arbitrage par un opérateur avec motif écrit ; issues — en faveur de l'un, des deux, ou sans suite ; conséquences sur la réputation et sur les plafonds ; gel du compte en cas de récidive.

**Tenants — ce qu'il faut avant.** Expédition, offre figée, réputation.

**Aboutissants — ce que ça ouvre.** La décision D12 se tranche avec les chiffres produits par ce lot.

**Dépend de :**
- `v8-expedition` — Envoyer, suivre, recevoir

## 3. Mission

1. Dossier de litige constitué automatiquement, consultable par les deux parties et par l'opérateur.
2. Écran d'arbitrage réservé à l'opérateur, décision motivée obligatoire, conservation de la trace.
3. Conséquences appliquées : réputation, plafonds, gel — et notification écrite aux deux parties.
4. Indicateurs exportables : taux de litige, valeur moyenne en jeu, délai moyen de résolution.

## 4. Risques & pièges

L'arbitrage est un travail humain : on le dimensionne, on ne l'automatise pas. Une décision doit être motivée et conservée — c'est elle qui sera opposée à un parent mécontent. Le taux de litige mesuré ici est la donnée qui décidera, ou non, du mode garant : il doit être exploitable, pas seulement affiché.

## 5. Livrables — définition de « fini »

- litige de bout en bout, arbitré et tracé
- indicateurs de litige exportables (entrée de la décision D12)
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
python3 docs/roadmap/suivi.py tache v8-litiges <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu v8-litiges --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut v8-litiges <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "v8-litiges: …" && git push -u origin roadmap/v8-litiges
bash scripts/ouvrir-pr.sh roadmap/v8-litiges   # ouvre la PR, ou echoue en disant pourquoi
```

**La PR n'est pas optionnelle** : sans elle, la CI ne tourne pas sur ton travail, et c'est la CI qui fait foi. Si `ouvrir-pr.sh` sort en erreur, tu NE conclus PAS que c'est sans importance : tu nommes le manque dans ton compte rendu et dans ton dernier message.

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

