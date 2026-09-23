# Livraison — mettre en ligne, et revenir en arrière

> **À lire avant toute mise en ligne.** Le geste technique : où ça tourne, qui construit, qui
> déploie, comment on prouve que c'est en ligne, comment on revient en arrière.
> Ce qui n'est pas ici : **quoi** sort et quand (`docs/RELEASE.md`), le code (`docs/CODE.md`),
> la préparation historique du serveur (`docs/infra/SERVEUR-POKEBOY.md`, rapport daté).
> Tous les chemins sont donnés **depuis la racine du dépôt**, sauf ceux préfixés `/srv` (serveur).

## ⛔ La règle d'or : on ne construit pas sur la machine qui sert

`kailo-srv` a **2 cœurs et 3,8 Go de RAM**, et il sert déjà `kailo.life`, `uat.kailo.life` et
`acx-connect.com`. Un build sur place dégrade le service pendant qu'il tourne — mesuré ailleurs :
charge 143 sur 4 cœurs, `/health` qui expire à 30 s pour un visiteur réel, un OOM-kill.

**chimera construit. devAI livre. Le serveur ne fait que recevoir et redémarrer.**
Aucun build, aucun `docker compose`, aucun déploiement **depuis le Mac de JF** — c'est le verrou
posé après l'incident du 2026-08-09 (`~/.claude/CLAUDE.md`).

## Contrainte absolue : kailo.life et ACX ne bougent pas

Avant **et** après chaque étape qui touche au serveur, on vérifie que les sites voisins répondent
comme avant :

```bash
for u in https://kailo.life https://www.kailo.life https://acx-connect.com \
         https://www.acx-connect.com https://uat.kailo.life; do
  printf "%-32s %s\n" "$u" "$(curl -s -o /dev/null -w '%{http_code}' "$u")"
done
# attendu : 200 200 308 200 307
```

Une seule valeur qui change : on arrête et on remet en état. Les sites de JF passent avant
PokeBoyManager.

## Ce qui tourne aujourd'hui

| | |
|---|---|
| PROD | **https://pokeboy.acx-connect.com** — en service depuis le **20/09/2026 15h39** (commit `5873a9c`) |
| UAT | **aucun** (D2, JF 19/09) : la recette se fait en local sur chimera, on déploie directement en PROD |
| Machine | `kailo-srv` / UpCloud « sites-and-crons » (`004ba88c…`), 5.22.213.226 |
| Services | `pokeboy-prod-web` (Next.js, port 3100), `pokeboy-prod-api` (FastAPI/uvicorn, 8100), `pokeboy-prod-worker` (arq) |
| Entrée | Caddy de l'hôte, qui importe `/srv/pokeboy/caddy/pokeboy.caddy` |
| Données | PostgreSQL 18 de l'hôte, base `pokeboy_prod` (rôle propre, `REVOKE CONNECT ... FROM PUBLIC`) ; Redis local, base logique **0 = prod, 1 = uat** |
| Fichiers | `/srv/pokeboy/prod/{app,config,data/photos,backups,logs,releases}`, utilisateur système `pokeboy` |

Les unités `pokeboy-uat-*` (ports 3110 / 8110) existent mais restent **inactives** tant qu'il n'y a
pas d'UAT.

## La chaîne de livraison

1. **La CI est verte** sur le commit à livrer (GitHub Actions fait foi — voir `docs/CODE.md`).
2. **chimera construit** les artefacts (front Next.js, API, dépendances).
3. **Transfert** vers `/srv/pokeboy/prod/releases/<horodatage>/` — le groupe `pokeboy` y écrit,
   c'est fait pour ça.
4. **Bascule** : `app/` pointe sur la nouvelle version.
5. **Migrations** Alembic appliquées.
6. `systemctl restart pokeboy-prod-{api,worker,web}`.
7. **Preuve** (voir ci-dessous), puis vérification des sites voisins.

> **Point ouvert.** Ces étapes sont celles du rapport `pbm-serveur` et de la mise en PROD du 20/09.
> Le script qui les enchaîne n'est **pas encore dans le dépôt** (`infra/` ne contient à ce jour que
> les SQL de la chaîne flotte). Tant qu'il n'y est pas, la livraison se fait depuis devAI à la main
> et **chaque livraison doit reporter ici ce qu'elle a réellement exécuté**. Le jour où le script
> existe, son chemin remplace ce paragraphe.

