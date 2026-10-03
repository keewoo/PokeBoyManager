# Lot `j-adversaire-ia` — Adversaire IA : un partenaire d'entraînement qui raisonne et explique ses coups, sur la clé du joueur

> Prompt GÉNÉRÉ depuis `docs/roadmap/jeu/plan/` (via `jeu.json`) par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Plan du jeu : `docs/roadmap/jeu/BACKLOG-JEU.md` · onglet « Backlog du jeu » de `docs/roadmap/ROADMAP.html`.

**P1** · piste Serveur de parties · couloir **J-SRV** (**chimera**) · jalon **J4 — La partie laisse une trace** · palier 17 · taille M · complexité 4/5 · difficulté 3/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur chimera**. Lance `hostname -s` :

- **Chimaera (dans la WSL)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier j-adversaire-ia`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur chimera :

```bash
ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- bash -lc "cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-j-adversaire-ia -b roadmap/j-adversaire-ia origin/main && mkdir -p ~/dev/logs"'
```

3. Lance le lot autonome : par le mécanisme de lots de chimera (`~/dev/lots/launch-lot.sh`, étendu au dépôt `~/dev/pokeboy` par le lot `v0-flotte`), **lancé côté Windows** — un `nohup` interne à la WSL meurt avec la session. Journal : `~/dev/logs/j-adversaire-ia.log`.
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/j-adversaire-ia` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 8 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy (WSL Ubuntu-24.04, utilisateur upgreg)`. Travaille dans ton **worktree** `../wt-j-adversaire-ia`, branche `roadmap/j-adversaire-ia` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier j-adversaire-ia
python3 docs/roadmap/suivi.py demarrer j-adversaire-ia --machine "$(hostname -s)" --branche roadmap/j-adversaire-ia
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut j-adversaire-ia attente_validation --motif "<raisons>"`, section 8, dernier message `ATTENTE VALIDATION — j-adversaire-ia — <raisons>`.
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

**Jalon J4 — La partie laisse une trace.** La fin de partie écrit sur le compte : historique, statistiques par deck, classement privé entre comptes invités, badges. On revient parce qu'il y a quelque chose à suivre.

**Principes du jeu — ils valent pour ce lot comme pour tous les autres :**

- **Le serveur fait autorité.** Le client n'est qu'un écran : il n'apprend jamais la main de l'adversaire ni l'ordre de la pioche, et toute action qu'il propose est rejouée et validée côté serveur.
- **Un effet non implémenté n'est jamais approximé** (D9). Une carte dont l'effet n'est pas scripté et testé est refusée à la construction du deck, en disant pourquoi. Le jeu préfère dire « je ne sais pas jouer cette carte » que de la jouer de travers.
- **Tout est rejouable.** Une partie est un état initial, une graine d'aléatoire et un journal d'actions numéroté. Rejouer le journal doit redonner exactement le même état — c'est ce qui fait tenir la reprise après un F5, le replay, le support et l'anti-triche.
- **Le moteur ne connaît ni HTTP ni React.** Fonctions pures, état sérialisable, aucune entrée/sortie : c'est la seule façon de le tester par milliers de cas et de le faire jouer par des bots.
- **L'interface ne décide de rien.** Elle affiche les actions que le moteur déclare légales, et affiche la raison quand un coup est refusé. Aucune règle n'est réécrite côté écran.
- **Le jeu est celui d'un enfant de onze ans.** Lisible sans connaître les règles, animé, sonore, indulgent : on peut annuler avant de valider, on comprend pourquoi un coup est interdit, et on n'attend jamais devant un écran muet.

**Gain.** DJ7 (JF, 03/10/2026) : le bot d'abord, puis une IA branchée sur la clé de l'utilisateur. Le bot heuristique joue juste mais muet ; l'IA du joueur — le principe même du produit — peut jouer en expliquant pourquoi, ce qui fait d'une partie d'entraînement une leçon pour un enfant de onze ans.

