# CLAUDE.md — PokeBoyManager

## Ce qu'est le projet
Espace privé (compte e-mail + mot de passe) : photos de cartes Pokémon → reconnaissance par l'IA
**de l'utilisateur** (clé Claude, Gemini ou OpenAI déposée dans son profil) → collection filtrable,
valeur dans le temps, fiche carte (image officielle, état estimé, anecdotes sourcées, étude en jeu).

## Le plan fait foi
- `docs/roadmap/roadmap.json` : le plan (lots, dépendances, décisions). Seule source.
- `docs/roadmap/etat.json` : l'état réel, écrit **uniquement** par `docs/roadmap/suivi.py`.
- `BACKLOG.md`, `prompts/*.md`, `docs/roadmap/ROADMAP.html` sont **générés** (`python3 docs/roadmap/suivi.py build`) — ne jamais les éditer à la main.
- Chaque lot démarre par `suivi.py verifier <id>` : code 2 = ordre non tenu → on s'arrête et on demande à JF.

## Règles
- Un lot = un worktree `../wt-<id>`, une branche `roadmap/<id>`, une PR. Jamais `git stash`, jamais `git add -A`.
- Python **3.12** (`UV_PYTHON=3.12`), Node 24. La CI GitHub Actions fait foi.
- Toute route utilisateur filtre par `user_id` issu de la session ; test d'accès croisé obligatoire.
- Les clés IA ne sont **jamais** renvoyées, journalisées ni écrites en clair (chiffrement AES-256-GCM, clé maître hors base).
- Aucun secret dans le dépôt (`.env` ignoré, `.env.example` sans valeur réelle).
- Le front reproduit la maquette (onglet « Maquette du site » de `ROADMAP.html`) ; identité propre, pas de logo officiel Pokémon.
- Construire sur chimera, déployer par devAI ; jamais de build ni de déploiement depuis le Mac de JF.
- Un repli silencieux (`|| true`, `except: pass`, `2>/dev/null` sur un chemin nominal) est interdit : un relevé de prix vide ou un lot sans compte rendu est une panne.

## Monorepo — structure et commandes

```
apps/web            Next.js 15 (App Router), TypeScript strict, Tailwind 4, ESLint, Vitest
apps/api             FastAPI, Python 3.12, uv, ruff, pytest — /health
packages/api-client  Client TypeScript généré depuis l'OpenAPI de apps/api (openapi-typescript)
infra/postgres/init  Scripts d'initialisation (extensions pg_trgm, unaccent)
docker-compose.yml   Postgres 16, Redis 7, MinIO, Mailpit — ports par défaut = infra partagée de la flotte
```

Versions épinglées : Node 24, pnpm 12.4.2 (`packageManager` dans `package.json`), Python 3.12,
uv (voir `uv.lock` dans `apps/api`) ; images Docker à tag majeur fixe (`postgres:16-alpine`,
`redis:7-alpine`).

```bash
# Infra locale (Postgres, Redis, MinIO, Mailpit)
cp .env.example .env   # optionnel : les valeurs par défaut suffisent
docker compose up -d
docker compose down -v # arrêt + purge des volumes

# Front — apps/web
pnpm install
pnpm --filter @pbm/web dev          # http://localhost:3000
pnpm --filter @pbm/web lint
pnpm --filter @pbm/web type-check
pnpm --filter @pbm/web test
pnpm --filter @pbm/web build

# API — apps/api
cd apps/api
uv sync
uv run uvicorn pbm_api.main:app --reload   # http://localhost:8000/health
uv run ruff check .
uv run pytest -q

# Client TypeScript généré depuis l'OpenAPI (à relancer après tout changement de schéma API)
pnpm gen:api
```

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
déploiement).
Chaque lot pointe sa propre base/bucket/préfixe — ne jamais réutiliser ceux d'un autre lot sur
l'infra partagée (`pbm-shared`). `apps/web` lit `NEXT_PUBLIC_API_URL` (défaut
`http://localhost:8000`) et `NEXT_PUBLIC_SESSION_COOKIE_NAME` (défaut `pbm_session`, doit
rester alignée avec `SESSION_COOKIE_NAME` côté API : le middleware de garde de route ne lit que
la présence de ce cookie, `apps/web/src/middleware.ts`). `apps/api` accepte les requêtes
cross-origin du front (`CORSMiddleware`, origine = `APP_PUBLIC_URL`, `allow_credentials=True`
pour le cookie de session) — obligatoire dès qu'ils tournent sur des ports/domaines différents.

