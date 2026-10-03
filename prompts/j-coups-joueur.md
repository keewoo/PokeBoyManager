# Lot `j-coups-joueur` — Coups du joueur : la partie se joue vraiment, de la mise en place à la victoire

> Prompt GÉNÉRÉ depuis `docs/roadmap/jeu/plan/` (via `jeu.json`) par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Plan du jeu : `docs/roadmap/jeu/BACKLOG-JEU.md` · onglet « Backlog du jeu » de `docs/roadmap/ROADMAP.html`.

**P0** · piste Serveur de parties · couloir **J-SRV** (**chimera**) · jalon **J1 — Deux joueurs jouent une partie honnête** · palier 14 · taille L · complexité 4/5 · difficulté 4/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur chimera**. Lance `hostname -s` :

- **Chimaera (dans la WSL)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier j-coups-joueur`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur chimera :

```bash
ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- bash -lc "cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-j-coups-joueur -b roadmap/j-coups-joueur origin/main && mkdir -p ~/dev/logs"'
```

3. Lance le lot autonome : par le mécanisme de lots de chimera (`~/dev/lots/launch-lot.sh`, étendu au dépôt `~/dev/pokeboy` par le lot `v0-flotte`), **lancé côté Windows** — un `nohup` interne à la WSL meurt avec la session. Journal : `~/dev/logs/j-coups-joueur.log`.
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/j-coups-joueur` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 8 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy (WSL Ubuntu-24.04, utilisateur upgreg)`. Travaille dans ton **worktree** `../wt-j-coups-joueur`, branche `roadmap/j-coups-joueur` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier j-coups-joueur
python3 docs/roadmap/suivi.py demarrer j-coups-joueur --machine "$(hostname -s)" --branche roadmap/j-coups-joueur
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut j-coups-joueur attente_validation --motif "<raisons>"`, section 8, dernier message `ATTENTE VALIDATION — j-coups-joueur — <raisons>`.
- Tu n'accordes **jamais** toi-même une dérogation.

## 1. Cadre — relire avant d'agir

| Document | Pourquoi |
|---|---|
| `CLAUDE.md` | règles du dépôt, carte des fiches, « où écrire quoi » |
| `docs/CODE.md` | structure du monorepo, commandes, tests, définition du « fini » |
| `docs/roadmap/jeu/BACKLOG-JEU.md` | le plan du jeu : principes, jalons, décisions `DJ*`, fiches des 67 lots |
| `docs/jeu/REGLES.md` | le corpus de règles qui fait foi (créé par `j-regles-reference`) : tout test de règle cite son identifiant `R-x.y` |
| `docs/ARCHITECTURE.md` | données, catalogue, decks — ce que le jeu consomme |
| `~/.claude/CLAUDE.md` de la machine | règles de la flotte (construire ≠ servir, Python 3.12, WSL) |

Le cadre l'emporte sur ce prompt : en cas de contradiction, passe en `attente_validation` avec la contradiction en motif.

## 1 bis. Le dépôt est graphifié — interroge le graphe avant de lire dix fichiers

Le code, la documentation et les schémas de ce dépôt sont indexés par **Graphify**. Dans ton worktree, `graphify-out/` n'existe pas encore (il n'est pas versionné) : construis-le, puis pose tes questions au graphe.

```bash
export PATH=$HOME/.local/bin:$PATH   # sur la flotte, graphify vit là
graphify update .                     # ~5-25 s, sans LLM
graphify query "<ta question>"      # qui appelle quoi, où vit telle règle
graphify explain "<symbole>"        # un nœud et ses voisins
graphify affected "<symbole>"       # ce qui dépend de ce que tu vas modifier
```

Si le serveur MCP `graphify` est chargé dans ta session, `query_graph`, `get_neighbors` et `shortest_path` font la même chose. Le graphe **oriente**, il ne prouve pas : ouvre le fichier réel avant d'affirmer qu'une ligne existe. Mode d'emploi : `docs/CODE.md` § « Chercher dans le dépôt ».

## 2. Contexte

