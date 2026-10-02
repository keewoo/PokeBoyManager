# Lot `j-mise-en-ligne-jeu` — Mettre le jeu en ligne sur le serveur partagé

> Prompt GÉNÉRÉ depuis `docs/roadmap/jeu/plan/` (via `jeu.json`) par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Plan du jeu : `docs/roadmap/jeu/BACKLOG-JEU.md` · onglet « Backlog du jeu » de `docs/roadmap/ROADMAP.html`.

**P0** · piste Qualité & exploitation · couloir **J-SRV** (**chimera**) · jalon **J5 — Le jeu tient debout tout seul** · palier 18 · taille M · complexité 3/5 · difficulté 3/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur chimera**. Lance `hostname -s` :

- **Chimaera (dans la WSL)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier j-mise-en-ligne-jeu`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur chimera :

```bash
ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- bash -lc "cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-j-mise-en-ligne-jeu -b roadmap/j-mise-en-ligne-jeu origin/main && mkdir -p ~/dev/logs"'
```

3. Lance le lot autonome : par le mécanisme de lots de chimera (`~/dev/lots/launch-lot.sh`, étendu au dépôt `~/dev/pokeboy` par le lot `v0-flotte`), **lancé côté Windows** — un `nohup` interne à la WSL meurt avec la session. Journal : `~/dev/logs/j-mise-en-ligne-jeu.log`.
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/j-mise-en-ligne-jeu` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 8 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy (WSL Ubuntu-24.04, utilisateur upgreg)`. Travaille dans ton **worktree** `../wt-j-mise-en-ligne-jeu`, branche `roadmap/j-mise-en-ligne-jeu` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier j-mise-en-ligne-jeu
python3 docs/roadmap/suivi.py demarrer j-mise-en-ligne-jeu --machine "$(hostname -s)" --branche roadmap/j-mise-en-ligne-jeu
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut j-mise-en-ligne-jeu attente_validation --motif "<raisons>"`, section 8, dernier message `ATTENTE VALIDATION — j-mise-en-ligne-jeu — <raisons>`.
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

**Jalon J5 — Le jeu tient debout tout seul.** Des bots jouent des milliers de parties sans bloquer, l'e2e passe en CI, le petit serveur encaisse les parties simultanées prévues, et une règle qui casse se voit dans une métrique avant de se voir dans une plainte.

**Principes du jeu — ils valent pour ce lot comme pour tous les autres :**

- **Le serveur fait autorité.** Le client n'est qu'un écran : il n'apprend jamais la main de l'adversaire ni l'ordre de la pioche, et toute action qu'il propose est rejouée et validée côté serveur.
- **Un effet non implémenté n'est jamais approximé** (D9). Une carte dont l'effet n'est pas scripté et testé est refusée à la construction du deck, en disant pourquoi. Le jeu préfère dire « je ne sais pas jouer cette carte » que de la jouer de travers.
- **Tout est rejouable.** Une partie est un état initial, une graine d'aléatoire et un journal d'actions numéroté. Rejouer le journal doit redonner exactement le même état — c'est ce qui fait tenir la reprise après un F5, le replay, le support et l'anti-triche.
- **Le moteur ne connaît ni HTTP ni React.** Fonctions pures, état sérialisable, aucune entrée/sortie : c'est la seule façon de le tester par milliers de cas et de le faire jouer par des bots.
- **L'interface ne décide de rien.** Elle affiche les actions que le moteur déclare légales, et affiche la raison quand un coup est refusé. Aucune règle n'est réécrite côté écran.
- **Le jeu est celui d'un enfant de onze ans.** Lisible sans connaître les règles, animé, sonore, indulgent : on peut annuler avant de valider, on comprend pourquoi un coup est interdit, et on n'attend jamais devant un écran muet.

**Gain.** Le jeu ne vaut que joué. Et il doit arriver sur une machine qui sert déjà deux autres sites, sans les mettre en péril.

**Fonctionnalités.** Images construites sur chimera et tirées par le serveur (jamais construites sur place), service de temps réel derrière le proxy avec WebSocket, migrations appliquées, plafond de parties simultanées configuré, sauvegarde des parties, surveillance branchée, procédure de retour arrière.

**Vient après :**
- `j-securite-jeu` — Revue de sécurité du jeu avant ouverture
- `j-charge-temps-reel` — Tenue en charge : combien de parties simultanées sur deux cœurs
- `j-fin-effets-compte` — Ce qu'une partie laisse sur le compte : écriture unique et exacte

**Débloque :**
- aucun lot n'en dépend

## 3. Mission

1. Construire sur chimera, publier les images, faire tirer le serveur (`pull` + `up -d`) — la règle du projet.
2. Configurer le proxy pour le WebSocket et vérifier la reprise de connexion à travers lui.
3. Appliquer les migrations et vérifier la purge et les sauvegardes des tables de parties.
4. Écrire la procédure de retour arrière et l'essayer une fois pour de vrai.
5. Ne conclure « en ligne » que sur une partie réellement jouée de bout en bout par deux comptes.

## 4. Critères d'acceptation

Le lot n'est fini que si **chacun** est vrai, preuve à l'appui dans le compte rendu :

- [ ] Aucune construction d'image n'a lieu sur le serveur qui sert les visiteurs.
- [ ] Une partie complète est jouée en production par deux comptes, et la preuve est jointe.
- [ ] Le retour arrière a été exécuté une fois et documenté.
- [ ] Les autres sites du serveur ne sont pas dégradés pendant la mise en ligne (mesures avant/après).

## 5. Risques & pièges

Conclure « déployé » sur une ligne de journal : un build en échec laisse la plateforme debout sur les anciennes images, tout a l'air normal et rien n'est livré.

## 6. Livrables — définition de « fini »

- jeu en production
- procédure de retour arrière éprouvée
- preuve de partie jouée
- CI GitHub Actions verte sur la PR (elle fait foi, pas une suite verte sur une machine).
- Compte rendu `docs/roadmap/comptes-rendus/j-mise-en-ligne-jeu.md` : résumé, livrables, preuves, écarts, reste à faire.
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
python3 docs/roadmap/suivi.py tache j-mise-en-ligne-jeu <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu j-mise-en-ligne-jeu --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut j-mise-en-ligne-jeu <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "j-mise-en-ligne-jeu: …" && git push -u origin roadmap/j-mise-en-ligne-jeu
bash scripts/ouvrir-pr.sh roadmap/j-mise-en-ligne-jeu   # ouvre la PR, ou echoue en disant pourquoi
```

**La PR n'est pas optionnelle** : sans elle, la CI ne tourne pas sur ton travail, et c'est la CI qui fait foi. Si `ouvrir-pr.sh` sort en erreur, tu NE conclus PAS que c'est sans importance : tu nommes le manque dans ton compte rendu et dans ton dernier message.

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