Pages d'authentification (lot `v1-pages-auth`) : `/inscription`, `/connexion`,
`/mot-de-passe-oublie`, `/verifier?token=…`, `/reinitialiser?token=…` — ces deux derniers
chemins doivent rester alignés avec les liens envoyés par e-mail
(`pbm_api.auth.service.register_user`/`request_password_reset`). e2e Playwright du parcours
inscription → vérification → connexion : `apps/web/e2e/auth.spec.ts` (`pnpm --filter @pbm/web
test:e2e`, nécessite Mailpit ; navigateurs déjà en cache sur chimera).

## Coffre de clés IA (lot `v1-byok`)

Routes (`apps/api/src/pbm_api/routers/ai_keys.py`) : `GET/PUT/DELETE /me/ai-keys[/{provider}]`,
`POST /me/ai-keys/{provider}/test`, `GET/PATCH /me/ai-settings`, `GET /me/ai-usage`. Chiffrement
AES-256-GCM (`pbm_api.security.crypto`, `user_id` en données associées) ; filtre anti-fuite de
clé dans les journaux (`pbm_api.security.log_filter`, installé au démarrage) et dans les
réponses 422 de validation (`pbm_api.security.validation_errors` — le comportement par défaut
de FastAPI renverrait sinon la valeur soumise en clair sur une clé trop courte/longue). Le test
d'une clé
appelle réellement le fournisseur (liste de modèles, coût nul) via `pbm_api.ai.providers.
ProviderKeyTester`, injecté par dépendance FastAPI — remplacé par un double dans les tests
(aucune clé IA réelle disponible sur chimera) ; essai manuel avec une vraie clé :
`uv run python scripts/test_ai_key_manual.py <provider> <clé>` depuis `apps/api`.

## Fournisseurs IA (lot `v3-ia-providers`)

Interface unique `AIProvider.extract(images, schema, prompt) -> (objet validé, usage)`
(`apps/api/src/pbm_api/ai/base.py`) — implémentations `AnthropicProvider`/`OpenAiProvider`/
`GeminiProvider` (`apps/api/src/pbm_api/ai/`), fabriquées par `pbm_api.ai.factory.
create_provider(provider, api_key)`. Sortie structurée native par fournisseur + validation
Pydantic (schéma traduit par `pbm_api.ai.json_schema`, `$ref` repliés) ; une nouvelle tentative
guidée si le JSON ne valide pas. Erreurs normalisées (`pbm_api.ai.errors` :
`InvalidApiKeyError`/`QuotaExceededError`/`ProviderOverloadedError`/`ProviderUnreachableError`/
`ContentRefusedError`), chacune avec un `user_message` prêt à consigner sur un `Job`. Détail :
`docs/ARCHITECTURE.md` § « Fournisseurs IA ». Tests sur réponses enregistrées
(`apps/api/tests/test_ai_providers.py`, `httpx.MockTransport`, aucune clé réelle sur chimera) ;
essai manuel avec une vraie clé : `uv run python scripts/test_ai_extraction_manual.py <provider>
<clé>` depuis `apps/api`.

## Détection de cartes (lot `v3-detection`)

