# Lot `j-ko-recompenses` — Mises K.O., récompenses et conditions de victoire

> Prompt GÉNÉRÉ depuis `docs/roadmap/jeu/plan/` (via `jeu.json`) par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Plan du jeu : `docs/roadmap/jeu/BACKLOG-JEU.md` · onglet « Backlog du jeu » de `docs/roadmap/ROADMAP.html`.

**P0** · piste Règles & moteur · couloir **J-MOT** (**devAI**) · jalon **J1 — Deux joueurs jouent une partie honnête** · palier 7 · taille M · complexité 4/5 · difficulté 4/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur devAI**. Lance `hostname -s` :

- **Mac-mini-de-keewoo (hostname -s)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier j-ko-recompenses`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur devAI :

```bash
ssh devai 'cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-j-ko-recompenses -b roadmap/j-ko-recompenses origin/main && mkdir -p ~/dev/logs'
```

3. Lance le lot autonome : `ssh devai 'cd ~/dev/wt-j-ko-recompenses && nohup claude -p --dangerously-skip-permissions < prompts/j-ko-recompenses.md > ~/dev/logs/j-ko-recompenses.log 2>&1 &'` (toutes les sorties redirigées : ssh rend la main).
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/j-ko-recompenses` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 8 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy`. Travaille dans ton **worktree** `../wt-j-ko-recompenses`, branche `roadmap/j-ko-recompenses` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier j-ko-recompenses
python3 docs/roadmap/suivi.py demarrer j-ko-recompenses --machine "$(hostname -s)" --branche roadmap/j-ko-recompenses
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut j-ko-recompenses attente_validation --motif "<raisons>"`, section 8, dernier message `ATTENTE VALIDATION — j-ko-recompenses — <raisons>`.
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

**Gain.** La fin d'une partie est le moment où une erreur de moteur coûte le plus cher : c'est là que le résultat se décide.

**Fonctionnalités.** Détection du K.O. (compteurs ≥ PV), défausse du Pokémon avec toute sa pile d'évolutions, ses énergies et son outil, prise du bon nombre de récompenses selon le marqueur de règle (1 pour un Pokémon ordinaire, 2 pour un Pokémon-ex/V/GX, 3 pour un TAG TEAM), K.O. simultané, promotion obligatoire d'un Pokémon du banc, et les trois conditions de victoire : plus de récompenses à prendre, adversaire sans Pokémon à promouvoir, adversaire incapable de piocher. Abandon et égalité.

**Vient après :**
- `j-degats-resolution` — Attaque et dégâts : coût, faiblesse, résistance, modificateurs

**Débloque :**
- `j-cartes-regles-speciales` — Règles de cartes particulières : ACE SPEC, Radiant, VSTAR, GX, Prism Star
- `j-effets-architecture` — Pile d'effets et déclencheurs : l'architecture qui accueille toutes les cartes
- `j-fin-effets-compte` — Ce qu'une partie laisse sur le compte : écriture unique et exacte
- `j-partie-fin-ui` — Fin de partie : qui a gagné, pourquoi, et ce qu'on en retient
- `j-tests-regles` — Batterie de cas de règles : la table qui dit si le moteur a raison

## 3. Mission

1. Résoudre les K.O. dans l'ordre officiel, y compris quand une attaque en provoque plusieurs.
2. Lire le nombre de récompenses depuis la carte du catalogue (marqueur de règle) et non depuis une liste en dur.
3. Traiter le K.O. simultané et l'égalité selon `REGLES.md`.
4. Interrompre la partie proprement : état final figé, vainqueur, raison, journal clos.
5. Tests : chaque condition de victoire, le double K.O., le K.O. du dernier Pokémon, la victoire par pioche vide.

## 4. Critères d'acceptation

Le lot n'est fini que si **chacun** est vrai, preuve à l'appui dans le compte rendu :

- [ ] Les trois conditions de victoire et l'égalité sont couvertes par des tests nommés.
- [ ] Le nombre de récompenses vient du catalogue ; une carte inconnue au marqueur inconnu fait échouer bruyamment, pas silencieusement à 1.
- [ ] Une partie terminée refuse toute action supplémentaire.

## 5. Risques & pièges

Le repli silencieux « marqueur inconnu → 1 récompense » : c'est exactement la panne muette que ce dépôt a déjà payée quatre fois. Un marqueur inconnu est une erreur qui remonte.

## 6. Livrables — définition de « fini »

- résolution des K.O.
- fin de partie normalisée (vainqueur + raison)
- CI GitHub Actions verte sur la PR (elle fait foi, pas une suite verte sur une machine).
- Compte rendu `docs/roadmap/comptes-rendus/j-ko-recompenses.md` : résumé, livrables, preuves, écarts, reste à faire.
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
python3 docs/roadmap/suivi.py tache j-ko-recompenses <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu j-ko-recompenses --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut j-ko-recompenses <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "j-ko-recompenses: …" && git push -u origin roadmap/j-ko-recompenses
bash scripts/ouvrir-pr.sh roadmap/j-ko-recompenses   # ouvre la PR, ou echoue en disant pourquoi
```

**La PR n'est pas optionnelle** : sans elle, la CI ne tourne pas sur ton travail, et c'est la CI qui fait foi. Si `ouvrir-pr.sh` sort en erreur, tu NE conclus PAS que c'est sans importance : tu nommes le manque dans ton compte rendu et dans ton dernier message.

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

