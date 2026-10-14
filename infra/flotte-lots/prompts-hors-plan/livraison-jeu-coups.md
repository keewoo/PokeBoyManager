# Lot `livraison-jeu-coups` — Mettre en PROD les coups du joueur : la partie se joue vraiment

Tu tournes sur **devAI**, en session autonome (`claude -p`) lancée par la file de lots (file B). **Personne ne répondra à une question** : tu tranches, tu consignes, tu conclus. devAI est la seule machine habilitée à livrer ; chimera construit ; le Mac de JF ne livre jamais.

## L'ordre de JF (03/10/2026, ~9h10)
La livraison du 03/10 à 03:52 (`livraison-jeu-j1`, release `20261003-033245`) a mis en PROD salon, invitations, plateau et temps réel, **sans aucun coup jouable** au-delà de l'abandon. JF : « Oui, lot + livraison » — le lot `j-coups-joueur` branche les coups ; toi, tu le livres dès qu'il est intégré. Le jeu reste **privé** (D11) : accès réservé à JF et Aymeric. **Une PROD debout sur la version actuelle vaut mieux qu'une PROD cassée** : au moindre doute, tu ne livres pas et tu l'écris.

## 0. Attendre que `j-coups-joueur` ET son correctif soient dans `main`
Deux tentatives de cette livraison ont été **bloquées** le 03/10 (13:07 et 13:22) : sept événements sans projecteur faisaient répondre 500 au premier vrai coup (`docs/LIVRAISON.md`, « Tentative de livraison des coups du joueur — BLOQUÉE ») — la PROD est revenue sur J1, sans dégât. Le correctif `fix-projection-evenements` te précède dans la file : sa branche `roadmap/fix-projection-evenements` doit être **ancêtre de `origin/main`** (`git merge-base --is-ancestor`), en plus de `j-coups-joueur` `integre`. Sinon attends au premier plan (commandes de 9 minutes, timeout 600000, relancées), **1 h au plus**, puis `BLOQUÉ — livraison-jeu-coups — correctif absent de main`. Puis **fige le commit** : `origin/main` à cet instant, CI « CI » verte (passage `push`). Tu livres **ce** commit et rien d'autre. Le script de preuve de la tentative précédente est décrit dans `docs/LIVRAISON.md` : réutilise-le.

## 1. Lire ce que les lots ont laissé pour la livraison
Lis le compte rendu `docs/roadmap/comptes-rendus/j-coups-joueur.md` et la section « Livraison du jeu — 03/10/2026 » de `docs/LIVRAISON.md` (la livraison précédente : elle a dû patcher `pbm-build-lol.sh` et `/tmp/prep-lol.sh` pour le paquet `apps/game` — vérifie que ces correctifs sont toujours en place), et `git diff --stat <release PROD actuelle>..<commit>` : **nouvelles variables d'environnement, migrations, nouveaux processus (worker, temps réel), routes hors `/api`, besoins Caddy** (WebSocket, SSE). Fais-en la liste dans ton rapport **avant** de toucher au serveur. Lis `docs/LIVRAISON.md` en entier (les livraisons du 23/09, du 01/10 et du 02/10 y sont décrites, avec leurs pièges) et `docs/infra/DOMAINE-POKEBOY-LOL.md` pour Caddy.

## 2. Livrer — le déroulé éprouvé du 01/10 (`docs/LIVRAISON.md`)
Portes (CI verte, voisins `200 200 308 200 307`, charge et mémoire du serveur) → build sur chimera du commit figé dans `~/dev/wt-pbm-deploy` (dépôt relais ; **HEAD vérifié** ; `export PATH=$HOME/.local/bin:$HOME/.local/node/bin:$PATH` ; build détaché par `setsid` et sondé) → transfert avec SHA-256 aux trois étapes → `backup.sh` frais → `/tmp/prep-lol.sh` (migrations) → `/tmp/deploy-switch.sh` (retour arrière automatique). Ces deux scripts vivent dans `/tmp` de `kailo-srv` : s'ils ont disparu, reconstitue-les **depuis la description de `docs/LIVRAISON.md`** et dis-le.
- **Variables d'environnement nouvelles** : ajoute-les à `/srv/pokeboy/prod/config/.env` (sauvegarde du fichier avant ; aucune valeur affichée ; une valeur secrète se génère sans s'afficher).
- **Caddy** : seulement si le temps réel l'exige vraiment (le `reverse_proxy` de Caddy relaie déjà les WebSocket sous `/api`). Sinon tu n'y touches pas. Si oui : copie de sauvegarde de `/srv/pokeboy/caddy/pokeboy.caddy`, modification minimale, `caddy validate`, puis `systemctl reload caddy` (jamais `restart`), et les voisins revérifiés **immédiatement** — une valeur qui change → fichier restauré, reload, arrêt.
- **Nouveau processus** (ex. serveur temps réel séparé) : unité systemd PROD sur le modèle des trois existantes, ports locaux uniquement.
- Ne redémarre jamais PostgreSQL. Aucune écriture UpCloud. Aucun secret affiché.

