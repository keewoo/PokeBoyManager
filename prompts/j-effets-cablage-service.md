# Lot `j-effets-cablage-service` — Brancher les effets dans le service de parties : Objets, Supporters, talents, Outils, Stades, en partie réelle

> Prompt GÉNÉRÉ depuis `docs/roadmap/jeu/plan/` (via `jeu.json`) par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Plan du jeu : `docs/roadmap/jeu/BACKLOG-JEU.md` · onglet « Backlog du jeu » de `docs/roadmap/ROADMAP.html`.

**P0** · piste Serveur de parties · couloir **J-SRV** (**chimera**) · jalon **J2 — Toutes les cartes du deck sont vraiment jouées** · palier 15 · taille L · complexité 4/5 · difficulté 4/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur chimera**. Lance `hostname -s` :

- **Chimaera (dans la WSL)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier j-effets-cablage-service`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur chimera :

```bash
ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- bash -lc "cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-j-effets-cablage-service -b roadmap/j-effets-cablage-service origin/main && mkdir -p ~/dev/logs"'
```

3. Lance le lot autonome : par le mécanisme de lots de chimera (`~/dev/lots/launch-lot.sh`, étendu au dépôt `~/dev/pokeboy` par le lot `v0-flotte`), **lancé côté Windows** — un `nohup` interne à la WSL meurt avec la session. Journal : `~/dev/logs/j-effets-cablage-service.log`.
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/j-effets-cablage-service` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 8 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy (WSL Ubuntu-24.04, utilisateur upgreg)`. Travaille dans ton **worktree** `../wt-j-effets-cablage-service`, branche `roadmap/j-effets-cablage-service` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier j-effets-cablage-service
python3 docs/roadmap/suivi.py demarrer j-effets-cablage-service --machine "$(hostname -s)" --branche roadmap/j-effets-cablage-service
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut j-effets-cablage-service attente_validation --motif "<raisons>"`, section 8, dernier message `ATTENTE VALIDATION — j-effets-cablage-service — <raisons>`.
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

**Gain.** Constat de la livraison bloquée du 04/10 (« livraison-effets-cartes ») : les lots d'effets ont écrit le moteur et renvoyé le branchement côté service « à un lot ultérieur » qui n'existait pas — `CatalogueJeu.registre_continus` vide, `objets` jamais alimenté depuis `card_scripts`, talents non câblés dans l'orchestrateur, `attacher_outil` jamais proposé. Une carte à effet ne peut donc pas être jouée en partie réelle, même avec son script. Ce lot est celui qui rend les effets jouables.

**Fonctionnalités.** À la création d'une partie, le service assemble depuis les decks et `card_scripts` tout ce dont le moteur a besoin : registre des Objets et Supporters, registres de talents, effets continus (Outils, Stades), modificateurs consultés au calcul des dégâts ; les familles correspondantes (jouer un Objet, un Supporter, un Stade, attacher un Outil, utiliser un talent) apparaissent dans les coups légaux ; les décisions qu'ouvrent ces effets passent par les fenêtres de `j-plateau-decisions` ; la zone Stade est rendue sur le plateau.

**Vient après :**
- `j-cartes-attaques-effets` — Attaques à effet : pile ou face, dégâts variables, blocages, états infligés
- `j-cartes-objets` — Cartes Objet, dont les appâts qui forcent l'échange de l'actif adverse
- `j-cartes-supporters` — Supporters : un par tour, et les effets qui perturbent l'adversaire
- `j-cartes-talents` — Talents : passifs, activés une fois par tour, déclenchés — et annulables
- `j-cartes-outils` — Outils Pokémon : un par Pokémon, attaché, défaussé au K.O.
- `j-cartes-stades` — Stades : un seul en jeu, des effets qui s'appliquent aux deux joueurs
- `j-effets-catalogue-compilation` — Du catalogue aux cartes jouables : compilation, versions et errata
- `j-plateau-decisions` — Fenêtres de décision : choisir des cartes, ordonner, répondre pendant le tour adverse
- `j-coups-joueur` — Coups du joueur : la partie se joue vraiment, de la mise en place à la victoire

**Débloque :**
- aucun lot n'en dépend

## 3. Mission

1. Relire la section « Reste à faire » des comptes rendus de `j-cartes-attaques-effets`, `j-cartes-objets`, `j-cartes-supporters`, `j-cartes-talents`, `j-cartes-outils`, `j-cartes-stades`, `j-plateau-decisions` et en faire la liste de ce que ce lot branche — tout ce qui relève du service ou de l'écran est ici, rien n'est renvoyé à un « lot ultérieur » sans en créer la fiche.
2. Alimenter le `CatalogueJeu` d'une partie depuis `card_scripts` (Objets, Supporters, talents) et depuis le moteur (Outils, Stades, effets continus) ; câbler les modificateurs continus dans le calcul des dégâts ; surfacer les familles manquantes en coups légaux.
3. Semer dans `card_scripts` les scripts écrits à la main par les lots (les 15 Objets de `j-cartes-objets`, et ceux des autres lots), par la commande d'import prévue — avec leur preuve (tests), conformément à la contrainte `ck_card_scripts_scripte_gate`.
4. Prouver par **une partie réelle à travers l'API et le WebSocket** (client de test FastAPI) qu'on joue et résout : une attaque à effet, un Objet, un Supporter, un talent, un Outil et un Stade, avec au moins une fenêtre de décision ouverte et répondue — sans fuite dans la vue de chaque joueur.
5. Rendre la zone Stade sur le plateau (le journal traduit déjà `stade_joue`).

## 4. Critères d'acceptation

Le lot n'est fini que si **chacun** est vrai, preuve à l'appui dans le compte rendu :

- [ ] Une partie réelle, jouée par les routes HTTP et le WebSocket, résout une attaque à effet, un Objet, un Supporter, un talent, un Outil et un Stade — test vert en CI.
- [ ] Un deck contenant ces cartes passe la construction (D9) dès que leurs scripts sont dans `card_scripts`, et est refusé sinon, en disant pourquoi.
- [ ] Aucune ligne de « Reste à faire » des lots d'effets relevant du service ou de l'écran n'est laissée sans être faite ou sans fiche de lot créée.

## 5. Risques & pièges

Refaire l'erreur des lots précédents : tester dans le moteur seul et laisser le chemin réel (service, API, temps réel) non exercé. La preuve passe par les routes, ou elle ne vaut rien.

## 6. Livrables — définition de « fini »

- effets branchés dans le service de parties
- scripts écrits à la main semés dans card_scripts
- partie réelle à effets testée par l'API et le WebSocket
- zone Stade sur le plateau
- CI GitHub Actions verte sur la PR (elle fait foi, pas une suite verte sur une machine).
- Compte rendu `docs/roadmap/comptes-rendus/j-effets-cablage-service.md` : résumé, livrables, preuves, écarts, reste à faire.
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
python3 docs/roadmap/suivi.py tache j-effets-cablage-service <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu j-effets-cablage-service --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut j-effets-cablage-service <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "j-effets-cablage-service: …" && git push -u origin roadmap/j-effets-cablage-service
bash scripts/ouvrir-pr.sh roadmap/j-effets-cablage-service   # ouvre la PR, ou echoue en disant pourquoi
```

**La PR n'est pas optionnelle** : sans elle, la CI ne tourne pas sur ton travail, et c'est la CI qui fait foi. Si `ouvrir-pr.sh` sort en erreur, tu NE conclus PAS que c'est sans importance : tu nommes le manque dans ton compte rendu et dans ton dernier message.

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

