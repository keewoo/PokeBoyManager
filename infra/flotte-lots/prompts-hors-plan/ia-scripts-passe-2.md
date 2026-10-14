# CONTEXTE D'EXÉCUTION

Tu tournes sur **devAI**, en session autonome (`claude -p`) lancée par la file de lots : **personne ne répondra à une question**. Tu tranches, tu consignes, tu conclus. Lot **hors plan**, suite de `ia-scripts-passe` (05/10/2026 : 0 script admissible sur 97, génération à corriger) — DJ8, JF ; ne lance pas `suivi.py verifier/demarrer`, ne touche ni à `etat.json`, ni à `ROADMAP.html`, ni à `BACKLOG.md`, ni à `prompts/`.

- **Où travailler** : sur **chimera** (`ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- bash -s' < script` ; tout script commence par `export PATH=$HOME/.local/bin:$HOME/.local/node/bin:$PATH` ; le SSH coupe souvent : 5 tentatives espacées de 15 s ; un traitement long se lance détaché avec `setsid` et se **sonde dans une seule commande bloquante**). Dépôt `~/dev/pokeboy`, `git fetch github` d'abord (`origin` est un relais qui retarde). Worktree `~/dev/wt-ia-scripts-passe-2`, branche `roadmap/ia-scripts-passe-2` depuis `github/main`.
- **Le dépôt est graphifié** : dans ton worktree, `graphify update .` puis `graphify query "…"`, `graphify explain "X"`, `graphify affected "X"` avant de lire dix fichiers (`docs/CODE.md` § « Chercher dans le dépôt »). Le graphe oriente, il ne prouve pas.
- **Code documenté** : tout ce que tu ajoutes ou modifies sort avec sa docstring / son `/** … */`, en français (`docs/CODE.md` § « Documenter le code »).
- **Git, CI, fusion** : commits ciblés (jamais `git add -A`, jamais `git stash`), `git push -u github roadmap/ia-scripts-passe-2` ; la PR s'ouvre seule (son passage « pull_request » reste en `action_required` : pas un échec). CI **verte** du passage `push` (workflow « CI » seulement), attendue depuis devAI (boucle du rappel final). Fusion sur chimera sous `flock ~/dev/pokeboy.git/pbm-merge.lock` : `git fetch github && git checkout --detach github/main && git merge --no-ff roadmap/ia-scripts-passe-2 -m "Fusion : ia-scripts-passe-2 — …" && git push github HEAD:main`, puis CI sur `main`. Le jeton de devAI ne peut pas relancer une CI (`actions: write` absent) : un échec d'infrastructure démontré se relance par un commit vide **sur ta branche**, jamais sur `main`.
- **Pas de déploiement de code** ; en revanche ce lot **importe des données** en PROD (étape 5), sous le verrou de livraison et avec un point de restauration — c'est la seule écriture PROD permise.

# Mission — corriger la génération, re-mesurer, puis seulement dépenser

**Le constat** (`docs/roadmap/comptes-rendus/ia-scripts-passe.md`) : sur 97 effets et deux modèles (haiku-4-5, sonnet-5), **0 script admissible** — 36 refus de **schéma** (le prompt `grammaire_dsl()` donne les noms des opérations mais pas leurs **arguments requis** : clés inventées, `piocher` sans `nombre`), 22 refus de **sémantique** (le cas de test écrit par l'IA ne colle pas à l'état exact du moteur), 38 effets réellement hors DSL. La porte (tests + contradicteur, `ck_card_scripts_scripte_gate`) a eu raison : **on n'y touche pas**. Dépensé : 1,87 € sur les 50 € de DJ8 (grand livre cumulé).

