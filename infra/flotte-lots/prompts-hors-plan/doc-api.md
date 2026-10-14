# CONTEXTE D'EXÉCUTION

Tu tournes sur **devAI**, en session autonome (`claude -p`) lancée par la file de lots : **personne ne répondra à une question**. Tu tranches, tu consignes, tu conclus. Lot **hors plan**, demandé par JF le 02/10/2026 (« faudra bien documenter tout le code, y compris avec graphify ») ; ne lance pas `suivi.py verifier/demarrer`, ne touche ni à `etat.json`, ni à `ROADMAP.html`, ni à `BACKLOG.md`, ni à `prompts/`.

- **Où travailler** : sur **chimera** (`ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- bash -s' < script` ; tout script commence par `export PATH=$HOME/.local/bin:$HOME/.local/node/bin:$PATH` ; le SSH coupe souvent : 5 tentatives espacées de 15 s ; un traitement long se lance détaché avec `setsid` et se **sonde dans une seule commande bloquante**). Dépôt `~/dev/pokeboy`, `git fetch github` d'abord (`origin` est un relais qui retarde). Worktree `~/dev/wt-doc-api`, branche `roadmap/doc-api` depuis `github/main`.
- **Le dépôt est graphifié** : dans ton worktree, `graphify update .` puis `graphify query "…"`, `graphify explain "X"`, `graphify affected "X"` avant de lire dix fichiers (`docs/CODE.md` § « Chercher dans le dépôt »). Le graphe oriente, il ne prouve pas.
- **Code documenté** : tout ce que tu ajoutes ou modifies sort avec sa docstring / son `/** … */`, en français (`docs/CODE.md` § « Documenter le code »).
- **Git, CI, fusion** : commits ciblés (jamais `git add -A`, jamais `git stash`), `git push -u github roadmap/doc-api` ; la PR s'ouvre seule (son passage « pull_request » reste en `action_required` : pas un échec). CI **verte** du passage `push` (workflow « CI » seulement), attendue depuis devAI (boucle du rappel final). Fusion sur chimera sous `flock ~/dev/pokeboy.git/pbm-merge.lock` : `git fetch github && git checkout --detach github/main && git merge --no-ff roadmap/doc-api -m "Fusion : doc-api — …" && git push github HEAD:main`, puis CI sur `main`. Le jeton de devAI ne peut pas relancer une CI (`actions: write` absent) : un échec d'infrastructure démontré se relance par un commit vide **sur ta branche**, jamais sur `main`.
- **Aucun déploiement** : la PROD se livre à part, par devAI.

# Mission — documenter `apps/api`

**Mesure du 02/10/2026** : 297 des 764 fonctions et classes publiques de `apps/api/src` ont une docstring (38 %), 134 modules sur 195. **Objectif : 100 % des modules, ≥ 95 % des fonctions et classes publiques**, mesuré par le même script AST avant et après (dans le compte rendu).

**Règle d'or : aucun changement de comportement.** Ce lot n'ajoute que de la documentation. La preuve est mécanique :
- **Python** : pour chaque fichier touché, l'AST **sans les docstrings** est identique avant et après (script de comparaison `ast.dump` après retrait des docstrings, lancé sur tout le diff, résultat dans le compte rendu) ; `ruff` vert ; suite de tests verte.
- **TypeScript** : le diff ne contient **que** des lignes de commentaire (vérifie-le par un filtre sur `git diff -U0`) ; `tsc`, lint, tests et build verts.

**Comment documenter** (`docs/CODE.md` § « Documenter le code ») : en français, le **pourquoi**, les entrées qui comptent, ce que la fonction refuse ou lève, les effets de bord ; pas de paraphrase. Pour savoir pourquoi un code existe, lis le compte rendu du lot qui l'a écrit (`docs/roadmap/comptes-rendus/`, retrouvé par `git log` sur le fichier) et la fiche `docs/` concernée. **Commence par les pivots** : `graphify god-nodes` donne les nœuds les plus connectés — ce sont eux que les lots suivants liront le plus.

**Si le contexte s'épuise avant la fin** : commite et fusionne ce qui est fait, **par paquet cohérent**, avec la couverture atteinte dans le compte rendu — la file relancera le lot, qui reprendra là où tu t'es arrêté. Un lot de documentation à moitié fait et fusionné vaut mieux qu'un lot complet perdu.

**Clôture** : compte rendu `docs/roadmap/comptes-rendus/doc-api.md` (couverture avant/après, par paquet ; preuve « aucun changement de comportement ») commité et fusionné, CI verte sur `main`, `graphify update .` relancé et nombre de nœuds noté, puis dernier message `FAIT — doc-api` ou `BLOQUÉ — doc-api — <raison>`.



---

## ⛔ RAPPEL FINAL — lis ceci avant d'écrire ton dernier message

Tu es une session `claude -p`. **Il n'existe aucune notification** : rien ne te réveillera. Écrire « j'attends », « standing by », « je reprends à la fin de la tâche de fond » ou « le watcher me préviendra » **termine la session** et fait échouer le lot. Deux lots sont morts ainsi le 21/09.

Une attente se code **au premier plan, dans une commande bloquante**, jamais entre deux messages. Les tâches de fond sont **désactivées** dans cette session (`CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`) et une commande ne peut pas dépasser **10 minutes** : une attente plus longue se fait en **plusieurs commandes de 9 minutes**, relancées tant que ce qu'on attend n'est pas fini.

```bash
# attendre la CI GitHub sur un commit (jeton dans ~/.kailo-tokens sur devAI).
# Seul le workflow « CI » compte : « PR automatique des lots » tourne sur le même push et finit
# avant elle — le prendre pour la CI, c'est conclure sur un workflow qui ne teste rien.
source ~/.kailo-tokens
# le SHA est celui que tu as poussé DEPUIS CHIMERA (pas le dossier courant de devAI) :
SHA=$(ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- git -C /home/upgreg/dev/wt-doc-api rev-parse HEAD' | tr -d '\r')
for i in $(seq 1 18); do   # 9 min au plus par commande (outil Bash, timeout 600000) : relance-la tant que la CI tourne
  R=$(curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
      "https://api.github.com/repos/keewoo/PokeBoyManager/actions/runs?head_sha=$SHA&per_page=20" \
      | python3 -c "import json,sys;w=[r for r in json.load(sys.stdin)['workflow_runs'] if r['name']=='CI'];print('aucune' if not w else ('terminee ' + ','.join(sorted({r['conclusion'] or '?' for r in w})) if all(r['status']=='completed' for r in w) else 'en cours'))")
  case "$R" in terminee*) echo "CI : $R"; break;; esac   # « terminee success » et rien d'autre = verte
  sleep 30
done
```

Tu termines **toujours** par la clôture (compte rendu commité **et fusionné dans `main`**) puis `FAIT — doc-api` ou `BLOQUÉ — doc-api — <raison>`.
