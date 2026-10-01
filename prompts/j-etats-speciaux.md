# Lot `j-etats-speciaux` — États spéciaux : Empoisonné, Brûlé, Endormi, Paralysé, Confus

> Prompt GÉNÉRÉ depuis `docs/roadmap/jeu/plan/` (via `jeu.json`) par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Plan du jeu : `docs/roadmap/jeu/BACKLOG-JEU.md` · onglet « Backlog du jeu » de `docs/roadmap/ROADMAP.html`.

**P0** · piste Règles & moteur · couloir **J-MOT** (**devAI**) · jalon **J1 — Deux joueurs jouent une partie honnête** · palier 7 · taille M · complexité 4/5 · difficulté 4/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur devAI**. Lance `hostname -s` :

- **Mac-mini-de-keewoo (hostname -s)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier j-etats-speciaux`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur devAI :

```bash
ssh devai 'cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-j-etats-speciaux -b roadmap/j-etats-speciaux origin/main && mkdir -p ~/dev/logs'
```

3. Lance le lot autonome : `ssh devai 'cd ~/dev/wt-j-etats-speciaux && nohup claude -p --dangerously-skip-permissions < prompts/j-etats-speciaux.md > ~/dev/logs/j-etats-speciaux.log 2>&1 &'` (toutes les sorties redirigées : ssh rend la main).
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/j-etats-speciaux` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 8 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy`. Travaille dans ton **worktree** `../wt-j-etats-speciaux`, branche `roadmap/j-etats-speciaux` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier j-etats-speciaux
python3 docs/roadmap/suivi.py demarrer j-etats-speciaux --machine "$(hostname -s)" --branche roadmap/j-etats-speciaux
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut j-etats-speciaux attente_validation --motif "<raisons>"`, section 8, dernier message `ATTENTE VALIDATION — j-etats-speciaux — <raisons>`.
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

**Jalon J1 — Deux joueurs jouent une partie honnête.** Une partie complète se joue de bout en bout entre deux navigateurs, avec des Pokémon, des énergies et des attaques simples — sans Dresseur, sans talent, sans état spécial. Laid mais juste : les règles sont appliquées, la partie reprend après un F5, et le vainqueur est le bon.

**Principes du jeu — ils valent pour ce lot comme pour tous les autres :**

- **Le serveur fait autorité.** Le client n'est qu'un écran : il n'apprend jamais la main de l'adversaire ni l'ordre de la pioche, et toute action qu'il propose est rejouée et validée côté serveur.
- **Un effet non implémenté n'est jamais approximé** (D9). Une carte dont l'effet n'est pas scripté et testé est refusée à la construction du deck, en disant pourquoi. Le jeu préfère dire « je ne sais pas jouer cette carte » que de la jouer de travers.
- **Tout est rejouable.** Une partie est un état initial, une graine d'aléatoire et un journal d'actions numéroté. Rejouer le journal doit redonner exactement le même état — c'est ce qui fait tenir la reprise après un F5, le replay, le support et l'anti-triche.
- **Le moteur ne connaît ni HTTP ni React.** Fonctions pures, état sérialisable, aucune entrée/sortie : c'est la seule façon de le tester par milliers de cas et de le faire jouer par des bots.
- **L'interface ne décide de rien.** Elle affiche les actions que le moteur déclare légales, et affiche la raison quand un coup est refusé. Aucune règle n'est réécrite côté écran.
- **Le jeu est celui d'un enfant de onze ans.** Lisible sans connaître les règles, animé, sonore, indulgent : on peut annuler avant de valider, on comprend pourquoi un coup est interdit, et on n'attend jamais devant un écran muet.

**Gain.** JF les a explicitement mis dans la première version (D9). Ce sont aussi les règles les plus souvent jouées de travers, parce que leur cumul et leur ordre de résolution changent selon les époques.

**Fonctionnalités.** Les cinq états, leur pose, leurs règles de cumul (un seul état « couché » à la fois, poison et brûlure cumulables avec les autres selon la version retenue), leurs effets (pas d'attaque ni de retraite sous paralysie ou sommeil, pile ou face de confusion avec auto-dégâts, compteurs de poison et de brûlure), leur guérison (passage au banc, évolution, effets de soin, réveil au pile ou face).

**Vient après :**
- `j-retraite-banc` — Banc, retraite et promotion : le Pokémon actif change de place
- `j-checkup` — Phase entre les deux tours : l'ordre exact de résolution

**Débloque :**
- `j-cartes-attaques-effets` — Attaques à effet : pile ou face, dégâts variables, blocages, états infligés

**Décision DJ1** — Quelle version des règles fait foi ? Standard actuel (rotation), Étendu, ou un format « maison » sans rotation acceptant toute carte de la collection ? Lis la décision prise dans `docs/roadmap/etat.json` (`decisions_prises.DJ1`) et applique-la à la lettre ; la proposition du pilote n'est qu'un contexte : _Format maison sans rotation (on joue ce qu'on possède), mais avec le corpus de règles ACTUEL (faiblesse ×2, résistance −30, 6 récompenses, banc de 5, le joueur qui commence n'attaque pas à son premier tour). Une carte ancienne est jouée avec les règles actuelles._

## 3. Mission

1. Encoder les cinq états et la matrice de cumul exacte de la version retenue.
2. Brancher leur résolution sur la phase entre les tours (`j-checkup`), dans l'ordre officiel.
3. Implémenter la confusion : pile ou face à la déclaration d'attaque, auto-dégâts sur échec, attaque annulée.
4. Représenter l'orientation de la carte (couchée, tournée) dans l'état, pour que l'interface la montre comme sur une vraie table.
5. Tests : un cas par état, un cas par combinaison autorisée, guérison par retraite, par évolution, par effet.

## 4. Critères d'acceptation

Le lot n'est fini que si **chacun** est vrai, preuve à l'appui dans le compte rendu :

- [ ] La matrice de cumul est testée exhaustivement (toutes les paires).
- [ ] Un Pokémon endormi ou paralysé ne peut ni attaquer ni battre en retraite, mais peut être échangé de force.
- [ ] Les compteurs de poison et de brûlure s'appliquent au bon moment, et le pile ou face de brûlure est journalisé.

## 5. Risques & pièges

Le cumul est le piège : selon la version, poison + sommeil coexistent mais sommeil + paralysie non. Le seul garde-fou est la matrice écrite dans `REGLES.md` et testée paire par paire.

## 6. Livrables — définition de « fini »

- cinq états + matrice de cumul
- résolution en phase intermédiaire
- CI GitHub Actions verte sur la PR (elle fait foi, pas une suite verte sur une machine).
- Compte rendu `docs/roadmap/comptes-rendus/j-etats-speciaux.md` : résumé, livrables, preuves, écarts, reste à faire.
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
python3 docs/roadmap/suivi.py tache j-etats-speciaux <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu j-etats-speciaux --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut j-etats-speciaux <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "j-etats-speciaux: …" && git push -u origin roadmap/j-etats-speciaux
bash scripts/ouvrir-pr.sh roadmap/j-etats-speciaux   # ouvre la PR, ou echoue en disant pourquoi
```

**La PR n'est pas optionnelle** : sans elle, la CI ne tourne pas sur ton travail, et c'est la CI qui fait foi. Si `ouvrir-pr.sh` sort en erreur, tu NE conclus PAS que c'est sans importance : tu nommes le manque dans ton compte rendu et dans ton dernier message.

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

