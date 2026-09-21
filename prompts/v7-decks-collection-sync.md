# Lot `v7-decks-collection-sync` — Une carte quitte la collection : les decks le disent tout de suite

> Prompt GÉNÉRÉ depuis `docs/roadmap/roadmap.json` par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Suivi : `docs/roadmap/ROADMAP.html` (onglets Roadmap et Maquette) · processus : `docs/roadmap/PROCESSUS.md`.

**P0** · piste Jeu — decks et parties · couloir **DA3** — Decks — API, légalité, synchronisation (**devAI**) · prévu du 5 oct. au 8 oct. · jalon **MVP en UAT** · taille M · complexité 3/5 · difficulté 3/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur devAI**. Lance `hostname -s` :

- **Mac-mini-de-keewoo (hostname -s)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier v7-decks-collection-sync`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur devAI :

```bash
ssh devai 'cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-v7-decks-collection-sync -b roadmap/v7-decks-collection-sync origin/main && mkdir -p ~/dev/logs'
```

3. Lance le lot autonome : `ssh devai 'cd ~/dev/wt-v7-decks-collection-sync && nohup claude -p --dangerously-skip-permissions < prompts/v7-decks-collection-sync.md > ~/dev/logs/v7-decks-collection-sync.log 2>&1 &'` (toutes les sorties redirigées : ssh rend la main).
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/v7-decks-collection-sync` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 7 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy`. Travaille dans ton **worktree** `../wt-v7-decks-collection-sync`, branche `roadmap/v7-decks-collection-sync` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier v7-decks-collection-sync
python3 docs/roadmap/suivi.py demarrer v7-decks-collection-sync --machine "$(hostname -s)" --branche roadmap/v7-decks-collection-sync
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut v7-decks-collection-sync attente_validation --motif "<raisons>"`, section 7, dernier message `ATTENTE VALIDATION — v7-decks-collection-sync — <raisons>`.
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

**Gain.** Demande explicite de JF : une carte vendue, échangée ou supprimée ne doit pas laisser un deck faussement jouable.

**Fonctionnalités.** À chaque changement de collection, les decks concernés passent en « à compléter » ; alerte dans le deck et notification au joueur ; trois issues proposées — remplacer par une carte équivalente possédée, retirer du deck, voir la carte ; historique des modifications du deck.

**Tenants — ce qu'il faut avant.** Modèle de deck, légalité, collection.

**Aboutissants — ce que ça ouvre.** Confiance dans la liste de decks.

**Dépend de :**
- `v7-decks-legalite` — Contrôle de légalité d'un deck, expliqué ligne par ligne

## 3. Mission

1. Déclencheur applicatif sur suppression ou mise en vente d'un exemplaire : marquage des decks concernés, sans les modifier.
2. Suggestions de remplacement classées, prises dans la collection, avec la raison ; une seule requête, pas d'appel IA.
3. Notification au joueur (en-tête et liste des decks) ; état « à compléter » visible partout où le deck apparaît.
4. Tests : vente d'une carte utilisée dans deux decks, doublon retiré mais exemplaire restant (le deck reste jouable), partie en cours non affectée.

## 4. Risques & pièges

**Jamais de correction silencieuse** : on ne retire pas automatiquement la carte du deck. Une partie en cours n'est pas affectée (le deck y est figé au démarrage). Suggestion de remplacement : même type, même rôle, coût d'attaque proche — et uniquement parmi les cartes possédées.

## 5. Livrables — définition de « fini »

- alerte et suggestions testées
- aucun deck modifié en silence
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
python3 docs/roadmap/suivi.py tache v7-decks-collection-sync <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu v7-decks-collection-sync --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut v7-decks-collection-sync <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "v7-decks-collection-sync: …" && git push -u origin roadmap/v7-decks-collection-sync && gh pr create --fill
```

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

