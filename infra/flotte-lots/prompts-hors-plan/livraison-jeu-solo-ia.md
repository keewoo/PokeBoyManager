# Lot `livraison-jeu-solo-ia` — Mettre en PROD l'entraînement contre le bot, l'adversaire IA et le coach

Tu tournes sur **devAI**, en session autonome (`claude -p`) lancée par la file de lots (file B). **Personne ne répondra à une question** : tu tranches, tu consignes, tu conclus. devAI est la seule machine habilitée à livrer ; chimera construit ; le Mac de JF ne livre jamais.

## L'ordre de JF (03/10/2026)
« Après, commence les lots de partenaire de jeu IA », puis DJ7 : « Bot d'abord, IA ensuite ». Les lots `j-simulation-bots`, `j-mode-solo`, `j-adversaire-ia`, `j-coach-ia` te précèdent dans la file B ; toi, tu les livres. Le jeu reste **privé** (D11) : accès réservé à JF et Aymeric. **Une PROD debout sur la version actuelle vaut mieux qu'une PROD cassée** : au moindre doute, tu ne livres pas et tu l'écris.

## 0. Attendre que les quatre lots soient dans `main`
`j-simulation-bots`, `j-mode-solo`, `j-adversaire-ia`, `j-coach-ia` doivent être **`integre`** dans `docs/roadmap/etat.json` de `origin/main`. Sinon attends au premier plan (commandes de 9 minutes, timeout 600000, relancées), **1 h au plus**, puis `BLOQUÉ — livraison-jeu-solo-ia — lots manquants : <liste>`. Regarde aussi où en est la livraison des coups (`livraison-jeu-coups`, file A, section correspondante de `docs/LIVRAISON.md`) : si elle a été bloquée, lis pourquoi — ta livraison embarque le même code, ne refais pas son erreur. Puis **fige le commit** : `origin/main` à cet instant, CI « CI » verte (passage `push`). Tu livres **ce** commit et rien d'autre.

## 1. Lire ce que les lots ont laissé pour la livraison
Lis les comptes rendus `docs/roadmap/comptes-rendus/j-{simulation-bots,mode-solo,adversaire-ia,coach-ia}.md`, celui de `j-coups-joueur` et la section « Livraison du jeu — 03/10/2026 » de `docs/LIVRAISON.md` (la livraison précédente : elle a dû patcher `pbm-build-lol.sh` et `/tmp/prep-lol.sh` pour le paquet `apps/game` — vérifie que ces correctifs sont toujours en place), et `git diff --stat <release PROD actuelle>..<commit>` : **nouvelles variables d'environnement, migrations, nouveaux processus (worker, temps réel), routes hors `/api`, besoins Caddy** (WebSocket, SSE). Fais-en la liste dans ton rapport **avant** de toucher au serveur. Lis `docs/LIVRAISON.md` en entier (les livraisons du 23/09, du 01/10 et du 02/10 y sont décrites, avec leurs pièges) et `docs/infra/DOMAINE-POKEBOY-LOL.md` pour Caddy.

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
- **Une partie d'entraînement contre le bot**, jouée jusqu'au bout par l'API et le WebSocket avec un compte de test jetable ayant l'accès et un deck jouable : lancement depuis l'entrée « S'entraîner », coups réels, le bot répond, la partie se termine, elle est marquée « entraînement » (hors classement), et rien de caché ne fuit vers le client.
- **L'adversaire IA** : si `~/.pokeboy-secrets/platform-anthropic-key` existe sur devAI, dépose-la dans le coffre du compte de test jetable (par la route du coffre, jamais en clair dans un journal), joue **quelques coups** contre « mon IA » (plafonne-toi à une dizaine d'appels), vérifie que chaque coup est légal et expliqué ; sinon, prouve le chemin « sans clé » (l'option explique comment ajouter une clé et le bot joue). **N'utilise jamais la clé d'Aymeric.**
- **Le coach** : un conseil demandé pendant la partie d'entraînement propose un coup légal (même règle de clé que ci-dessus), et il est **indisponible** dans une partie entre deux joueurs.
- Puis **suppression du compte de test, de son coffre et de ses parties**, prouvée.
- Voisins inchangés du début à la fin ; RAM et charge après.
- Si une preuve tombe après une bascule réussie : retour sur la release précédente (`ln -sfn` + restart des unités, comme `deploy-switch.sh`), santé revérifiée. Les migrations restent (additives).

## 5. Trace et rapport
- Section **« Livraison de l'entraînement et de l'IA — <date> »** dans `docs/LIVRAISON.md` (ce qui a réellement été exécuté, release, commit, variables ajoutées — noms seulement —, Caddy touché ou non, preuves, écarts), commitée et poussée sur `main` depuis un worktree transitoire (`/Volumes/Data` est refusé par macOS aux sessions launchd : `~/dev/wt-livraison-solo-ia`, supprimé après le push ; jamais `~/dev/pokeboy`).
- Rapport `~/dev/logs/pbm-livraison-jeu-solo-ia-rapport.md`, sans aucun secret, qui se termine par **« Pour tester »** : l'URL du salon, les comptes ouverts, la commande pour ouvrir l'accès à un autre compte, comment lancer une partie d'entraînement, choisir « le bot » ou « mon IA », demander un conseil, ce que ça coûte sur la clé IA, et ce qui ne marche pas encore (pas de Dresseurs, pas de talents).
- **Dernier message** : `FAIT — livraison-jeu-solo-ia` ou `BLOQUÉ — livraison-jeu-solo-ia — <raison>`.

## ⛔ Tu es une session `claude -p` : il n'existe aucune notification
Écrire « j'attends », « je reprends à la fin du build » ou « le watcher me préviendra » **termine la session** — c'est arrivé le 01/10 à 22:54. Toute attente se code **au premier plan**, en commandes de 9 minutes au plus, relancées tant que nécessaire. Tu termines **toujours** par le rapport puis `FAIT` ou `BLOQUÉ`.
