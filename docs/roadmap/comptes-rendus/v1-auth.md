# Compte rendu — `v1-auth`

Session autonome (`claude -p`) sur chimera, worktree `~/dev/wt-pbm-v1-auth`, branche
`roadmap/v1-auth`. Exécuté sous le régime décrit dans le CONTEXTE D'EXÉCUTION du prompt
(sections A/P/0/7 du prompt de lot remplacées) : pas de `suivi.py`, pas d'écriture dans
`etat.json`/`ROADMAP.html`/`BACKLOG.md`/`prompts/`, dépendances déjà fusionnées dans
`origin/main` (dépôt relais local, pas GitHub).

## Résumé

Comptes e-mail + mot de passe pour PokeBoyManager : inscription, vérification d'adresse,
connexion, déconnexion, mot de passe oublié/réinitialisation. Six routes FastAPI sous
`/auth`, session par cookie opaque haché en base (rotation à chaque connexion, sessions
multiples), CSRF par double soumission signée, limitation de tentatives par Redis,
mots de passe argon2id contrôlés contre les fuites connues (k-anonymat HIBP). E-mails
transactionnels envoyés via SMTP (Mailpit en dev, D5). Aucun front dans ce lot (back-end
seul — les pages viennent du lot `v1-pages-auth`).

## Livrables

- `apps/api/src/pbm_api/routers/auth.py` — les six routes : `POST /auth/register`,
  `/auth/login`, `/auth/logout`, `/auth/verify-email`, `/auth/forgot`, `/auth/reset`.
  Pose les cookies `pbm_session` (`HttpOnly; Secure; SameSite=Lax`) et `pbm_csrf` (lisible
  par le front) à la connexion, les efface à la déconnexion.