**Jalon J1 — Deux joueurs jouent une partie honnête.** Une partie complète se joue de bout en bout entre deux navigateurs, avec des Pokémon, des énergies et des attaques simples — sans Dresseur, sans talent, sans état spécial. Laid mais juste : les règles sont appliquées, la partie reprend après un F5, et le vainqueur est le bon.

**Principes du jeu — ils valent pour ce lot comme pour tous les autres :**

- **Le serveur fait autorité.** Le client n'est qu'un écran : il n'apprend jamais la main de l'adversaire ni l'ordre de la pioche, et toute action qu'il propose est rejouée et validée côté serveur.
- **Un effet non implémenté n'est jamais approximé** (D9). Une carte dont l'effet n'est pas scripté et testé est refusée à la construction du deck, en disant pourquoi. Le jeu préfère dire « je ne sais pas jouer cette carte » que de la jouer de travers.
- **Tout est rejouable.** Une partie est un état initial, une graine d'aléatoire et un journal d'actions numéroté. Rejouer le journal doit redonner exactement le même état — c'est ce qui fait tenir la reprise après un F5, le replay, le support et l'anti-triche.
- **Le moteur ne connaît ni HTTP ni React.** Fonctions pures, état sérialisable, aucune entrée/sortie : c'est la seule façon de le tester par milliers de cas et de le faire jouer par des bots.
- **L'interface ne décide de rien.** Elle affiche les actions que le moteur déclare légales, et affiche la raison quand un coup est refusé. Aucune règle n'est réécrite côté écran.
- **Le jeu est celui d'un enfant de onze ans.** Lisible sans connaître les règles, animé, sonore, indulgent : on peut annuler avant de valider, on comprend pourquoi un coup est interdit, et on n'attend jamais devant un écran muet.

**Gain.** Constat de la livraison du 03/10/2026 : salon, invitations, plateau et temps réel sont en PROD, mais le générateur d'actions légales ne connaît que « avancer la phase » et « abandonner » (`FAMILLES_DEFAUT`). Chaque lot a livré sa brique en renvoyant le branchement des coups au suivant, et aucun ne le portait : on ne peut ni poser un Pokémon, ni attacher une énergie, ni attaquer. Ce lot est celui qui rend le jeu jouable.

**Fonctionnalités.** Familles de coups construites depuis les définitions de cartes résolues à la création de la partie (catalogue) : poser un Pokémon de base au banc, faire évoluer, attacher une énergie (une par tour), déclarer une attaque dont le coût est payé, battre en retraite (coût payé), passer le tour, promouvoir après un K.O. ; mise en place interactive (actif et banc face cachée, mulligans) par les fenêtres de décision ; enchaînement des tours par le serveur (pioche de début de tour, phase entre les tours, fin de partie) ; exposition des coups légaux de chaque joueur par l'API et le canal temps réel ; le plateau les propose et les joue.

**Vient après :**
- `j-plateau-interactions` — Jouer un coup : cibles valides, annulation, confirmation
- `j-initialisation` — Mise en place : mélange, main de sept, mulligans, actif et banc face cachée, six récompenses
- `j-effets-choix` — Demandes de décision : quand le moteur doit attendre un joueur — y compris l'adversaire
- `j-cartes-energies` — Énergies : de base fournies, spéciales possédées
- `j-cartes-pokemon` — Cartes Pokémon : base, évolutions, marqueurs de règle
- `j-degats-resolution` — Attaque et dégâts : coût, faiblesse, résistance, modificateurs
- `j-retraite-banc` — Banc, retraite et promotion : le Pokémon actif change de place
- `j-ko-recompenses` — Mises K.O., récompenses et conditions de victoire
- `j-temps-reel` — Canal temps réel : diffusion des coups, reconnexion et reprise après F5

**Débloque :**
- aucun lot n'en dépend

## 3. Mission

