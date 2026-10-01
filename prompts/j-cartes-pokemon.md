# Lot `j-cartes-pokemon` — Cartes Pokémon : base, évolutions, marqueurs de règle

> Prompt GÉNÉRÉ depuis `docs/roadmap/jeu/plan/` (via `jeu.json`) par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Plan du jeu : `docs/roadmap/jeu/BACKLOG-JEU.md` · onglet « Backlog du jeu » de `docs/roadmap/ROADMAP.html`.

**P0** · piste Effets & cartes · couloir **J-EFF** (**chimera**) · jalon **J1 — Deux joueurs jouent une partie honnête** · palier 7 · taille M · complexité 3/5 · difficulté 3/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur chimera**. Lance `hostname -s` :

- **Chimaera (dans la WSL)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier j-cartes-pokemon`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur chimera :

```bash
ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- bash -lc "cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-j-cartes-pokemon -b roadmap/j-cartes-pokemon origin/main && mkdir -p ~/dev/logs"'
```

3. Lance le lot autonome : par le mécanisme de lots de chimera (`~/dev/lots/launch-lot.sh`, étendu au dépôt `~/dev/pokeboy` par le lot `v0-flotte`), **lancé côté Windows** — un `nohup` interne à la WSL meurt avec la session. Journal : `~/dev/logs/j-cartes-pokemon.log`.
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/j-cartes-pokemon` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 8 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy (WSL Ubuntu-24.04, utilisateur upgreg)`. Travaille dans ton **worktree** `../wt-j-cartes-pokemon`, branche `roadmap/j-cartes-pokemon` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier j-cartes-pokemon
python3 docs/roadmap/suivi.py demarrer j-cartes-pokemon --machine "$(hostname -s)" --branche roadmap/j-cartes-pokemon
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut j-cartes-pokemon attente_validation --motif "<raisons>"`, section 8, dernier message `ATTENTE VALIDATION — j-cartes-pokemon — <raisons>`.
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

**Gain.** Sans elles il n'y a pas de partie du tout : ce sont les seules cartes indispensables au jalon J1.

**Fonctionnalités.** Pokémon de base posables au banc, évolutions de stade 1 et 2 (sur le bon Pokémon, pas le tour de sa pose, pas au premier tour), PV, type, faiblesse, résistance, coût de retraite, marqueur de règle (récompenses données), conservation des énergies et des compteurs de dégâts à l'évolution, guérison des états spéciaux à l'évolution.

**Vient après :**
- `j-degats-resolution` — Attaque et dégâts : coût, faiblesse, résistance, modificateurs
- `j-retraite-banc` — Banc, retraite et promotion : le Pokémon actif change de place

**Débloque :**
- `j-cartes-energies` — Énergies : de base fournies, spéciales possédées
- `j-effets-catalogue-compilation` — Du catalogue aux cartes jouables : compilation, versions et errata
- `j-initialisation` — Mise en place : mélange, main de sept, mulligans, actif et banc face cachée, six récompenses
- `j-partie-service` — Service de parties : créer, persister, reprendre, expirer

## 3. Mission

1. Charger les cartes Pokémon sans passer par le langage d'effets : à ce stade, seules les attaques à dégâts secs sont jouables ; les attaques à effet arrivent avec `j-cartes-attaques-effets`.
2. Charger ces caractéristiques depuis le catalogue (`cards.attacks`, `weaknesses`, `resistances`, `retreat_cost`, `rule_marker`) plutôt que de les redéclarer.
3. Implémenter la pile d'évolution et ce qu'elle conserve ou efface.
4. Traiter les cas particuliers de pose (Pokémon qui arrivent directement en jeu par un effet).
5. Tests : évolution interdite le tour de la pose, évolution qui soigne le sommeil, K.O. d'une pile d'évolution qui défausse toute la pile.

## 4. Critères d'acceptation

Le lot n'est fini que si **chacun** est vrai, preuve à l'appui dans le compte rendu :

- [ ] Aucune caractéristique de Pokémon n'est écrite en dur dans le moteur.
- [ ] Une carte du catalogue dont le marqueur de règle est inconnu est refusée avec un message clair, jamais jouée par défaut.
- [ ] Les tests d'évolution couvrent les six cas de `cas-de-regles.yaml`.

## 5. Risques & pièges

Les données du catalogue sont hétérogènes selon la source (TCGdex / Pokémon TCG API) : les champs manquants doivent bloquer la carte, pas être devinés.

## 6. Livrables — définition de « fini »

- cartes Pokémon jouables depuis le catalogue
- CI GitHub Actions verte sur la PR (elle fait foi, pas une suite verte sur une machine).
- Compte rendu `docs/roadmap/comptes-rendus/j-cartes-pokemon.md` : résumé, livrables, preuves, écarts, reste à faire.
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
python3 docs/roadmap/suivi.py tache j-cartes-pokemon <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu j-cartes-pokemon --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut j-cartes-pokemon <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "j-cartes-pokemon: …" && git push -u origin roadmap/j-cartes-pokemon
bash scripts/ouvrir-pr.sh roadmap/j-cartes-pokemon   # ouvre la PR, ou echoue en disant pourquoi
```

**La PR n'est pas optionnelle** : sans elle, la CI ne tourne pas sur ton travail, et c'est la CI qui fait foi. Si `ouvrir-pr.sh` sort en erreur, tu NE conclus PAS que c'est sans importance : tu nommes le manque dans ton compte rendu et dans ton dernier message.

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