Pipeline `pbm_api.detection.pipeline.run_detection` : contours OpenCV (`opencv_pipeline.py`,
ratio 63×88 mm) + redressement perspective (`geometry.py`, recadrage fixe 630×880) ; repli par
boîtes englobantes demandées au LLM (`llm_fallback.py`, un seul appel par photo) quand
`has_unclaimed_regions` signale une zone de la taille d'une carte non rattachée à un
quadrilatère retenu, affinées ensuite par le même OpenCV dans chaque boîte. Orchestration
DB/stockage (`detection/service.py`) déclenchée par `pbm_api.worker.detect_cards_task`, mis en
file depuis `POST /uploads/{id}/complete` via `pbm_api.queue.get_arq_pool` — **premier job du
dépôt enfilé depuis une route HTTP** (les autres jobs `arq` du dépôt sont en cron ou CLI direct).
Résultat consultable par `GET /uploads/{id}/detections` et `.../detections/{id}/crop`
(`routers/uploads.py`), bornés au propriétaire de l'envoi. Jeu de test : 30 photos
**synthétiques** (`pbm_api.detection.synthetic` — aucun appareil photo/carte physique sur
chimera) ; mise au point : `uv run python scripts/measure_detection_rate.py [--provider <p>
--api-key <clé>]` depuis `apps/api`, écrit une image annotée de contrôle par photo. Détail :
`docs/ARCHITECTURE.md` § « Reconnaissance ».

## Export et suppression RGPD (lot `v5-rgpd`)