1. **Le prompt de génération** (`apps/api/src/pbm_api/jeu/scripts/assistance/`, lot `j-effets-assistance-ia`) : (a) `grammaire_dsl()` donne pour **chaque** primitive ses arguments requis et facultatifs, leurs types et un exemple, **dérivés des constantes du moteur** (`apps/game`), avec un **test anti-dérive** qui casse si le moteur ajoute ou change une primitive sans que la grammaire suive ; (b) des **exemples validés** joints au prompt même quand `card_scripts` est vide — les scripts écrits à la main de `apps/api/scripts/seed_effets.json` et les cas DSL des tests du moteur ; (c) le **format exact de l'état** des cas de test, avec un exemple complet qui passe.
2. **Re-mesure** sur **50 effets** (possédés d'abord, DJ2), plafond **3 €** pour cette mesure : taux d'admission, refus par cause, coût par effet. **Seuil pour continuer : ≥ 40 % d'admis parmi les effets que le DSL sait exprimer**, et un contradicteur qui refuse réellement quelque chose (s'il approuve tout, c'est lui qui est cassé). Sous le seuil : tu t'arrêtes, tu corriges encore si la cause est claire (une seule itération de plus, 3 € de plus au maximum), sinon `BLOQUÉ` avec le diagnostic.
3. **Passage** si le seuil est tenu : jusqu'au plafond **cumulé** de 50 € (grand livre), possédés d'abord puis les plus fréquents ; détaché (`setsid`) et sondé ; clé par entrée standard ou fichier `chmod 600` temporaire supprimé à la fin, preuve à l'appui.
4. **Rapport par famille** pour JF (admises / refusées par les tests / refusées par le contradicteur, exemples, coût) : `docs/roadmap/comptes-rendus/ia-scripts-passe-2.md` et `~/dev/logs/pbm-ia-scripts-2-rapport.md`.
5. **Import en PROD** par la chaîne flotte (`infra/fleet/export_card_scripts.sql`, `import_card_scripts.sql`), sous le **verrou de livraison** de devAI (`~/dev/pbm/.verrou-livraison`, attends s'il est pris par une autre livraison, libère-le à la fin), après un **point de restauration** frais : preuve en lecture seule — `card_scripts` par statut, cartes que la construction de deck accepte avant/après (tableau de couverture), et pour les collections de JF et d'Aymeric. Voisins `200 200 308 200 307` avant et après. Aucun redéploiement de code n'est nécessaire si le code de lecture des scripts est déjà en PROD ; sinon, tu le dis et tu n'importes pas (la livraison suivante le fera).
6. Les changements de code passent par la branche `roadmap/ia-scripts-passe-2`, PR, CI verte, fusion.

**Clôture** : compte rendu et rapport par famille commités et fusionnés, dépense cumulée écrite, import PROD prouvé (ou non fait, avec la raison), puis dernier message `FAIT — ia-scripts-passe-2` ou `BLOQUÉ — ia-scripts-passe-2 — <raison>`.

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
SHA=$(ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- git -C /home/upgreg/dev/wt-ia-scripts-passe-2 rev-parse HEAD' | tr -d '\r')
for i in $(seq 1 18); do   # 9 min au plus par commande (outil Bash, timeout 600000) : relance-la tant que la CI tourne
  R=$(curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
      "https://api.github.com/repos/keewoo/PokeBoyManager/actions/runs?head_sha=$SHA&per_page=20" \
      | python3 -c "import json,sys;w=[r for r in json.load(sys.stdin)['workflow_runs'] if r['name']=='CI'];print('aucune' if not w else ('terminee ' + ','.join(sorted({r['conclusion'] or '?' for r in w})) if all(r['status']=='completed' for r in w) else 'en cours'))")
  case "$R" in terminee*) echo "CI : $R"; break;; esac   # « terminee success » et rien d'autre = verte
  sleep 30
done
```

Tu termines **toujours** par la clôture (compte rendu commité **et fusionné dans `main`**) puis `FAIT — ia-scripts-passe-2` ou `BLOQUÉ — ia-scripts-passe-2 — <raison>`.
