# Lot `j-effets-architecture` — Pile d'effets et déclencheurs : l'architecture qui accueille toutes les cartes

> Prompt GÉNÉRÉ depuis `docs/roadmap/jeu/plan/` (via `jeu.json`) par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Plan du jeu : `docs/roadmap/jeu/BACKLOG-JEU.md` · onglet « Backlog du jeu » de `docs/roadmap/ROADMAP.html`.

**P0** · piste Effets & cartes · couloir **J-EFF** (**chimera**) · jalon **J2 — Toutes les cartes du deck sont vraiment jouées** · palier 8 · taille L · complexité 5/5 · difficulté 5/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur chimera**. Lance `hostname -s` :

- **Chimaera (dans la WSL)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier j-effets-architecture`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur chimera :

```bash
ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- bash -lc "cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-j-effets-architecture -b roadmap/j-effets-architecture origin/main && mkdir -p ~/dev/logs"'
```

3. Lance le lot autonome : par le mécanisme de lots de chimera (`~/dev/lots/launch-lot.sh`, étendu au dépôt `~/dev/pokeboy` par le lot `v0-flotte`), **lancé côté Windows** — un `nohup` interne à la WSL meurt avec la session. Journal : `~/dev/logs/j-effets-architecture.log`.
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/j-effets-architecture` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 8 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy (WSL Ubuntu-24.04, utilisateur upgreg)`. Travaille dans ton **worktree** `../wt-j-effets-architecture`, branche `roadmap/j-effets-architecture` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier j-effets-architecture
python3 docs/roadmap/suivi.py demarrer j-effets-architecture --machine "$(hostname -s)" --branche roadmap/j-effets-architecture
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut j-effets-architecture attente_validation --motif "<raisons>"`, section 8, dernier message `ATTENTE VALIDATION — j-effets-architecture — <raisons>`.
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

**Jalon J2 — Toutes les cartes du deck sont vraiment jouées.** Objets, Supporters, Stades, Outils, talents, états spéciaux, appâts, attaques à effet, énergies spéciales : ce que la carte dit, le moteur le fait. Et ce qu'il ne sait pas faire, il le refuse au deck au lieu de l'inventer.

**Principes du jeu — ils valent pour ce lot comme pour tous les autres :**

- **Le serveur fait autorité.** Le client n'est qu'un écran : il n'apprend jamais la main de l'adversaire ni l'ordre de la pioche, et toute action qu'il propose est rejouée et validée côté serveur.
- **Un effet non implémenté n'est jamais approximé** (D9). Une carte dont l'effet n'est pas scripté et testé est refusée à la construction du deck, en disant pourquoi. Le jeu préfère dire « je ne sais pas jouer cette carte » que de la jouer de travers.
- **Tout est rejouable.** Une partie est un état initial, une graine d'aléatoire et un journal d'actions numéroté. Rejouer le journal doit redonner exactement le même état — c'est ce qui fait tenir la reprise après un F5, le replay, le support et l'anti-triche.
- **Le moteur ne connaît ni HTTP ni React.** Fonctions pures, état sérialisable, aucune entrée/sortie : c'est la seule façon de le tester par milliers de cas et de le faire jouer par des bots.
- **L'interface ne décide de rien.** Elle affiche les actions que le moteur déclare légales, et affiche la raison quand un coup est refusé. Aucune règle n'est réécrite côté écran.
- **Le jeu est celui d'un enfant de onze ans.** Lisible sans connaître les règles, animé, sonore, indulgent : on peut annuler avant de valider, on comprend pourquoi un coup est interdit, et on n'attend jamais devant un écran muet.

**Gain.** C'est le lot qui décide si les mille cartes suivantes coûtent une heure ou une semaine chacune. Un moteur qui traite les effets au fil de l'eau se réécrit à la première carte qui dit « votre adversaire ne peut pas ».

**Fonctionnalités.** Un bus d'événements de jeu (avant et après les dégâts, à la pose, à l'évolution, au K.O., au début et à la fin du tour, à l'attachement d'énergie, à la pioche, entre les tours), une pile d'effets résolue en dernier entré premier sorti, des fenêtres d'interruption, la distinction entre effets ponctuels et effets continus, et des verrous nommés (« pas de Supporter ce tour », « ce Pokémon ne peut pas attaquer », « les talents sont sans effet »).

**Vient après :**
- `j-checkup` — Phase entre les deux tours : l'ordre exact de résolution
- `j-ko-recompenses` — Mises K.O., récompenses et conditions de victoire

**Débloque :**
- `j-cartes-outils` — Outils Pokémon : un par Pokémon, attaché, défaussé au K.O.
- `j-cartes-stades` — Stades : un seul en jeu, des effets qui s'appliquent aux deux joueurs
- `j-cartes-talents` — Talents : passifs, activés une fois par tour, déclenchés — et annulables
- `j-effets-dsl` — Langage d'effets : décrire ce que fait une carte, sans écrire de code par carte

## 3. Mission

1. Définir la liste des événements et leurs charges utiles, à partir des besoins réels relevés sur 200 cartes prises au hasard du catalogue.
2. Implémenter la pile, l'ordre de résolution et les fenêtres d'interruption ; toute résolution est journalisée avec sa source (« à cause de l'Outil X »).
3. Implémenter les effets continus comme des modificateurs consultés au calcul, jamais comme des mutations de l'état (sinon leur retrait est impossible à faire proprement).
4. Implémenter les verrous et leur portée (ce tour, tant que ce Pokémon est actif, tant que ce Stade est en jeu).
5. Documenter l'architecture dans `docs/jeu/EFFETS.md` avec trois exemples complets de bout en bout.

## 4. Critères d'acceptation

Le lot n'est fini que si **chacun** est vrai, preuve à l'appui dans le compte rendu :

- [ ] Les 200 cartes de l'échantillon sont exprimables sans ajouter d'événement nouveau — ou la liste est complétée et le test refait.
- [ ] Le retrait d'un effet continu (Outil défaussé, Stade remplacé) restaure exactement l'état antérieur du calcul.
- [ ] Chaque résolution d'effet est journalisée avec sa carte source.
- [ ] Le moteur socle (`j-machine-tour`, `j-degats-resolution`) n'a pas été modifié pour accueillir les effets : ils se branchent sur les points d'accroche existants.

## 5. Risques & pièges

Sous-estimer les effets qui modifient les règles elles-mêmes (« les attaques de votre adversaire coûtent une énergie de plus », « les Pokémon de base ne peuvent pas être mis K.O. »). Si la pile ne sait pas les porter, ils seront codés en dur dans le socle, et le socle pourrira.

## 6. Livrables — définition de « fini »

- bus d'événements + pile d'effets
- effets continus par modificateurs
- docs/jeu/EFFETS.md
- CI GitHub Actions verte sur la PR (elle fait foi, pas une suite verte sur une machine).
- Compte rendu `docs/roadmap/comptes-rendus/j-effets-architecture.md` : résumé, livrables, preuves, écarts, reste à faire.
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
python3 docs/roadmap/suivi.py tache j-effets-architecture <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu j-effets-architecture --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut j-effets-architecture <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "j-effets-architecture: …" && git push -u origin roadmap/j-effets-architecture
bash scripts/ouvrir-pr.sh roadmap/j-effets-architecture   # ouvre la PR, ou echoue en disant pourquoi
```

**La PR n'est pas optionnelle** : sans elle, la CI ne tourne pas sur ton travail, et c'est la CI qui fait foi. Si `ouvrir-pr.sh` sort en erreur, tu NE conclus PAS que c'est sans importance : tu nommes le manque dans ton compte rendu et dans ton dernier message.

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

