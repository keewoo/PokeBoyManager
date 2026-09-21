# Lot `v7-regles-cartes` — Cartes Dresseur, talents et états spéciaux

> Prompt GÉNÉRÉ depuis `docs/roadmap/roadmap.json` par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Suivi : `docs/roadmap/ROADMAP.html` (onglets Roadmap et Maquette) · processus : `docs/roadmap/PROCESSUS.md`.

**P0** · piste Jeu — decks et parties · couloir **DA1** — API, comptes & données (**devAI**) · prévu du 11 janv. au 5 févr. · jalon **En ligne** · taille L · complexité 5/5 · difficulté 5/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur devAI**. Lance `hostname -s` :

- **Mac-mini-de-keewoo (hostname -s)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier v7-regles-cartes`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur devAI :

```bash
ssh devai 'cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-v7-regles-cartes -b roadmap/v7-regles-cartes origin/main && mkdir -p ~/dev/logs'
```

3. Lance le lot autonome : `ssh devai 'cd ~/dev/wt-v7-regles-cartes && nohup claude -p --dangerously-skip-permissions < prompts/v7-regles-cartes.md > ~/dev/logs/v7-regles-cartes.log 2>&1 &'` (toutes les sorties redirigées : ssh rend la main).
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/v7-regles-cartes` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 7 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy`. Travaille dans ton **worktree** `../wt-v7-regles-cartes`, branche `roadmap/v7-regles-cartes` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier v7-regles-cartes
python3 docs/roadmap/suivi.py demarrer v7-regles-cartes --machine "$(hostname -s)" --branche roadmap/v7-regles-cartes
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut v7-regles-cartes attente_validation --motif "<raisons>"`, section 7, dernier message `ATTENTE VALIDATION — v7-regles-cartes — <raisons>`.
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

**Gain.** Décision de JF (19/09) : le jeu doit se jouer pour de vrai — sans Dresseurs ni talents, ce n'est pas le JCC Pokémon.

**Fonctionnalités.** Objets, Supporters (un par tour), Stades, Outils ; talents (déclenchés, passifs, une fois par tour) ; états spéciaux (Empoisonné, Brûlé, Endormi, Paralysé, Confus) avec leur résolution entre les tours ; effets d'attaque (soin, défausse, pioche, recherche, changement de Pokémon actif, protection).

**Tenants — ce qu'il faut avant.** Socle du moteur, catalogue complet (textes des cartes en base).

**Aboutissants — ce que ça ouvre.** Decks réellement jouables, parties complètes.

**Dépend de :**
- `v7-regles-moteur` — Moteur de règles du jeu (socle) : zones, tour, attaques, récompenses

**Décision D9** (avant le 19 sept.) : Périmètre des règles v1 du moteur de jeu : proposition — Pokémon de base et évolutions, énergies, attaques, faiblesse/résistance, retraite, banc, récompenses, conditions de victoire ; dresseurs, talents et états spéciaux en v2. — lis la décision prise dans `etat.json` (`decisions_prises`) et applique-la à la lettre.

## 3. Mission

1. Registre d'effets : un identifiant d'effet par comportement (pioche, soin, recherche, défausse, changement de position, protection, condition), et une table qui relie chaque carte du catalogue à ses effets.
2. Analyse des textes du catalogue pour rattacher automatiquement les cartes aux effets connus, avec revue manuelle des cas ambigus ; ce qui n'est pas reconnu reste « non pris en charge ».
3. États spéciaux et leur résolution entre les tours ; règles des Supporters (un par tour), des Stades (un seul en jeu) et des Outils (un par Pokémon).
4. Talents : déclenchés, passifs, une fois par tour ; fenêtres d'interruption gérées par le socle.
5. Couverture mesurée : part des cartes du catalogue jouables, et 100 % des cartes des decks de test ; au moins 200 tests d'effets.
6. Le contrôle de légalité d'un deck refuse toute carte non prise en charge, en le disant clairement.

## 4. Risques & pièges

Chaque carte a son texte : on ne peut pas tout implémenter d'un coup pour 21 900 cartes. **Un effet non implémenté n'est jamais approximé** : la carte est marquée « non prise en charge en jeu » et le contrôle de légalité du deck la refuse en l'expliquant. La couverture se mesure et progresse par familles d'effets.

## 5. Livrables — définition de « fini »

- registre d'effets + rattachement des cartes
- couverture chiffrée
- ≥ 200 tests d'effets
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
python3 docs/roadmap/suivi.py tache v7-regles-cartes <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu v7-regles-cartes --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut v7-regles-cartes <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "v7-regles-cartes: …" && git push -u origin roadmap/v7-regles-cartes && gh pr create --fill
```

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

