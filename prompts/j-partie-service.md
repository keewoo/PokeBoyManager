# Lot `j-partie-service` — Service de parties : créer, persister, reprendre, expirer

> Prompt GÉNÉRÉ depuis `docs/roadmap/jeu/plan/` (via `jeu.json`) par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Plan du jeu : `docs/roadmap/jeu/BACKLOG-JEU.md` · onglet « Backlog du jeu » de `docs/roadmap/ROADMAP.html`.

**P0** · piste Serveur de parties · couloir **J-SRV** (**chimera**) · jalon **J1 — Deux joueurs jouent une partie honnête** · palier 8 · taille M · complexité 4/5 · difficulté 4/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur chimera**. Lance `hostname -s` :

- **Chimaera (dans la WSL)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier j-partie-service`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur chimera :

```bash
ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- bash -lc "cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-j-partie-service -b roadmap/j-partie-service origin/main && mkdir -p ~/dev/logs"'
```

3. Lance le lot autonome : par le mécanisme de lots de chimera (`~/dev/lots/launch-lot.sh`, étendu au dépôt `~/dev/pokeboy` par le lot `v0-flotte`), **lancé côté Windows** — un `nohup` interne à la WSL meurt avec la session. Journal : `~/dev/logs/j-partie-service.log`.
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/j-partie-service` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 8 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy (WSL Ubuntu-24.04, utilisateur upgreg)`. Travaille dans ton **worktree** `../wt-j-partie-service`, branche `roadmap/j-partie-service` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier j-partie-service
python3 docs/roadmap/suivi.py demarrer j-partie-service --machine "$(hostname -s)" --branche roadmap/j-partie-service
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut j-partie-service attente_validation --motif "<raisons>"`, section 8, dernier message `ATTENTE VALIDATION — j-partie-service — <raisons>`.
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

**Gain.** C'est l'enveloppe qui transforme un moteur de règles en parties réelles : deux comptes, deux decks, un journal persistant, et une partie qui survit à un redémarrage du serveur.

**Fonctionnalités.** Tables `games`, `game_players`, `game_events` (journal), `game_snapshots` (instantanés) ; création d'une partie à partir de deux decks résolus en scripts ; application d'une action (validation, journalisation, diffusion) ; reprise d'une partie depuis l'instantané et la queue de journal ; expiration des parties abandonnées ; purge.

**Vient après :**
- `j-journal-actions` — Journal d'actions : la partie est sa suite de coups, pas son état
- `j-cartes-pokemon` — Cartes Pokémon : base, évolutions, marqueurs de règle

**Débloque :**
- `j-autorite-vues` — Autorité du serveur : le client ne voit que ce qu'il a le droit de voir
- `j-file-attente` — Recherche d'un adversaire : file d'attente privée et appariement
- `j-mode-solo` — Partie d'entraînement contre un bot
- `j-observabilite-jeu` — Voir ce qui se passe : métriques du jeu et alertes de règles
- `j-replay` — Replay d'une partie : la rejouer coup par coup, et la partager

## 3. Mission

1. Écrire le modèle et les migrations Alembic, en gardant le journal append-only (aucune mise à jour d'une entrée existante).
2. Implémenter la boucle : action reçue → validation par le moteur → écriture du journal → nouvel état → événements diffusés, le tout dans une transaction.
3. Résoudre les decks en scripts au moment de la création, et refuser la partie si une carte n'est pas jouable (`j-effets-catalogue-compilation`).
4. Reprise : recharger depuis le dernier instantané, rejouer la queue, comparer l'empreinte.
5. Purge des parties mortes et des instantanés anciens, avec une métrique de ce qui a été purgé.

## 4. Critères d'acceptation

Le lot n'est fini que si **chacun** est vrai, preuve à l'appui dans le compte rendu :

- [ ] Une partie survit à un redémarrage complet de l'API : la reprise redonne l'état exact, empreinte comprise.
- [ ] Deux actions concurrentes sur la même partie ne peuvent pas être appliquées deux fois (verrou testé).
- [ ] Une partie dont le deck contient une carte non scriptée est refusée à la création, avec la liste des cartes.

## 5. Risques & pièges

La partie est l'endroit où deux requêtes arrivent en même temps (le joueur clique deux fois, le réseau rejoue). L'idempotence par numéro d'action est obligatoire dès le premier jour.

## 6. Livrables — définition de « fini »

- modèle + migrations
- boucle d'application transactionnelle
- reprise et purge
- CI GitHub Actions verte sur la PR (elle fait foi, pas une suite verte sur une machine).
- Compte rendu `docs/roadmap/comptes-rendus/j-partie-service.md` : résumé, livrables, preuves, écarts, reste à faire.
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
python3 docs/roadmap/suivi.py tache j-partie-service <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu j-partie-service --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut j-partie-service <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "j-partie-service: …" && git push -u origin roadmap/j-partie-service
bash scripts/ouvrir-pr.sh roadmap/j-partie-service   # ouvre la PR, ou echoue en disant pourquoi
```

**La PR n'est pas optionnelle** : sans elle, la CI ne tourne pas sur ton travail, et c'est la CI qui fait foi. Si `ouvrir-pr.sh` sort en erreur, tu NE conclus PAS que c'est sans importance : tu nommes le manque dans ton compte rendu et dans ton dernier message.

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