## Livraison du 23/09/2026 — vague V7D « Gestionnaire de decks »

Ce qui a réellement été exécuté (la chaîne n'est toujours pas scriptée dans le dépôt).
Release **`20260923-024121`**, commit **`3063f41`**, précédente `20260922-234920` (`b32daec`).

```bash
# 0. Portes : CI verte sur 3063f41 ; codes HTTP des voisins relevés AVANT (200 200 308 200 307)
# 1. chimera construit — le worktree de build appartient au dépôt RELAIS, pas au clone :
ssh chimera 'wsl … -- bash -lc "cd ~/dev/wt-pbm-deploy && git fetch github && git checkout --detach github/main"'
ssh chimera 'wsl … -- bash -lc "bash ~/dev/pbm-build-lol.sh"'   # → ~/dev/pbm-artefacts/{web,api}-TS.tgz
# 2. transfert chimera → devAI → serveur, empreintes SHA-256 comparées aux TROIS étapes
ssh chimera 'wsl … -- cp ~/dev/pbm-artefacts/*-TS.tgz /mnt/c/tmp/pbm/'
ssh devai   'scp chimera:C:/tmp/pbm/{web,api}-TS.tgz /tmp/pbm/ && scp /tmp/pbm/*-TS.tgz kailo-srv:/tmp/pbm/'
# 3. point de restauration frais AVANT toute écriture
ssh kailo-srv 'sudo -n -u pokeboy bash /srv/pokeboy/prod/backups/backup.sh'
# 4. préparation (n'engage rien : le service tourne encore sur l'ancienne release)
ssh kailo-srv 'TS=20260923-024121 COMMIT=3063f41 LOT=v7d-gestionnaire-de-decks bash /tmp/prep-lol.sh'
# 5. bascule, avec retour arrière automatique sur échec de santé
ssh kailo-srv 'TS=20260923-024121 bash /tmp/deploy-switch.sh'
```

**Preuve relevée après bascule** : `app/ -> releases/20260923-024121`, `RELEASE_INFO` porte
`commit=3063f41` ; les 3 unités `active` ; `https://pokeboy.lol/api/health` → 200 ;
`/jeu/decks` → 307 (route présente et gardée, pas 404) ; l'OpenAPI servi expose **14 routes
`decks`**, dont `/me/decks/cards` (recherche), `/me/decks/{id}/stats`, `/me/decks/{id}/propose`
(assistant IA), `/me/decks/alerts` et `/me/decks/{id}/replacements` (synchro collection) ;
voisins **inchangés** (200 200 308 200 307).

**Aucune migration** : la base était déjà à `b2d4f6a8c0e1`, `alembic upgrade head` n'a rien eu
à faire — la release précédente avait déjà embarqué `v7-decks-collection-sync`.

### Deux pièges rencontrés, à ne pas rejouer

- **Le worktree de build de chimera (`~/dev/wt-pbm-deploy`) est rattaché au dépôt relais
  `~/dev/pokeboy.git`, pas au clone `~/dev/pokeboy`.** Un `git fetch` fait dans le clone ne
  l'avance pas : son `github/main` retardait de **12 commits**. Rien n'échoue dans ce cas —
  on construit l'ancienne version en croyant livrer la nouvelle. **Vérifier le HEAD du
  worktree après le checkout**, jamais supposer qu'il a bougé.
- **Le SSH vers chimera se fait couper** (`kex_exchange_identification: Connection reset`)
  pendant les builds : ce n'est pas une panne, on réessaie. Une boucle de 5 tentatives
  espacées de 15 s a suffi à chaque fois.

## Conclure « déployé » — jamais sur une ligne de journal

Un build qui échoue laisse la plateforme **debout sur l'ancienne version** : tout a l'air normal et
rien n'est livré. La preuve minimale, dans cet ordre :

```bash
systemctl is-active pokeboy-prod-api pokeboy-prod-web pokeboy-prod-worker   # active ×3
curl -s https://pokeboy.acx-connect.com/api/health                          # 200
# et la version servie est bien le commit attendu
```

Plus un parcours réel : se connecter, ouvrir la collection, ouvrir une fiche carte.

## Traitements lourds : sur la flotte, jamais sur la machine qui sert

Relevé de prix, import du catalogue, génération par lots, relevé de tournoi : ils tournent **sur
chimera**, et seul le résultat est importé en PROD (`infra/fleet/*.sql`). Le worker de PROD ne garde
que le court — reconnaissance, exports RGPD, e-mails — sous la garde `HEAVY_JOBS_ENABLED`
(**faux par défaut en production**). Runbook complet : `docs/infra/JOBS-LOURDS.md`.

## ⛔ « L'outil est absent » : vérifie le PATH avant de le croire (2026-09-22)

Trois pannes du 22/09, une seule cause. Un lot lancé par `ssh devai 'nohup claude -p …'` est mort à
la seconde : `claude: No such file or directory`, **journal de 41 octets**, aucune branche. Le même
jour, deux lots ont écrit « `gh` CLI absent de cette session » puis se sont déclarés **finis, sans
PR donc sans CI**.

Les trois diagnostics étaient faux : `claude` et `gh` vivent dans `/opt/homebrew/bin`, que le PATH
d'un **ssh non interactif** ne contenait pas. Les binaires étaient là depuis juillet.

Corrigé dans le `~/.zshenv` de devAI, **en fin de PATH** et pas en tête : Homebrew fournit aussi
`node`/`npm`/`npx`, et c'est `~/.local/node/bin` qui doit continuer de gagner.

**La règle** : avant de conclure qu'un outil manque, `command -v <outil>` puis
`ls /opt/homebrew/bin/<outil>`. Introuvable dans un shell non interactif ≠ absent — et « absent »
n'a jamais été une raison de livrer sans CI.

## La PR n'est pas optionnelle

`bash scripts/ouvrir-pr.sh <branche>` ouvre la PR du lot. Il ne se rabat jamais en silence :

| Situation | Code |
|---|---|
| PR déjà ouverte | `0`, et il en donne l'URL |
| Branche déjà fusionnée dans `main` | `0`, en le **disant** (vérifie alors la CI sur `main`) |
| Branche pas poussée, ou pas de remote GitHub | `3` |
| Jeton sans `pull_requests=write` | `4`, avec la cause nommée |
| Machine sans jeton (chimera) | `5`, avec la commande à lancer depuis devAI |

Il **ne dépend pas de `gh`** (absent de la WSL de chimera) : API REST via `curl` et `python3`. Il
trouve seul le bon remote — `origin` sur devAI, `github` sur chimera, dont l'`origin` est un dépôt
relais local **qui retarde**.

Un code ≠ 0 n'autorise pas à conclure : le lot passe en `bloque`, ou nomme le manque **dans son
compte rendu ET dans son dernier message**. Sans PR, le workflow ne tourne pas sur la branche
(il se déclenche sur `pull_request` et sur `push: [main]`), et c'est la CI qui fait foi.

### Pourquoi ça ne marche pas encore tout seul

Quatre identifiants testés le 22/09 — `GITHUB_TOKEN` et `~/.github-token-claude-desktop` sur devAI,
le jeton stocké de `gh`, `~/.config/git/github-token` sur le Mac. **Aucun ne peut ouvrir une PR.**
Ce n'est pas une déduction, GitHub le dit dans l'en-tête de son refus :

```
HTTP/2 403
x-accepted-github-permissions: pull_requests=write
```

`.github/workflows/pr-auto.yml` contourne le problème par le jeton du runner, que GitHub fabrique
lui-même. Il est en place, il **tourne**, et il bute sur un réglage du dépôt :
*« GitHub Actions is not permitted to create or approve pull requests »*.

**Deux corrections, toutes deux chez JF — une seule suffit :**
1. cocher *Settings → Actions → General → Workflow permissions → « Allow GitHub Actions to create
   and approve pull requests »* → **toutes** les PR s'ouvrent seules, pour toujours ;
2. ou ajouter *Pull requests: write* au jeton fine-grained → `ouvrir-pr.sh` fonctionne.

Tant qu'aucune n'est faite, `pr-auto` **reste rouge exprès** — un lot sans PR n'a pas de CI, ça doit
se voir — mais son message dit que le code n'est pas en cause et donne le lien d'ouverture manuelle.

## Retour arrière

Les versions précédentes restent dans `/srv/pokeboy/prod/releases/` : revenir en arrière, c'est
refaire pointer `app/` sur la version précédente et redémarrer les trois services. Une migration de
base déjà appliquée, elle, ne se défait pas toute seule — c'est le point à vérifier **avant** de
livrer une migration destructive.

> **À éprouver** : le compte rendu de `v5-prod` laisse deux points ouverts — « sauvegardes à
> éprouver sur une vraie restauration » et « surveillance à compléter ». Tant que la restauration
> n'a pas été essayée pour de vrai, on ne sait pas si on a des sauvegardes : on a des fichiers.

## Configuration par variables d'environnement

`apps/api` lit sa configuration via `pbm_api.config.Settings` (pydantic-settings, fichier `.env`
optionnel) : `DATABASE_URL`, `REDIS_URL`, `S3_ENDPOINT_URL`/`S3_ACCESS_KEY`/`S3_SECRET_KEY`/
`S3_BUCKET`/`S3_REGION`, `SMTP_HOST`/`SMTP_PORT`/`SMTP_USER`/`SMTP_PASSWORD`/`SMTP_FROM`,
`SECRET_KEY`/`APP_PUBLIC_URL`/`API_PUBLIC_URL`/`SESSION_COOKIE_NAME`/`CSRF_COOKIE_NAME`/
`SESSION_TTL_DAYS`/`EMAIL_TOKEN_TTL_MINUTES`/`LOGIN_RATE_LIMIT_MAX_ATTEMPTS`/
`LOGIN_RATE_LIMIT_WINDOW_SECONDS` (comptes, lot `v1-auth` — `SECRET_KEY` signe les jetons CSRF,
à définir par variable d'environnement en dehors du dépôt pour tout déploiement ;
`API_PUBLIC_URL`, lot `v5-rgpd`, est l'origine de l'API elle-même, distincte d'`APP_PUBLIC_URL` —
le lien de téléchargement d'export envoyé par e-mail pointe dessus), `AI_KEY_ENCRYPTION_KEY`
(coffre de clés IA, lot `v1-byok` — clé maître AES-256 en base64, 32 octets ; chiffre/déchiffre
les clés des utilisateurs, à définir par variable d'environnement hors dépôt pour tout
déploiement), `PLATFORM_ANTHROPIC_API_KEY`/`INSIGHTS_BUDGET_EUR`/`INSIGHTS_BATCH_MODEL`/
`INSIGHTS_BATCH_CHUNK_SIZE` (insights par lots, lot `v4-insights-batch` — clé PLATEFORME
distincte de toute clé d'utilisateur et plafond de dépense cumulé, vides/nuls par défaut : sans
eux, `scripts/run_insights_batch.py` refuse de dépenser quoi que ce soit ; à fournir par JF hors
dépôt, D4).
Chaque lot pointe sa propre base/bucket/préfixe — ne jamais réutiliser ceux d'un autre lot sur
l'infra partagée (`pbm-shared`). `apps/web` lit `NEXT_PUBLIC_API_URL` (défaut
`http://localhost:8000`) et `NEXT_PUBLIC_SESSION_COOKIE_NAME` (défaut `pbm_session`, doit
rester alignée avec `SESSION_COOKIE_NAME` côté API : le middleware de garde de route ne lit que
la présence de ce cookie, `apps/web/src/middleware.ts`). `apps/api` accepte les requêtes
cross-origin du front (`CORSMiddleware`, origine = `APP_PUBLIC_URL`, `allow_credentials=True`
pour le cookie de session) — obligatoire dès qu'ils tournent sur des ports/domaines différents.
`apps/web` lit aussi `NEXT_PUBLIC_UPLOAD_ORIGIN` (lot `v5-e2e`, doit rester alignée avec
`S3_ENDPOINT_URL` côté API quand `STORAGE_BACKEND=s3` — vide/absente avec `STORAGE_BACKEND=local`) :
la CSP `connect-src` du middleware (lot `v5-securite`) doit inclure l'origine du stockage objet,
sinon le `PUT` présigné direct du navigateur vers MinIO est bloqué et **tout envoi de photo
échoue** — trouvé en faisant tourner un vrai envoi par le navigateur pour la première fois
(`parcours-complet.spec.ts`), jamais exercé avant par les e2e précédentes (résultat toujours semé
directement en base).

> Les pages d'authentification et leurs chemins (`/verifier`, `/reinitialiser`…) sont décrits
> dans `docs/UI-UX.md` : ce sont des écrans, pas de la configuration.
