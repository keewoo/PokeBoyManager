# Lot `pbm-deploy` — Livraison du 02/10/2026 : un stade ordinaire n'est jamais un marqueur de règle

Tu tournes sur **devAI**, en session autonome (`claude -p`), lancée par `~/dev/pbm/deploy-runner.sh`, armée par le lot `fix-marqueur-stades` après sa CI verte. **Personne ne répondra à une question** : tu tranches, tu consignes, tu conclus. devAI est la seule machine habilitée à livrer ; chimera construit ; le Mac de JF ne livre jamais.

## L'ordre de JF (01/10/2026, ~23h40)
« Je te laisse décider. Fais au mieux pour que ça fonctionne demain matin en prod sur le site. » — JF dort : **une PROD debout sur l'ancienne version vaut mieux qu'une PROD cassée**. Au moindre doute, tu restes sur la release actuelle et tu l'écris.

## Ce que tu livres — et rien d'autre
**Commit figé : `124f0cd8c5bf6a0c4cc90eb2a9c34b8488c429a2`** — tête de la branche `roadmap/fix-marqueur-stades`, **basée sur `b0df8ae`** (la release en PROD). Tu ne livres **pas** `main` : il contient d'autres lots (`j-cartes-pokemon`…) qui ne partent pas cette fois. PROD actuelle : release `20261001-234045`, commit `b0df8ae`.

Ce qui change pour ce qui tourne, entre `b0df8ae` et `124f0cd8c5bf6a0c4cc90eb2a9c34b8488c429a2` : la normalisation des stades (`Stage1`/`Stage2` sans espace reconnus comme stades **ordinaires**) dans l'import et dans `normalized_prize_marker`, et **une migration de correction des données** (`rule_marker` remis à `NULL` pour les stades ordinaires, `prize_marker` recalculé). Vérifie par `git diff --stat b0df8ae 124f0cd8c5bf6a0c4cc90eb2a9c34b8488c429a2` que rien d'autre ne part ; si autre chose part, arrêt.

## Règles absolues
- **Aucun secret affiché** (ni `.env`, ni mot de passe, ni clé) : sortie, journal, rapport, dépôt.
- **kailo.life et ACX ne bougent pas** : codes HTTP de `https://kailo.life https://www.kailo.life https://acx-connect.com https://www.acx-connect.com https://uat.kailo.life` relevés AVANT, après chaque étape serveur et à la FIN — attendu `200 200 308 200 307`. Une valeur qui change → retour arrière immédiat de ta dernière action, puis arrêt.
- **On ne construit pas sur la machine qui sert** : build sur chimera, transit par devAI, le serveur ne fait que `uv sync --frozen`, migration, lien, redémarrage. Ne redémarre **ni Caddy ni PostgreSQL**. Aucune écriture UpCloud.
- Le SSH de chimera se fait couper (`kex_exchange_identification: Connection reset`) : boucle de 5 tentatives espacées de 15 s, ce n'est pas une panne. Les scripts envoyés à chimera commencent par `export PATH=$HOME/.local/bin:$PATH`.

