# CONTEXTE D'EXÉCUTION

Tu tournes sur **devAI**, en session autonome (`claude -p`) lancée par la file de lots : **personne ne répondra à une question**. Tu tranches, tu consignes, tu conclus. Lot **hors plan**, ouvert par le pilote le 03/10/2026 après le double blocage de `livraison-jeu-coups` (13:07 et 13:22) ; JF a demandé que le jeu soit jouable ; ne lance pas `suivi.py verifier/demarrer`, ne touche ni à `etat.json`, ni à `ROADMAP.html`, ni à `BACKLOG.md`, ni à `prompts/`.

- **Où travailler** : sur **chimera** (`ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- bash -s' < script` ; tout script commence par `export PATH=$HOME/.local/bin:$HOME/.local/node/bin:$PATH` ; le SSH coupe souvent : 5 tentatives espacées de 15 s ; un traitement long se lance détaché avec `setsid` et se **sonde dans une seule commande bloquante**). Dépôt `~/dev/pokeboy`, `git fetch github` d'abord (`origin` est un relais qui retarde). Worktree `~/dev/wt-fix-projection-evenements`, branche `roadmap/fix-projection-evenements` depuis `github/main`.
- **Le dépôt est graphifié** : dans ton worktree, `graphify update .` puis `graphify query "…"`, `graphify explain "X"`, `graphify affected "X"` avant de lire dix fichiers (`docs/CODE.md` § « Chercher dans le dépôt »). Le graphe oriente, il ne prouve pas.
- **Code documenté** : tout ce que tu ajoutes ou modifies sort avec sa docstring / son `/** … */`, en français (`docs/CODE.md` § « Documenter le code »).
- **Git, CI, fusion** : commits ciblés (jamais `git add -A`, jamais `git stash`), `git push -u github roadmap/fix-projection-evenements` ; la PR s'ouvre seule (son passage « pull_request » reste en `action_required` : pas un échec). CI **verte** du passage `push` (workflow « CI » seulement), attendue depuis devAI (boucle du rappel final). Fusion sur chimera sous `flock ~/dev/pokeboy.git/pbm-merge.lock` : `git fetch github && git checkout --detach github/main && git merge --no-ff roadmap/fix-projection-evenements -m "Fusion : fix-projection-evenements — …" && git push github HEAD:main`, puis CI sur `main`. Le jeton de devAI ne peut pas relancer une CI (`actions: write` absent) : un échec d'infrastructure démontré se relance par un commit vide **sur ta branche**, jamais sur `main`.
- **Aucun déploiement** : la PROD se livre à part, par devAI.

# Mission — sept événements sans projecteur : le premier vrai coup renvoie 500

**Le constat** (`docs/LIVRAISON.md`, « Tentative de livraison des coups du joueur — 03/10/2026 — BLOQUÉE ») : `j-coups-joueur` et la mise en place émettent sept types d'événements absents de `PROJECTEURS` (`apps/game/src/pbm_game/sortie/evenements.py`) : `energie_attachee`, `placement_cache`, `mulligan`, `main_revelee`, `mise_en_place_prete`, `mise_en_place_revelee`, `fin_tour`. `projeter_evenement` les refuse (à raison : jamais de repli), donc `POST /games/{id}/actions` (`placer_mise_en_place`) répond **500**, et le WebSocket ne reçoit aucune resync. La CI était verte parce que les tests de partie complète passent par `appliquer_action` / `reprendre_partie`, **jamais** par `projeter_resultat` / `resynchroniser`.

1. **Déclare les sept projecteurs**, chacun avec sa décision de visibilité **écrite** (docstring + `docs/jeu/` concernée) et citée à `docs/jeu/REGLES.md` :
   - `placement_cache` — R-4.2 : Pokémon posés **face cachée** ; le propriétaire voit ses cartes, l'adversaire n'en voit que le **nombre et les emplacements**, **jamais** les identités ni les `instance_id` qui permettraient de les suivre ;
   - `mise_en_place_revelee` — la révélation rend Actif et banc **publics** ;
   - `mulligan`, `main_revelee` — R-4.4 : la main d'un mulligan est **révélée à l'adversaire** (publique à ce moment-là, et seulement celle-là) ; tranche ce que montre `mulligan` lui-même (nombre de mulligans, R-4.5) ;
   - `mise_en_place_prete`, `fin_tour`, `energie_attachee` — publics, sans information de main ni de pioche.
   Si une règle ne tranche pas un cas, choisis le **moins révélateur** et écris pourquoi.
2. **Test de parité** : tout type d'`Evenement` que le moteur peut produire a une entrée dans `PROJECTEURS` (énumération statique des émetteurs ou registre des types) — un futur événement sans projecteur casse **en CI**, plus jamais en PROD.
3. **Test qui exerce la vraie sortie** : une partie complète (mise en place avec mulligan, énergies, attaques, K.O., récompenses, fin) jouée **par les routes HTTP et le WebSocket** du service (client de test FastAPI), qui vérifie à chaque coup la réponse 200, la diffusion aux deux joueurs, et l'**absence de fuite** dans la vue de chacun (main adverse, pioche, cartes face cachée avant révélation) — par un parcours de la structure projetée, comme le test de non-fuite de `j-modele-etat`.
4. **Rejoue le scénario de la livraison** qui a échoué (deux comptes, decks Pokémon + Énergies de base, `placer_mise_en_place` puis tours réels) dans ce test, pour prouver que le 500 a disparu.
5. Compte rendu `docs/roadmap/comptes-rendus/fix-projection-evenements.md` : les sept décisions de visibilité, les règles citées, les preuves.

**Clôture** : compte rendu commité et fusionné dans `main`, CI verte sur `main`, puis dernier message `FAIT — fix-projection-evenements` ou `BLOQUÉ — fix-projection-evenements — <raison>`.



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
SHA=$(ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- git -C /home/upgreg/dev/wt-fix-projection-evenements rev-parse HEAD' | tr -d '\r')
for i in $(seq 1 18); do   # 9 min au plus par commande (outil Bash, timeout 600000) : relance-la tant que la CI tourne
  R=$(curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
      "https://api.github.com/repos/keewoo/PokeBoyManager/actions/runs?head_sha=$SHA&per_page=20" \
      | python3 -c "import json,sys;w=[r for r in json.load(sys.stdin)['workflow_runs'] if r['name']=='CI'];print('aucune' if not w else ('terminee ' + ','.join(sorted({r['conclusion'] or '?' for r in w})) if all(r['status']=='completed' for r in w) else 'en cours'))")
  case "$R" in terminee*) echo "CI : $R"; break;; esac   # « terminee success » et rien d'autre = verte
  sleep 30
done
```

Tu termines **toujours** par la clôture (compte rendu commité **et fusionné dans `main`**) puis `FAIT — fix-projection-evenements` ou `BLOQUÉ — fix-projection-evenements — <raison>`.
