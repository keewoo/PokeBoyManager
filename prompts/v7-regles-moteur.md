# Lot `v7-regles-moteur` — Moteur de règles du jeu, côté serveur, rejouable et testé

> Prompt GÉNÉRÉ depuis `docs/roadmap/roadmap.json` par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Suivi : `docs/roadmap/ROADMAP.html` (onglets Roadmap et Maquette) · processus : `docs/roadmap/PROCESSUS.md`.

**P0** · piste Jeu — decks et parties · couloir **DA1** — API, comptes & données (**devAI**) · prévu du 30 nov. au 18 déc. · jalon **En ligne** · taille L · complexité 5/5 · difficulté 4/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur devAI**. Lance `hostname -s` :

- **Mac-mini-de-keewoo (hostname -s)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier v7-regles-moteur`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur devAI :

```bash
ssh devai 'cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-v7-regles-moteur -b roadmap/v7-regles-moteur origin/main && mkdir -p ~/dev/logs'
```

3. Lance le lot autonome : `ssh devai 'cd ~/dev/wt-v7-regles-moteur && nohup claude -p --dangerously-skip-permissions < prompts/v7-regles-moteur.md > ~/dev/logs/v7-regles-moteur.log 2>&1 &'` (toutes les sorties redirigées : ssh rend la main).
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/v7-regles-moteur` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 7 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy`. Travaille dans ton **worktree** `../wt-v7-regles-moteur`, branche `roadmap/v7-regles-moteur` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier v7-regles-moteur
python3 docs/roadmap/suivi.py demarrer v7-regles-moteur --machine "$(hostname -s)" --branche roadmap/v7-regles-moteur
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut v7-regles-moteur attente_validation --motif "<raisons>"`, section 7, dernier message `ATTENTE VALIDATION — v7-regles-moteur — <raisons>`.
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

**Gain.** Le cœur du jeu : sans un moteur qui applique les règles et fait autorité, il n'y a ni partie honnête ni reprise après coupure.

**Fonctionnalités.** État complet d'une partie (zones : actif, banc, main, pioche, défausse, récompenses, énergies attachées), déroulé d'un tour (pioche, pose, évolution, énergie, attaque, retraite), dégâts avec faiblesse et résistance, mises KO, récompenses, conditions de victoire, abandon.

**Tenants — ce qu'il faut avant.** Cartes, attaques et faiblesses déjà en base (catalogue complet) ; D9.

**Aboutissants — ce que ça ouvre.** File d'attente, temps réel, plateau, parties.

**Dépend de :**
- aucune

**Décision D9** (avant le 27 nov.) : Périmètre des règles v1 du moteur de jeu : proposition — Pokémon de base et évolutions, énergies, attaques, faiblesse/résistance, retraite, banc, récompenses, conditions de victoire ; dresseurs, talents et états spéciaux en v2. — lis la décision prise dans `etat.json` (`decisions_prises`) et applique-la à la lettre.

## 3. Mission

1. Modéliser l'état d'une partie (structures pures, sérialisable en JSON) et le journal d'actions numéroté.
2. Implémenter les actions légales d'un tour et la résolution des attaques (dégâts, faiblesse ×2, résistance, KO, récompenses) ; toute action illégale est refusée avec sa raison.
3. Rejouabilité : rejouer le journal reconstruit exactement le même état (test de propriété).
4. Couverture : au moins 150 cas de règles, dont les cas limites (plus de cartes à piocher = défaite, banc plein, retraite sans énergie, KO simultané).
5. Interface claire pour la v2 (dresseurs, talents, états spéciaux) sans réécriture.

## 4. Risques & pièges

Périmètre (D9) : dresseurs, talents et états spéciaux ne sont PAS dans la v1 — le moteur doit être écrit pour les accueillir sans être réécrit. Un moteur de règles se teste par des centaines de cas : chaque règle a son test, et toute partie est rejouable depuis son journal d'actions.

## 5. Livrables — définition de « fini »

- moteur pur + journal rejouable
- ≥ 150 tests de règles verts
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
python3 docs/roadmap/suivi.py tache v7-regles-moteur <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu v7-regles-moteur --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut v7-regles-moteur <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "v7-regles-moteur: …" && git push -u origin roadmap/v7-regles-moteur && gh pr create --fill
```

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