**Fonctionnalités.** Dans une partie d'entraînement, l'adversaire peut être « le bot » ou « mon IA » (fournisseur et clé du coffre du joueur, `pbm_api.ai`) : à chaque décision, l'IA reçoit la **vue** de son camp (jamais l'information cachée) et la liste des coups légaux avec leurs étiquettes, choisit un coup et l'explique en une ou deux phrases simples, en français ; le moteur valide le coup ; l'explication s'affiche dans le journal de la partie. Budget par partie (nombre d'appels plafonné), délai maximal par coup, coût estimé affiché. Sans clé : bot seulement, avec l'explication pour ajouter une clé.

**Vient après :**
- `j-mode-solo` — Partie d'entraînement contre un bot

**Débloque :**
- `j-coach-ia` — Coach IA : un conseil sur demande, et ce qu'on retient d'une partie

**Décision DJ7** — Mode solo contre un bot ? Lis la décision prise dans `docs/roadmap/etat.json` (`decisions_prises.DJ7`) et applique-la à la lettre ; la proposition du pilote n'est qu'un contexte : _Oui, en réutilisant le bot heuristique de la simulation, annoncé comme « entraînement » et non compté au classement._

## 3. Mission

1. Une seule interface « joueur automatique » (bot ou IA) que la partie d'entraînement appelle : l'IA ne contourne ni la validation du moteur ni l'autorité du serveur.
2. Le message envoyé à l'IA ne contient que la vue du joueur IA et les coups légaux : un test parcourt le message à la recherche d'un identifiant caché (main adverse, ordre de la pioche, récompenses) — zéro occurrence.
3. Réponse invalide, absente ou trop lente : c'est le bot qui joue ce coup **et l'écran le dit** (« mon IA n'a pas répondu, le bot a joué à sa place ») — jamais un repli silencieux, jamais un coup inventé.
4. Plafonds : appels par partie, délai par coup, longueur des explications ; coût estimé visible ; clé jamais journalisée ni renvoyée (règles du coffre, `docs/SECURITE.md`).
5. Tests avec un fournisseur factice (coup valide, coup illégal, délai dépassé, réponse non conforme), test d'accès croisé (l'IA d'un joueur ne joue jamais dans la partie d'un autre).

## 4. Critères d'acceptation

Le lot n'est fini que si **chacun** est vrai, preuve à l'appui dans le compte rendu :

- [ ] Une partie d'entraînement se joue jusqu'au bout contre « mon IA » avec un fournisseur factice, chaque coup de l'IA est légal et expliqué.
- [ ] Aucune information cachée n'est envoyée à l'IA (vérifié par un test sur le message).
- [ ] Un échec de l'IA fait jouer le bot et s'affiche ; le plafond d'appels arrête l'IA proprement et le dit.
- [ ] Sans clé IA, l'option « mon IA » explique comment en ajouter une et la partie se joue contre le bot.

## 5. Risques & pièges

Laisser l'IA voir l'état complet « pour qu'elle joue mieux » : ce serait de la triche, et un enfant ne battrait jamais un adversaire qui voit sa main. L'IA joue avec la même vue que n'importe quel joueur.

## 6. Livrables — définition de « fini »

- adversaire « mon IA » dans les parties d'entraînement
- explications des coups dans le journal
- plafonds et coût affiché
- CI GitHub Actions verte sur la PR (elle fait foi, pas une suite verte sur une machine).
- Compte rendu `docs/roadmap/comptes-rendus/j-adversaire-ia.md` : résumé, livrables, preuves, écarts, reste à faire.
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
python3 docs/roadmap/suivi.py tache j-adversaire-ia <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu j-adversaire-ia --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut j-adversaire-ia <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "j-adversaire-ia: …" && git push -u origin roadmap/j-adversaire-ia
bash scripts/ouvrir-pr.sh roadmap/j-adversaire-ia   # ouvre la PR, ou echoue en disant pourquoi
```

**La PR n'est pas optionnelle** : sans elle, la CI ne tourne pas sur ton travail, et c'est la CI qui fait foi. Si `ouvrir-pr.sh` sort en erreur, tu NE conclus PAS que c'est sans importance : tu nommes le manque dans ton compte rendu et dans ton dernier message.

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