Routes (`apps/api/src/pbm_api/routers/export.py`) : `POST /me/export` (session + CSRF) crée le
`DataExport` et l'enfile vers le worker (`pbm_api.queue.get_arq_pool`, même schéma que
`detect_cards_task` ci-dessus — `export_user_data_task` fait le travail réel), `GET
/me/export/{id}` (statut), `GET /export/download?token=…` (sans session, jeton opaque valable
24 h envoyé par e-mail — comme un jeton d'e-mail de `v1-auth`, jamais un cookie). Le ZIP
(`pbm_api.export.archive`) contient `profil.json`, `collection.json`, `collection.csv` et
`photos/` (exemplaires avec `photo_s3_key`) ; aucune clé IA n'y figure jamais (elles ne sont de
toute façon jamais déchiffrables hors de leur usage fournisseur). La suppression de compte
(`pbm_api.profile.service.delete_account`, posée par `v1-profil`) purge désormais aussi les
objets de stockage (photos de collection, envois, recadrages de détection, archives d'export)
avant le `DELETE` en cascade — pas seulement l'avatar.

## Identification des cartes (lot `v3-identification`)

Chaîné dans le même job `detect_cards` que la détection (`pbm_api.identification.service.
run_identification_for_upload`, appelé par `pbm_api.worker.detect_cards_task` juste après
`run_detection_for_upload`) — jamais un second aller-retour par la file. Pour chaque `Detection`
en attente : empreinte perceptuelle du recadrage (aHash 64 bits, `pbm_api.identification.
fingerprint.compute_phash`) ; touchée dans `identification_cache` (distance de Hamming ≤ 6,
`pbm_api.identification.cache`, cache partagé entre utilisateurs comme `card_insights`), le
résultat est réutilisé sans appel IA ; sinon un appel `AIProvider.extract`
(`pbm_api.identification.extraction.extract_card`, schéma `CardExtraction` — nom, numéro, total,
code d'extension, langue, PV, type, variante, confiance par champ) puis rapprochement catalogue
(`pbm_api.identification.reconciliation.reconcile` : numéro + extension exacts, sinon numéro +
nom, sinon recherche floue sur le nom seul, en réutilisant `pbm_api.catalog.search.
match_candidates` tel quel) — top 3 avec score combiné (score catalogue × confiance moyenne),
présélection au-delà de 0,9. Résultat écrit sur `Detection.extraction`/`Detection.candidates`,
exposé par `GET /uploads/{id}/detections`. Comparaison visuelle recadrage/image officielle
(second appel IA par carte) non implémentée : contredirait le principe « un seul appel IA par
carte, dès le premier tir ». Jeu de 100 cartes étiquetées et mesure de précision : `uv run
pytest tests/test_identification_synthetic_dataset.py` (fait foi, CI) ou `uv run python
scripts/measure_identification_rate.py` (mise au point, `report.json`) ; essai manuel avec une
vraie clé : `uv run python scripts/test_identification_manual.py <provider> <clé>` depuis
`apps/api`. Détail : `docs/ARCHITECTURE.md` § « Reconnaissance ».

## État estimé de l'exemplaire (lot `v3-etat`)

Chaîné après l'identification dans le même job `detect_cards`
(`pbm_api.state.service.run_state_estimation_for_upload`, appelé par
`pbm_api.worker.detect_cards_task` juste après `run_identification_for_upload`) — jamais un job
ni un appel IA de plus. Deux sources combinées en un palier global (le plus sévère l'emporte,
`pbm_api.state.grades.worst_grade`) : centrage mesuré par OpenCV sur le recadrage déjà en
stockage (`pbm_api.state.centering`, sans clé IA requise, `None` plutôt qu'une mesure inventée
sans bordure distincte) ; coins/bords/surface demandés à l'IA dans le même appel que
l'identification (`CardExtraction.corner_wear`/`edge_wear`/`surface_wear`, `pbm_api.
identification.extraction`). Palier mappé sur l'abréviation Cardmarket et une note /10 dérivée de
`pbm_api.pricing.valuation.CONDITION_MULTIPLIERS` (même barème que la décote de valeur). Résultat
sur `Detection.condition_assessment`, exposé par `GET /uploads/{id}/detections`. Contrefaçon
probable (`pbm_api.state.counterfeit`) : signal IA + contrôle déterministe (carte « gold » perçue
mais rareté catalogue non confirmée) ; `CollectionItem.counterfeit_suspected` neutralise la
valeur à zéro dans `pbm_api.pricing.valuation.item_value`. Mise au point centrage : `uv run
python scripts/measure_centering_rate.py` depuis `apps/api` (jeu synthétique dédié,
`pbm_api.state.synthetic` — aucune carte physique sur chimera). Détail :
`docs/ARCHITECTURE.md` § « Reconnaissance ».

## Identité du compte (lot `v1-identite`)

`users` porte prénom (facultatif), nom, date de naissance, version/horodatage des conditions
acceptées et `must_change_password`. Validations dans `pbm_api.auth.service` (inscription) et
`pbm_api.profile.service` (`PATCH /me`) : date de naissance passée, conditions obligatoires, âge
minimum 15 ans réservé à l'inscription libre (RGPD art. 8) — contournable seulement par la
commande d'administration (consentement du parent porté par JF) :
```
uv run python -m pbm_api.admin create-user --email … --pseudo … --last-name … \
  --birth-date AAAA-MM-JJ --accept-terms [--password-stdin] [--must-change-password]
```
Mot de passe lu sur l'entrée standard ou généré et affiché une seule fois — jamais en argument ni
journalisé. Détail : `docs/ARCHITECTURE.md` § « Identité du compte ».

## Écran de validation (lot `v3-validation`)

Routes (`apps/api/src/pbm_api/routers/uploads.py`, `routers/detections.py`) : `GET
/uploads/{id}` (état de l'envoi + job de reconnaissance le plus récent + détections — chargement
initial de l'écran), `GET /uploads/{id}/events` (flux SSE, `event: snapshot` à chaque changement
détecté par sondage puis `event: done`/`timeout` en fin de job), `POST
/detections/{id}/confirm`/`/reject`, `POST /uploads/{id}/confirm-all`. `Upload.status` ne reflète
que le traitement de la photo brute (EXIF, HEIC), pas la reconnaissance : la progression réelle
vient du `Job` (`type="detect_cards"`) le plus récent pour cet envoi
(`pbm_api.uploads.service.get_latest_recognition_job`). `pbm_api.detection.service` et
`pbm_api.identification.service` commitent désormais une détection à la fois (pas un seul commit
en fin de job) pour que le flux SSE voie une progression réelle et qu'un job interrompu (clé
épuisée) garde les cartes déjà traitées.

`confirm` crée `quantity` `CollectionItem` (une ligne par exemplaire, `CollectionItem` n'a pas de
colonne quantité) et écrit une `IdentificationCorrection` (`pbm_api.models.identification`) :
candidat proposé (premier de `Detection.candidates`, `None` si aucun) contre celui réellement
retenu (`None` = rejetée) — le jeu de régression de l'identification, jamais consulté par le
produit lui-même. `confirm-all` (« Tout ajouter ») n'agit que sur les détections dont le premier
candidat est présélectionné (`preselected`, score > `PRESELECTION_THRESHOLD` — voir
`pbm_api.identification.reconciliation`), langue "fr"/variante normale/un exemplaire par défaut ;
le reste reste `pending`, jamais ajouté sans qu'un candidat se soit démarqué même implicitement.

Front (`apps/web/src/app/ajouter/validation/`) : un envoi peut regrouper plusieurs photos (donc
plusieurs `upload_id`, l'API n'ayant pas de notion de lot) — `upload-view.tsx` redirige vers
`/ajouter/validation?uploads=<id1>,<id2>,…` après l'envoi, la liste des détections de tous les
envois est fusionnée côté client et triée par ordre de lecture. Raccourcis clavier (mission point
2) : Entrée valide la détection active (premier `pending` de la liste), 1/2/3 changent son
candidat sélectionné — désactivés quand le focus est dans un champ de saisie. Recherche manuelle :
réutilise `GET /catalog/search` tel quel (`pbm_api.routers.catalog`, lot `v2-recherche`).

Rebasé sur `v3-etat`/`v1-identite` (fusionnés dans `origin/main` pendant cette session) :
`Detection.condition_assessment` (état estimé + contrefaçon, un seul appel IA partagé avec
l'identification) existe désormais — la carte de validation affiche l'état estimé et un badge
« contrefaçon probable » quand il est présent, pré-remplit (sans l'imposer) le champ « État »
manuel. `confirm`/`confirm-all` reprennent le drapeau `counterfeit_suspected` de la détection sur
le `CollectionItem` créé (`pbm_api.validation.service._counterfeit_suspected`) — sans ça, une
contrefaçon probable aurait été valorisée comme l'originale
(`pbm_api.pricing.valuation.item_value`).

Tests : `apps/api/tests/test_validation_routes.py` (confirm/reject/confirm-all, flux SSE, accès
croisé) — le worker arq n'étant pas démarré pendant les tests, `_simulate_worker` reproduit
`worker._run_detect_cards` (détection puis identification directement, `Job.status` transité à la
main). e2e Playwright de conformité à la maquette :
`apps/web/e2e/validation.spec.ts` — aucune clé IA réelle disponible sur chimera, l'envoi
« déjà identifié » est semé directement en base par `apps/api/scripts/seed_validation_e2e.py`
(même forme que `_simulate_worker`) ; seul l'écran de validation est exercé par le navigateur, pas
le pipeline de reconnaissance réel.

## Règles de la flotte applicables ici (résumé de `~/.claude/CLAUDE.md`)

- On construit sur chimera (32 Go, 16 threads) et on ne construit jamais sur la machine qui sert.
- Le réseau de chimera plafonne à ~250 Ko/s : éviter les téléchargements/images Docker inutiles.
- Session autonome (`claude -p`) : jamais de `git stash`, jamais `git add -A`, commits ciblés,
  compte rendu obligatoire même en cas d'échec ou de blocage.
