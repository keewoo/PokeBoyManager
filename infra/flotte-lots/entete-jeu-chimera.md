# CONTEXTE D'EXÉCUTION — prime sur les sections A, P, 0 et 8 du prompt de lot ci-dessous

Tu tournes sur **devAI**, en session autonome (`claude -p`) lancée par la file de lots : **personne ne répondra à une question**. Tu tranches, tu consignes, tu conclus. Ton lot appartient au **backlog du jeu** (`docs/roadmap/jeu/`) et à un couloir **chimera** : tu pilotes depuis devAI, tu **travailles sur chimera**, parce que c'est là que vivent le catalogue et la puissance de calcul.

- **Où travailler** : sur **chimera**, jamais dans `~/dev/pokeboy` de devAI (la file s'en sert). Commande type : `ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- bash -s' < script` (déposer un script plutôt qu'un one-liner : le quoting PowerShell casse les commandes en ligne). Dépôt `~/dev/pokeboy` de la WSL, **worktree dédié** `~/dev/wt-<id>`, branche `roadmap/<id>` depuis `github/main` (sur chimera, `origin` est un relais local qui RETARDE : `git fetch github` d'abord). Le SSH de chimera coupe souvent : réessaie plutôt que de conclure à une panne. **Tout script envoyé à chimera commence par `export PATH=$HOME/.local/bin:$PATH`** : `uv` et `claude` y vivent, et `bash -s` n'est pas un shell de connexion — sans cette ligne, `uv` paraît absent alors qu'il est là (c'est le faux « outil absent » du 22/09, `docs/LIVRAISON.md`).
- **Reprise** : si le worktree `~/dev/wt-<id>` ou la branche `roadmap/<id>` existent déjà, c'est une **reprise** d'une tentative coupée (limite d'usage, session arrêtée) : lis `git log`, `git status` et le compte rendu éventuel, et **repars de ce travail** — ne le jette pas.
- **Disques (règle de flotte, JF, 06/10/2026)** : sur **devAI**, rien de volumineux sur le disque système — tout fichier en transit (artefacts, dumps, exports, rapports lourds) passe par `/Volumes/Data/DevAI/pokeboy/tmp/` et en est supprimé à la fin ; volume absent → tu t'arrêtes et tu le dis. Sur **chimera**, la règle de son `~/.claude/CLAUDE.md` (§ Disques) s'applique.
- **Garde-fou** : `python3 docs/roadmap/suivi.py verifier <id>` dans ton worktree. Code 2 → tu ne codes rien, dernier message `BLOQUÉ — <id> — ordre non tenu : <raisons>`. Ne lance **pas** `suivi.py demarrer` : l'état est tenu par la file.
- **Catalogue** : la base de référence de chimera `pbm_catalogue_ref` (conteneur `pbm-shared-postgres-1`, port 55432, voir `docs/infra/JOBS-LOURDS.md`) est **en lecture seule** pour toi. Tes tests ont leur propre base ou leurs propres données ; tu ne modifies jamais une base partagée.
- **Décisions de JF** : `decisions_prises` dans `docs/roadmap/etat.json` fait foi (DJ1, DJ2, DJ4 prises le 01/10/2026). Le moteur (`apps/game`, paquet `pbm_game`) et le corpus `docs/jeu/REGLES.md` sont **livrés** : tu t'y conformes, et toute règle appliquée cite son `R-x.y`.
- **Tests** : Python **3.12** (`uv run …`, un venv par worktree). Le moteur reste **pur** (ni HTTP, ni base, ni réseau — son test d'import le garde) : ce qui lit le catalogue vit **hors** de `pbm_game` (adaptateur côté `apps/api` ou script), et `pbm_game` ne reçoit que des données. Lis `.github/workflows/ci.yml` : un test que la CI n'exécute pas est une CI **verte sur rien**.
- **Git** : commits ciblés (jamais `git add -A`, jamais `git stash`), push sur le remote **`github`** (`git push -u github roadmap/<id>`). La PR s'ouvre **seule** (workflow `pr-auto`). Son passage CI « pull_request » reste en `action_required` (approbation exigée par le dépôt) : ce n'est pas un échec ; c'est le passage déclenché par le **push** qui fait foi.
- **CI** : attends la CI GitHub **verte** — depuis **devAI**, qui a le jeton (boucle du rappel final, avec le SHA de ton commit). Rouge → tu corriges, tu repousses, tu ré-attends.
- **Fusion** — après CI verte seulement, sur chimera, **sous le verrou** :
  ```bash
  cd ~/dev/wt-<id> && flock ~/dev/pokeboy.git/pbm-merge.lock bash -c '
    git fetch github && git checkout --detach github/main \
    && git merge --no-ff roadmap/<id> -m "Fusion : <id> — <ce que le lot apporte, en une ligne>" \
    && git push github HEAD:main'
  ```
  Push refusé (main a bougé) → recommence. Conflit non trivial → rebase ta branche sur `github/main`, repousse, ré-attends la CI. Puis attends la CI sur `main` (SHA du commit de fusion) : rouge sur `main` = tu répares avant de conclure. Un passage **annulé** sur `main` parce qu'un commit plus récent est arrivé n'est pas un échec : c'est alors la CI du commit suivant qui fait foi.
- **Suivi** : ne touche ni à `docs/roadmap/etat.json`, ni à `ROADMAP.html`, ni à `BACKLOG.md`, ni à `prompts/`. La file marque ton lot `integre` dès qu'elle voit ta branche dans `main`. Ton compte rendu va dans `docs/roadmap/comptes-rendus/<id>.md`, commité avec ton travail : il **remplace** les commandes `suivi.py tache / compte-rendu / statut / build` et la republication de l'artefact de la section 8.
- **Règles de fond** : un effet non implémenté n'est jamais approximé (D9) ; aucun repli silencieux ; aucun secret affiché ; aucun traitement lourd sur le serveur de PROD ; **aucun déploiement** (la PROD se livre à part, par devAI).
- **Traitement long = au premier plan.** Une session `claude -p` se termine dès que tu rends la main : n'écris jamais « j'attends » ou « je reprends à la notification ». Tu finis par la clôture ou par `BLOQUÉ`.
- **Clôture** : compte rendu écrit, commité et fusionné, puis dernier message `FAIT — <id>` ou `BLOQUÉ — <id> — <raison>`.

---

