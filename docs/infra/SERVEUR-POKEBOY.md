> Rapport de la session devAI du 19/09/2026 (lot `pbm-serveur`), versé tel quel. Correction du pilote : le serveur **est** dans le compte UpCloud « kailo » (uuid 004ba88c…, lu par l’API le 19/09) — la remarque « compte distinct » du §Capacité est erronée.

# Rapport — pbm-serveur : préparation de kailo-srv pour PokeBoyManager

Exécuté en session autonome sur devAI, 2026-09-19. Serveur cible : `kailo-srv` (5.22.213.226,
UpCloud « sites-and-crons », 2 vCPU / 3,8 Go RAM / 30 Go disque). **Aucun code applicatif
déployé** — préparation d'accueil uniquement (D2/D5 de JF).

## Contrainte absolue : kailo.life et ACX non affectés

| Mesure | Avant | Après |
|---|---|---|
| `https://kailo.life` | 200 | 200 |
| `https://www.kailo.life` | 200 | 200 |
| `https://acx-connect.com` | 308 | 308 |
| `https://www.acx-connect.com` | 200 | 200 |
| `https://uat.kailo.life` | 307 | 307 |
| `caddy` / `postgresql@18-main` / `kailo-uat` / `kailo-uat-web` | active | active |
| RAM (`free -m`, used) | 875 Mo | 990 Mo |
| RAM disponible (`available`) | 2986 Mo | 2871 Mo |
| Disque `/` | 9,7 Go / 19 Go libres | 11 Go / 19 Go libres |

