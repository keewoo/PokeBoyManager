# CONTEXTE D'EXÉCUTION

Tu tournes sur **devAI**, en session autonome (`claude -p`) lancée par la file de lots : **personne ne répondra à une question**. Tu tranches, tu consignes, tu conclus. Lot **hors plan**, ouvert par le pilote le 04/10/2026, premier lot du chantier des effets (« go pour le gros chantier effet », JF) ; ne lance pas `suivi.py verifier/demarrer`, ne touche ni à `etat.json`, ni à `ROADMAP.html`, ni à `BACKLOG.md`, ni à `prompts/`.

- **Où travailler** : sur **chimera** (`ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- bash -s' < script` ; tout script commence par `export PATH=$HOME/.local/bin:$HOME/.local/node/bin:$PATH` ; le SSH coupe souvent : 5 tentatives espacées de 15 s ; un traitement long se lance détaché avec `setsid` et se **sonde dans une seule commande bloquante**). Dépôt `~/dev/pokeboy`, `git fetch github` d'abord (`origin` est un relais qui retarde). Worktree `~/dev/wt-cat-stades`, branche `roadmap/cat-stades` depuis `github/main`.
- **Le dépôt est graphifié** : dans ton worktree, `graphify update .` puis `graphify query "…"`, `graphify explain "X"`, `graphify affected "X"` avant de lire dix fichiers (`docs/CODE.md` § « Chercher dans le dépôt »). Le graphe oriente, il ne prouve pas.
- **Code documenté** : tout ce que tu ajoutes ou modifies sort avec sa docstring / son `/** … */`, en français (`docs/CODE.md` § « Documenter le code »).
- **Git, CI, fusion** : commits ciblés (jamais `git add -A`, jamais `git stash`), `git push -u github roadmap/cat-stades` ; la PR s'ouvre seule (son passage « pull_request » reste en `action_required` : pas un échec). CI **verte** du passage `push` (workflow « CI » seulement), attendue depuis devAI (boucle du rappel final). Fusion sur chimera sous `flock ~/dev/pokeboy.git/pbm-merge.lock` : `git fetch github && git checkout --detach github/main && git merge --no-ff roadmap/cat-stades -m "Fusion : cat-stades — …" && git push github HEAD:main`, puis CI sur `main`. Le jeton de devAI ne peut pas relancer une CI (`actions: write` absent) : un échec d'infrastructure démontré se relance par un commit vide **sur ta branche**, jamais sur `main`.
- **Aucun déploiement** : la PROD se livre à part, par devAI.

# Mission — le stade de chaque Pokémon du catalogue

**Le constat** (03/10/2026, en remplissant la collection de JF) : le catalogue de PROD ne compte que **30 cartes jouables** (26 espèces). Une grande partie des Pokémon n'ont **pas de stade** (`cards.stage` vide — Zekrom, Kyurem Blanc / Noir, Magicarpe Brillant…) et `definition_depuis_card` (`apps/api/src/pbm_api/jeu/catalogue.py`) les **bloque** à raison (R-7 : « stade absent du catalogue — carte bloquée, jamais deviné »). Tant que ce trou existe, aucun script d'effet ne rendra ces cartes jouables.

1. **Mesure** sur `pbm_catalogue_ref` (chimera) : Pokémon sans stade, par série et par langue ; et ce que TCGdex renvoie pour un échantillon (champ `stage`, en français puis en anglais — l'import connaît déjà le repli anglais, `fix/catalogue-repli-en`).
2. **Import** (`catalog/import_service.py`) : le stade est pris dans la langue du catalogue, sinon en anglais, normalisé par la **même** fonction que la classification des marqueurs (`Stage1` = `stage 1` = `Niveau 1`, lot `fix-marqueur-stades`) ; une carte dont **aucune** source ne donne le stade reste vide **et se compte** — jamais un stade deviné (pas de déduction depuis le nom ou les PV).
3. **Remplissage du catalogue de référence** par la voie normale de l'import (lien de chimera ~250 Ko/s : mesure le volume, bride la concurrence, passe par devAI si c'est lourd).
4. **Le chemin vers la PROD** : vérifie que l'export/import flotte (`infra/fleet/export_cards.sql`, `import_weekly.sql`, `docs/infra/JOBS-LOURDS.md`) transporte `stage` ; corrige-le sinon. Ne touche pas la PROD : c'est la livraison qui importera.
5. **Preuve chiffrée** : Pokémon sans stade avant/après ; et surtout **cartes que `definition_depuis_card` accepte** avant/après sur tout le catalogue de référence (c'est le chiffre qui compte pour le jeu). Mets à jour `docs/catalogue/COMPLETUDE.md`.
6. **Tests** : import d'un Pokémon dont le stade n'existe qu'en anglais, d'un `Stage1` sans espace, d'une carte sans stade nulle part (reste vide, comptée).

**Clôture** : compte rendu `docs/roadmap/comptes-rendus/cat-stades.md` commité et fusionné, CI verte sur `main`, puis dernier message `FAIT — cat-stades` ou `BLOQUÉ — cat-stades — <raison>`.



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
SHA=$(ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- git -C /home/upgreg/dev/wt-cat-stades rev-parse HEAD' | tr -d '\r')
for i in $(seq 1 18); do   # 9 min au plus par commande (outil Bash, timeout 600000) : relance-la tant que la CI tourne
  R=$(curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
      "https://api.github.com/repos/keewoo/PokeBoyManager/actions/runs?head_sha=$SHA&per_page=20" \
      | python3 -c "import json,sys;w=[r for r in json.load(sys.stdin)['workflow_runs'] if r['name']=='CI'];print('aucune' if not w else ('terminee ' + ','.join(sorted({r['conclusion'] or '?' for r in w})) if all(r['status']=='completed' for r in w) else 'en cours'))")
  case "$R" in terminee*) echo "CI : $R"; break;; esac   # « terminee success » et rien d'autre = verte
  sleep 30
done
```

Tu termines **toujours** par la clôture (compte rendu commité **et fusionné dans `main`**) puis `FAIT — cat-stades` ou `BLOQUÉ — cat-stades — <raison>`.
