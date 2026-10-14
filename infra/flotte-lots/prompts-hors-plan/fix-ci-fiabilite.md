# CONTEXTE D'EXÉCUTION

Tu tournes sur **devAI**, en session autonome (`claude -p`) lancée par la file de lots : **personne ne répondra à une question**. Tu tranches, tu consignes, tu conclus. Ce lot est un **correctif hors plan**, ouvert par le pilote le 01/10/2026 au soir, après trois échecs de CI sur `main` en une heure ; il n'a pas d'entrée dans `roadmap.json` — ne lance pas `suivi.py verifier/demarrer`, ne touche ni à `etat.json`, ni à `ROADMAP.html`, ni à `BACKLOG.md`, ni à `prompts/`.

- **Où travailler** : sur **chimera**, jamais dans `~/dev/pokeboy` de devAI. `ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- bash -s' < script` (dépose un script : le quoting PowerShell casse les one-liners). Dépôt `~/dev/pokeboy` de la WSL, worktree `~/dev/wt-fix-ci-fiabilite`, branche `roadmap/fix-ci-fiabilite` depuis `github/main` (`git fetch github` d'abord : `origin` est un relais local qui retarde). Le SSH de chimera coupe souvent : réessaie. **Tout script envoyé à chimera commence par `export PATH=$HOME/.local/bin:$PATH`** : `uv` et `claude` y vivent, et `bash -s` n'est pas un shell de connexion — sans cette ligne, `uv` paraît absent alors qu'il est là (c'est le faux « outil absent » du 22/09, `docs/LIVRAISON.md`).
- **Catalogue** : base de référence `pbm_catalogue_ref` (conteneur `pbm-shared-postgres-1`, port 55432 — `docs/infra/JOBS-LOURDS.md`), **lecture seule**. Tes tests ont leur propre base.
- **Git, CI, fusion** : commits ciblés (jamais `git add -A`, jamais `git stash`), `git push -u github roadmap/fix-ci-fiabilite` ; la PR s'ouvre seule (`pr-auto`, son passage « pull_request » reste en `action_required` : ce n'est pas un échec). Attends la CI **verte** du passage « push » depuis devAI (boucle ci-dessous), puis fusionne sur chimera sous `flock ~/dev/pokeboy.git/pbm-merge.lock` (`git fetch github && git checkout --detach github/main && git merge --no-ff roadmap/fix-ci-fiabilite -m "Fusion : fix-ci-fiabilite — …" && git push github HEAD:main`), puis attends la CI sur `main`.
- **Aucun déploiement** : la PROD se livre à part, par devAI. Ta migration doit donc s'appliquer **sans intervention** à la prochaine livraison (non destructive, rejouable).

# Mission — une CI qui ne ment pas, dans un sens ou dans l'autre

**Le constat (01/10/2026, 21:34–21:53).** Sur un arbre **identique** à une branche verte (`f105cef`), la CI de `main` a échoué trois fois de suite, et le lot `fix-marqueur-recompenses` a poussé **trois commits vides** sur `main` pour la relancer (`0c544c5`, `f11cabf`, `5b3916b`). Deux causes :
- **Build web** (runs `36915337319`, `36917084943`, et déjà le 01/10 à 12:03) : `An error occurred in next/font — TypeError: Cannot read properties of null (reading '1')` dans `nextFontGoogleFontLoader`. `apps/web/src/app/layout.tsx` charge **Exo 2, JetBrains Mono, Press Start 2P et Roboto** depuis Google **au moment du build** : la moindre réponse incomplète de `fonts.googleapis.com` casse le build.
- **e2e** (run `36916045307`, job `110550141463`) : `asyncpg.exceptions.DeadlockDetectedError: deadlock detected` levé **par l'API** pendant le parcours d'authentification Playwright. Ce n'est peut-être pas qu'un défaut de CI : deux requêtes concurrentes qui s'interbloquent peuvent arriver en PROD.

1. **Polices embarquées.** Remplace `next/font/google` par `next/font/local` : fichiers `woff2` (sous-ensembles latin + latin-ext, mêmes graisses et styles qu'aujourd'hui, mêmes variables CSS) commités dans `apps/web`, avec leur **licence** (OFL pour Exo 2, JetBrains Mono, Press Start 2P ; Apache 2.0 pour Roboto). Télécharge-les **depuis devAI** (le lien de chimera plafonne à ~250 Ko/s) puis copie-les. Preuve : plus aucun `next/font/google` dans le dépôt, build vert, et une capture avant/après de l'accueil et d'une fiche carte montrant un rendu identique (jointe au compte rendu).
2. **L'interblocage.** Lis le journal complet du job e2e cité (API GitHub, jeton dans `~/.kailo-tokens` sur devAI) : quelle route, quelles requêtes, quelles tables. Trouve la cause (ordre des verrous, deux transactions qui touchent les mêmes lignes dans un ordre différent, mise à jour concurrente d'une session ou d'un compteur de tentatives…) et corrige-la **à la racine** (ordre des écritures, `SELECT … FOR UPDATE`, une seule transaction). Une relance automatique sur `DeadlockDetectedError` n'est acceptable que si la cause est démontrée inévitable, bornée, et **journalisée** — jamais muette. Ajoute un test qui reproduit la concurrence (requêtes simultanées) et échoue sans le correctif.
3. **Relancer sans polluer `main`.** Vérifie si le jeton de devAI peut relancer un passage (`POST /repos/keewoo/PokeBoyManager/actions/runs/{id}/rerun-failed-jobs`) ; si oui, documente-le dans `docs/CODE.md` comme **la** manière de relancer une CI instable, à la place d'un commit vide ; sinon, nomme la permission manquante (en-tête `x-accepted-github-permissions`) dans ton compte rendu et dans ton dernier message.
4. **Compte rendu** `docs/roadmap/comptes-rendus/fix-ci-fiabilite.md` : causes établies (avec extraits de journaux), corrections, preuves, et ce qui reste instable s'il en reste.

**Clôture** : compte rendu commité et fusionné dans `main`, CI verte sur `main` (sans commit vide), puis dernier message `FAIT — fix-ci-fiabilite` ou `BLOQUÉ — fix-ci-fiabilite — <raison>`.



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
SHA=$(ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- git -C /home/upgreg/dev/wt-fix-ci-fiabilite rev-parse HEAD' | tr -d '\r')
for i in $(seq 1 60); do
  R=$(curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
      "https://api.github.com/repos/keewoo/PokeBoyManager/actions/runs?head_sha=$SHA&per_page=20" \
      | python3 -c "import json,sys;w=[r for r in json.load(sys.stdin)['workflow_runs'] if r['name']=='CI'];print('aucune' if not w else ('terminee ' + ','.join(sorted({r['conclusion'] or '?' for r in w})) if all(r['status']=='completed' for r in w) else 'en cours'))")
  case "$R" in terminee*) echo "CI : $R"; break;; esac   # « terminee success » et rien d'autre = verte
  sleep 30
done
```

Tu termines **toujours** par la clôture (compte rendu commité **et fusionné dans `main`**) puis `FAIT — fix-ci-fiabilite` ou `BLOQUÉ — fix-ci-fiabilite — <raison>`.
