# Lot `j-anim-attaques-typees` — Une attaque Feu brûle la carte d'en face : un effet par type

> Prompt GÉNÉRÉ depuis `docs/roadmap/jeu/plan/` (via `jeu.json`) par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Plan du jeu : `docs/roadmap/jeu/BACKLOG-JEU.md` · onglet « Backlog du jeu » de `docs/roadmap/ROADMAP.html`.

**P1** · piste Graphisme & animations · couloir **J-GFX** (**chimera**) · jalon **J3 — Le plateau donne envie d'y jouer** · palier 15 · taille L · complexité 4/5 · difficulté 4/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur chimera**. Lance `hostname -s` :

- **Chimaera (dans la WSL)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier j-anim-attaques-typees`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur chimera :

```bash
ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- bash -lc "cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-j-anim-attaques-typees -b roadmap/j-anim-attaques-typees origin/main && mkdir -p ~/dev/logs"'
```

3. Lance le lot autonome : par le mécanisme de lots de chimera (`~/dev/lots/launch-lot.sh`, étendu au dépôt `~/dev/pokeboy` par le lot `v0-flotte`), **lancé côté Windows** — un `nohup` interne à la WSL meurt avec la session. Journal : `~/dev/logs/j-anim-attaques-typees.log`.
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/j-anim-attaques-typees` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 8 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy (WSL Ubuntu-24.04, utilisateur upgreg)`. Travaille dans ton **worktree** `../wt-j-anim-attaques-typees`, branche `roadmap/j-anim-attaques-typees` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier j-anim-attaques-typees
python3 docs/roadmap/suivi.py demarrer j-anim-attaques-typees --machine "$(hostname -s)" --branche roadmap/j-anim-attaques-typees
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut j-anim-attaques-typees attente_validation --motif "<raisons>"`, section 8, dernier message `ATTENTE VALIDATION — j-anim-attaques-typees — <raisons>`.
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

**Jalon J3 — Le plateau donne envie d'y jouer.** La carte, c'est SA photo ou l'image officielle. Une attaque Feu brûle la carte d'en face, l'éclair fait trembler le plateau, certains Pokémon apparaissent au-dessus de leur carte. Le tout reste lisible, coupable en un clic, et respecte « animations réduites ».

**Principes du jeu — ils valent pour ce lot comme pour tous les autres :**

- **Le serveur fait autorité.** Le client n'est qu'un écran : il n'apprend jamais la main de l'adversaire ni l'ordre de la pioche, et toute action qu'il propose est rejouée et validée côté serveur.
- **Un effet non implémenté n'est jamais approximé** (D9). Une carte dont l'effet n'est pas scripté et testé est refusée à la construction du deck, en disant pourquoi. Le jeu préfère dire « je ne sais pas jouer cette carte » que de la jouer de travers.
- **Tout est rejouable.** Une partie est un état initial, une graine d'aléatoire et un journal d'actions numéroté. Rejouer le journal doit redonner exactement le même état — c'est ce qui fait tenir la reprise après un F5, le replay, le support et l'anti-triche.
- **Le moteur ne connaît ni HTTP ni React.** Fonctions pures, état sérialisable, aucune entrée/sortie : c'est la seule façon de le tester par milliers de cas et de le faire jouer par des bots.
- **L'interface ne décide de rien.** Elle affiche les actions que le moteur déclare légales, et affiche la raison quand un coup est refusé. Aucune règle n'est réécrite côté écran.
- **Le jeu est celui d'un enfant de onze ans.** Lisible sans connaître les règles, animé, sonore, indulgent : on peut annuler avant de valider, on comprend pourquoi un coup est interdit, et on n'attend jamais devant un écran muet.

**Gain.** C'est la demande explicite de JF, et c'est ce qui fait qu'un enfant a envie de rejouer : l'attaque doit se voir et se sentir, pas s'afficher en chiffres.

**Fonctionnalités.** Un effet par type d'énergie, joué sur la carte cible : **Feu** — flammes qui lèchent la carte adverse, bords qui noircissent, braises qui retombent ; **Eau** — vague qui traverse, ruissellement, carte trempée ; **Plante** — lianes qui enserrent, pétales ; **Électrique** — arc, flash blanc, tremblement du plateau ; **Psy** — onde concentrique, distorsion de l'image de la carte ; **Combat** — impact, fissure, recul ; **Obscurité** — ombre qui engloutit ; **Métal** — éclat, étincelles ; **Dragon** — souffle ; **Fée** — étoiles. Intensité proportionnelle aux dégâts, effet renforcé en cas de faiblesse, effet atténué en cas de résistance, effet particulier pour un échec au pile ou face.

**Vient après :**
- `j-anim-socle` — Socle d'animation : les effets suivent les événements, jamais l'inverse

**Débloque :**
- aucun lot n'en dépend

## 3. Mission

1. Écrire les effets en shaders/canvas légers réutilisables, paramétrés par intensité — pas dix animations sans rapport entre elles.
2. Lier l'intensité au résultat réel : dégâts infligés, faiblesse appliquée, résistance, échec.
3. Faire subsister une trace brève (la carte brûlée reste noircie une seconde) sans jamais masquer les compteurs de dégâts.
4. Prévoir la version réduite de chaque effet pour `prefers-reduced-motion` et pour les appareils lents.
5. Faire valider le rendu par JF et par Aymeric avant d'industrialiser les dix types.

## 4. Critères d'acceptation

Le lot n'est fini que si **chacun** est vrai, preuve à l'appui dans le compte rendu :

- [ ] Les dix types ont leur effet, et l'intensité reflète le résultat du calcul.
- [ ] L'effet ne masque jamais l'état du plateau plus d'une seconde.
- [ ] La version réduite existe pour chaque effet et reste compréhensible.
- [ ] Le plancher d'images par seconde est tenu avec l'effet le plus lourd.

## 5. Risques & pièges

Dix animations écrites séparément : impossible à maintenir, et l'une d'elles finira par cacher un compteur de dégâts au moment décisif.

## 6. Livrables — définition de « fini »

- dix effets typés paramétrés
- versions réduites
- validation par JF
- CI GitHub Actions verte sur la PR (elle fait foi, pas une suite verte sur une machine).
- Compte rendu `docs/roadmap/comptes-rendus/j-anim-attaques-typees.md` : résumé, livrables, preuves, écarts, reste à faire.
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
python3 docs/roadmap/suivi.py tache j-anim-attaques-typees <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu j-anim-attaques-typees --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut j-anim-attaques-typees <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "j-anim-attaques-typees: …" && git push -u origin roadmap/j-anim-attaques-typees
bash scripts/ouvrir-pr.sh roadmap/j-anim-attaques-typees   # ouvre la PR, ou echoue en disant pourquoi
```

**La PR n'est pas optionnelle** : sans elle, la CI ne tourne pas sur ton travail, et c'est la CI qui fait foi. Si `ouvrir-pr.sh` sort en erreur, tu NE conclus PAS que c'est sans importance : tu nommes le manque dans ton compte rendu et dans ton dernier message.

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

