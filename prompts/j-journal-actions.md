# Lot `j-journal-actions` — Journal d'actions : la partie est sa suite de coups, pas son état

> Prompt GÉNÉRÉ depuis `docs/roadmap/jeu/plan/` (via `jeu.json`) par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Plan du jeu : `docs/roadmap/jeu/BACKLOG-JEU.md` · onglet « Backlog du jeu » de `docs/roadmap/ROADMAP.html`.

**P0** · piste Règles & moteur · couloir **J-MOT** (**devAI**) · jalon **J1 — Deux joueurs jouent une partie honnête** · palier 3 · taille M · complexité 3/5 · difficulté 4/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur devAI**. Lance `hostname -s` :

- **Mac-mini-de-keewoo (hostname -s)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier j-journal-actions`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur devAI :

```bash
ssh devai 'cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-j-journal-actions -b roadmap/j-journal-actions origin/main && mkdir -p ~/dev/logs'
```

3. Lance le lot autonome : `ssh devai 'cd ~/dev/wt-j-journal-actions && nohup claude -p --dangerously-skip-permissions < prompts/j-journal-actions.md > ~/dev/logs/j-journal-actions.log 2>&1 &'` (toutes les sorties redirigées : ssh rend la main).
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/j-journal-actions` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 8 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy`. Travaille dans ton **worktree** `../wt-j-journal-actions`, branche `roadmap/j-journal-actions` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier j-journal-actions
python3 docs/roadmap/suivi.py demarrer j-journal-actions --machine "$(hostname -s)" --branche roadmap/j-journal-actions
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut j-journal-actions attente_validation --motif "<raisons>"`, section 8, dernier message `ATTENTE VALIDATION — j-journal-actions — <raisons>`.
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

**Gain.** C'est la pièce qui rend possibles quatre choses d'un coup : la reprise après un F5, le replay, le support (« montre-moi la partie ») et l'anti-triche. La stocker dès le premier jour coûte peu ; la rajouter après coûte une réécriture.

**Fonctionnalités.** Journal append-only numéroté : chaque entrée porte son numéro, son auteur, l'action demandée, les événements produits par le moteur, l'horodatage et l'empreinte de l'état résultant. `rejouer(journal)` reconstruit l'état. Le journal est la source de vérité persistée ; l'état n'est qu'un cache.

**Vient après :**
- `j-aleatoire-determinisme` — Aléatoire reproductible : mélange, pile ou face, et graine vérifiable

**Débloque :**
- `j-actions-legales` — Générateur d'actions légales : ce qui est jouable, et pourquoi le reste ne l'est pas
- `j-partie-service` — Service de parties : créer, persister, reprendre, expirer
- `j-replay` — Replay d'une partie : la rejouer coup par coup, et la partager

## 3. Mission

1. Définir le format d'une entrée et sa sérialisation stable (versionnée).
2. Implémenter `appliquer(etat, action) -> (etat, evenements)` sans effet de bord, et `rejouer(journal) -> etat`.
3. Empreinte de l'état après chaque coup : une divergence se détecte au coup près, pas à la fin de la partie.
4. Test de propriété : pour toute partie simulée, `rejouer(journal) == etat` et les empreintes concordent.
5. Prévoir la compaction : instantané périodique + queue de journal, pour ne pas rejouer 400 coups à chaque reconnexion.

## 4. Critères d'acceptation

Le lot n'est fini que si **chacun** est vrai, preuve à l'appui dans le compte rendu :

- [ ] Sur 1 000 parties simulées, rejouer le journal redonne exactement l'état final et toutes les empreintes intermédiaires.
- [ ] Une entrée de journal est lisible par un humain sans outil (identifiants de cartes résolus en noms dans la vue de débogage).
- [ ] La reprise depuis un instantané + queue donne le même état que le rejeu complet.

## 5. Risques & pièges

Journaliser l'état plutôt que les actions : le fichier gonfle, la divergence ne se voit plus, et le replay ment. Le journal enregistre ce qui a été DEMANDÉ et ce que le moteur en a FAIT, pas une photo du plateau.

## 6. Livrables — définition de « fini »

- format de journal versionné
- `rejouer()` + empreintes
- instantanés
- CI GitHub Actions verte sur la PR (elle fait foi, pas une suite verte sur une machine).
- Compte rendu `docs/roadmap/comptes-rendus/j-journal-actions.md` : résumé, livrables, preuves, écarts, reste à faire.
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
python3 docs/roadmap/suivi.py tache j-journal-actions <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu j-journal-actions --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut j-journal-actions <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "j-journal-actions: …" && git push -u origin roadmap/j-journal-actions
bash scripts/ouvrir-pr.sh roadmap/j-journal-actions   # ouvre la PR, ou echoue en disant pourquoi
```

**La PR n'est pas optionnelle** : sans elle, la CI ne tourne pas sur ton travail, et c'est la CI qui fait foi. Si `ouvrir-pr.sh` sort en erreur, tu NE conclus PAS que c'est sans importance : tu nommes le manque dans ton compte rendu et dans ton dernier message.

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

