# CONTEXTE D'EXÉCUTION

Tu tournes sur **devAI**, en session autonome (`claude -p`) lancée par la file de lots : **personne ne répondra à une question**. Tu tranches, tu consignes, tu conclus. Lot **hors plan**, reprise du passage DJ8 demandée par JF le 06/10/2026 (« re run ») pour dépenser le budget restant ; ne lance pas `suivi.py verifier/demarrer`, ne touche ni à `etat.json`, ni à `ROADMAP.html`, ni à `BACKLOG.md`, ni à `prompts/`.

- **Où travailler** : sur **chimera** (`ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- bash -s' < script` ; tout script commence par `export PATH=$HOME/.local/bin:$HOME/.local/node/bin:$PATH` ; le SSH coupe souvent : 5 tentatives espacées de 15 s ; un traitement long se lance détaché avec `setsid` et se **sonde dans une seule commande bloquante**). Dépôt `~/dev/pokeboy`, `git fetch github` d'abord (`origin` est un relais qui retarde). Worktree `~/dev/wt-ia-scripts-passe-3`, branche `roadmap/ia-scripts-passe-3` depuis `github/main`.
- **Le dépôt est graphifié** : dans ton worktree, `graphify update .` puis `graphify query "…"`, `graphify explain "X"`, `graphify affected "X"` avant de lire dix fichiers (`docs/CODE.md` § « Chercher dans le dépôt »). Le graphe oriente, il ne prouve pas.
- **Code documenté** : tout ce que tu ajoutes ou modifies sort avec sa docstring / son `/** … */`, en français (`docs/CODE.md` § « Documenter le code »).
- **Git, CI, fusion** : commits ciblés (jamais `git add -A`, jamais `git stash`), `git push -u github roadmap/ia-scripts-passe-3` ; la PR s'ouvre seule (son passage « pull_request » reste en `action_required` : pas un échec). CI **verte** du passage `push` (workflow « CI » seulement), attendue depuis devAI (boucle du rappel final). Fusion sur chimera sous `flock ~/dev/pokeboy.git/pbm-merge.lock` : `git fetch github && git checkout --detach github/main && git merge --no-ff roadmap/ia-scripts-passe-3 -m "Fusion : ia-scripts-passe-3 — …" && git push github HEAD:main`, puis CI sur `main`. Le jeton de devAI ne peut pas relancer une CI (`actions: write` absent) : un échec d'infrastructure démontré se relance par un commit vide **sur ta branche**, jamais sur `main`.
- **Pas de déploiement de code** ; en revanche ce lot **importe des données** en PROD (étape 5), sous le verrou de livraison et avec un point de restauration — c'est la seule écriture PROD permise.

# Mission — reprendre le passage DJ8 jusqu'au plafond cumulé de 50 €

**Où on en est** (`docs/roadmap/comptes-rendus/ia-scripts-passe-2.md`, 05/10/2026) : génération corrigée, re-mesure à 55 % d'admission, passage de 224 effets → **90 scripts admis**, **88 importés en PROD** (94 scriptés au total) ; effets possédés par JF et Aymeric couverts **36/181** ; **dépense cumulée 9,80 € / 50 €** au grand livre (reprenable). Ni la porte (tests + contradicteur, `ck_card_scripts_scripte_gate`) ni le prompt de génération ne changent dans ce lot.

1. **Reprends le passage** depuis le grand livre, comme `ia-scripts-passe-2` (chimera, `pbm_ia_scripts_ref` ou sa remplaçante à jour, clé plateforme de devAI par entrée standard ou fichier `chmod 600` supprimé à la fin, détaché par `setsid` et sondé en commandes de 9 minutes) : d'abord les **effets possédés** par les comptes ayant l'accès au jeu (liste rafraîchie en lecture seule depuis la PROD — de nouvelles cartes ont pu entrer), puis les **plus fréquents** du catalogue, jusqu'au plafond **cumulé** de 50 €.
2. **Arrêt de rendement** : mesure l'admission par tranche de 50 effets ; si une tranche tombe sous **20 %** parmi les effets que le DSL sait exprimer, tu t'arrêtes là et tu le dis — le reste du budget sert mieux à une version 2 du DSL qu'à des refus.
3. **Import en PROD** comme la dernière fois (chaîne flotte insert-only, sous le verrou de livraison de devAI, point de restauration frais, voisins avant/après), et la preuve : `card_scripts` scriptés avant/après, effets possédés couverts avant/après (sur 181 ou le nouveau total), cartes de JF et d'Aymeric entièrement jouables avant/après, cartes du catalogue jouables avant/après.
4. **Rapport par famille** du passage complet (cumul des deux passages) pour JF : `docs/roadmap/comptes-rendus/ia-scripts-passe-3.md` et `~/dev/logs/pbm-ia-scripts-3-rapport.md` — avec la liste des **familles d'effets hors DSL v1** les plus fréquentes dans les collections (c'est le chantier suivant).
5. **Disque de devAI presque plein** (≈ 15 Go libres le 06/10) : ne laisse rien de volumineux sur devAI (transferts dans un dossier temporaire supprimé à la fin) ; tout le gros travail reste sur chimera.

**Clôture** : compte rendu fusionné, dépense cumulée écrite, import PROD prouvé (ou non fait, avec la raison), puis dernier message `FAIT — ia-scripts-passe-3` ou `BLOQUÉ — ia-scripts-passe-3 — <raison>`.

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
SHA=$(ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- git -C /home/upgreg/dev/wt-ia-scripts-passe-3 rev-parse HEAD' | tr -d '\r')
for i in $(seq 1 18); do   # 9 min au plus par commande (outil Bash, timeout 600000) : relance-la tant que la CI tourne
  R=$(curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
      "https://api.github.com/repos/keewoo/PokeBoyManager/actions/runs?head_sha=$SHA&per_page=20" \
      | python3 -c "import json,sys;w=[r for r in json.load(sys.stdin)['workflow_runs'] if r['name']=='CI'];print('aucune' if not w else ('terminee ' + ','.join(sorted({r['conclusion'] or '?' for r in w})) if all(r['status']=='completed' for r in w) else 'en cours'))")
  case "$R" in terminee*) echo "CI : $R"; break;; esac   # « terminee success » et rien d'autre = verte
  sleep 30
done
```

Tu termines **toujours** par la clôture (compte rendu commité **et fusionné dans `main`**) puis `FAIT — ia-scripts-passe-3` ou `BLOQUÉ — ia-scripts-passe-3 — <raison>`.
