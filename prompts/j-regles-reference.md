# Lot `j-regles-reference` — Corpus de règles de référence : la version des règles qui fait foi, écrite et citée

> Prompt GÉNÉRÉ depuis `docs/roadmap/jeu/plan/` (via `jeu.json`) par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Plan du jeu : `docs/roadmap/jeu/BACKLOG-JEU.md` · onglet « Backlog du jeu » de `docs/roadmap/ROADMAP.html`.

**P0** · piste Règles & moteur · couloir **J-MOT** (**devAI**) · jalon **J1 — Deux joueurs jouent une partie honnête** · palier 0 · taille M · complexité 2/5 · difficulté 3/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur devAI**. Lance `hostname -s` :

- **Mac-mini-de-keewoo (hostname -s)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier j-regles-reference`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur devAI :

```bash
ssh devai 'cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-j-regles-reference -b roadmap/j-regles-reference origin/main && mkdir -p ~/dev/logs'
```

3. Lance le lot autonome : `ssh devai 'cd ~/dev/wt-j-regles-reference && nohup claude -p --dangerously-skip-permissions < prompts/j-regles-reference.md > ~/dev/logs/j-regles-reference.log 2>&1 &'` (toutes les sorties redirigées : ssh rend la main).
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/j-regles-reference` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 8 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy`. Travaille dans ton **worktree** `../wt-j-regles-reference`, branche `roadmap/j-regles-reference` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier j-regles-reference
python3 docs/roadmap/suivi.py demarrer j-regles-reference --machine "$(hostname -s)" --branche roadmap/j-regles-reference
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut j-regles-reference attente_validation --motif "<raisons>"`, section 8, dernier message `ATTENTE VALIDATION — j-regles-reference — <raisons>`.
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

**Gain.** Sans une référence écrite, chaque lot du moteur invente sa propre version des règles et personne ne peut arbitrer un désaccord. Ce document est la vérité contre laquelle le moteur est jugé, et il est écrit AVANT la première ligne de moteur.

**Fonctionnalités.** Un document unique qui fixe, pour la version retenue en DJ1 : zones et leurs limites, déroulé d'un tour, règle du premier tour, calcul des dégâts, faiblesse et résistance, retraite, banc, états spéciaux et leur cumul, phase entre les tours, mises K.O., récompenses par marqueur de règle, conditions de victoire, mulligan, et les règles de cartes particulières (ACE SPEC, Radiant, VSTAR, GX, Pokémon-ex). Chaque point cite sa source et la date de la version.

**Vient après :**
- rien : premier lot de sa chaîne

**Débloque :**
- `j-modele-etat` — État d'une partie : zones, attachements, compteurs, et vues par joueur
- `j-tests-regles` — Batterie de cas de règles : la table qui dit si le moteur a raison

**Décision DJ1** — Quelle version des règles fait foi ? Standard actuel (rotation), Étendu, ou un format « maison » sans rotation acceptant toute carte de la collection ? Lis la décision prise dans `docs/roadmap/etat.json` (`decisions_prises.DJ1`) et applique-la à la lettre ; la proposition du pilote n'est qu'un contexte : _Format maison sans rotation (on joue ce qu'on possède), mais avec le corpus de règles ACTUEL (faiblesse ×2, résistance −30, 6 récompenses, banc de 5, le joueur qui commence n'attaque pas à son premier tour). Une carte ancienne est jouée avec les règles actuelles._

## 3. Mission

1. Choisir la version des règles avec JF (DJ1) et la citer : édition du livret officiel, date, langue de référence.
2. Rédiger `docs/jeu/REGLES.md` : une section par mécanique, chaque affirmation numérotée (`R-3.4`) pour être citée par un test.
3. Lister explicitement les points où les règles ont changé selon les époques (faiblesse ×2 contre +30, résistance −20 contre −30, cumul des états spéciaux, premier tour) et écrire lequel s'applique ici.
4. Dresser la table des cas limites connus : pioche vide en début de tour, banc vide après un K.O., K.O. simultané, dernier Pokémon mis K.O. par un effet hors attaque, abandon, égalité.
5. Produire la table de cas de test initiale (`docs/jeu/cas-de-regles.yaml`) : chaque cas nomme la règle qu'il vérifie.

## 4. Critères d'acceptation

Le lot n'est fini que si **chacun** est vrai, preuve à l'appui dans le compte rendu :

- [ ] Chaque section du document porte un identifiant de règle citable par un test.
- [ ] Aucun point de règle n'est laissé en « selon l'époque » : un seul comportement est choisi et écrit.
- [ ] La table de cas couvre au minimum les dix cas limites listés dans la mission.
- [ ] JF a validé DJ1 et la validation est datée dans le document.

## 5. Risques & pièges

Le piège est de recopier une page d'encyclopédie amateur : les règles y mélangent les époques. Une seule source officielle, datée, et tout écart assumé par écrit.

## 6. Livrables — définition de « fini »

- docs/jeu/REGLES.md (règles numérotées)
- docs/jeu/cas-de-regles.yaml (table de cas)
- CI GitHub Actions verte sur la PR (elle fait foi, pas une suite verte sur une machine).
- Compte rendu `docs/roadmap/comptes-rendus/j-regles-reference.md` : résumé, livrables, preuves, écarts, reste à faire.
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
python3 docs/roadmap/suivi.py tache j-regles-reference <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu j-regles-reference --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut j-regles-reference <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "j-regles-reference: …" && git push -u origin roadmap/j-regles-reference
bash scripts/ouvrir-pr.sh roadmap/j-regles-reference   # ouvre la PR, ou echoue en disant pourquoi
```

**La PR n'est pas optionnelle** : sans elle, la CI ne tourne pas sur ton travail, et c'est la CI qui fait foi. Si `ouvrir-pr.sh` sort en erreur, tu NE conclus PAS que c'est sans importance : tu nommes le manque dans ton compte rendu et dans ton dernier message.

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

