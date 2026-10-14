# CONTEXTE D'EXÉCUTION

Tu tournes sur **devAI**, en session autonome (`claude -p`) lancée par la file de lots : **personne ne répondra à une question**. Tu tranches, tu consignes, tu conclus. Lot **hors plan**, ouvert par le pilote le 02/10/2026 (vague validée par JF : « Oui, les 4 »), préalable aux lots d'effets du jeu ; ne lance pas `suivi.py verifier/demarrer`, ne touche ni à `etat.json`, ni à `ROADMAP.html`, ni à `BACKLOG.md`, ni à `prompts/`.

- **Où travailler** : sur **chimera** (`ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- bash -s' < script` ; tout script commence par `export PATH=$HOME/.local/bin:$HOME/.local/node/bin:$PATH` ; le SSH coupe souvent : 5 tentatives espacées de 15 s ; un traitement long se lance détaché avec `setsid` et se **sonde dans une seule commande bloquante**). Dépôt `~/dev/pokeboy`, `git fetch github` d'abord (`origin` est un relais qui retarde). Worktree `~/dev/wt-cat-textes-effets`, branche `roadmap/cat-textes-effets` depuis `github/main`.
- **Le dépôt est graphifié** : dans ton worktree, `graphify update .` puis `graphify query "…"`, `graphify explain "X"`, `graphify affected "X"` avant de lire dix fichiers (`docs/CODE.md` § « Chercher dans le dépôt »). Le graphe oriente, il ne prouve pas.
- **Code documenté** : tout ce que tu ajoutes ou modifies sort avec sa docstring / son `/** … */`, en français (`docs/CODE.md` § « Documenter le code »).
- **Git, CI, fusion** : commits ciblés (jamais `git add -A`, jamais `git stash`), `git push -u github roadmap/cat-textes-effets` ; la PR s'ouvre seule (son passage « pull_request » reste en `action_required` : pas un échec). CI **verte** du passage `push` (workflow « CI » seulement), attendue depuis devAI (boucle du rappel final). Fusion sur chimera sous `flock ~/dev/pokeboy.git/pbm-merge.lock` : `git fetch github && git checkout --detach github/main && git merge --no-ff roadmap/cat-textes-effets -m "Fusion : cat-textes-effets — …" && git push github HEAD:main`, puis CI sur `main`. Le jeton de devAI ne peut pas relancer une CI (`actions: write` absent) : un échec d'infrastructure démontré se relance par un commit vide **sur ta branche**, jamais sur `main`.
- **Aucun déploiement** : la PROD se livre à part, par devAI.

# Mission — le texte d'effet des Dresseurs et des Énergies dans le catalogue

**Le constat** (compte rendu de `j-effets-architecture`, 02/10/2026) : **2 766 des 2 873 Dresseurs** du catalogue n'ont ni `abilities` ni `attacks` — leur **texte d'effet n'est pas stocké**, pas plus que celui des Énergies spéciales. Or tout le chantier des effets du jeu (`j-effets-dsl`, `j-effets-catalogue-compilation`, `j-cartes-objets`, `j-cartes-supporters`, `j-cartes-stades`, `j-cartes-outils`, `j-cartes-energies`) part de ce texte : sans lui, aucune carte Dresseur ne peut être scriptée, et la règle D9 les refuserait toutes.

1. **Inventaire** : colonnes de `cards` (et tables liées) qui pourraient déjà porter ce texte ; échantillon de réponses TCGdex pour des Objets, Supporters, Stades, Outils, Énergies spéciales (champ `effect`, sous-type `trainerType` / `energyType`, et leurs équivalents) dans la langue du catalogue — regarde comment l'import gère déjà la langue et le repli anglais (`fix/catalogue-repli-en`).
2. **Modèle** : les colonnes manquantes (texte d'effet, sous-type de Dresseur, type d'Énergie si absent), migration Alembic **additive**, renseignées par l'import (`catalog/import_service.py`).
3. **Remplissage du catalogue de référence** de chimera (`pbm_catalogue_ref`, `docs/infra/JOBS-LOURDS.md`) : c'est **l'objet** de ce lot, tu y écris — par la voie normale de l'import, jamais par un `UPDATE` à la main. Le lien de chimera plafonne à ~250 Ko/s : mesure le volume avant, bride la concurrence, et si le téléchargement dépasse ce que le lien encaisse, passe par devAI (`docs/infra/JOBS-LOURDS.md`).
4. **Le chemin vers la PROD** : vérifie que la chaîne flotte (`infra/fleet/export_cards.sql`, `import_weekly.sql`…) transporte les nouvelles colonnes jusqu'à la base PROD à la prochaine importation ; corrige-la sinon. Ne touche pas la PROD.
5. **Preuve chiffrée** : nombre de Dresseurs et d'Énergies spéciales avec un texte d'effet, avant/après, par sous-type ; liste (ou nombre) de ceux qui restent vides et pourquoi (TCGdex ne l'a pas ?). Mets à jour `docs/catalogue/COMPLETUDE.md` et `docs/ARCHITECTURE.md` (section catalogue).
6. **Tests** : import d'un Objet, d'un Supporter, d'un Stade, d'un Outil et d'une Énergie spéciale avec leur texte ; une carte sans texte chez TCGdex reste vide **et se compte**, jamais un texte inventé.

**Clôture** : compte rendu `docs/roadmap/comptes-rendus/cat-textes-effets.md` commité et fusionné, CI verte sur `main`, puis dernier message `FAIT — cat-textes-effets` ou `BLOQUÉ — cat-textes-effets — <raison>`.



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
SHA=$(ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- git -C /home/upgreg/dev/wt-cat-textes-effets rev-parse HEAD' | tr -d '\r')
for i in $(seq 1 18); do   # 9 min au plus par commande (outil Bash, timeout 600000) : relance-la tant que la CI tourne
  R=$(curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
      "https://api.github.com/repos/keewoo/PokeBoyManager/actions/runs?head_sha=$SHA&per_page=20" \
      | python3 -c "import json,sys;w=[r for r in json.load(sys.stdin)['workflow_runs'] if r['name']=='CI'];print('aucune' if not w else ('terminee ' + ','.join(sorted({r['conclusion'] or '?' for r in w})) if all(r['status']=='completed' for r in w) else 'en cours'))")
  case "$R" in terminee*) echo "CI : $R"; break;; esac   # « terminee success » et rien d'autre = verte
  sleep 30
done
```

Tu termines **toujours** par la clôture (compte rendu commité **et fusionné dans `main`**) puis `FAIT — cat-textes-effets` ou `BLOQUÉ — cat-textes-effets — <raison>`.