Aucun redémarrage de Caddy ni de PostgreSQL. Aucune tentative ACME (le fichier Caddy de
PokeBoyManager n'est **pas importé**). La hausse RAM/disque est celle du nouvel outillage
`pokeboy` (Node 24, uv, Python 3.12, Redis) — attendue, pas une dégradation des sites existants.

## Ce qui a été créé

### Espace de noms
```
/srv/pokeboy/{uat,prod}/{app,config,data/photos,backups,logs,releases}
/srv/pokeboy/caddy/
/srv/pokeboy/tools/            (Node 24, uv, Python 3.12 — $HOME de l'utilisateur pokeboy)
```
- Utilisateur système `pokeboy` (uid 995, gid 982, `nologin`, sans mot de passe), `kailo` ajouté
  à son groupe pour pouvoir déployer.
- `app/` et `releases/` : `2775 pokeboy:pokeboy` (setgid, groupe `pokeboy` peut écrire — `kailo`
  y dépose les artefacts construits sur chimera).
- `config/`, `data/`, `data/photos/`, `backups/`, `logs/` : `750 pokeboy:pokeboy` (pas d'accès
  groupe — seul le processus applicatif, qui tourne en `pokeboy`, y touche).

### PostgreSQL (cluster 18 existant, aucun redémarrage)
- Rôles `pokeboy_uat` / `pokeboy_prod` : `LOGIN`, sans superutilisateur, mots de passe générés
  aléatoirement (`openssl rand -hex 24`), jamais affichés.
- Bases `pokeboy_uat` / `pokeboy_prod`, chacune appartenant à son rôle, encodage UTF8,
  `LC_COLLATE`/`LC_CTYPE` `C.utf8`.
- Extensions `pg_trgm` et `unaccent` créées dans les deux bases.
- Isolation : `REVOKE CONNECT ... FROM PUBLIC` sur les deux bases + `GRANT CONNECT` au seul
  propriétaire. **Vérifié** : `pokeboy_uat` reçoit `FATAL: permission denied for database
  "pokeboy_prod"` et réciproquement ; chaque rôle se connecte normalement à sa propre base.
- `pg_hba.conf` **déjà** restreint à `127.0.0.1/32` et `::1/128` pour tous les rôles (hérité de
  la configuration existante) → **aucune modification, aucun reload nécessaire**.

### Redis (nouveau service, installé par ce lot)
- `redis-server` 8.0.5 installé via apt, actif et activé.
- `bind 127.0.0.1 -::1` (défaut du paquet, vérifié), `maxmemory 128mb`,
  `maxmemory-policy allkeys-lru`, `requirepass` (mot de passe généré, jamais affiché).
- Bases logiques : **0 = prod, 1 = uat** (par convention dans les `.env`, pas une contrainte du
  serveur).
- Sauvegarde de la configuration avant modification : `/etc/redis/redis.conf.bak-pokeboy-20260919`
  (⚠️ capturée juste après l'ajout du bloc — le bloc ajouté est délimité par un commentaire
  `# --- PokeBoyManager ---` et donc trivialement réversible à la main si besoin).
- Vérifié : `PING` refusé sans mot de passe (`NOAUTH`), accepté avec (`PONG`), `maxmemory` et
  `maxmemory-policy` confirmés par `CONFIG GET`.

### Secrets (`.env`, jamais affichés)
`/srv/pokeboy/{uat,prod}/config/.env`, `chmod 600`, propriétaire `pokeboy` seul. Contenu :
`APP_ENV`, `APP_BASE_URL`, `DATABASE_URL`, `REDIS_URL` (forme `redis://default:motdepasse@127.0.0.1:6379/{0,1}`
— la forme sans nom d'utilisateur `redis://:motdepasse@...` n'est pas fiablement analysée par ce
build de `redis-cli`, corrigé après test), `PHOTOS_STORAGE_PATH`, `WEB_PORT`, `API_PORT`,
`AI_KEYS_MASTER_KEY` (32 octets aléatoires distincts par environnement), `SESSION_SECRET`.
**Vérifié de bout en bout** comme utilisateur `pokeboy` : connexion PostgreSQL et `PING` Redis
réussis en lisant exactement ces fichiers.

### Node / uv / Python pour l'utilisateur `pokeboy`
- `$HOME` de `pokeboy` fixé à `/srv/pokeboy/tools` (pas de `/home/pokeboy` — cohérent avec la
  convention « tout sous `/srv/pokeboy` »).
- Node **v24.21.0** (tarball officiel, `/srv/pokeboy/tools/node24/`).
- `uv` **0.12.17** (`/srv/pokeboy/tools/.local/bin/`).
- Python **3.12.14** installé via `uv python install 3.12`.

### Services systemd (créés, **non démarrés, non activés**)
`pokeboy-{uat,prod}-{web,api,worker}.service` dans `/etc/systemd/system/`, `daemon-reload` fait.
Confirmé `inactive`/`disabled` pour les 6, syntaxe validée (`systemd-analyze verify`, aucune
erreur propre à ces unités).

| Service | Port | Ports choisis |
|---|---|---|
| `pokeboy-uat-web` | Next.js | 3110 |
| `pokeboy-uat-api` | FastAPI/uvicorn | 8110 |
| `pokeboy-uat-worker` | arq | — (pas de port) |
| `pokeboy-prod-web` | Next.js | 3100 |
| `pokeboy-prod-api` | FastAPI/uvicorn | 8100 |
| `pokeboy-prod-worker` | arq | — |

Durcissement appliqué : `NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome`, `PrivateTmp`,
`ReadWritePaths` limité à `data/` et `logs/`, `MemoryMax` (320 Mo web/api, 256 Mo worker — voir
projection de capacité).

⚠️ **Hypothèse de mise en page à vérifier avant le premier déploiement réel** (documentée en
commentaire dans chaque unité) : `app/web` = build Next.js standard (`next start`), `app/api` =
projet Python géré par `uv` avec `app.main:app` (API) et `app.worker.WorkerSettings` (worker
arq). Si la structure réelle construite sur chimera diffère, ajuster `ExecStart`
avant `systemctl enable --now`.

### Caddy (fichier séparé, **non importé**)
`/srv/pokeboy/caddy/pokeboy.caddy` — vhosts `pokeboy.acx-connect.com` (PROD) et
`uat.pokeboy.acx-connect.com` (UAT), reverse proxy vers web + `/api/*` vers l'API (hypothèse :
l'API ne porte pas le préfixe `/api` en interne — `handle_path` le retire ; à corriger en
`handle` sinon), en-têtes de sécurité (bloc `pokeboy_secu` autonome, ne dépend pas du snippet
`secu` du Caddyfile hôte — leçon d'`acx.caddy`), limite d'upload 25 Mo.

Validation faite **en isolation** (`caddy validate` sur une config jetable important seulement ce
fichier) : **configuration valide**. Le Caddy en service n'a pas été touché (confirmé : toujours
`active`, kailo.life et ACX toujours 200 juste après).

**Procédure d'activation** (documentée en tête du fichier, à faire quand les DNS existeront) :
1. `dig +short pokeboy.acx-connect.com uat.pokeboy.acx-connect.com` → doit résoudre vers l'IP du
   serveur pour les deux ;
2. ajouter `import /srv/pokeboy/caddy/pokeboy.caddy` à `/etc/caddy/Caddyfile` ;
3. `sudo caddy validate --config /etc/caddy/Caddyfile` ;
4. `sudo systemctl reload caddy` ;
5. vérifier les deux nouveaux domaines **et** re-vérifier kailo.life/ACX juste après.

### Sauvegardes
- Script `/srv/pokeboy/prod/backups/backup.sh` (`750 pokeboy:pokeboy`) : `pg_dump -Fc` des deux
  bases + archive `tar.gz` de `prod/data/photos/`, purge des fichiers de plus de 7 jours.
- Cron `pokeboy` : `15 3 * * *` (03:15 UTC), journal vers `/srv/pokeboy/prod/logs/backup.log`.
- **Testé manuellement** : dumps + archive produits, tailles cohérentes.
- **Test de restauration effectué** : dump `pokeboy_uat` restauré dans une base temporaire
  `pokeboy_restore_test` (propriétaire `pokeboy_uat`), extensions `pg_trgm`/`unaccent`
  confirmées présentes après restauration, puis base temporaire **supprimée**.

## Recommandation — stockage des photos

