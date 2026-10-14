# Lot `livraison-jeu-j1` — Mettre en PROD la première version jouable du jeu, réservée à JF et Aymeric

Tu tournes sur **devAI**, en session autonome (`claude -p`) lancée par la file de lots (file B). **Personne ne répondra à une question** : tu tranches, tu consignes, tu conclus. devAI est la seule machine habilitée à livrer ; chimera construit ; le Mac de JF ne livre jamais.

## L'ordre de JF (02/10/2026, ~12h30)
« On en est où de pouvoir tester le jeu sur le site ? » puis « go » à la proposition : préparer la livraison pour qu'elle parte dès le dernier écran fusionné, **accès limité à JF et Aymeric**. Le jeu est **privé** (D11) et l'inscription est **libre** (D8) : un compte ordinaire ne doit **rien** voir du jeu. **Une PROD debout sur la version actuelle vaut mieux qu'un jeu ouvert à tous ou une PROD cassée** : au moindre doute, tu ne livres pas et tu l'écris.

## 0. Attendre que tout ce qu'il faut pour jouer soit dans `main`
Ces lots doivent être **`integre`** dans `docs/roadmap/etat.json` de `origin/main` : `j-partie-service`, `j-autorite-vues`, `j-file-attente`, `j-temps-reel`, `j-invitations`, `j-lancement-partie`, `j-salon-partie`, `j-cartes-energies`, `j-initialisation`, `j-plateau-layout`, `j-plateau-etat-visuel`, `j-plateau-interactions`, `j-plateau-journal`. L'autre file (A) peut être encore en train d'en finir un : **attends au premier plan** : boucle `git fetch` + lecture d'`etat.json` toutes les 2 min, dans des commandes de **9 minutes au plus** (timeout 600000 ; les tâches de fond sont désactivées dans cette session), relancées tant qu'il manque un lot — **3 h au plus** au total. Au-delà : `BLOQUÉ — livraison-jeu-j1 — lots manquants : <liste>`.

Puis **fige le commit** : `origin/main` à cet instant, CI GitHub verte (workflow « CI », passage `push` ; si un passage plus récent l'a annulé, prends le commit vert le plus récent qui contient tous ces lots). Tu livres **ce** commit et rien d'autre, même si `main` avance pendant la livraison.

## 1. Lire ce que les lots ont laissé pour la livraison
Lis les comptes rendus `docs/roadmap/comptes-rendus/j-*.md` des lots ci-dessus, et `git diff --stat <release PROD actuelle>..<commit>` : **nouvelles variables d'environnement, migrations, nouveaux processus (worker, temps réel), routes hors `/api`, besoins Caddy** (WebSocket, SSE). Fais-en la liste dans ton rapport **avant** de toucher au serveur. Lis `docs/LIVRAISON.md` en entier (les livraisons du 23/09, du 01/10 et du 02/10 y sont décrites, avec leurs pièges) et `docs/infra/DOMAINE-POKEBOY-LOL.md` pour Caddy.

## 2. Livrer — le déroulé éprouvé du 01/10 (`docs/LIVRAISON.md`)
Portes (CI verte, voisins `200 200 308 200 307`, charge et mémoire du serveur) → build sur chimera du commit figé dans `~/dev/wt-pbm-deploy` (dépôt relais ; **HEAD vérifié** ; `export PATH=$HOME/.local/bin:$HOME/.local/node/bin:$PATH` ; build détaché par `setsid` et sondé) → transfert avec SHA-256 aux trois étapes → `backup.sh` frais → `/tmp/prep-lol.sh` (migrations) → `/tmp/deploy-switch.sh` (retour arrière automatique). Ces deux scripts vivent dans `/tmp` de `kailo-srv` : s'ils ont disparu, reconstitue-les **depuis la description de `docs/LIVRAISON.md`** et dis-le.
- **Variables d'environnement nouvelles** : ajoute-les à `/srv/pokeboy/prod/config/.env` (sauvegarde du fichier avant ; aucune valeur affichée ; une valeur secrète se génère sans s'afficher).
- **Caddy** : seulement si le temps réel l'exige vraiment (le `reverse_proxy` de Caddy relaie déjà les WebSocket sous `/api`). Sinon tu n'y touches pas. Si oui : copie de sauvegarde de `/srv/pokeboy/caddy/pokeboy.caddy`, modification minimale, `caddy validate`, puis `systemctl reload caddy` (jamais `restart`), et les voisins revérifiés **immédiatement** — une valeur qui change → fichier restauré, reload, arrêt.
- **Nouveau processus** (ex. serveur temps réel séparé) : unité systemd PROD sur le modèle des trois existantes, ports locaux uniquement.
- Ne redémarre jamais PostgreSQL. Aucune écriture UpCloud. Aucun secret affiché.

