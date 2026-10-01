# Lot `j-effets-catalogue-compilation` — Du catalogue aux cartes jouables : compilation, versions et errata

> Prompt GÉNÉRÉ depuis `docs/roadmap/jeu/plan/` (via `jeu.json`) par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Plan du jeu : `docs/roadmap/jeu/BACKLOG-JEU.md` · onglet « Backlog du jeu » de `docs/roadmap/ROADMAP.html`.

**P0** · piste Effets & cartes · couloir **J-EFF** (**chimera**) · jalon **J2 — Toutes les cartes du deck sont vraiment jouées** · palier 10 · taille L · complexité 4/5 · difficulté 4/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur chimera**. Lance `hostname -s` :

- **Chimaera (dans la WSL)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier j-effets-catalogue-compilation`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur chimera :

```bash
ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- bash -lc "cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-j-effets-catalogue-compilation -b roadmap/j-effets-catalogue-compilation origin/main && mkdir -p ~/dev/logs"'
```

3. Lance le lot autonome : par le mécanisme de lots de chimera (`~/dev/lots/launch-lot.sh`, étendu au dépôt `~/dev/pokeboy` par le lot `v0-flotte`), **lancé côté Windows** — un `nohup` interne à la WSL meurt avec la session. Journal : `~/dev/logs/j-effets-catalogue-compilation.log`.
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/j-effets-catalogue-compilation` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 8 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy (WSL Ubuntu-24.04, utilisateur upgreg)`. Travaille dans ton **worktree** `../wt-j-effets-catalogue-compilation`, branche `roadmap/j-effets-catalogue-compilation` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier j-effets-catalogue-compilation
python3 docs/roadmap/suivi.py demarrer j-effets-catalogue-compilation --machine "$(hostname -s)" --branche roadmap/j-effets-catalogue-compilation
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut j-effets-catalogue-compilation attente_validation --motif "<raisons>"`, section 8, dernier message `ATTENTE VALIDATION — j-effets-catalogue-compilation — <raisons>`.
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

**Gain.** C'est le pont entre les trente mille cartes du catalogue et les cartes réellement jouables. Sans lui, chaque carte est un travail manuel sans mémoire.

**Fonctionnalités.** Une table `card_scripts` : carte, version du langage, script, statut (scripté / non supporté / à revoir), empreinte du texte source, auteur, date de validation, tests associés. Quand le texte d'une carte change en base (correction du catalogue, errata), l'empreinte ne correspond plus et le script repasse « à revoir » — il ne peut plus être joué tant qu'il n'a pas été confirmé.

**Vient après :**
- `j-effets-dsl` — Langage d'effets : décrire ce que fait une carte, sans écrire de code par carte
- `j-cartes-pokemon` — Cartes Pokémon : base, évolutions, marqueurs de règle

**Débloque :**
- `j-effets-assistance-ia` — Assistance IA : proposer le script d'une carte, jamais le valider seule
- `j-effets-couverture-outil` — Tableau de couverture : ce qui est jouable, ce qui manque, et pour qui

**Décision DJ2** — Quel périmètre de cartes scripter en premier ? Lis la décision prise dans `docs/roadmap/etat.json` (`decisions_prises.DJ2`) et applique-la à la lettre ; la proposition du pilote n'est qu'un contexte : _Piloté par la collection : on script d'abord les cartes réellement possédées par les comptes invités, puis les cartes les plus fréquentes du catalogue. Le tableau de couverture dit à tout moment ce qui manque pour rendre un deck jouable._

## 3. Mission

1. Créer la table et ses migrations, avec l'empreinte du texte source par langue.
2. Écrire le chargeur qui, au lancement d'une partie, résout chaque carte du deck vers son script validé — et refuse la partie si l'une manque.
3. Détecter les textes modifiés et basculer automatiquement les scripts concernés en « à revoir ».
4. Regrouper les cartes par texte identique : des centaines de cartes partagent le même effet, un script doit pouvoir en couvrir plusieurs.
5. Commande de maintenance : importer, valider, lister, diffuser les scripts.

## 4. Critères d'acceptation

Le lot n'est fini que si **chacun** est vrai, preuve à l'appui dans le compte rendu :

- [ ] Une carte dont le texte a changé ne se joue plus avec l'ancien script : elle passe « à revoir » et le deck le dit.
- [ ] Le regroupement par texte identique réduit mesurablement le nombre de scripts à écrire (chiffre publié dans le compte rendu).
- [ ] Le lancement d'une partie avec une carte non scriptée est refusé avant la mise en place, jamais en plein milieu.

## 5. Risques & pièges

La tentation d'un repli « script manquant → effet neutre » : c'est précisément l'approximation interdite par D9. Une carte sans script bloque le deck, et le dit.

## 6. Livrables — définition de « fini »

- table `card_scripts` + migrations
- chargeur de partie
- détection d'errata
- CI GitHub Actions verte sur la PR (elle fait foi, pas une suite verte sur une machine).
- Compte rendu `docs/roadmap/comptes-rendus/j-effets-catalogue-compilation.md` : résumé, livrables, preuves, écarts, reste à faire.
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
python3 docs/roadmap/suivi.py tache j-effets-catalogue-compilation <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu j-effets-catalogue-compilation --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut j-effets-catalogue-compilation <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "j-effets-catalogue-compilation: …" && git push -u origin roadmap/j-effets-catalogue-compilation
bash scripts/ouvrir-pr.sh roadmap/j-effets-catalogue-compilation   # ouvre la PR, ou echoue en disant pourquoi
```

**La PR n'est pas optionnelle** : sans elle, la CI ne tourne pas sur ton travail, et c'est la CI qui fait foi. Si `ouvrir-pr.sh` sort en erreur, tu NE conclus PAS que c'est sans importance : tu nommes le manque dans ton compte rendu et dans ton dernier message.

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