| Option | Avis |
|---|---|
| **(a) Disque local derrière l'API** (`/srv/pokeboy/<env>/data/photos/`) | **Recommandé pour le lancement MVP/UAT et le démarrage PROD.** Zéro coût RAM, zéro service supplémentaire, déjà préparé. Limite : lié au disque du serveur (19 Go libres aujourd'hui) et pas de réplication hors-site au-delà des sauvegardes cron. |
| (b) MinIO en binaire systemd | Coûte ~50-100 Mo de RAM en continu sur une machine à 3,8 Go — non négligeable ici — et un service de plus à opérer (mises à jour, supervision). À envisager seulement si l'app a réellement besoin d'une API S3. |
| (c) UpCloud Managed Object Storage | La bonne cible à terme (durabilité, hors-site, pas de disque à gérer) mais **nécessite une écriture UpCloud** (création de ressource + coût récurrent) — proposition seulement, **rien n'a été créé**. À chiffrer et décider avec JF quand le volume de photos réelles sera connu. |

**Recommandation retenue pour aujourd'hui : (a).** Migrer vers (c) si le volume de photos ou une
exigence de durabilité/hors-site l'impose.

## Projection de capacité (RAM)

Base actuelle (avant PokeBoyManager, mesurée) : ~958-990 Mo utilisés, ~2,87-2,90 Go
`available`. Postgres (cluster unique, `shared_buffers=128 Mo`) ≈ 68-180 Mo selon charge,
Caddy ≈ 65-70 Mo, Kailo UAT (web+API) ≈ 110+170 Mo, Redis neuf ≈ 4 Mo au repos (plafonné à
128 Mo).

| Scénario | Ajout estimé | Disponible restant |
|---|---|---|
| **Réaliste** (web ~150 Mo ×2, API ~180 Mo ×2, worker ~100 Mo ×2, Redis en usage réel, overhead Postgres +2 bases) | ~1,0-1,1 Go | ~1,8 Go — **marge confortable** |
| **Pire cas** (les 6 services au plafond `MemoryMax` + Redis à son `maxmemory`) | 640+640+512+128 = **1,92 Go** | **< 1 Go** — tendu mais **borné** : `MemoryMax` fait limiter/killer le service en cause, pas saturer l'hôte ; swap de 2 Go (0 utilisé aujourd'hui) reste un filet |

**Conclusion : ça tient dans 3,8 Go, avec une marge confortable en usage réaliste.** Le pire cas
théorique est tendu — à surveiller une fois du trafic réel présent, surtout côté PROD.

⚠️ **Aucune sonde ne surveille `kailo-srv`** aujourd'hui (l'`infra-watch` de devAI couvre la PROD
et l'UAT UpGreg, pas ce serveur — projet distinct). Gap pré-existant, hors périmètre de ce lot,
signalé pour arbitrage futur.

**Si la capacité s'avère insuffisante avec du trafic réel** : proposer un redimensionnement
UpCloud du VPS. Je n'ai **pas pu vérifier le tarif exact en direct** : `kailo-srv` n'apparaît pas
dans le compte UpCloud dont le jeton est disponible sur devAI (`~/.upcloud-tokens`, compte
« kailo » documenté dans le CLAUDE.md de la flotte) — ce serveur semble être sur un compte
UpCloud distinct. Recommandation : vérifier le tarif de montée en gamme directement dans la
console UpCloud pour ce serveur précis avant toute décision.

## Observation hors périmètre (non traitée)

Aucune sauvegarde automatisée n'a été trouvée pour les bases `kailo_prod` / `kailo_uat`
existantes (ni cron, ni `pg_backupcluster` configuré). Pré-existant, sans lien avec
PokeBoyManager — signalé pour arbitrage, pas corrigé ici.

## Ce qui reste à faire / attend JF

1. **DNS** : créer `pokeboy.acx-connect.com` et `uat.pokeboy.acx-connect.com` → IP de kailo-srv
   (bloque l'activation Caddy).
2. **Déploiement réel depuis chimera** : construire les artefacts, les copier dans
   `releases/<horodatage>/`, les faire pointer depuis `app/` (symlink ou sync — mécanique non
   posée aujourd'hui, hors périmètre), puis vérifier/ajuster les hypothèses de mise en page des
   unités systemd avant `systemctl enable --now`.
3. **Décision stockage photos** : (a) retenu par défaut ; passage à (c) UpCloud Object Storage
   à chiffrer avec JF si besoin de durabilité/hors-site.
4. **Activation Caddy** une fois les DNS propagés (procédure dans
   `/srv/pokeboy/caddy/pokeboy.caddy`).
5. **Capacité** : resurveiller après premier trafic réel ; si tendu, chiffrer un
   redimensionnement UpCloud via la console (le compte de ce serveur n'est pas accessible par
   API depuis devAI).
6. Gap pré-existant signalé : pas de sauvegarde automatisée pour `kailo_prod`/`kailo_uat`.

---
FAIT — pbm-serveur
