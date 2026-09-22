# Lot `v7-decks-api` — Decks : création, légalité et sauvegarde, uniquement avec ses cartes

> Prompt GÉNÉRÉ depuis `docs/roadmap/roadmap.json` par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Suivi : `docs/roadmap/ROADMAP.html` (onglets Roadmap et Maquette) · processus : `docs/roadmap/PROCESSUS.md`.

**P0** · piste Jeu — decks et parties · couloir **DA3** — Decks — API, légalité, synchronisation (**devAI**) · prévu du 22 sept. au 25 sept. · jalon **MVP en UAT** · taille M · complexité 3/5 · difficulté 2/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur devAI**. Lance `hostname -s` :

- **Mac-mini-de-keewoo (hostname -s)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier v7-decks-api`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur devAI :

```bash
ssh devai 'cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-v7-decks-api -b roadmap/v7-decks-api origin/main && mkdir -p ~/dev/logs'
```

3. Lance le lot autonome : `ssh devai 'cd ~/dev/wt-v7-decks-api && nohup claude -p --dangerously-skip-permissions < prompts/v7-decks-api.md > ~/dev/logs/v7-decks-api.log 2>&1 &'` (toutes les sorties redirigées : ssh rend la main).
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/v7-decks-api` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 7 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy`. Travaille dans ton **worktree** `../wt-v7-decks-api`, branche `roadmap/v7-decks-api` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier v7-decks-api
python3 docs/roadmap/suivi.py demarrer v7-decks-api --machine "$(hostname -s)" --branche roadmap/v7-decks-api
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut v7-decks-api attente_validation --motif "<raisons>"`, section 7, dernier message `ATTENTE VALIDATION — v7-decks-api — <raisons>`.
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

**Gain.** Un joueur construit ses decks à partir de sa collection réelle — c'est ce qui rend le jeu personnel.

**Fonctionnalités.** Plusieurs decks par joueur, nom, duplication, suppression ; contrôle de légalité (60 cartes, maximum 4 exemplaires d'une même carte par son nom) ; **Énergies de base fournies en quantité illimitée**, **Énergies spéciales traitées comme des cartes ordinaires** (il faut les posséder et la règle des 4 s'applique) ; un deck ne peut contenir que des exemplaires possédés, et signale ce qui manque.

**Tenants — ce qu'il faut avant.** Collection, moteur de règles ; D10.

**Aboutissants — ce que ça ouvre.** Constructeur de deck, proposition par l'IA, file d'attente.

**Dépend de :**
- `v4-collection` — Page collection : grille, filtres, tris et valeur totale

**Décision D10** (avant le 19 sept.) : Un deck n'utilise que les cartes possédées — faut-il faire une exception pour les Énergies de base (illimitées, comme dans les decks papier) ? Proposition : oui, les Énergies de base sont fournies. — lis la décision prise dans `etat.json` (`decisions_prises`) et applique-la à la lettre.

## 3. Mission

1. Tables `decks` et `deck_cards` (référence à l'exemplaire possédé), routes CRUD filtrées par `user_id`.
2. Service de légalité : 60 cartes, règle des 4 exemplaires, Énergies de base illimitées et non décomptées de la collection, Énergies spéciales soumises à possession et à la règle des 4, cartes non possédées, et un rapport lisible de ce qui bloque.
3. Revalidation d'un deck quand la collection change ; tests d'accès croisé.

## 4. Risques & pièges

Une carte vendue ou supprimée de la collection casse un deck existant : le deck reste lisible mais devient injouable, avec la raison affichée. Une carte dont l'effet n'est pas encore pris en charge par le moteur (`v7-regles-cartes`) est refusée dans un deck, en l'expliquant.

## 5. Livrables — définition de « fini »

- API decks + légalité testée
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
python3 docs/roadmap/suivi.py tache v7-decks-api <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu v7-decks-api --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut v7-decks-api <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "v7-decks-api: …" && git push -u origin roadmap/v7-decks-api
bash scripts/ouvrir-pr.sh roadmap/v7-decks-api   # ouvre la PR, ou echoue en disant pourquoi
```

**La PR n'est pas optionnelle** : sans elle, la CI ne tourne pas sur ton travail, et c'est la CI qui fait foi. Si `ouvrir-pr.sh` sort en erreur, tu NE conclus PAS que c'est sans importance : tu nommes le manque dans ton compte rendu et dans ton dernier message.

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