## Déroulé — c'est celui du 23/09, à lire d'abord dans `docs/LIVRAISON.md` (§ « Livraison du 23/09/2026 » et ses deux pièges)
0. **Portes** : la CI GitHub (workflow « CI », passage `push`) est **verte** sur `124f0cd8c5bf6a0c4cc90eb2a9c34b8488c429a2` (jeton `GITHUB_TOKEN` de `~/.kailo-tokens`) — sinon arrêt. Codes des voisins relevés. `free -m` et charge du serveur relevés.
1. **Build sur chimera** : le worktree de build `~/dev/wt-pbm-deploy` appartient au **dépôt relais** `~/dev/pokeboy.git` : `git fetch github && git checkout --detach 124f0cd8c5bf6a0c4cc90eb2a9c34b8488c429a2`, puis **vérifie le HEAD** (c'est le piège n°1 : rien n'échoue si on construit l'ancienne version). Lis `~/dev/pbm-build-lol.sh` avant de le lancer : il ne fait pas son propre checkout (constaté le 01/10) : c'est le HEAD vérifié qui est construit. Artefacts `~/dev/pbm-artefacts/{web,api}-<TS>.tgz` (`TS=$(date +%Y%m%d-%H%M%S)`). Contrôle dans l'artefact web : des `.woff2` sous `.next/static/media/`, et **aucune** occurrence de `fonts.googleapis.com` ni `fonts.gstatic.com`.
2. **Transfert** chimera → devAI → `kailo-srv:/tmp/pbm/`, empreintes **SHA-256 comparées aux trois étapes**.
3. **Point de restauration frais** AVANT toute écriture : `ssh kailo-srv 'sudo -n -u pokeboy bash /srv/pokeboy/prod/backups/backup.sh'` — vérifie qu'il a produit un fichier daté de maintenant.
4. **Préparation** (n'engage rien, l'ancienne release sert encore ; c'est ici que passe la migration) : `ssh kailo-srv 'TS=<TS> COMMIT=124f0cd8c5bf6a0c4cc90eb2a9c34b8488c429a2 LOT=livraison-20261002 bash /tmp/prep-lol.sh'` → attendu `PREPARATION_OK`, et la tête Alembic est la **nouvelle** migration de correction après migration.
5. **Bascule** avec retour arrière automatique : `ssh kailo-srv 'TS=<TS> bash /tmp/deploy-switch.sh'` → attendu `BASCULE_OK`. `BASCULE_ECHOUEE` → la PROD est revenue seule sur `20261001-234045` : vérifie-le, consigne, arrêt.

## Preuve — on ne conclut jamais « déployé » sur une ligne de journal
- `readlink /srv/pokeboy/prod/app` → la nouvelle release ; `RELEASE_INFO` porte `commit=124f0cd8c5bf6a0c4cc90eb2a9c34b8488c429a2` ; les 3 unités `active` ; `https://pokeboy.lol/api/health` → 200 ; `https://pokeboy.lol/` → 200.
- **Le correctif en PROD** (lecture seule) : dans `pokeboy_prod`, **0** carte `prize_marker = 'inconnu'` (564 avant), **0** `rule_marker` égal à un stade ordinaire, et les autres comptes par marqueur **inchangés** par rapport à avant la migration (relève-les AVANT la préparation). Puis `prize_rule_of` du **code déployé** sur une de ces anciennes cartes `Stage1` → **1 récompense**, une Méga-Évolution ex → 3, une TAG TEAM → 3 (comme le 01/10 : sans appeler la route `in-game-study`, qui déclenche une génération IA facturée).
- **Les voisins** inchangés (`200 200 308 200 307`), `free -m` et charge après.
- **Retour arrière manuel** si une preuve tombe après une bascule réussie : relink `app/` sur `20261001-234045` + restart des 3 unités (comme dans `deploy-switch.sh`), santé revérifiée. La migration reste en place : elle corrige des données que l'ancienne version lit sans erreur.

## Trace dans le dépôt
Ajoute à `docs/LIVRAISON.md` une section **« Livraison du 02/10/2026 »** sur le modèle des précédentes (exécuté réellement, release, commit, preuves, écarts), dans un worktree **transitoire** (le 01/10, `/Volumes/Data` a été refusé à la session par macOS — TCC — : si c'est encore le cas, worktree sous `~/dev/`, supprimé aussitôt le push fait ; jamais dans `~/dev/pokeboy`, dont la file se sert). Commit `Livraison : correctif des stades en PROD (release <TS>, commit <SHA court>)`, push sur `main` (rebase sur `origin/main` si besoin — documentation seule).

## Rapport (obligatoire, quelle que soit l'issue)
`~/dev/logs/pbm-livraison-20261002-rapport.md`, sans aucun secret : commit livré, release, portes, empreintes, sortie de la préparation et de la bascule, preuves, voisins avant/après, RAM et charge, écarts, ce que JF doit regarder au réveil. **Dernier message** : `FAIT — pbm-deploy` ou `BLOQUÉ — pbm-deploy — <raison>`.

## ⛔ Tu es une session `claude -p` : il n'existe aucune notification
Écrire « j'attends », « je reprends à la fin du build » ou « le watcher me préviendra » **termine la session** — un lot est mort ainsi le 01/10 à 22:54. Toute attente se code **dans une seule commande bloquante** (boucle `until … ; do sleep 30; done`, ou la commande longue lancée au premier plan). Tu termines **toujours** par le rapport puis `FAIT — pbm-deploy` ou `BLOQUÉ — pbm-deploy — <raison>`.