- `apps/api/src/pbm_api/auth/` — logique métier indépendante de FastAPI :
  - `service.py` : inscription (anti-énumération — même réponse, même code, qu'un compte
    existe déjà ou non ; aucun doublon créé), vérification d'e-mail, authentification +
    rotation de session, déconnexion, demande/réalisation de réinitialisation (révoque
    **toutes** les sessions actives de l'utilisateur).
  - `dependencies.py` : `get_current_user`/`get_current_session`/`require_csrf` —
    dépendances FastAPI **réutilisables par les lots suivants** pour toute route
    utilisateur. Ne dérivent jamais d'un identifiant fourni par le client, uniquement du
    cookie de session résolu côté serveur.
  - `errors.py`, `schemas.py` — exceptions du domaine, schémas Pydantic des requêtes/réponses.
- `apps/api/src/pbm_api/security/` :
  - `passwords.py` — hachage argon2id (`argon2-cffi`), politique 10 caractères minimum.
  - `compromised.py` — `CompromisedPasswordChecker`, k-anonymat HIBP (SHA-1, 5 premiers
    caractères seulement quittent le serveur) ; en panne du service tiers, n'empêche pas
    l'inscription (journalisé, pas un repli silencieux).
  - `csrf.py` — double soumission signée (cookie CSRF = HMAC du jeton de session, comparé
    en temps constant à l'en-tête `X-CSRF-Token`).
  - `rate_limit.py` — limiteur Redis à fenêtre glissante, 5 tentatives / 15 min, scindé par
    compte et par IP ; appliqué à `/auth/login` et `/auth/forgot`.
  - `tokens.py` — jetons opaques (session, e-mail) : seul le hash SHA-256 est stocké,
    jamais le jeton en clair.
- `apps/api/src/pbm_api/email.py` — `EmailSender` injectable (SMTP réel en prod/dev,
  substitué par un enregistreur dans les tests — CI n'a pas de Mailpit).
- `apps/api/src/pbm_api/config.py` — nouveaux réglages (`SECRET_KEY`, `APP_PUBLIC_URL`,
  cookies, TTL session/jetons, limitation de connexion) ; défauts de base/bucket/préfixe
  Redis repointés sur ce lot (`pbm_v1_auth`, `pbm-v1-auth`, `pbm:v1-auth:`).
- `apps/api/tests/test_auth.py` — 20 tests (parcours complet, jeton expiré, jeton réutilisé,
  force brute, session révoquée, accès croisé — détail ci-dessous).
- `apps/api/tests/conftest.py` — `api_client` (httpx.AsyncClient + `ASGITransport`, base de
  données de test partagée avec le test via la même transaction, e-mails/HIBP simulés),
  nettoyage des compteurs Redis entre tests.
- `.env.example`, `CLAUDE.md`, `docs/ARCHITECTURE.md` — nouvelle section « Authentification »
  et variables d'environnement documentées.
- Bases dédiées créées sur l'infra partagée : `pbm_v1_auth` (dev) et `pbm_v1_auth_test`
  (tests) — aucune migration Alembic nouvelle, le schéma `v0-schema` couvrait déjà
  `users`/`sessions`/`email_tokens`.

## Choix techniques

- **Anti-énumération sur `/register` et `/forgot`** : réponse strictement identique (code,
  corps) que l'e-mail soit déjà pris/connu ou non — le prompt ne l'exigeait explicitement
  que pour la connexion, mais la section « Risques & pièges » du lot cite l'énumération de
  comptes comme risque général ; extension cohérente avec le reste du dispositif.
- **Limitation appliquée aussi à `/forgot`** (même limiteur, portée distincte) : un
  formulaire de réinitialisation sans limite est un vecteur de spam/énumération par
  chronométrage ; réutilise le même composant que `/login` sans complexité ajoutée.
- **CSRF appliqué seulement à `/auth/logout`** dans ce lot : c'est la seule route qui écrit
  pour un utilisateur déjà authentifié. `require_csrf` est posé comme dépendance
  réutilisable pour les routes d'écriture des lots suivants (profil, collection…).
- **Réinitialisation du mot de passe révoque toutes les sessions actives** de l'utilisateur
  (pas seulement celle utilisée pour la demande) — comportement standard si le compte a pu
  être compromis. Le prompt ne le précisait pas explicitement mais c'est cohérent avec
  l'exigence de test « session révoquée ».
- **Aucune vérification d'adresse obligatoire avant connexion** : un compte non vérifié peut
  se connecter (le champ `email_verified` est renvoyé au front pour qu'il adapte l'UI).
  Le prompt ne demande pas de bloquer, seulement de proposer le parcours de vérification.
- **`GET /auth/me` volontairement absent** : la mission liste exactement six routes : m'y
  suis tenu pour ne pas étendre le périmètre sans nécessité — un lot suivant l'ajoutera s'il
  en a besoin.
- **Colonnes `expires_at`/`used_at` sans fuseau** (héritées de `v0-schema`,
  `TIMESTAMP WITHOUT TIME ZONE`) : toutes les valeurs manipulées sont en UTC naïf
  (`_utc_now_naive()` dans `service.py`) — un datetime « aware » ferait échouer l'insertion
  asyncpg.
- **Client Redis reconstruit à chaque appel** (`get_redis()`, pas de singleton de module) :
  un client `redis.asyncio` est lié à la boucle asyncio qui l'a créé ; un singleton de
  processus survit d'un test à l'autre alors que pytest-asyncio recrée une boucle par test,
  ce qui provoquait des `RuntimeError: … attached to a different loop`. Coût négligeable
  face à l'aller-retour réseau ; à revisiter si le volume le justifie un jour (pool partagé
  via le cycle de vie de l'app).
- **Tests HTTP via `httpx.AsyncClient(transport=ASGITransport(...))`**, pas
  `fastapi.testclient.TestClient` : le client synchrone exécute l'app dans un thread/boucle
  asyncio séparés, incompatible avec le partage d'une session SQLAlchemy async créée dans la
  boucle du test (même symptôme « attached to a different loop », côté asyncpg cette fois).
  `ASGITransport` exécute l'app dans la boucle du test — cf. `conftest.py`.
- **`expire_on_commit=False` sur la session de test** (`conftest.py`), pour s'aligner sur
  `pbm_api.db.async_session_factory` déjà utilisé en prod — sans ça, accéder à un attribut
  après un `commit()` lève `MissingGreenlet` (rechargement implicite hors du pont greenlet
  async de SQLAlchemy).

## Décisions provisoires utilisées

- D5 (e-mails) : SMTP configurable, Mailpit en dev — appliqué tel quel via
  `pbm_api.config.Settings` (`smtp_*`, déjà posé par `v0-monorepo`).

## Preuves — commandes lancées, résultats chiffrés

```
$ cd apps/api && uv run ruff check .
All checks passed!

$ TZ=Europe/Paris TEST_DATABASE_URL=postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v1_auth_test \
    uv run pytest -q
..............................                                           [100%]
30 passed, 2 warnings in 3.54s
```

Preuve « un test échoue sans le changement, passe avec » (§6) — `app.include_router(auth_router)`
retiré de `main.py`, seule `tests/test_auth.py` relancée :

```
20 failed in 0.91s
  FAILED test_register_sends_verification_email — 404 == 202
  FAILED test_register_does_not_create_duplicate_or_leak_that_email_exists
  FAILED test_register_rejects_password_too_short
  FAILED test_register_rejects_compromised_password
  FAILED test_verify_email_activates_account
  FAILED test_verify_email_rejects_unknown_token
  FAILED test_verify_email_rejects_reused_token
  FAILED test_verify_email_rejects_expired_token
  FAILED test_login_succeeds_and_sets_session_and_csrf_cookies
  FAILED test_login_rejects_unknown_email_and_wrong_password_identically
  FAILED test_login_rotates_session_on_each_successful_login
  FAILED test_login_is_rate_limited_after_five_failed_attempts
  FAILED test_logout_requires_csrf_header
  FAILED test_logout_revokes_the_session
  FAILED test_logout_only_revokes_the_caller_session_not_another_users
  FAILED test_forgot_password_gives_identical_response_known_or_unknown_email
  FAILED test_reset_password_updates_password_and_revokes_all_sessions
  FAILED test_reset_password_rejects_reused_token
  FAILED test_reset_password_rejects_expired_token
  FAILED test_reset_password_rejects_short_or_compromised_password
```
puis `app.include_router(auth_router)` restauré → les 30 tests repassent au vert.

Simulation du job CI (une seule base éphémère `pbm_v1_auth_citest`, comme le service
Postgres GitHub Actions, migration puis tests) :

```
$ uv run alembic upgrade head
Running upgrade  -> 5e0d551b788e, initial schema

$ TZ=Europe/Paris DATABASE_URL=…/pbm_v1_auth_citest TEST_DATABASE_URL=…/pbm_v1_auth_citest \
    REDIS_URL=redis://localhost:56379/0 uv run pytest -q
30 passed, 2 warnings in 3.46s
```
(base éphémère supprimée après coup.)

**Test d'accès croisé** (`test_logout_only_revokes_the_caller_session_not_another_users`) :
deux utilisateurs A et B connectés via deux clients HTTP distincts (mêmes overrides de
dépendances, cookies séparés) ; la déconnexion de A (avec son propre jeton CSRF) ne retire
que sa session — `SELECT count(*) FROM sessions WHERE user_id = B` reste à 1, et la session
de B continue à authentifier ses propres requêtes.

**Preuve manuelle — e-mails reçus dans Mailpit** (SMTP réel, pas le simulateur de tests),
serveur `uv run uvicorn` sur la base `pbm_v1_auth`, boîte Mailpit vidée avant :

```
$ curl -X POST :58100/auth/register -d '{"email":"manuel-…@example.com","password":"…"}'
{"message":"Si cette adresse n'est pas déjà utilisée, un e-mail de vérification vient d'être envoyé."}
HTTP 202

$ curl http://localhost:58025/api/v1/messages
total: 1 — To: manuel-…@example.com — Subject: Vérifiez votre adresse PokeBoyManager

$ curl -X POST :58100/auth/verify-email -d '{"token":"<extrait du corps>"}'
{"message":"Adresse e-mail vérifiée."} HTTP 200

$ curl -c cookies.txt -X POST :58100/auth/login -d '{"email":"…","password":"…"}'
{"id":"83f19cfe-…","email":"manuel-…@example.com","email_verified":true} HTTP 200
  → cookies posés : pbm_session (HttpOnly) et pbm_csrf

$ curl -b cookies.txt -X POST :58100/auth/logout                       # sans en-tête CSRF
{"detail":"Jeton CSRF invalide"} HTTP 403
$ curl -b cookies.txt -X POST :58100/auth/logout -H "X-CSRF-Token: <cookie pbm_csrf>"
HTTP 204

$ curl -X POST :58100/auth/forgot -d '{"email":"…"}'                   # e-mail de reset reçu
$ curl -X POST :58100/auth/reset -d '{"token":"<extrait>","password":"<nouveau>"}'
{"message":"Mot de passe mis à jour."} HTTP 200
$ curl -X POST :58100/auth/login -d '{"email":"…","password":"<nouveau>"}'
{"id":"83f19cfe-…", …, "email_verified":true} HTTP 200
```
Serveur manuel arrêté, boîte Mailpit et cookies temporaires nettoyés après coup — aucune
donnée résiduelle de cette vérification.

## Écarts au plan

Aucun écart de périmètre. Les six routes de la mission sont posées, les cinq risques listés
(énumération, force brute, CSRF) sont couverts, les cinq catégories de tests exigées (parcours
complet, jeton expiré, jeton réutilisé, force brute, session révoquée) sont présentes, plus un
test d'accès croisé explicite.

## Reste à faire

- **Front** (`v1-pages-auth`) : pages `/inscription`, `/connexion`, `/verifier-email`,
  `/mot-de-passe-oublie`, `/reinitialiser-mot-de-passe` — les chemins des liens d'e-mail
  (`{APP_PUBLIC_URL}/verifier-email?token=…` et `.../reinitialiser-mot-de-passe?token=…`)
  sont fixés dans `pbm_api/auth/service.py` : à aligner avec le routing Next.js du lot front.
- **Fournisseur SMTP définitif** : D5 reste provisoire pour l'expéditeur
  (`no-reply@acx-connect.com`, MX Google Workspace) — `SMTP_FROM`/`SMTP_HOST` à définir en
  UAT/PROD, aucune action ici (hors périmètre, pas de déploiement dans ce lot).
  `SECRET_KEY` (signature CSRF) doit également être fixé par variable d'environnement hors
  dépôt à ce moment-là — la valeur de dev n'est pas un secret réel mais ne doit jamais servir
  en ligne.
- **Client Redis par appel** (choix technique ci-dessus) : optimisation possible (pool
  partagé via le cycle de vie de l'app) si le volume de connexions le justifie — non
  nécessaire pour le MVP.
- **`GET /auth/me`** ou équivalent : pas posé (hors périmètre strict de la mission) — le lot
  qui en a besoin (profil ?) pourra le poser en réutilisant `get_current_user`.
- Aucune CI GitHub Actions déclenchée depuis cette session (dépôt relais local, pas GitHub) —
  la simulation locale du job `api` (migration + suite complète sur base éphémère) est
  documentée ci-dessus en attendant que le pilote synchronise vers GitHub.
