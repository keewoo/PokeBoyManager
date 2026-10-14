# CONTEXTE D'EXÉCUTION

Tu tournes sur **devAI**, en session autonome (`claude -p`) lancée par la file de lots : **personne ne répondra à une question**. Tu tranches, tu consignes, tu conclus. Correctif **hors plan**, ouvert par le pilote dans la nuit du 01 au 02/10/2026 sur ordre de JF (« fais au mieux pour que ça fonctionne demain matin en prod ») ; ne lance pas `suivi.py verifier/demarrer`, ne touche ni à `etat.json`, ni à `ROADMAP.html`, ni à `BACKLOG.md`, ni à `prompts/`.

- **Où travailler** : sur **chimera** (`ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- bash -s' < script` ; tout script commence par `export PATH=$HOME/.local/bin:$HOME/.local/node/bin:$PATH` ; le SSH coupe souvent : 5 tentatives espacées de 15 s). Dépôt `~/dev/pokeboy`, `git fetch github` d'abord (`origin` est un relais qui retarde). Worktree `~/dev/wt-fix-marqueur-stades`, branche `roadmap/fix-marqueur-stades` **créée depuis `b0df8ae`** — la release en PROD — **et pas depuis `main`** : `main` contient désormais d'autres lots (`j-cartes-pokemon`…) qui ne doivent pas partir en PROD avec ce correctif.
- **Catalogue** : `pbm_catalogue_ref` sur chimera (conteneur `pbm-shared-postgres-1`, port 55432) en lecture seule.
- **Git, CI** : commits ciblés (jamais `git add -A`, jamais `git stash`), `git push -u github roadmap/fix-marqueur-stades` ; la PR s'ouvre seule (son passage « pull_request » reste en `action_required` : pas un échec). Attends la CI **verte** du passage `push` (workflow « CI » seulement) depuis devAI — boucle du rappel final.

# Le défaut (constaté en PROD le 01/10 à 23h50, release `20261001-234045`)

**564 cartes** de la base PROD ont `cards.rule_marker` = `Stage1` / `Stage2` (sans espace) : l'import qui les a écrites ne reconnaissait comme stades ordinaires que `stage 1` / `stage 2` (`ORDINARY_STAGES`, `apps/api/src/pbm_api/catalog/import_service.py`). La classification `normalized_prize_marker` (`catalog/prize_marker.py`) les range donc en `inconnu` → la fiche « En jeu » affiche « Récompenses non déterminées » au lieu de 1, et le moteur les refuserait (R-15.22). Effet de bord du même défaut : `decks/stats.py` (`if c.rule_marker …`) les compte comme cartes à Rule Box. Le catalogue de chimera n'a pas ces valeurs : c'est pour ça que la preuve chiffrée du lot `fix-marqueur-recompenses` (0 inconnu) ne l'a pas vu.

# Mission

1. **Une seule normalisation des stades** : comparaison sans casse **et sans espaces ni tirets** (`Stage1` = `stage 1` = `Stage-1` ; `Basic`/`Base` ; `Niveau 1`/`Niveau 2`), partagée par l'import et par `normalized_prize_marker`. Un stade ordinaire n'est **jamais** un marqueur de règle.
2. **Migration Alembic de correction des données**, additive et rejouable, qui s'appliquera à la livraison : `rule_marker` remis à `NULL` quand sa valeur est un stade ordinaire, puis `prize_marker` recalculé (par la même fonction pure) pour les lignes concernées. Elle ne touche à rien d'autre.
3. **Tests** qui échouent sans le correctif : `Stage1`, `Stage2`, `Stage 1`, `stage-2`, `Basic`, `Niveau 1` → `ordinaire` ; une vraie Rule Box inconnue reste `inconnu` ; la migration corrige une ligne `Stage1` et laisse une ligne `VMAX` intacte.
4. **Preuve** : reproduis le cas PROD sur une base de test (lignes `Stage1`/`Stage2`), montre avant/après. Compte rendu `docs/roadmap/comptes-rendus/fix-marqueur-stades.md`.

