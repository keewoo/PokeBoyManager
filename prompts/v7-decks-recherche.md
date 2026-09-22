# Lot `v7-decks-recherche` — Recherche de cartes du constructeur : trouver une carte en trois secondes

> Prompt GÉNÉRÉ depuis `docs/roadmap/roadmap.json` par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Suivi : `docs/roadmap/ROADMAP.html` (onglets Roadmap et Maquette) · processus : `docs/roadmap/PROCESSUS.md`.

**P0** · piste Jeu — decks et parties · couloir **CH5** — Decks — écrans, recherche, assistant (**chimera**) · prévu du 22 sept. au 25 sept. · jalon **MVP en UAT** · taille M · complexité 3/5 · difficulté 2/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur chimera**. Lance `hostname -s` :

- **Chimaera (dans la WSL)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier v7-decks-recherche`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur chimera :

```bash
ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- bash -lc "cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-v7-decks-recherche -b roadmap/v7-decks-recherche origin/main && mkdir -p ~/dev/logs"'
```

3. Lance le lot autonome : par le mécanisme de lots de chimera (`~/dev/lots/launch-lot.sh`, étendu au dépôt `~/dev/pokeboy` par le lot `v0-flotte`), **lancé côté Windows** — un `nohup` interne à la WSL meurt avec la session. Journal : `~/dev/logs/v7-decks-recherche.log`.
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/v7-decks-recherche` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 7 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy (WSL Ubuntu-24.04, utilisateur upgreg)`. Travaille dans ton **worktree** `../wt-v7-decks-recherche`, branche `roadmap/v7-decks-recherche` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier v7-decks-recherche
python3 docs/roadmap/suivi.py demarrer v7-decks-recherche --machine "$(hostname -s)" --branche roadmap/v7-decks-recherche
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut v7-decks-recherche attente_validation --motif "<raisons>"`, section 7, dernier message `ATTENTE VALIDATION — v7-decks-recherche — <raisons>`.
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

**Gain.** Construire un deck à la main n'est supportable que si la carte cherchée apparaît immédiatement — c'est la brique la plus utilisée du module.

**Fonctionnalités.** Recherche par nom (FR/EN, accents ignorés), numéro (`236/217`, `XY121`, `TG05`), extension, type, rareté, PV, coût d'attaque ; filtres cumulables ; tri (valeur, nom, numéro, date d'ajout) ; bascule « seulement mes cartes » et « doublons » ; navigation et ajout au clavier ; pagination par curseur.

**Tenants — ce qu'il faut avant.** Collection, recherche catalogue existante.

**Aboutissants — ce que ça ouvre.** Constructeur de deck, assistant IA.

**Dépend de :**
- `v4-collection` — Page collection : grille, filtres, tris et valeur totale

## 3. Mission

1. Route `GET /me/decks/cards?` : facettes (type, rareté, extension, PV, possédées, doublons), tri, curseur ; réponse enrichie du nombre possédé et déjà utilisé dans le deck courant.
2. Index et mesures : 150 ms au 95e centile sur un jeu de 22 000 cartes et 5 000 exemplaires, chiffré dans le compte rendu.
3. Clavier : flèches pour parcourir, Entrée pour ajouter, Échap pour fermer ; testé.
4. Tests d'accès croisé : les cartes d'un autre utilisateur ne sont jamais renvoyées.

## 4. Risques & pièges

Performance : la recherche porte sur 22 000 cartes et sur la collection de l'utilisateur — viser moins de 150 ms, index trigram et index composés, mesurés. Ne jamais proposer une carte que l'utilisateur ne possède pas quand le filtre le dit.

## 5. Livrables — définition de « fini »

- route de recherche du constructeur
- mesures de performance
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
python3 docs/roadmap/suivi.py tache v7-decks-recherche <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu v7-decks-recherche --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut v7-decks-recherche <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "v7-decks-recherche: …" && git push -u origin roadmap/v7-decks-recherche
bash scripts/ouvrir-pr.sh roadmap/v7-decks-recherche   # ouvre la PR, ou echoue en disant pourquoi
```

**La PR n'est pas optionnelle** : sans elle, la CI ne tourne pas sur ton travail, et c'est la CI qui fait foi. Si `ouvrir-pr.sh` sort en erreur, tu NE conclus PAS que c'est sans importance : tu nommes le manque dans ton compte rendu et dans ton dernier message.

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

