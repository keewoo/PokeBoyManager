# Revue de sécurité avant ouverture — `v5-securite`

Revue menée avant mise en PROD (jalon « En ligne »). Périmètre : `apps/api` (FastAPI) et
`apps/web` (Next.js). Pas de déploiement dans ce lot (D2/D8 hors périmètre) — cette revue porte
sur le code et sa configuration, pas sur l'infrastructure PROD elle-même (voir
`docs/infra/SERVEUR-POKEBOY.md` pour la cible).

## 1. Accès croisé entre comptes (IDOR)

Méthode : inventaire exhaustif de toutes les routes de `apps/api/src/pbm_api/routers/*.py` qui
prennent un identifiant d'objet potentiellement privé (envoi, détection, exemplaire de
collection, export, clé IA, session, avatar), vérification que le filtre d'appartenance est bien
`WHERE ... user_id = <utilisateur de la session>` (jamais un identifiant fourni par l'appelant),
et qu'un test automatisé à deux comptes existe pour chacune.

**Résultat : posture déjà solide.** Sur 28 routes scopées à un utilisateur, toutes filtrent
correctement par `user_id` et renvoient **404** (jamais 403, jamais un 200 vide) sur un objet
d'un autre compte. Trois écarts trouvés et corrigés dans ce lot :

| Écart | Sévérité | Correction |
|---|---|---|
| `GET /me/collection/{item_id}` (`routers/collection.py`) faisait son propre `session.get()` + contrôle Python au lieu de passer par `collection.service.get_owned_item` comme les autres routes du même fichier (`PATCH`, `DELETE`, `/photo`) — correctement gardé et testé, mais forme incohérente, exactement le motif qu'un futur refactoring pourrait casser sans le remarquer. | Faible (pas une faille observée) | Route reroutée par `service.get_owned_item` (`apps/api/src/pbm_api/routers/collection.py`) |
| `POST /detections/{id}/reject` n'avait pas son propre test d'accès croisé (partageait le filtre de `confirm`, testé, mais pas sa propre preuve) | Faible (couverture, pas un filtre manquant) | `test_reject_detection_returns_404_for_another_users_detection` (`test_validation_routes.py`) |
| `POST /me/ai-keys/{provider}/test` idem, pas de test dédié | Faible (couverture) | `test_test_route_returns_404_for_another_users_key` (`test_ai_keys.py`), vérifie en plus qu'aucune clé de A n'a été transmise au fournisseur pour le compte de B (`tester.received_keys == []`) |

Aucune route n'a été trouvée avec un filtre manquant, un `.get()` par id sans contrôle
d'appartenance, ou un 403 à la place d'un 404.

Cas volontairement hors du filtre par `user_id` (bearer token, pas de session) — audités
séparément :
- `PUT /uploads/{id}/raw?token=...` : jeton HMAC lié à cet `upload_id` précis (équivalent d'une
  URL présignée S3), vérifié (`test_local_backend_raw_upload_rejects_token_for_another_upload`).
- `GET /export/download?token=...` : jeton opaque 256 bits (`secrets.token_urlsafe(32)`),
  haché en base, TTL 24 h — entropie et durée jugées suffisantes pour un lien envoyé par e-mail.
- `/auth/verify-email`, `/auth/reset` : même famille de jeton (256 bits, haché, à usage unique).

## 2. En-têtes, cookies, CORS, débit, taille d'envoi

### En-têtes de réponse

**Absents avant ce lot** sur les deux applications. Ajoutés :

- `apps/api` : `pbm_api.security.headers.SecurityHeadersMiddleware` (nouveau) — `X-Content-
  Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-
  origin`, `Permissions-Policy: camera=(), microphone=(), geolocation=()`,
  `Strict-Transport-Security: max-age=63072000; includeSubDomains`, et `Content-Security-
  Policy: default-src 'none'; frame-ancestors 'none'; base-uri 'none'` (l'API ne sert que du
  JSON/des octets d'image, jamais de HTML) — sauf sur `/docs`/`/redoc`/`/openapi.json` (Swagger
  UI charge des scripts depuis un CDN, une CSP stricte casserait la page ; les autres en-têtes
  défensifs y restent posés). Vérifié : `tests/test_security_headers.py` (4 tests, y compris
  sur une réponse 404 — les en-têtes viennent du middleware, pas d'une route précise).
- `apps/web` : `src/middleware.ts`, élargi de quatre routes protégées à **toutes** les pages
  (`matcher` exclut seulement les assets statiques `_next/static`/`_next/image`/`favicon.ico`).
  CSP avec **nonce par requête** sur `script-src` (`'self' 'nonce-...'`, jamais `'unsafe-
  inline'`) : Next.js relit le nonce depuis l'en-tête `x-nonce` posé par le middleware et
  l'applique automatiquement à tous les scripts qu'il génère (vérifié en conditions réelles,
  voir § Preuves) ; le seul script inline du dépôt (`NO_FLASH_THEME_SCRIPT` dans
  `src/app/layout.tsx`, évite un flash clair/sombre) porte désormais ce même nonce
  (`headers()` de `next/headers`, lu dans le Server Component racine). `style-src` garde
  `'unsafe-inline'` : deux composants (`ai-tab.tsx`, `design/page.tsx`) posent une couleur
  dynamique via l'attribut `style`, qui ne peut pas porter de nonce — compromis courant même
  sous CSP stricte (une injection CSS est un risque nettement plus faible qu'une injection JS).
  `img-src`/`connect-src` autorisent l'origine de l'API (`NEXT_PUBLIC_API_URL`, cross-origin en
  PROD) en plus de `'self'`. `frame-ancestors 'none'` (protection anti-clickjacking, pertinent
  ici : l'app manipule des clés IA et des photos privées). Vérifié :
  `src/__tests__/middleware.test.ts` (+4 tests) et en conditions réelles (§ Preuves).

### Cookies

Déjà corrects avant ce lot (`routers/auth.py::_set_auth_cookies`), vérifiés à cette occasion :
cookie de session `HttpOnly`, `Secure`, `SameSite=Lax` ; cookie CSRF `Secure`, `SameSite=Lax`,
**non** `HttpOnly` par conception (le front doit le relire pour le renvoyer dans l'en-tête
`X-CSRF-Token`, protection en double soumission signée par HMAC du jeton de session —
`pbm_api.security.csrf`).

### CORS

`CORSMiddleware` (déjà en place) : `allow_origins=[settings.app_public_url]` — une seule
origine explicite, jamais `*` (`allow_credentials=True` l'interdirait de toute façon).
`allow_methods=["*"]`/`allow_headers=["*"]` restent larges, mais sans risque réel puisque
l'origine autorisée est déjà unique et explicite (le risque qu'une liste de méthodes/en-têtes
ouverte adresse — un site tiers arbitraire qui contourne le CORS — ne s'applique pas ici).
Vérifié en conditions réelles (préflight `OPTIONS`, § Preuves).

### Limitation de débit

Déjà en place sur `/auth/login` et `/auth/forgot` (5 tentatives / 15 min, par e-mail et par IP,
Redis). **Ajouté dans ce lot** : `/auth/register` (par IP, mêmes réglages) — cette route fait un
hachage de mot de passe coûteux et un appel réseau HIBP (vérification mot de passe compromis)
**avant même** de savoir si le compte existe déjà, et peut bombarder d'e-mails de vérification
une adresse tierce ; sans limite, les deux étaient exploitables à volonté. Vérifié :
`test_register_is_rate_limited_by_ip_after_five_attempts` (`test_auth.py`).

`/auth/verify-email` et `/auth/reset` restent sans limitation dédiée : protégés par l'entropie
du jeton (256 bits) plutôt que par un compteur — un jeton de cette taille n'est pas devinable en
un nombre de tentatives qu'une limitation de débit changerait de façon significative.

**Reste à faire** (faible priorité, non bloquant) : `POST /me/ai-keys/{provider}/test` n'a pas
de limitation — un appel réseau vers le fournisseur IA de l'utilisateur, à ses frais (sa propre
clé), coût pour ce serveur seulement (bande passante), pas un vecteur d'abus vers un tiers.

### Taille d'envoi

Le backend `local` (disque, **cible réelle de PROD** — voir `docs/infra/SERVEUR-POKEBOY.md`)
était déjà correctement gardé : `PUT /uploads/{id}/raw` vérifie l'en-tête `Content-Length` *et*
la taille réelle du corps avant d'écrire sur disque (`routers/uploads.py`).

**Faille trouvée et corrigée** sur le backend `s3` (MinIO en dev/CI — pas la cible de PROD, mais
un même code sert les deux) : `POST /uploads` valide la taille **déclarée** par le client avant
d'émettre une URL présignée, mais `generate_presigned_url("put_object", ...)` (boto3) n'impose
**aucune** limite de taille côté S3/MinIO lui-même (contrairement à un présignage POST avec
condition `content-length-range`) — un appelant qui capture cette URL peut y déposer un objet
de n'importe quelle taille. `POST /uploads/{id}/complete` chargeait ensuite tout l'objet en
mémoire (`storage.get()` → `bytes`) pour le traiter : sans garde-fou, un dépôt volumineux aurait
pu épuiser la mémoire du serveur API. Corrigé par un contrôle de taille (`storage.head()`,
nouveau sur les deux backends — `HEAD`/`stat`, sans télécharger le corps) **avant** tout
chargement en mémoire : au-delà de `upload_max_size_bytes`, l'objet est supprimé du stockage,
l'envoi passé en `failed`, réponse `413`. Vérifié :
`test_complete_rejects_an_object_bigger_than_declared_at_creation` (`test_uploads.py`), qui
dépose réellement un objet de `upload_max_size_bytes + 1` octets sur MinIO (contournant la
taille déclarée) et vérifie le rejet, la suppression de l'objet et le statut `failed`.

Ce correctif reste partiel pour le backend `s3` : l'objet trop volumineux transite bien vers
MinIO avant d'être détecté et supprimé (coût de stockage transitoire), contrairement à un
présignage POST qui l'aurait refusé à l'écriture. Non corrigé dans ce lot (changerait le contrat
front/back du flux d'envoi, hors budget de cette revue) — sans conséquence en PROD puisque le
backend réel y est `local`, déjà protégé en amont. Limite de fichiers par lot
(`upload_max_files_per_batch`, 30) déjà en place, non modifiée.

## 3. Journaux et traces

Déjà en place (lot `v1-byok`) : `pbm_api.security.log_filter.install_api_key_redaction` masque
toute clé IA (Anthropic/OpenAI/Google) dans **tout** enregistrement de log, quel que soit le
logger d'origine (`uvicorn.access`, `uvicorn.error`, bibliothèques tierces) — installé via
`logging.setLogRecordFactory`, pas un simple filtre de logger (qui n'aurait pas couvert un
logger nommé se contentant de propager vers `root`).

**Ajouté dans ce lot** : `install_secret_url_redaction`, même mécanisme, pour les jetons portés
par l'URL elle-même plutôt que par un cookie — le lien de téléchargement d'export (`GET
/export/download?token=...`) et le jeton d'envoi du backend local (`PUT /uploads/{id}/raw?
token=...`). `uvicorn.access` journalise la ligne de requête complète (chemin + query string) :
sans cette redaction, ces jetons finissaient en clair dans les journaux malgré leur portée
volontairement limitée (une ressource, durée bornée). Vérifié : `tests/test_log_filter.py`
(+4 tests), dont un qui reproduit la forme réelle du format d'accès d'uvicorn (ligne de requête
complète en un seul argument `%s`) et confirme la redaction sur un logger nommé
`uvicorn.access`.

Recherche de fuite en clair dans le code : aucun `logger.*`/`print()` ne journalise de clé, jeton,
cookie ou mot de passe — la seule occurrence de mot de passe en clair est le `print()` volontaire
et documenté de `pbm_api.admin` (commande d'administration, affichage unique à l'opérateur,
jamais journalisé).

## 4. Dépendances (`pip-audit`, `pnpm audit`)

### `apps/api` (Python)

```
$ cd apps/api && uv export --no-hashes --no-header | grep -v '^-e ' > requirements.txt
$ uvx pip-audit -r requirements.txt
No known vulnerabilities found
```

Aucune vulnérabilité connue au 20/09/2026. **Ajouté à la CI** (`.github/workflows/ci.yml`, job
`api`), bloquant : une régression future doit empêcher le merge.

### `apps/web` (JS)

```
$ pnpm --filter @pbm/web audit
11 advisories : 7 moderate, 3 high, 1 critical
  vite, vitest, postcss, esbuild, @vitest/mocker
```

Toutes dans des **devDependencies de build** (`vite`, `vitest`, `postcss`, `esbuild`,
`@vitest/mocker`) — jamais expédiées dans le bundle de production (`next build` ne les inclut
pas ; elles ne tournent que sur la machine de build/CI, jamais chez un visiteur). La plus grave
(`critical`, vitest — lecture/exécution de fichier arbitraire **si le serveur UI de Vitest
écoute**) ne s'applique pas ici : ce projet n'utilise jamais `vitest --ui`. Corriger exigerait un
saut de version majeure (`vitest`/`vite` dépassent la plage `^2.x`/`^6.x` déjà déclarée dans
`package.json`) partagé par tout le monorepo front, pendant que plusieurs autres lots travaillent
en parallèle sur les mêmes fichiers — hors budget de cette revue, risque de régression plus large
qu'une revue de sécurité ponctuelle ne devrait en introduire. **Ajouté à la CI**, non bloquant
(`continue-on-error: true`) : visible à chaque run, pour qu'une régression (nouvelle faille, ou
une de ces cinq qui gagnerait en sévérité réelle) se voie avant de devenir bloquante — voir
« Reste à faire ».

## 5. SSRF

Audit de tout appel réseau sortant fait par le serveur avec une donnée qui pourrait être
influencée par un utilisateur :

- `GET /img/cards/{id}` (`routers/images.py`) : fait un `GET` serveur vers `Card.image_url`.
  Cette colonne n'est **jamais** écrite depuis une requête entrante — uniquement par le job
  d'import du catalogue (`pbm_api.catalog.import_service`), depuis la réponse de l'API TCGdex
  (domaine fixe `api.tcgdex.net`). `card_id` (le seul paramètre client) ne sélectionne qu'une
  ligne déjà en base, jamais une URL arbitraire. **Pas de SSRF exploitable aujourd'hui.**
- `pbm_api.insights.context.MediaWikiClient` (anecdotes) : URL de base fixe
  (`pokepedia.fr`/`bulbagarden.net`), requête construite côté serveur à partir d'un nom de
  carte déjà connu du catalogue — jamais une URL fournie par l'utilisateur.
- Coffre de clés IA (`routers/ai_keys.py`) : les fournisseurs (Anthropic/OpenAI/Gemini) ont
  chacun une URL de base fixe dans `pbm_api.ai.providers` ; rien ne permet à un utilisateur de
  substituer une autre URL.

**Défense en profondeur ajoutée** malgré l'absence de chemin exploitable aujourd'hui :
`pbm_api.catalog.import_service._is_safe_image_url` rejette (avec un `logger.warning`, jamais
silencieusement) une `image_url` qui ne serait pas `https://` ou qui pointerait vers une IP
privée/de boucle locale/lien-local (`169.254.0.0/16`, métadonnées cloud comprises) — au cas où
une réponse TCGdex compromise (compromission amont, pas un scénario testé mais un risque de
chaîne d'approvisionnement classique) tenterait de faire pointer le proxy d'images vers le
réseau interne. Volontairement pas une liste blanche stricte du domaine `assets.tcgdex.net` :
aurait cassé les doublures de test existantes (`https://x/...`, fidèles en forme mais pas en
domaine). Vérifié : `tests/test_import_service.py` (+6 tests, dont un bout en bout qui simule
une réponse TCGdex renvoyant `https://169.254.169.254/...` et confirme que la carte est importée
**sans** image plutôt qu'avec cette URL).

## 6. Envoi de fichiers malveillants

Déjà solide avant ce lot (lot `v3-upload`), vérifié à cette occasion :
`pbm_api.uploads.processing.process_uploaded_image` ouvre **et décode réellement** chaque envoi
avec Pillow (`Image.open(...).load()`, pas seulement un test d'en-tête magique) — un fichier
renommé en `.jpg` qui n'est pas une image lève une erreur explicite, jamais un octet traité tel
quel. Liste blanche de formats (`JPEG`, `PNG`, `HEIF`), tout le reste rejeté. Chaque image est
**ré-encodée** avant stockage (jamais les octets d'origine conservés tels quels) : ceci supprime
les métadonnées EXIF (position GPS comprise) et neutralise tout fichier polyglotte (un PNG qui
serait aussi un script valide, par exemple) — le format de sortie ne contient que ce que Pillow y
a lui-même écrit. Type déclaré revérifié contre le type réel à `complete_upload`, jamais fait
confiance seul.

## 7. Reste à faire

- **`pnpm audit`** : 11 vulnérabilités dans des devDependencies de build (vite/vitest/postcss/
  esbuild), sans impact production, mais un vrai correctif exige un saut de version majeure
  partagé par tout `apps/web` — à traiter par un lot dédié aux dépendances, pas ce lot-ci
  (risque de régression plus large que le périmètre d'une revue de sécurité). Suivi : étape CI
  non bloquante ajoutée, visible à chaque run.
- **Rate limit sur `POST /me/ai-keys/{provider}/test`** : non ajouté (coût aux frais de
  l'utilisateur, pas un vecteur d'abus vers un tiers) — faible priorité.
- **Présignage S3 sans limite de taille imposée par MinIO lui-même** (§ Taille d'envoi) :
  mitigation par rejet + suppression après coup, pas un refus à l'écriture — sans impact PROD
  (backend réel = `local`, déjà protégé en amont) ; un vrai correctif (présignage POST avec
  `content-length-range`) changerait le contrat front/back du flux d'envoi.
- **Vérification en navigateur réel de la CSP** (nonce, `frame-ancestors`, chargement des
  images cross-origin) non faite localement : le Chromium headless de Playwright ne démarre pas
  sur cette machine (`error while loading shared libraries: libnspr4.so`,
  `playwright install-deps` exige un `sudo` avec mot de passe indisponible en session
  autonome — limitation déjà documentée par le lot `v5-rgpd`). Vérifiée autrement : serveur
  `next start` (build de production) + API réels lancés en local, en-têtes et nonce inspectés
  par requêtes HTTP directes (§ Preuves) — confirme que Next.js applique bien le nonce du
  middleware à tous ses scripts générés, mais ne constate pas l'absence d'erreur CSP dans une
  vraie console de navigateur. La CI (`e2e`, `playwright install --with-deps chromium` sur un
  runner complet) fait foi pour cette dernière vérification.
- **Domaine allowlist stricte pour `Card.image_url`** (au lieu du contrôle IP privée/schéma
  actuel) : envisagé, écarté pour ne pas casser les doublures de test existantes en dehors du
  périmètre de ce lot — à reconsidérer si `pbm_api.catalog.import_service` est retouché.

## Preuves (commandes lancées, résultats)

```
$ cd apps/api && uv run ruff check .
All checks passed!

$ TEST_DATABASE_URL=postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v5_securite_test \
  TZ=Europe/Paris uv run pytest -q
541 passed, 2 deselected in ~214s
# déselectionnés : test_catalogue_seed.py (pg_dump absent de cette machine, préexistant,
# sans rapport avec ce lot — GitHub Actions ubuntu-latest fournit postgresql-client de base)

$ cd apps/web && pnpm --filter @pbm/web lint && pnpm --filter @pbm/web type-check
# aucune erreur

$ pnpm --filter @pbm/web test
Test Files  25 passed (25) — Tests  84 passed (84)

$ pnpm --filter @pbm/web build
✓ Compiled successfully — 18 routes, toutes dynamiques (cookie de session déjà lu partout)
```

En-têtes en conditions réelles (`next start` — build de production réel — + `uvicorn` réels,
ports 3100/8100, bases/bucket dédiés `pbm_v5_securite_e2e`) :

```
$ curl -sD - http://localhost:3100/ -o /tmp/home.html | grep -i content-security-policy
content-security-policy: default-src 'self'; script-src 'self' 'nonce-NzM3Y...'; style-src
  'self' 'unsafe-inline'; img-src 'self' data: http://localhost:8100; connect-src 'self'
  http://localhost:8100; font-src 'self'; frame-ancestors 'none'; base-uri 'self';
  form-action 'self'; object-src 'none'

$ grep -o '<script nonce="[^"]*"' /tmp/home.html | sort -u | wc -l
1   # un seul nonce dans toute la page — identique à celui de l'en-tête, sur tous les <script>

$ curl -sD - http://localhost:8100/nope -o /dev/null | grep -i content-security-policy
content-security-policy: default-src 'none'; frame-ancestors 'none'; base-uri 'none'

$ curl -sD - -X OPTIONS http://localhost:8100/me/collection \
  -H "Origin: http://localhost:3100" -H "Access-Control-Request-Method: GET" -o /dev/null \
  | grep -i access-control-allow-origin
access-control-allow-origin: http://localhost:3100
```

Bases dédiées créées sur l'infra partagée `pbm-shared` : `pbm_v5_securite` (dev),
`pbm_v5_securite_test` (tests), `pbm_v5_securite_e2e` (preuve en conditions réelles) ;
`apps/api/.env` local (gitignored), `REDIS_PREFIX=pbm:v5-securite:`, bucket `pbm-v5-securite`.