## 3. Ouvrir le jeu à JF et Aymeric — et à personne d'autre
- `python -m pbm_api.admin set-game-access <email> on` (commande exacte dans le rapport du 03/10) : **`aymeric.fonteray@gmail.com`** reste ouvert (vérifie-le) ; **`jfonteray@gmail.com`** : s'il s'est inscrit depuis, ouvre-lui l'accès ; sinon, tu ne crées rien et tu le notes.
- **Preuve de fermeture** : un compte **sans** ce droit reçoit 404 sur les routes du jeu et ne voit aucune entrée « Jouer ». Fais-le avec un compte de test jetable, **supprimé ensuite** (et prouve la suppression).

## 4. Preuve que le jeu marche en PROD — on ne conclut pas sur une ligne de journal
- `RELEASE_INFO` porte le commit figé ; unités `active` ; `/api/health` 200 ; `/` 200 ; tête Alembic = celle du commit.
- **Une partie complète, jouée pour de vrai** par l'API **et** le WebSocket (en local sur le serveur ou via `https://pokeboy.lol`) entre **deux comptes de test jetables** ayant le droit d'accès et un deck jouable (Pokémon de base + Énergies de base ; le compte rendu de `j-coups-joueur` dit comment doter un compte de test) : mise en place interactive, puis des tours **réels** — poser, attacher une énergie, attaquer — jusqu'à la **victoire par les récompenses** ou au moins **un K.O. et une récompense prise**, l'état vu par chaque joueur **sans fuite** de la main adverse, et la partie qui se **rejoue depuis son journal**. Puis **suppression des deux comptes et de leurs parties**, prouvée.
- Voisins inchangés du début à la fin ; RAM et charge après.
- Si une preuve tombe après une bascule réussie : retour sur la release précédente (`ln -sfn` + restart des unités, comme `deploy-switch.sh`), santé revérifiée. Les migrations restent (additives).

## 5. Trace et rapport
- Section **« Livraison des coups du joueur — <date> »** dans `docs/LIVRAISON.md` (ce qui a réellement été exécuté, release, commit, variables ajoutées — noms seulement —, Caddy touché ou non, preuves, écarts), commitée et poussée sur `main` depuis un worktree transitoire (`/Volumes/Data` est refusé par macOS aux sessions launchd : `~/dev/wt-livraison-coups`, supprimé après le push ; jamais `~/dev/pokeboy`).
- Rapport `~/dev/logs/pbm-livraison-jeu-coups-rapport.md`, sans aucun secret, qui se termine par **« Pour tester »** : l'URL du salon, les comptes ouverts, la commande pour ouvrir l'accès à un autre compte, ce qui marche — **une partie complète** — et ce qui ne marche pas encore (pas de Dresseurs, pas de talents).
- **Dernier message** : `FAIT — livraison-jeu-coups` ou `BLOQUÉ — livraison-jeu-coups — <raison>`.

## ⛔ Tu es une session `claude -p` : il n'existe aucune notification
Écrire « j'attends », « je reprends à la fin du build » ou « le watcher me préviendra » **termine la session** — c'est arrivé le 01/10 à 22:54. Toute attente se code **au premier plan**, en commandes de 9 minutes au plus, relancées tant que nécessaire. Tu termines **toujours** par le rapport puis `FAIT` ou `BLOQUÉ`.