# Fusion, puis livraison — dans cet ordre, et seulement si tout est vert

5. **Fusion dans `main`** après CI verte de la branche, sur chimera, sous le verrou : `flock ~/dev/pokeboy.git/pbm-merge.lock` puis `git fetch github && git checkout --detach github/main && git merge --no-ff roadmap/fix-marqueur-stades -m "Fusion : fix-marqueur-stades — un stade ordinaire n'est jamais un marqueur de règle" && git push github HEAD:main`. Conflit non trivial avec ce qui est arrivé sur `main` → résous-le, ré-attends la CI. Attends ensuite la CI sur `main`.
6. **Armer la livraison du correctif** (c'est le **commit de tête de la branche**, basé sur `b0df8ae`, qui part en PROD — **pas** `main`) :
   ```bash
   SHA=<SHA complet de la tête de roadmap/fix-marqueur-stades, CI verte>
   cd ~/dev/pbm && A=archive-deploy-20261001 && mkdir -p $A \
     && mv pbm-deploy-prompt.txt deploy.flag deploy.done deploy.launched $A/ 2>/dev/null; mv ~/dev/logs/pbm-deploy.log $A/ 2>/dev/null
   sed "s/__SHA__/$SHA/g" pbm-deploy-prompt-stades.txt > pbm-deploy-prompt.txt && touch deploy.flag \
     && launchctl kickstart gui/$(id -u)/ai.upgreg.pbm-deploy
   ```
   Vérifie qu'un `claude -p` de livraison a démarré (`~/dev/logs/pbm-deploy.log` porte « déploiement lancé »). La livraison elle-même n'est **pas** ton travail : tu t'arrêtes là.
   **Si la CI n'est pas verte, ou si quoi que ce soit cloche, tu n'armes RIEN** : la PROD actuelle tourne, elle affiche seulement « non déterminé » pour 564 cartes. Mieux vaut cela qu'une livraison douteuse.

**Clôture** : compte rendu commité et fusionné, livraison armée (ou non, avec la raison), puis dernier message `FAIT — fix-marqueur-stades` ou `BLOQUÉ — fix-marqueur-stades — <raison>`.



---

## ⛔ RAPPEL FINAL — lis ceci avant d'écrire ton dernier message

Tu es une session `claude -p`. **Il n'existe aucune notification** : rien ne te réveillera. Écrire « j'attends », « standing by », « je reprends à la fin de la tâche de fond » ou « le watcher me préviendra » **termine la session** et fait échouer le lot. Deux lots sont morts ainsi le 21/09.

Une attente se code **dans une seule commande bloquante**, jamais entre deux messages :

```bash
# attendre la CI GitHub sur un commit (jeton dans ~/.kailo-tokens sur devAI).
# Seul le workflow « CI » compte : « PR automatique des lots » tourne sur le même push et finit
# avant elle — le prendre pour la CI, c'est conclure sur un workflow qui ne teste rien.
source ~/.kailo-tokens
# le SHA est celui que tu as poussé DEPUIS CHIMERA (pas le dossier courant de devAI) :
SHA=$(ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- git -C /home/upgreg/dev/wt-fix-marqueur-stades rev-parse HEAD' | tr -d '\r')
for i in $(seq 1 60); do
  R=$(curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
      "https://api.github.com/repos/keewoo/PokeBoyManager/actions/runs?head_sha=$SHA&per_page=20" \
      | python3 -c "import json,sys;w=[r for r in json.load(sys.stdin)['workflow_runs'] if r['name']=='CI'];print('aucune' if not w else ('terminee ' + ','.join(sorted({r['conclusion'] or '?' for r in w})) if all(r['status']=='completed' for r in w) else 'en cours'))")
  case "$R" in terminee*) echo "CI : $R"; break;; esac   # « terminee success » et rien d'autre = verte
  sleep 30
done
```

Tu termines **toujours** par la clôture (compte rendu commité **et fusionné dans `main`**) puis `FAIT — fix-marqueur-stades` ou `BLOQUÉ — fix-marqueur-stades — <raison>`.