## 3. Ouvrir le jeu à JF et Aymeric — et à personne d'autre
- Commande d'administration du lot `j-file-attente` (`set-game-access <email> on`, ou son nom réel) pour **`aymeric.fonteray@gmail.com`** et **`jfonteray@gmail.com`**. Un compte qui n'existe pas en PROD : tu ne le crées pas, tu le notes (« JF devra s'inscrire, puis : `<commande exacte>` »).
- **Preuve de fermeture** : un compte **sans** ce droit reçoit 404 sur les routes du jeu et ne voit aucune entrée « Jouer ». Fais-le avec un compte de test jetable, **supprimé ensuite** (et prouve la suppression).

## 4. Preuve que le jeu marche en PROD — on ne conclut pas sur une ligne de journal
- `RELEASE_INFO` porte le commit figé ; unités `active` ; `/api/health` 200 ; `/` 200 ; tête Alembic = celle du commit.
- **Une partie réelle**, jouée par l'API **et** le canal temps réel (en local sur le serveur ou via `https://pokeboy.lol`) entre **deux comptes de test jetables** ayant le droit d'accès et un deck jouable (Pokémon de base + Énergies de base ; si les lots ont outillé une graine de test, sers-t'en ; sinon dote-les par la voie la plus propre que tu trouves — jamais en modifiant les données d'un vrai compte) : création ou invitation, mise en place, quelques tours (attacher une énergie, attaquer), et l'état vu par chaque joueur **sans fuite** de la main adverse. Puis **suppression des deux comptes et de leurs parties**, prouvée.
- Voisins inchangés du début à la fin ; RAM et charge après.
- Si une preuve tombe après une bascule réussie : retour sur la release précédente (`ln -sfn` + restart des unités, comme `deploy-switch.sh`), santé revérifiée. Les migrations restent (additives).

## 5. Trace et rapport
- Section **« Livraison du jeu — <date> »** dans `docs/LIVRAISON.md` (ce qui a réellement été exécuté, release, commit, variables ajoutées — noms seulement —, Caddy touché ou non, preuves, écarts), commitée et poussée sur `main` depuis un worktree transitoire (`/Volumes/Data` est refusé par macOS aux sessions launchd : `~/dev/wt-livraison-jeu`, supprimé après le push ; jamais `~/dev/pokeboy`).
- Rapport `~/dev/logs/pbm-livraison-jeu-j1-rapport.md`, sans aucun secret, qui se termine par **« Pour tester »** : l'URL du salon, les comptes ouverts, la commande pour ouvrir l'accès à un autre compte, ce qui marche et ce qui ne marche pas encore (pas de Dresseurs, pas de talents, pas d'horloges si `j-timer` n'est pas livré).
- **Dernier message** : `FAIT — livraison-jeu-j1` ou `BLOQUÉ — livraison-jeu-j1 — <raison>`.

## ⛔ Tu es une session `claude -p` : il n'existe aucune notification
Écrire « j'attends », « je reprends à la fin du build » ou « le watcher me préviendra » **termine la session** — c'est arrivé le 01/10 à 22:54. Toute attente se code **au premier plan**, en commandes de 9 minutes au plus, relancées tant que nécessaire. Tu termines **toujours** par le rapport puis `FAIT` ou `BLOQUÉ`.