1. Écrire les familles manquantes dans le moteur (`apps/game`, paquet pur) à partir des transitions déjà livrées (`j-cartes-pokemon`, `j-cartes-energies`, `j-degats-resolution`, `j-retraite-banc`, `j-ko-recompenses`) et des définitions de cartes chargées du catalogue — sans dupliquer une règle : la famille liste, la transition applique, la validation vérifie l'appartenance.
2. Brancher ces familles dans le service de parties (`apps/api`, `games/`) : la partie connaît les définitions de cartes de ses deux decks, et `actions_legales` / `valider` les reçoivent.
3. Orchestrer la partie côté serveur : mise en place (coup système + décisions des joueurs par `j-effets-choix`), pioche de début de tour, phase entre les tours, passage de tour, fin de partie par récompenses, banc vide ou pioche impossible — tout par le journal, rien hors journal.
4. Exposer à chaque joueur ses coups légaux (avec leurs cibles et une étiquette lisible) dans sa vue et sur le WebSocket ; le plateau (`j-plateau-interactions`) les affiche et les envoie, sans aucune règle côté écran.
5. Prouver le jalon J1 : un test d'intégration qui joue **une partie complète** par l'API entre deux comptes, avec deux decks Pokémon + Énergies de base, jusqu'à la victoire par les six récompenses ; la partie se rejoue depuis son journal à l'identique ; et un e2e Playwright à deux contextes de navigateur qui joue au moins une mise en place, une énergie attachée et une attaque.

## 4. Critères d'acceptation

Le lot n'est fini que si **chacun** est vrai, preuve à l'appui dans le compte rendu :

- [ ] `actions_legales` propose poser, évoluer, attacher une énergie, attaquer, battre en retraite, passer et promouvoir quand c'est légal, et jamais sinon — vérifié sur des états tirés de parties jouées.
- [ ] Une partie complète se joue par l'API jusqu'à la victoire par les récompenses, et `rejouer(journal)` redonne l'état final à l'identique.
- [ ] Le plateau joue ces coups dans un navigateur (e2e à deux contextes, vert en CI).
- [ ] Aucune règle n'est réécrite côté écran ; aucun coup hors de la liste n'est accepté par le serveur.

## 5. Risques & pièges

Réécrire une règle dans la famille au lieu de réutiliser la transition livrée : les deux divergent, et le refus ne cite plus la bonne règle. Et repousser encore le branchement « au lot suivant » : il n'y en a pas.

## 6. Livrables — définition de « fini »

- familles de coups du moteur
- orchestration de la partie côté serveur
- coups exposés à l'API et au temps réel, joués par le plateau
- partie complète testée jusqu'à la victoire
- CI GitHub Actions verte sur la PR (elle fait foi, pas une suite verte sur une machine).
- Compte rendu `docs/roadmap/comptes-rendus/j-coups-joueur.md` : résumé, livrables, preuves, écarts, reste à faire.
- Le savoir durable va dans **une** fiche (« Où écrire quoi » de `CLAUDE.md`) ; pour le jeu, `docs/jeu/`.
- Aucun secret dans le dépôt, les journaux ou les sorties.
- **Code documenté** : chaque module, fonction et classe publique ajouté ou modifié a sa docstring (Python) ou son `/** … */` (TypeScript), en français, qui dit le pourquoi — `docs/CODE.md` § « Documenter le code ».
- **Graphe à jour** : après la fusion dans `main`, `graphify update .` sur le clone qui suit `main` (un graphe en retard fait mentir les lots suivants).

## 7. Tests exigés

- Un test qui **échoue sans** ton changement et passe avec.
- Moteur : fonctions pures, aucune entrée/sortie — un test d'import le prouve ; chaque test de règle cite son `R-x.y`.
- Route utilisateur → test d'accès croisé (l'utilisateur B reçoit 404 sur les objets de A).
- Écran → conforme à l'onglet « Maquette du jeu » (capture jointe au compte rendu).
- Suites complètes lancées sur la flotte, jamais sur le Mac de JF.

## 8. Clôture — obligatoire

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
python3 docs/roadmap/suivi.py tache j-coups-joueur <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu j-coups-joueur --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut j-coups-joueur <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "j-coups-joueur: …" && git push -u origin roadmap/j-coups-joueur
bash scripts/ouvrir-pr.sh roadmap/j-coups-joueur   # ouvre la PR, ou echoue en disant pourquoi
```

**La PR n'est pas optionnelle** : sans elle, la CI ne tourne pas sur ton travail, et c'est la CI qui fait foi. Si `ouvrir-pr.sh` sort en erreur, tu NE conclus PAS que c'est sans importance : tu nommes le manque dans ton compte rendu et dans ton dernier message.

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

