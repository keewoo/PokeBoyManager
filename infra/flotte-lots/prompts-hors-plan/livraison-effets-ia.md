# Lot `livraison-effets-ia` — Mettre en PROD les scripts d'effets écrits par l'IA et le tableau de couverture

Tu tournes sur **devAI**, en session autonome (`claude -p`) lancée par la file de lots (file B). **Personne ne répondra à une question** : tu tranches, tu consignes, tu conclus. devAI est la seule machine habilitée à livrer ; chimera construit ; le Mac de JF ne livre jamais.

## L'ordre de JF (04/10/2026)
« Go pour le gros chantier effet » : rendre jouables les vraies cartes (attaques à effet, Dresseurs, talents, Outils, Stades), aujourd'hui bloquées — le catalogue de PROD ne comptait que **30 cartes jouables** le 03/10. Le jeu reste **privé** (D11 : JF, Aymeric). **Une PROD debout sur la version actuelle vaut mieux qu'une PROD cassée.**

## 0. Attendre les lots
Doivent être **`integre`** : `j-effets-couverture-outil`, `j-effets-assistance-ia`, `j-cartes-regles-speciales`. Sinon attends au premier plan, **3 h au plus**, puis `BLOQUÉ — livraison-effets-ia — manquent : <liste>`. Lis le rapport de `j-effets-assistance-ia` : familles admises, cartes couvertes, dépense réelle sur les 50 € (DJ8). Si ses scripts vivent en base plutôt que dans le code, livre-les par la voie que son compte rendu décrit. Puis **fige** le commit.

## Verrou de livraison — une seule livraison à la fois
Deux files peuvent livrer le même jour. **Avant toute action sur la PROD**, prends le verrou : `mkdir ~/dev/pbm/.verrou-livraison && echo <ton id de lot> > ~/dev/pbm/.verrou-livraison/qui`. S'il existe déjà : une autre livraison tourne — attends au premier plan (commandes de 9 minutes, timeout 600000, relancées), **2 h au plus**, puis `BLOQUÉ — <id> — autre livraison en cours`. Un verrou de plus de 4 h est orphelin : tu le supprimes en le disant. **Tu le libères à la fin, quelle que soit l'issue** (`rm -rf ~/dev/pbm/.verrou-livraison`).

## Le catalogue de PROD doit porter les données des effets
Les textes d'effet des Dresseurs et Énergies (`cat-textes-effets`, 02/10) et les stades (`cat-stades`) ont été remplis dans le catalogue de **référence** de chimera ; la PROD ne les reçoit que par la chaîne flotte (`docs/infra/JOBS-LOURDS.md`, `infra/fleet/*.sql`). Avant la bascule, **compte** en PROD (lecture seule) les Dresseurs avec texte d'effet et les Pokémon avec stade ; s'ils manquent, lance l'**import flotte documenté** (export depuis chimera, import en PROD) — jamais un import complet sur le serveur — et recompte après. Un écart restant se dit dans le rapport.

## 1. Lire ce que les lots ont laissé pour la livraison
Lis les comptes rendus des lots que tu livres (`docs/roadmap/comptes-rendus/`) et la section « Livraison du jeu — 03/10/2026 » de `docs/LIVRAISON.md` (la livraison précédente : elle a dû patcher `pbm-build-lol.sh` et `/tmp/prep-lol.sh` pour le paquet `apps/game` — vérifie que ces correctifs sont toujours en place), et `git diff --stat <release PROD actuelle>..<commit>` : **nouvelles variables d'environnement, migrations, nouveaux processus (worker, temps réel), routes hors `/api`, besoins Caddy** (WebSocket, SSE). Fais-en la liste dans ton rapport **avant** de toucher au serveur. Lis `docs/LIVRAISON.md` en entier (les livraisons du 23/09, du 01/10 et du 02/10 y sont décrites, avec leurs pièges) et `docs/infra/DOMAINE-POKEBOY-LOL.md` pour Caddy.

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
- **Le chiffre qui compte** : cartes jouables en PROD avant/après cette livraison, et ce que le tableau de couverture affiche pour les decks de JF et d'Aymeric (lecture seule).
- **Une partie réelle** entre deux comptes de test jetables avec des cartes dont le script vient de l'IA (au moins trois), sans fuite ; puis **suppression** prouvée.
- Voisins inchangés du début à la fin ; RAM et charge après.
- Si une preuve tombe après une bascule réussie : retour sur la release précédente (`ln -sfn` + restart des unités, comme `deploy-switch.sh`), santé revérifiée. Les migrations restent (additives).

## 5. Trace et rapport
- Section **« Livraison des scripts d'effets IA — <date> »** dans `docs/LIVRAISON.md` (ce qui a réellement été exécuté, release, commit, variables ajoutées — noms seulement —, Caddy touché ou non, preuves, écarts), commitée et poussée sur `main` depuis un worktree transitoire (`/Volumes/Data` est refusé par macOS aux sessions launchd : `~/dev/wt-livraison-effets-ia`, supprimé après le push ; jamais `~/dev/pokeboy`).
- Rapport `~/dev/logs/pbm-livraison-effets-ia-rapport.md`, sans aucun secret, qui se termine par **« Pour tester »** : l'URL du salon, les comptes ouverts, la commande pour ouvrir l'accès à un autre compte, comment lancer une partie d'entraînement, choisir « le bot » ou « mon IA », demander un conseil, ce que ça coûte sur la clé IA, et ce qui ne marche pas encore (pas de Dresseurs, pas de talents).
- **Dernier message** : `FAIT — livraison-effets-ia` ou `BLOQUÉ — livraison-effets-ia — <raison>`.

## ⛔ Tu es une session `claude -p` : il n'existe aucune notification
Écrire « j'attends », « je reprends à la fin du build » ou « le watcher me préviendra » **termine la session** — c'est arrivé le 01/10 à 22:54. Toute attente se code **au premier plan**, en commandes de 9 minutes au plus, relancées tant que nécessaire. Tu termines **toujours** par le rapport puis `FAIT` ou `BLOQUÉ`.
