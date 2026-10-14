# Files de lots et livraison automatique — la mécanique de devAI

> Copie versionnée (14/10/2026) de ce qui tourne sur **devAI** dans `~/dev/pbm/` et
> `~/Library/LaunchAgents/`. **La version en service est celle de devAI** : modifier ici, puis
> recopier là-bas (et inversement) — un écart entre les deux est une panne qui attend son heure.

## Ce que ça fait

Deux **files de lots** jouent des sessions autonomes `claude -p` l'une après l'autre, chacune dans
son worktree, avec PR, CI verte et fusion dans `main` faites par le lot lui-même ; un **runner de
livraison** joue un prompt de mise en PROD quand on le lui demande. Rien ne dépend du Mac de JF :
un écran verrouillé ou un Tailscale déconnecté n'arrêtent rien.

| Fichier | Rôle |
|---|---|
| `file-lots.sh` | Une file : `file-lots.sh a` (`~/dev/pbm/file.txt`) ou `file-lots.sh b` (`file-b.txt`). Lancé toutes les 5 min par launchd. |
| `launchd/ai.upgreg.pbm-file{,-b}.plist` | Les deux agents des files (`~/Library/LaunchAgents/`). |
| `deploy-runner.sh` + `launchd/ai.upgreg.pbm-deploy.plist` | Le runner de livraison : joue `~/dev/pbm/pbm-deploy-prompt.txt` quand `deploy.flag` existe et que `deploy.done` n'existe pas. |
| `entete-jeu.md` | En-tête d'un lot du jeu qui travaille **sur devAI** (couloir dont la machine est devAI dans `jeu.json`). |
| `entete-jeu-chimera.md` | En-tête d'un lot qui travaille **sur chimera**, piloté depuis devAI (qui garde le jeton GitHub pour attendre la CI). |
| `rappel-jeu.md`, `rappel-jeu-chimera.md` | Le rappel final ajouté à chaque prompt (pas de tâche de fond, boucle d'attente de la CI). |
| `prompts-hors-plan/` | Les prompts des lots hors plan et des livraisons d'octobre 2026 — modèles à réutiliser. |

## Comment un lot part

1. Une ligne dans la file : `jeu-<id>.txt` (lot du plan du jeu), `v7d-<id>.txt` (plan daté) ou
   `<nom>.txt` (lot hors plan, prompt déposé dans `~/dev/pbm/`).
2. Au passage suivant : `~/dev/pokeboy` (clone d'automatisation) s'aligne sur `origin/main` sous un
   verrou (`~/dev/pbm/.verrou-clone`) ; pour un lot du jeu, `suivi.py verifier` est rejoué — code 2,
   la file se **suspend** sur ce lot sans consommer de tentative, et repart quand l'amont est intégré.
3. Le prompt d'un lot du jeu est **assemblé au départ** : en-tête (devAI ou chimera selon le couloir)
   + `prompts/<id>.md` du `main` du jour + rappel.
4. `claude -p` tourne au premier plan avec `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` (une session -p
   qui met une commande en arrière-plan meurt en croyant être réveillée plus tard).
5. Fini = ligne `FAIT — …` dans le journal **ou** branche `roadmap/<id>` dans `origin/main`. La file
   marque alors `integre` (lots du plan), régénère la page, pousse, et met le graphe à jour.

Pannes connues, toutes gérées par le script : limite d'usage du compte Claude (tentative rendue,
pause 20 min), journal effacé (preuve par git), lot déjà fusionné (pas de relance), push refusé
(trois essais depuis `origin/main`).

## Règles

- **Disque** : sur devAI, tout ce qui est volumineux vit sur `/Volumes/Data/DevAI/pokeboy/`
  (`worktrees/`, `tmp/`, `ops/`) — règle de flotte du 06/10/2026 (`~/.claude/CLAUDE.md` des machines).
  `~/dev/logs` et `~/dev/pbm` sont petits et **ne se nettoient pas** : les files en dépendent.
- **Secrets** : jamais dans un prompt ni ici. Clé plateforme Anthropic : `~/.pokeboy-secrets/` sur
  devAI (`chmod 600`), transmise aux traitements par entrée standard.
- **Livraison** : une seule à la fois (`~/dev/pbm/.verrou-livraison`), point de restauration avant
  toute écriture, voisins (kailo.life, ACX) vérifiés avant et après, preuve par une partie réelle —
  `docs/LIVRAISON.md`.

## Commandes utiles (sur devAI)

```bash
cat ~/dev/pbm/file.txt ~/dev/pbm/file-b.txt          # ce qui attend
tail -f ~/dev/logs/pbm-file.log ~/dev/logs/pbm-file-b.log
mv ~/dev/pbm/file.txt ~/dev/pbm/file-suspendue.txt   # suspendre la file A (et l'inverse pour reprendre)
launchctl kickstart gui/$(id -u)/ai.upgreg.pbm-file  # faire passer la file A tout de suite
```
