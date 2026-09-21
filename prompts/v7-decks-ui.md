# Lot `v7-decks-ui` — Constructeur de deck

> Prompt GÉNÉRÉ depuis `docs/roadmap/roadmap.json` par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Suivi : `docs/roadmap/ROADMAP.html` (onglets Roadmap et Maquette) · processus : `docs/roadmap/PROCESSUS.md`.

**P0** · piste Jeu — decks et parties · couloir **CH5** — Decks — écrans, recherche, assistant (**chimera**) · prévu du 29 sept. au 2 oct. · jalon **MVP en UAT** · taille M · complexité 3/5 · difficulté 2/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur chimera**. Lance `hostname -s` :

- **Chimaera (dans la WSL)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier v7-decks-ui`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur chimera :

```bash
ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- bash -lc "cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-v7-decks-ui -b roadmap/v7-decks-ui origin/main && mkdir -p ~/dev/logs"'
```

3. Lance le lot autonome : par le mécanisme de lots de chimera (`~/dev/lots/launch-lot.sh`, étendu au dépôt `~/dev/pokeboy` par le lot `v0-flotte`), **lancé côté Windows** — un `nohup` interne à la WSL meurt avec la session. Journal : `~/dev/logs/v7-decks-ui.log`.
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/v7-decks-ui` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 7 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy (WSL Ubuntu-24.04, utilisateur upgreg)`. Travaille dans ton **worktree** `../wt-v7-decks-ui`, branche `roadmap/v7-decks-ui` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier v7-decks-ui
python3 docs/roadmap/suivi.py demarrer v7-decks-ui --machine "$(hostname -s)" --branche roadmap/v7-decks-ui
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut v7-decks-ui attente_validation --motif "<raisons>"`, section 7, dernier message `ATTENTE VALIDATION — v7-decks-ui — <raisons>`.
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

**Gain.** Construire un deck doit être agréable, sinon personne ne joue.

**Fonctionnalités.** Deux modes : **assistant IA** (types privilégiés, répartition par type, nombre de cartes avec 60 par défaut, énergies automatiques ou fixées, style de jeu, inclusion des lignes d'évolution, des cartes spéciales V/ex/GX/VMAX, des Méga et des Dresseurs) et **manuel** (recherche par nom, numéro, extension, type, rareté, avec ajout en un clic). Deux colonnes : options ou recherche à gauche, deck à droite avec contrôle de légalité en direct, raison du choix pour chaque carte proposée par l'IA, retrait d'un exemplaire ou de la carte entière, sauvegarde, duplication, suppression, export de la liste.

**Tenants — ce qu'il faut avant.** API des decks, design system.

**Aboutissants — ce que ça ouvre.** File d'attente, partie.

**Dépend de :**
- `v7-decks-api` — Decks : création, légalité et sauvegarde, uniquement avec ses cartes
- `v7-decks-recherche` — Recherche de cartes du constructeur : trouver une carte en trois secondes

## 3. Mission

1. Page `/jeu/decks` et `/jeu/decks/[id]` conformes à la maquette du jeu.
2. Glisser-déposer ou clic pour ajouter, **retirer un exemplaire** et **retirer complètement une carte du deck** (bouton dédié, pas seulement le décrément), compteurs en direct, messages de légalité.
3. Tests d'interface et un e2e « construire un deck légal à partir de sa collection ».
4. Sur « Mes decks » : dupliquer et **supprimer un deck**, avec confirmation ; un deck supprimé ne doit pas disparaître d'une partie en cours.
5. Réaction au changement de collection : à chaque suppression d'exemplaire, les decks concernés passent en « à compléter » avec l'alerte et les trois issues ; une partie en cours n'est pas affectée.

## 4. Risques & pièges

Une carte retirée de la collection (vendue, échangée, supprimée) doit **alerter dans le deck concerné** : le deck reste modifiable mais n'est plus jouable tant qu'il n'est pas complété, avec trois issues proposées (remplacer par une carte équivalente possédée, retirer du deck, voir la carte). Ne jamais corriger un deck en silence.

## 5. Livrables — définition de « fini »

- constructeur de deck utilisable
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
python3 docs/roadmap/suivi.py tache v7-decks-ui <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu v7-decks-ui --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut v7-decks-ui <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "v7-decks-ui: …" && git push -u origin roadmap/v7-decks-ui && gh pr create --fill
```

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

