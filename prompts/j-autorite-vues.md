# Lot `j-autorite-vues` — Autorité du serveur : le client ne voit que ce qu'il a le droit de voir

> Prompt GÉNÉRÉ depuis `docs/roadmap/jeu/plan/` (via `jeu.json`) par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Plan du jeu : `docs/roadmap/jeu/BACKLOG-JEU.md` · onglet « Backlog du jeu » de `docs/roadmap/ROADMAP.html`.

**P0** · piste Serveur de parties · couloir **J-SRV** (**chimera**) · jalon **J1 — Deux joueurs jouent une partie honnête** · palier 9 · taille M · complexité 4/5 · difficulté 4/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur chimera**. Lance `hostname -s` :

- **Chimaera (dans la WSL)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier j-autorite-vues`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur chimera :

```bash
ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- bash -lc "cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-j-autorite-vues -b roadmap/j-autorite-vues origin/main && mkdir -p ~/dev/logs"'
```

3. Lance le lot autonome : par le mécanisme de lots de chimera (`~/dev/lots/launch-lot.sh`, étendu au dépôt `~/dev/pokeboy` par le lot `v0-flotte`), **lancé côté Windows** — un `nohup` interne à la WSL meurt avec la session. Journal : `~/dev/logs/j-autorite-vues.log`.
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/j-autorite-vues` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 8 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy (WSL Ubuntu-24.04, utilisateur upgreg)`. Travaille dans ton **worktree** `../wt-j-autorite-vues`, branche `roadmap/j-autorite-vues` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier j-autorite-vues
python3 docs/roadmap/suivi.py demarrer j-autorite-vues --machine "$(hostname -s)" --branche roadmap/j-autorite-vues
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut j-autorite-vues attente_validation --motif "<raisons>"`, section 8, dernier message `ATTENTE VALIDATION — j-autorite-vues — <raisons>`.
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

**Gain.** Sans cette règle tenue dès le début, l'anti-triche ne se rajoute jamais : il suffit d'ouvrir les outils du navigateur pour lire la main de l'adversaire, et plus personne n'a envie de jouer.

**Fonctionnalités.** Toute action passe par `valider()` côté serveur ; le client reçoit exclusivement `vue(etat, joueur)` ; les événements diffusés sont filtrés par destinataire (le même K.O. n'est pas décrit pareil aux deux joueurs quand une information est cachée) ; les identifiants de cartes cachées sont remplacés par des jetons opaques, changés à chaque mélange.

**Vient après :**
- `j-partie-service` — Service de parties : créer, persister, reprendre, expirer

**Débloque :**
- `j-securite-jeu` — Revue de sécurité du jeu avant ouverture
- `j-temps-reel` — Canal temps réel : diffusion des coups, reconnexion et reprise après F5

## 3. Mission

1. Filtrer toute sortie de l'API et du canal temps réel par la projection joueur — un seul point de sortie, pas un filtrage par route.
2. Remplacer les identifiants des cartes cachées par des jetons opaques non corrélables entre deux mélanges.
3. Écrire le test de non-fuite : pour 1 000 états, aucun identifiant de carte cachée n'apparaît dans ce qui part vers le client ; ce test tourne en CI sur chaque lot de scripts de cartes.
4. Journaliser toute action refusée avec son motif, et alerter sur les motifs anormaux (un client qui propose des actions illégales en rafale).

## 4. Critères d'acceptation

Le lot n'est fini que si **chacun** est vrai, preuve à l'appui dans le compte rendu :

- [ ] Le test de non-fuite est vert et tourne sur chaque modification du moteur ou des scripts.
- [ ] Un client modifié qui envoie une action illégale reçoit un refus motivé et n'altère jamais l'état.
- [ ] Les jetons de cartes cachées ne permettent pas de suivre une carte d'un mélange à l'autre.

## 5. Risques & pièges

Le filtrage par route : il suffit d'une route oubliée. Le filtrage doit être structurel, au sérialiseur, et vérifié par un test qui cherche les fuites plutôt que de les supposer absentes.

## 6. Livrables — définition de « fini »

- point de sortie unique filtré
- jetons opaques
- test de non-fuite en CI
- CI GitHub Actions verte sur la PR (elle fait foi, pas une suite verte sur une machine).
- Compte rendu `docs/roadmap/comptes-rendus/j-autorite-vues.md` : résumé, livrables, preuves, écarts, reste à faire.
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
python3 docs/roadmap/suivi.py tache j-autorite-vues <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu j-autorite-vues --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut j-autorite-vues <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "j-autorite-vues: …" && git push -u origin roadmap/j-autorite-vues
bash scripts/ouvrir-pr.sh roadmap/j-autorite-vues   # ouvre la PR, ou echoue en disant pourquoi
```

**La PR n'est pas optionnelle** : sans elle, la CI ne tourne pas sur ton travail, et c'est la CI qui fait foi. Si `ouvrir-pr.sh` sort en erreur, tu NE conclus PAS que c'est sans importance : tu nommes le manque dans ton compte rendu et dans ton dernier message.

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

