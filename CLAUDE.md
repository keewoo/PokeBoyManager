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
exposé par `GET /uploads/{id}/detections`. Jeu de 100 cartes étiquetées et mesure de précision :
`uv run pytest tests/test_identification_synthetic_dataset.py` (fait foi, CI) ou `uv run python
scripts/measure_identification_rate.py` (mise au point, `report.json`) ; essai manuel avec une
vraie clé : `uv run python scripts/test_identification_manual.py <provider> <clé>` depuis
`apps/api`. Détail : `docs/ARCHITECTURE.md` § « Reconnaissance ».

## Comparaison visuelle (lot `v3-identification-visuelle`)

Insérée entre le cache d'empreinte ci-dessus et l'appel IA, dans `pbm_api.identification.
service._identify_one` : chaque recadrage est comparé à l'index des images officielles de toutes
les cartes (table `card_visual_index` — `full_phash`/`illustration_phash`, aHash 64 bits sur
l'image entière et sur sa seule zone d'illustration, `pbm_api.identification.visual_geometry`) ;
`pbm_api.identification.visual_index.VisualIndex` charge l'index en mémoire (numpy) une fois par
envoi, jamais par carte — recherche par XOR + comptage de bits vectorisé, pas en SQL (volume visé
~20 000 cartes × 2 langues, largement au-delà de ce que `identification_cache` documente comme
acceptable en scan SQL). Une correspondance confiante (`resolve`, `CONFIDENT_SCORE_THRESHOLD` =
0,85, sans concurrent d'une autre carte à moins d'`AMBIGUITY_MARGIN` = 0,06) identifie la carte
**sans aucun appel IA**, y compris sans clé configurée (D4) : les champs viennent directement du
catalogue (`pbm_api.identification.visual_resolve.build_confident_extraction`, confiance 1,0,
jamais repassés par le rapprochement flou), `Detection.identification_method = "visuel"` (colonne
posée par ce lot, comme `IdentificationCache.method`) — sert au badge « reconnue sans IA » de
l'écran de validation (`apps/web/src/app/ajouter/validation/detection-card.tsx`). Un groupe
« même illustration » (réimpression/reverse/promo) n'est jamais tranché par la seule comparaison
visuelle (pas d'OCR local disponible sur chimera — ni `tesseract` ni `sudo apt` sur cette
session, voir le compte rendu) : ses candidats sont injectés dans le prompt du **même** appel
`AIProvider.extract` (`pbm_api.identification.extraction.extract_card(..., visual_hints=...)`),
ou laissés à la validation humaine sans clé IA (`identification_method = "aucun"`, candidats tout
de même exposés). Construction de l'index (hors serveur de PROD) : `uv run python
scripts/build_visual_index.py [--limit N] [--languages fr,en]` — télécharge l'image officielle
basse définition par carte × langue (déduction d'URL par langue, `pbm_api.identification.
visual_build.image_url_for_language`), la met aussi en cache dans le stockage objet
(`cards/{id}/{langue}/low.webp`, réutilisée par le proxy `/img/cards/{id}`), idempotent et
reprenable (une carte déjà indexée est sautée). Mesure sur jeu synthétique (images procédurales,
`pbm_api.identification.visual_synthetic` — même contrainte qu'ailleurs, aucune vraie
photo/carte) : `uv run pytest tests/test_visual_identification_synthetic_dataset.py` (fait foi,
CI, objectif ≥ 60 % reconnu sans IA) ou `uv run python
scripts/measure_visual_identification_rate.py` (mise au point, `report.json`) ; performance/
mémoire à l'échelle de production (empreintes aléatoires, pas besoin d'images réelles) : `uv run
python scripts/measure_visual_index_performance.py`. Détail : `docs/ARCHITECTURE.md` §
« Reconnaissance ».

## État estimé de l'exemplaire (lot `v3-etat`)

Chaîné après l'identification dans le même job `detect_cards`
(`pbm_api.state.service.run_state_estimation_for_upload`, appelé par
`pbm_api.worker.detect_cards_task` juste après `run_identification_for_upload`) — jamais un job
ni un appel IA de plus. Deux sources combinées en un palier global (le plus sévère l'emporte,
`pbm_api.state.grades.worst_grade`) : centrage mesuré par OpenCV sur le recadrage déjà en
stockage (`pbm_api.state.centering`, sans clé IA requise, `None` plutôt qu'une mesure inventée
sans bordure distincte) ; coins/bords/surface demandés à l'IA dans le même appel que
l'identification (`CardExtraction.corner_wear`/`edge_wear`/`surface_wear`, `pbm_api.
identification.extraction`) — `None` (jamais inventés) quand la carte a été reconnue par le seul
index visuel (lot `v3-identification-visuelle`, `identification_method = "visuel"`, aucun appel
IA fait) : l'état global retombe alors sur le centrage seul, `worst_grade` ignore les paliers
absents. Palier mappé sur l'abréviation Cardmarket et une note /10 dérivée de
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

Étendu par `v3-identification-visuelle` : `detection-card.tsx` affiche un badge « reconnue sans
IA » quand `Detection.identification_method === "visuel"` (comparaison à l'index visuel des
images officielles, aucun appel IA) — même emplacement que les badges statut/contrefaçon
existants, aucun autre changement d'écran.

Tests : `apps/api/tests/test_validation_routes.py` (confirm/reject/confirm-all, flux SSE, accès
croisé) — le worker arq n'étant pas démarré pendant les tests, `_simulate_worker` reproduit
`worker._run_detect_cards` (détection puis identification directement, `Job.status` transité à la
main). e2e Playwright de conformité à la maquette :
`apps/web/e2e/validation.spec.ts` — aucune clé IA réelle disponible sur chimera, l'envoi
« déjà identifié » est semé directement en base par `apps/api/scripts/seed_validation_e2e.py`
(même forme que `_simulate_worker`) ; seul l'écran de validation est exercé par le navigateur, pas
le pipeline de reconnaissance réel.

## Insights par lots (lot `v4-insights-batch`)

Pré-génération, pour TOUTE carte du catalogue, de ce que `v4-anecdotes`/`v4-jeu` généraient
jusqu'ici à la demande (« autant tout prendre dès le premier tir », JF 19/09) — un seul appel
Anthropic par carte (Message Batches API, -50 %, `pbm_api.insights_batch.anthropic_batches`)
rend ensemble anecdotes sourcées FR + EN et étude en jeu (`pbm_api.insights_batch.
combined_generation.CombinedCardInsightExtraction`), écrit dans le même `card_insights` que les
routes à la demande — celles-ci deviennent un repli automatique pour une carte pas encore
couverte (leur logique de cache existante suffit, aucun changement côté `v4-anecdotes`/`v4-jeu`).
Anecdotes EN dans une colonne dédiée `card_insights.anecdotes_en` (même forme que `anecdotes`) :
mélanger les deux langues dans la liste déjà exposée par `GET /cards/{id}/insights` aurait fait
apparaître du texte anglais sans prévenir sur un produit francophone ; non exposée par une route
pour l'instant.

Orchestration (`pbm_api.insights_batch.runner.run_once`, appelé par
`scripts/run_insights_batch.py`, jamais depuis une route HTTP) : sélection idempotente (une
carte sans `CardInsight`, ou dont les anecdotes ou l'étude en jeu manquent encore, reste
candidate — jamais de re-dépense sur une fiche déjà utilisable), soumission d'un lot Anthropic
borné par `INSIGHTS_BATCH_CHUNK_SIZE` (défaut 100, très en-deçà de la limite réelle de 100 000
requêtes/256 Mo), sondage puis application idempotente des résultats. Clé **plateforme**
(`PLATFORM_ANTHROPIC_API_KEY`, jamais une clé d'`ai_credentials`) et budget cumulé
(`INSIGHTS_BUDGET_EUR`) lus depuis `pbm_api.config.Settings` — absents par défaut (dev),
`run_once` refuse alors de dépenser quoi que ce soit plutôt que de se replier silencieusement ;
D4 : à fournir par JF hors dépôt avant tout passage réel. Coût réel converti en EUR via
`pbm_api.pricing.exchange_rates` (même taux BCE que `v2-prix`) — un taux manquant bloque la
soumission (jamais un coût traité comme gratuit). Reprise : `var/insights_batch/ledger.json`
(non versionné) porte la dépense cumulée et le lot Anthropic en cours ; un script interrompu
entre soumission et récupération reprend ce même lot au lieu d'en resoumettre un second.

Tarifs (`pbm_api.insights_batch.pricing`, vérifiés le 20/09/2026 sur claude.com/pricing +
platform.claude.com/docs/en/build-with-claude/batch-processing, déjà remisés -50 % Batch) :
Haiku 4.5 (modèle par défaut du lot, le moins cher) 0,50 $/2,50 $ le Mtok entrée/sortie,
Sonnet 5 1 $/5 $. Mesure sur 100 cartes représentatives : `uv run python
scripts/measure_insights_batch_cost.py` (contexte wiki réel, `run_once(dry_run=True)` — aucun
appel Anthropic réel possible sur chimera, D4 ; coût ESTIMÉ par une heuristique
caractères/jeton documentée dans `pbm_api.insights_batch.runner`, jamais facturé) ; `--live`
relance ce même script pour la mesure réelle dès que la clé plateforme existera. User-Agent
identifié ajouté à `pbm_api.insights.context.MediaWikiClient` (risque « débit raisonnable » de
ce lot) — profite aussi à la collecte à la demande de `v4-anecdotes`, qui partage la classe.

Tests : `apps/api/tests/test_insights_batch_runner.py` (orchestration bout en bout, budget,
reprise, rejet d'anecdote hors contexte, idempotence — réponses enregistrées, aucune clé IA
réelle), `test_insights_batch_anthropic_client.py` (client Message Batches, réponses
enregistrées), `test_insights_batch_pricing.py`, `test_insights_batch_combined_generation.py`.
Pas de route HTTP dans ce lot (script/cron interne) : aucun test d'accès croisé utilisateur
propre à ajouter, `card_insights` reste le même cache partagé sans notion de propriétaire déjà
couvert par les tests de `v4-anecdotes`/`v4-jeu`.

## Page collection (lot `v4-collection`)

`GET /me/collection` (`pbm_api.collection.service.list_collection`) : filtres extension
(`set_id`)/série/rareté/type/langue/variante/état/valeur min-max/date d'ajout (`acquired_from`/
`acquired_to`)/doublons/contrefaçons, tri (`sort`, valeur/variation 30 j/date d'ajout/numéro/nom),
pagination par curseur (`cursor`, opaque — id du dernier exemplaire de la page), agrégats (nombre,
valeur totale, variation 7/30 j). `GET /me/collection/facets` (valeurs de filtre, scopées à
l'utilisateur — jamais le catalogue entier). `POST /me/collection` (ajout manuel, `card_id` +
quantité, réutilise `GET /catalog/search`, aucun `Detection`/`photo_s3_key`). `PATCH`/`DELETE
/me/collection/{item_id}` (`PATCH` partiel : seuls les champs envoyés changent).

Valeur calculée à la demande pour chaque exemplaire (comme `pricing.valuation.item_value`),
jamais stockée : `list_collection` charge en une requête le sous-ensemble filtré par les critères
« bon marché » (catalogue, langue, variante, état, dates, colonnes explicites — jamais les
entités ORM `Card`/`Set` complètes, coûteuses à 5 000 lignes à cause de leurs colonnes JSONB),
valorise ce sous-ensemble par lots (`pricing.valuation.bulk_item_values_multi` — une requête de
prix `UNION ALL`/`DISTINCT ON` pour les 3 dates de référence à la fois, aujourd'hui/-7 j/-30 j,
jamais une requête par exemplaire ni par fenêtre), puis applique le filtre de valeur, le tri et
la pagination en mémoire (mission point 4 : 5 000 exemplaires en moins de 300 ms — mesuré,
`scripts/measure_collection_performance.py`). `collection_value` (`v4-ranking`) réutilise
désormais ce même chemin (corrige le N+1 qu'il portait depuis `v2-prix`).

Doublon = même `card_id` (toutes langues/variantes confondues) présent au moins deux fois dans
la collection entière de l'utilisateur, jamais recalculé sur un sous-ensemble filtré. `value_eur`
neutralisée à `0` pour un exemplaire signalé contrefaçon probable, `value_change_30d_pct` calculé
serveur (`None` si la référence 30 j est inconnue ou nulle) pour rejoindre le composant partagé
`apps/web/src/components/value-delta.tsx` (seule forme montrée par la maquette).
`rarity-badge.tsx`/`condition-badge.tsx` (même composant partagé) ne sont **pas** réutilisés ici :
leurs taxonomies fixes ne correspondent ni aux libellés bruts du catalogue TCGdex
(`Card.rarity`) ni au barème `pricing.valuation.CONDITION_MULTIPLIERS` — les forcer aurait
affiché des libellés inexacts (voir `docs/roadmap/comptes-rendus/v4-collection.md`).

Front `apps/web/src/app/collection/` : panneau de filtres (tiroir sur mobile), recherche + tri,
état entièrement dans l'URL (partageable, retour arrière du navigateur fonctionnel), pagination
« Charger plus » (curseur en état de composant, pas dans l'URL). Tests :
`apps/api/tests/test_collection_routes.py` (accès croisé compris),
`apps/web/src/__tests__/collection-view.test.tsx`.

## Accueil connecté (lot `v4-dashboard`)

`apps/web/src/app/page.tsx` (Server Component) lit le cookie de session (`cookies()`, jamais un
état client après montage — évite un flash de l'accueil visiteur) et bascule vers `HomeContent`
(`apps/web/src/app/home-content.tsx`, isolé du Server Component pour rester testable hors
runtime Next.js) : `DashboardView` avec session, `LandingPage`
(`apps/web/src/components/landing/`, extraite sans changement de l'ancien contenu de `page.tsx`)
sinon. `GET /me/dashboard` (`pbm_api.dashboard.service.get_dashboard`, appelé par
`routers/dashboard.py`) réutilise tel quel `pricing.valuation.bulk_item_values_multi`
(`v4-collection`) : une seule valorisation en masse couvre à la fois la valeur du jour, les
points de la courbe et la référence 30 jours — jamais une requête de prix par exemplaire ni par
date. Courbe sur 90 jours avec un point tous les 7 jours (`HISTORY_POINT_INTERVAL_DAYS`) plutôt
qu'un par jour : `bulk_item_values_multi` fait un `UNION ALL` d'une sous-requête par date
demandée, 90 dates multiplieraient le coût par 90 pour un agrément visuel qu'une dizaine de
points suffit à donner (job lourd = job bridé, `~/.claude/CLAUDE.md`). Plus fortes variations
triées par montant absolu (mouvements à variation nulle exclus) ; cinq derniers ajouts par
`created_at`.

`apps/web/src/components/dashboard/total-value-delta.tsx` (montant en euros signé, ▲/▼/=) est
**distinct** de `value-delta.tsx` (`v4-collection`, pourcentage) : l'agrégat de tête de la
maquette (« ▲ +42,50 € sur 30 j ») n'est pas la même donnée, pas le même composant à réutiliser
tel quel. Courbe : `value-chart.tsx` (Recharts `LineChart`/`ResponsiveContainer`, ajouté à
`package.json` — déjà dans la stack cible de `docs/roadmap/ROADMAP.html`) ; rien affiché en
dessous de 2 points (le montant du dessus porte déjà l'information, un graphe à un seul point
serait trompeur). `vitest.setup.ts` polyfill `ResizeObserver` (absent de jsdom,
`ResponsiveContainer` en a besoin). Tests : `apps/api/tests/test_dashboard_routes.py` (accès
croisé compris), `apps/web/src/__tests__/dashboard-view.test.tsx`,
`apps/web/src/__tests__/home-content.test.tsx`. Détail, capture de conformité maquette et écarts
connus (en-tête `AppShell` non sensible à la session, images de carte bloquées par ORB — tous
deux préexistants, hors périmètre de ce lot) :
`docs/roadmap/comptes-rendus/v4-dashboard.md`.

## Règles de la flotte applicables ici (résumé de `~/.claude/CLAUDE.md`)

- On construit sur chimera (32 Go, 16 threads) et on ne construit jamais sur la machine qui sert.
- Le réseau de chimera plafonne à ~250 Ko/s : éviter les téléchargements/images Docker inutiles.
- Session autonome (`claude -p`) : jamais de `git stash`, jamais `git add -A`, commits ciblés,
  compte rendu obligatoire même en cas d'échec ou de blocage.
