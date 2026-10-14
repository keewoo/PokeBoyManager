# CONTEXTE D'EXÉCUTION — prime sur les sections A, P, 0 et 8 du prompt de lot ci-dessous

Tu tournes sur **devAI**, en session autonome (`claude -p`) lancée par la file de lots : **personne ne répondra à une question**. Tu tranches, tu consignes, tu conclus. Ton lot appartient au **backlog du jeu** (`docs/roadmap/jeu/`), couloir `J-MOT` : le moteur de règles, en Python pur.

- **Où travailler** : sur devAI même, dans un **worktree dédié** — jamais dans `~/dev/pokeboy`, dont la file se sert :
  `test -w /Volumes/Data/DevAI/pokeboy/worktrees || { echo "/Volumes/Data absent ou refusé"; exit 1; }; cd ~/dev/pokeboy && git fetch -q origin && git worktree add /Volumes/Data/DevAI/pokeboy/worktrees/wt-<id> -b roadmap/<id> origin/main`.
  **Règle de flotte (JF, 06/10/2026)** : sur devAI, tout travail volumineux vit sur `/Volumes/Data`
  (`/Volumes/Data/DevAI/pokeboy/` : `worktrees/`, `tmp/` pour les fichiers en transit, `ops/`), jamais
  sur le disque système. Volume absent ou écriture refusée : **tu t'arrêtes** —
  `BLOQUÉ — <id> — /Volumes/Data indisponible` —, jamais de repli sur `~/dev`.
  Une fois fusionné, supprime ton worktree (`git -C ~/dev/pokeboy worktree remove /Volumes/Data/DevAI/pokeboy/worktrees/wt-<id>`) : il ne sert plus.
  Si le worktree ou la branche existent déjà, c'est une **reprise** : lis `git log` et le compte rendu éventuel avant de toucher quoi que ce soit.
- **Garde-fou** : `python3 docs/roadmap/suivi.py verifier <id>` dans ton worktree. Code 2 → tu ne codes rien, dernier message `BLOQUÉ — <id> — ordre non tenu : <raisons>`. Ne lance **pas** `suivi.py demarrer` : l'état est tenu par la file.
- **Décisions de JF** : `decisions_prises` dans `docs/roadmap/etat.json` fait foi. Au 01/10/2026 : **DJ1** (règles), **DJ2** (cartes à scripter d'abord), **DJ4** (horloges) sont prises.
- **Tests** : Python **3.12** (`UV_PYTHON=3.12`, `uv run …`) ; le `python3` nu de devAI est le 3.9 système, ne t'en sers que pour `suivi.py`. Le moteur n'a besoin ni de base ni de Docker. Lis `.github/workflows/ci.yml` : un paquet ou une suite que la CI n'exécute pas est une CI **verte sur rien** — ajoute-les au workflow.
- **Git** : commits ciblés (jamais `git add -A`, jamais `git stash`), `git push -u origin roadmap/<id>`. La PR s'ouvre **seule** (workflow `pr-auto`, auteur `github-actions[bot]`) : vérifie qu'elle existe ; sinon `bash scripts/ouvrir-pr.sh roadmap/<id>`.
- **CI** : attends la CI GitHub **verte** sur ta PR (boucle du rappel final). Rouge → tu corriges, tu repousses, tu ré-attends.
- **Fusion** — après CI verte seulement, depuis ton worktree :
  ```bash
  git fetch origin && git checkout --detach origin/main \
    && git merge --no-ff roadmap/<id> -m "Fusion : <id> — <ce que le lot apporte, en une ligne>" \
    && git push origin HEAD:main
  ```
  Push refusé (main a bougé) → recommence fetch + merge. Conflit non trivial → rebase ta branche sur `origin/main`, repousse, ré-attends la CI. Puis attends la CI sur `main` (même boucle, SHA du commit de fusion) : rouge sur `main` = tu répares avant de conclure.
- **Suivi** : ne touche ni à `docs/roadmap/etat.json`, ni à `ROADMAP.html`, ni à `BACKLOG.md`, ni à `prompts/`. La file marque ton lot `integre` dès qu'elle voit ta branche dans `main`. Ton compte rendu va dans `docs/roadmap/comptes-rendus/<id>.md`, commité avec ton travail : il **remplace** les commandes `suivi.py tache / compte-rendu / statut / build` et la republication de l'artefact de la section 8.
- **Règles de fond** : le moteur ne connaît ni HTTP, ni base, ni React ; toute règle appliquée cite son `R-x.y` de `docs/jeu/REGLES.md` ; un effet non implémenté n'est jamais approximé ; aucun repli silencieux ; aucun secret affiché.
- **Traitement long = au premier plan.** Une session `claude -p` se termine dès que tu rends la main : n'écris jamais « j'attends » ou « je reprends à la notification ». Tu finis par la clôture ou par `BLOQUÉ`.
- **Clôture** : compte rendu écrit, commité et fusionné, puis dernier message `FAIT — <id>` ou `BLOQUÉ — <id> — <raison>`.

---

