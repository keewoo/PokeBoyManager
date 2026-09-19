# Lot `v7-file-attente` — File d'attente et appariement de deux joueurs

> Prompt GÉNÉRÉ depuis `docs/roadmap/roadmap.json` par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Suivi : `docs/roadmap/ROADMAP.html` (onglets Roadmap et Maquette) · processus : `docs/roadmap/PROCESSUS.md`.

**P0** · piste Jeu — decks et parties · couloir **DA1** — API, comptes & données (**devAI**) · prévu du 8 févr. au 12 févr. · jalon **En ligne** · taille M · complexité 3/5 · difficulté 3/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur devAI**. Lance `hostname -s` :

- **Mac-mini-de-keewoo (hostname -s)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier v7-file-attente`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur devAI :

```bash
ssh devai 'cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-v7-file-attente -b roadmap/v7-file-attente origin/main && mkdir -p ~/dev/logs'
```

3. Lance le lot autonome : `ssh devai 'cd ~/dev/wt-v7-file-attente && nohup claude -p --dangerously-skip-permissions < prompts/v7-file-attente.md > ~/dev/logs/v7-file-attente.log 2>&1 &'` (toutes les sorties redirigées : ssh rend la main).
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/v7-file-attente` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 7 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy`. Travaille dans ton **worktree** `../wt-v7-file-attente`, branche `roadmap/v7-file-attente` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier v7-file-attente
python3 docs/roadmap/suivi.py demarrer v7-file-attente --machine "$(hostname -s)" --branche roadmap/v7-file-attente
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut v7-file-attente attente_validation --motif "<raisons>"`, section 7, dernier message `ATTENTE VALIDATION — v7-file-attente — <raisons>`.
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

**Gain.** Le point d'entrée du jeu : on choisit son deck, on entre dans la file, et la partie démarre dès qu'un adversaire est prêt.

**Fonctionnalités.** Entrer dans la file avec un deck légal, voir l'attente, annuler ; appariement dès que deux joueurs sont prêts ; création de la partie et redirection des deux joueurs ; **file réservée aux comptes invités** (D11 : espace privé).

**Tenants — ce qu'il faut avant.** Moteur de règles, decks ; D11.

**Aboutissants — ce que ça ouvre.** Partie en temps réel.

**Dépend de :**
- `v7-regles-cartes` — Cartes Dresseur, talents et états spéciaux
- `v7-decks-api` — Decks : création, légalité et sauvegarde, uniquement avec ses cartes

**Décision D11** (avant le 9 janv.) : Cadre du jeu en ligne (propriété intellectuelle) : partie privée entre comptes invités seulement, ou file d'attente ouverte à tous les inscrits ? Sans revenu ni publicité dans les deux cas. — lis la décision prise dans `etat.json` (`decisions_prises`) et applique-la à la lettre.

## 3. Mission

1. Table `matchmaking_queue` et `matches` ; entrée, sortie, appariement atomique, expiration.
2. Création de la partie : tirage du premier joueur, mains de départ, 6 récompenses, mulligan selon les règles.
3. Tests : deux joueurs appariés une seule fois, annulation, joueur disparu.

## 4. Risques & pièges

Deux appariements simultanés pour le même joueur : l'entrée en partie est atomique (verrou en base). Un joueur qui ferme l'onglet dans la file en sort automatiquement.

## 5. Livrables — définition de « fini »

- file d'attente et appariement testés
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
- `maquette` — Conforme à la maquette (sans objet : back-end ; écran porté par v7-partie-ui)
- `doc_tech` — Doc technique (CLAUDE.md, docs/)
- `release_uat` — Recette locale sur chimera
- `release_prod` — Livré en PROD (preuve)
- `backlog` — BACKLOG.md et état à jour
- `compte_rendu` — Compte rendu dans le suivi

```bash
python3 docs/roadmap/suivi.py tache v7-file-attente <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu v7-file-attente --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut v7-file-attente <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "v7-file-attente: …" && git push -u origin roadmap/v7-file-attente && gh pr create --fill
```

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

