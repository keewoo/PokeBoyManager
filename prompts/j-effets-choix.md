# Lot `j-effets-choix` — Demandes de décision : quand le moteur doit attendre un joueur — y compris l'adversaire

> Prompt GÉNÉRÉ depuis `docs/roadmap/jeu/plan/` (via `jeu.json`) par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Plan du jeu : `docs/roadmap/jeu/BACKLOG-JEU.md` · onglet « Backlog du jeu » de `docs/roadmap/ROADMAP.html`.

**P0** · piste Effets & cartes · couloir **J-EFF** (**chimera**) · jalon **J2 — Toutes les cartes du deck sont vraiment jouées** · palier 10 · taille M · complexité 4/5 · difficulté 5/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur chimera**. Lance `hostname -s` :

- **Chimaera (dans la WSL)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier j-effets-choix`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur chimera :

```bash
ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- bash -lc "cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-j-effets-choix -b roadmap/j-effets-choix origin/main && mkdir -p ~/dev/logs"'
```

3. Lance le lot autonome : par le mécanisme de lots de chimera (`~/dev/lots/launch-lot.sh`, étendu au dépôt `~/dev/pokeboy` par le lot `v0-flotte`), **lancé côté Windows** — un `nohup` interne à la WSL meurt avec la session. Journal : `~/dev/logs/j-effets-choix.log`.
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/j-effets-choix` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 8 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy (WSL Ubuntu-24.04, utilisateur upgreg)`. Travaille dans ton **worktree** `../wt-j-effets-choix`, branche `roadmap/j-effets-choix` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier j-effets-choix
python3 docs/roadmap/suivi.py demarrer j-effets-choix --machine "$(hostname -s)" --branche roadmap/j-effets-choix
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut j-effets-choix attente_validation --motif "<raisons>"`, section 8, dernier message `ATTENTE VALIDATION — j-effets-choix — <raisons>`.
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

## 2. Contexte

**Jalon J2 — Toutes les cartes du deck sont vraiment jouées.** Objets, Supporters, Stades, Outils, talents, états spéciaux, appâts, attaques à effet, énergies spéciales : ce que la carte dit, le moteur le fait. Et ce qu'il ne sait pas faire, il le refuse au deck au lieu de l'inventer.

**Principes du jeu — ils valent pour ce lot comme pour tous les autres :**

- **Le serveur fait autorité.** Le client n'est qu'un écran : il n'apprend jamais la main de l'adversaire ni l'ordre de la pioche, et toute action qu'il propose est rejouée et validée côté serveur.
- **Un effet non implémenté n'est jamais approximé** (D9). Une carte dont l'effet n'est pas scripté et testé est refusée à la construction du deck, en disant pourquoi. Le jeu préfère dire « je ne sais pas jouer cette carte » que de la jouer de travers.
- **Tout est rejouable.** Une partie est un état initial, une graine d'aléatoire et un journal d'actions numéroté. Rejouer le journal doit redonner exactement le même état — c'est ce qui fait tenir la reprise après un F5, le replay, le support et l'anti-triche.
- **Le moteur ne connaît ni HTTP ni React.** Fonctions pures, état sérialisable, aucune entrée/sortie : c'est la seule façon de le tester par milliers de cas et de le faire jouer par des bots.
- **L'interface ne décide de rien.** Elle affiche les actions que le moteur déclare légales, et affiche la raison quand un coup est refusé. Aucune règle n'est réécrite côté écran.
- **Le jeu est celui d'un enfant de onze ans.** Lisible sans connaître les règles, animé, sonore, indulgent : on peut annuler avant de valider, on comprend pourquoi un coup est interdit, et on n'attend jamais devant un écran muet.

**Gain.** C'est le point où beaucoup de moteurs se cassent : une carte demande à l'ADVERSAIRE de choisir, pendant le tour de l'autre. Il faut une partie qui sait se mettre en pause, en ligne, avec une horloge et une reprise après coupure.

**Fonctionnalités.** Un mécanisme de demande : à qui, quoi choisir (une carte, plusieurs, un ordre, oui/non, un type, un nombre), combien, obligatoire ou facultatif, parmi quel ensemble (visible ou caché), avec une réponse par défaut et un délai. Le moteur suspend la résolution, l'état porte la demande en cours, et la reprise après F5 retrouve la demande intacte.

**Vient après :**
- `j-effets-dsl` — Langage d'effets : décrire ce que fait une carte, sans écrire de code par carte

**Débloque :**
- `j-cartes-objets` — Cartes Objet, dont les appâts qui forcent l'échange de l'actif adverse
- `j-cartes-supporters` — Supporters : un par tour, et les effets qui perturbent l'adversaire
- `j-cartes-talents` — Talents : passifs, activés une fois par tour, déclenchés — et annulables
- `j-plateau-decisions` — Fenêtres de décision : choisir des cartes, ordonner, répondre pendant le tour adverse
- `j-timer` — Horloges : par tour, par partie, par décision — et ce qui se passe à l'expiration

## 3. Mission

1. Modéliser la demande dans l'état (donc sérialisée, donc reprise) et non dans une variable d'exécution.
2. Traiter les demandes adressées à l'adversaire pendant le tour courant, avec leur propre horloge.
3. Définir la réponse par défaut de chaque type de demande (le premier choix valide, ou l'abandon de l'effet facultatif) pour l'expiration du délai.
4. Empêcher toute autre action tant qu'une demande est en cours, sauf l'abandon.
5. Tests : demande à l'adversaire, expiration, reprise après reconnexion au milieu d'une demande, demande imbriquée (un effet qui en déclenche un autre).

## 4. Critères d'acceptation

Le lot n'est fini que si **chacun** est vrai, preuve à l'appui dans le compte rendu :

- [ ] Une partie interrompue au milieu d'une demande reprend exactement à cette demande, avec le temps restant.
- [ ] Les demandes imbriquées se résolvent dans le bon ordre et se voient dans le journal.
- [ ] L'expiration applique la réponse par défaut et l'écrit dans le journal.

## 5. Risques & pièges

Implémenter les demandes en bloquant un fil d'exécution côté serveur : une partie sur deux reste bloquée à la première déconnexion. La demande est une donnée, pas une attente de code.

## 6. Livrables — définition de « fini »

- demandes de décision dans l'état
- réponses par défaut
- horloge par demande
- CI GitHub Actions verte sur la PR (elle fait foi, pas une suite verte sur une machine).
- Compte rendu `docs/roadmap/comptes-rendus/j-effets-choix.md` : résumé, livrables, preuves, écarts, reste à faire.
- Le savoir durable va dans **une** fiche (« Où écrire quoi » de `CLAUDE.md`) ; pour le jeu, `docs/jeu/`.
- Aucun secret dans le dépôt, les journaux ou les sorties.

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
python3 docs/roadmap/suivi.py tache j-effets-choix <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu j-effets-choix --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut j-effets-choix <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "j-effets-choix: …" && git push -u origin roadmap/j-effets-choix
bash scripts/ouvrir-pr.sh roadmap/j-effets-choix   # ouvre la PR, ou echoue en disant pourquoi
```

**La PR n'est pas optionnelle** : sans elle, la CI ne tourne pas sur ton travail, et c'est la CI qui fait foi. Si `ouvrir-pr.sh` sort en erreur, tu NE conclus PAS que c'est sans importance : tu nommes le manque dans ton compte rendu et dans ton dernier message.

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

