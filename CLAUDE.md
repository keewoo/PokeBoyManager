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
- **Traitements lourds sur la flotte, jamais sur la machine qui sert** (relevé de prix, import du catalogue, génération par lots, relevé de tournoi) : ils tournent sur chimera, seul le résultat est importé en PROD. Le worker de PROD ne garde que le court (reconnaissance, exports RGPD, e-mails), garde par `HEAVY_JOBS_ENABLED` (faux par défaut en production). Détail et runbook : `docs/infra/JOBS-LOURDS.md` (lot `pbm-jobs-flotte`).
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
`apps/web` lit aussi `NEXT_PUBLIC_UPLOAD_ORIGIN` (lot `v5-e2e`, doit rester alignée avec
`S3_ENDPOINT_URL` côté API quand `STORAGE_BACKEND=s3` — vide/absente avec `STORAGE_BACKEND=local`) :
la CSP `connect-src` du middleware (lot `v5-securite`) doit inclure l'origine du stockage objet,
sinon le `PUT` présigné direct du navigateur vers MinIO est bloqué et **tout envoi de photo
échoue** — trouvé en faisant tourner un vrai envoi par le navigateur pour la première fois
(`parcours-complet.spec.ts`), jamais exercé avant par les e2e précédentes (résultat toujours semé
directement en base).

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

## Détection des contrefaçons probables (lot `v6-contrefacon`)

Étend `pbm_api.state.counterfeit.assess_counterfeit` (v3-etat) de deux contrôles déterministes,
tous deux inactifs si aucune carte du catalogue n'a été rapprochée (`has_matched_card` — jamais
un signal par excès de prudence inverse) : **variante absente du catalogue** (holo/reverse
holo/1ère édition perçus alors que `Card.variants`, JSONB TCGdex, déclare *explicitement* cette
variante à `false` — une clé manquante, catalogue incomplet, ne compte jamais comme une preuve ;
`full_art`/`other` n'ont aucune clé de catalogue correspondante) et **numéro impossible** (total
de série imprimé `CardExtraction.total` incohérent avec `Set.total_cards` de l'extension
reconnue — jamais le NUMÉRO comparé à ce total, un secret rare le dépasse légitimement sans que
le total imprimé change, ex. 202/198, ce qui aurait signalé à tort une rareté légitime). Ces deux
contrôles rejoignent le signal explicite déjà rendu par l'IA dans le même appel que
l'identification (police, couleurs, format du numéro — « indices visuels par le LLM », inchangé
par ce lot) et le contrôle « gold non confirmé » existant. `pbm_api.state.service.
_matched_card_signals` (ex-`_matched_card_rarity`) fait le seul aller-retour DB supplémentaire :
`db.get(Set, card.set_id)` pour lire `total_cards` en plus de la rareté et des variantes déjà
chargées avec `Card`.

Toujours « probable », jamais « certain » (mission « risques & pièges » : faux positifs possibles
sur des promos rares) — aucun changement côté neutralisation de valeur
(`CollectionItem.counterfeit_suspected` → `pbm_api.pricing.valuation.item_value`), filtre
« contrefaçons probables » (`v4-collection`) ni badges (`v3-validation`, `v4-fiche`) : ils lisent
déjà `counterfeit_suspected`/`counterfeit_reasons`, une liste que ce lot peut simplement allonger.
Jeu de 60 cartes étiquetées (mission point 1, « 30 contrefaçons connues et 30 vraies cartes ») —
pas une image, une extraction/un catalogue simulés directement (aucune carte physique/clé IA
réelle sur chimera, même contrainte qu'ailleurs) : `pbm_api.state.counterfeit_synthetic`, 3
familles de contrefaçons (une par canal de détection) et 3 familles de cartes authentiques dont
des pièges délibérés (secret rare, variante confirmée par le catalogue, catalogue incomplet,
variante non modélisée par TCGdex, total non lu) — précision et rappel mesurés à 100 % sur ce
jeu, `tests/test_state_counterfeit_synthetic_dataset.py` (fait foi, CI). Détail :
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

## Fiche carte (lot `v4-fiche`)

Routes (`apps/api/src/pbm_api/routers/cards.py`, module `pbm_api.cards`) : `GET /cards/{id}`
(catalogue + prix EUR par variante + classement + résumé du meilleur exemplaire possédé — voir
plus bas), `GET /cards/{id}/price-history?variant=&range=7|30|365|all` (courbe de valeur,
`pbm_api.pricing.valuation.price_history_eur` — un point par jour où au moins une source a un
relevé exploitable, jamais interpolé : risque documenté du lot, un historique court en début de
vie s'affiche tel quel), `GET /cards/{id}/my-items` (tous les exemplaires possédés par
l'utilisateur courant, onglet « Mes exemplaires » — jamais le `GET /me/collection/{item}` déjà
existant, mission initiale : une fiche montre systématiquement *tous* les exemplaires, pas un
seul connu d'avance). `GET /me/collection/{item}/photo` (`routers/collection.py`), ajoutée par ce
lot pour la bascule « Ma photo » de l'en-tête : sert la photo brute de l'exemplaire
(`CollectionItem.photo_s3_key`), 404 explicite si l'exemplaire n'a pas de photo (ajout manuel) ou
si l'objet a disparu du stockage — jamais un succès vide. Les onglets Histoire/En jeu ne passent
par aucune route de ce lot : ils réutilisent tels quels `GET /cards/{id}/insights` et
`GET /cards/{id}/in-game-study` (missions `v4-anecdotes`/`v4-jeu`, déjà en génération à la demande
si absente) — **premiers écrans à les consommer**.

`MyCardItemOut.purchase_price_eur` : prix d'achat converti au taux du jour d'**acquisition**
(`pbm_api.pricing.exchange_rates.get_rate_to_eur`, jamais celui du jour de lecture — ce qui a été
payé ne change pas rétroactivement), `None` sans prix d'achat ou si ce taux n'a jamais été
relevé. Sert la plus-value de l'en-tête (`value_eur - purchase_price_eur`) sans second aller-
retour serveur. Bug trouvé en écrivant ce champ : `Decimal.__truediv__` d'une conversion de
change dont le quotient est « rond » (ex. 40 USD à 2 USD/EUR) renvoie un `Decimal` en notation
scientifique (`2E+1`) que Pydantic sérialise tel quel — `.quantize(Decimal("0.000001"))` après
toute conversion de devise, appliqué ici et dans `price_history_eur` (les deux fonctions de ce
lot ; les usages plus anciens de `convert_to_eur` dans `pricing/valuation.py`, testés à l'égalité
exacte par `test_valuation.py`, n'ont pas été touchés — hors périmètre, risque de régression pour
un autre lot).

En-tête de fiche et « État »/« Ajoutée le »/« Prix d'achat »/« Plus-value » : dérivés côté front
(`apps/web/src/app/carte/[id]/card-detail-view.tsx`, `pickPrimaryItem`) du **meilleur** exemplaire
possédé (valeur la plus forte, `MyCardItemOut[]` déjà chargé pour l'onglet « Mes exemplaires »),
même choix que `CardDetailResponse.collection_rank` côté API (`pbm_api.cards.service.
_best_owned_item`) — jamais un second calcul qui pourrait diverger. `CardRankingOut.
value_percentile` est un `PERCENT_RANK()` **0 → 1, 1 = le plus cher** (`pbm_api.ranking.service`,
vue matérialisée `card_value_rank`) : le badge « top X % de l'extension » calcule
`(1 - value_percentile) * 100`, jamais `100 - value_percentile` (confondre les deux échelles
aurait affiché un pourcentage dix fois trop petit).

Page `apps/web/src/app/carte/[id]/` : onglet actif en état local (`useState`, pas dérivé de
`useSearchParams` à chaque rendu comme `/collection`) — changer d'onglet ne redemande rien au
serveur, la bascule doit être instantanée ; l'URL (`?onglet=`) n'est mise à jour qu'ensuite, pour
le partage et le retour arrière. Cinq onglets (Valeur, **État**, Histoire, En jeu, Mes
exemplaires) : la maquette (`ROADMAP.html`, `V.fiche`) en montre cinq alors que la mission n'en
listait que quatre (l'État en moins) — la maquette prime (`CLAUDE.md` racine : « le front
reproduit la maquette »), d'autant que le contenu de cet onglet existe déjà entièrement
(`v3-etat`). Courbe de valeur : Recharts (`value-chart.tsx`, propre à ce lot — homonyme sans
rapport avec celui de `v4-dashboard`), ligne de référence en pointillés pour le prix d'achat,
palette et specs de marque suivant la référence dataviz du poste (un seul hue pour la série, pas
de légende à une série, grille recessive) ; partage avec `v4-dashboard` le mock `ResizeObserver`
de `vitest.setup.ts` (absent de jsdom, requis par `ResponsiveContainer`, les deux lots l'ayant
ajouté indépendamment en parallèle).

Tests : `apps/api/tests/test_card_detail_routes.py` (accès croisé sur les trois routes + la
photo, conversion de devise), `apps/web/src/__tests__/card-detail-view.test.tsx`. e2e Playwright
de conformité à la maquette (captures jointes au compte rendu du lot) :
`apps/web/e2e/card-detail.spec.ts` — aucune clé IA réelle disponible sur chimera, une carte
possédée avec historique de prix, état estimé, anecdotes et étude en jeu déjà en cache est semée
directement en base par `apps/api/scripts/seed_card_fiche_e2e.py` (même forme que
`seed_validation_e2e.py`) ; connexion par appels API directs (`page.request`, cookies partagés
avec `page`) plutôt qu'en remplissant le formulaire d'inscription à l'écran — la case CGU de ce
formulaire s'est révélée instable à cliquer dans l'environnement Playwright de ce poste
(`auth.spec.ts` échoue au même endroit, non lié à ce lot) ; seule la fiche elle-même reste
exercée par le navigateur.

## Revue de sécurité avant ouverture (lot `v5-securite`)

Rapport complet : `docs/SECURITE.md` (accès croisé, en-têtes/cookies/CORS/débit/taille d'envoi,
journaux, dépendances, SSRF, envoi de fichiers malveillants — ce qui a été testé, corrigé,
laissé en l'état et pourquoi). Ce que ça change dans le code, pour les lots suivants :

- `pbm_api.security.headers.SecurityHeadersMiddleware` (branché dans `main.py`) pose
  `Content-Security-Policy`/`X-Frame-Options`/`X-Content-Type-Options`/`Referrer-Policy`/
  `Permissions-Policy`/`Strict-Transport-Security` sur **toute** réponse de l'API — sauf
  `/docs`/`/redoc`/`/openapi.json`, qui gardent les en-têtes défensifs mais pas la CSP stricte
  (Swagger UI charge des scripts depuis un CDN). Toute nouvelle route en profite sans rien à
  faire.
- `apps/web/src/middleware.ts` pose la même famille d'en-têtes sur **toute** page (plus
  seulement les quatre routes protégées par session) et génère un nonce CSP par requête,
  transmis à `layout.tsx` via l'en-tête `x-nonce` (`headers()` de `next/headers`) — tout script
  inline ajouté par un futur lot doit porter ce nonce (`<script nonce={nonce}>`) pour s'exécuter
  sous cette CSP ; `'unsafe-inline'` reste ouvert sur `style-src` uniquement (attribut `style`
  dynamique, pas les balises `<script>`).
- `pbm_api.security.log_filter` a maintenant deux redactions installées au démarrage
  (`install_api_key_redaction`, `install_secret_url_redaction`) : toute nouvelle famille de
  secret journalisable (nouveau jeton d'URL, nouveau format de clé) s'ajoute par un nouveau
  motif + un nouvel appel `_install_redaction(...)`, pas une réécriture du mécanisme.
- `StorageBackend` (`pbm_api.storage`) expose désormais `head(key) -> int | None` (taille sans
  téléchargement) sur les deux implémentations (`ObjectStorage`, `LocalObjectStorage`) — à
  utiliser avant tout `get()` sur un contenu dont la taille n'est pas déjà garantie par un
  contrôle amont (voir `uploads/service.py::complete_upload` pour l'usage de référence).
- `/auth/register` est désormais limité en débit par IP (même `RateLimiter` que `/auth/login`/
  `/auth/forgot`, scope `register:ip`).

## Parcours e2e complet (lot `v5-e2e`)

`apps/web/e2e/parcours-complet.spec.ts` — inscription → vérification (Mailpit) → clé IA
(simulée) → envoi de la photo de référence 3×3 → validation → collection filtrée → fiche carte.
Contrairement à `validation.spec.ts`/`card-detail.spec.ts` (résultat semé directement en base,
aucune clé IA réelle sur chimera), ce lot fait tourner le **vrai** pipeline de bout en bout : un
vrai fichier envoyé par le navigateur, une vraie détection OpenCV, une vraie identification +
rapprochement catalogue — seul l'aller-retour réseau vers le fournisseur IA est remplacé.

`pbm_api.ai.simulated_provider.SimulatedProvider` (drapeau `AI_SIMULATED_PROVIDER`, faux par
défaut, jamais en UAT/PROD) bascule `pbm_api.ai.factory.create_provider` dessus quel que soit le
fournisseur demandé — un seul point de fabrication, comme la mission `v3-ia-providers` le
prévoyait déjà. Il ne simule que `CardExtraction` (identification/état) en servant les neuf
cartes de `pbm_api.seed.DEMO_CARDS` ; tout autre schéma (repli LLM de la détection, insights,
étude en jeu) lève une erreur explicite plutôt qu'une réponse inventée. Faire tourner le vrai
pipeline exige un worker arq réel : troisième entrée `webServer` de `playwright.config.ts`
(`uv run arq pbm_api.worker.WorkerSettings`, même base/redis que l'API) — jusqu'ici aucune spec
n'en avait besoin, le résultat de reconnaissance étant toujours semé directement.

Photo de référence : `apps/api/scripts/generate_e2e_reference_photo.py` écrit un classeur 3×3
propre (`pbm_api.detection.synthetic.make_binder_grid(glare=False)`) — OpenCV seul suffit à
détecter les neuf cartes, aucun repli LLM n'est donc exercé. Catalogue : idempotent comme
`pbm_api.seed` lui-même, `apps/api/scripts/seed_e2e_reference_catalog.py` sème aussi un
historique de prix minimal et rafraîchit `card_value_rank` (sinon le classement de la fiche
resterait vide pour des cartes fraîchement créées). En le relançant, un bogue latent de
`pbm_api.seed.seed()` a été trouvé et corrigé : `User` exige `last_name`/`birth_date`/
`terms_version`/`terms_accepted_at` depuis `v1-identite`, postérieur à ce module qui n'avait
jamais été rejoué depuis.

**Écart assumé** : les neuf recadrages du classeur synthétique sont visuellement indiscernables
(`pbm_api.detection.synthetic.draw_card` est pensé pour la géométrie de détection, pas pour
l'identification — même couleur, même cercle, quelle que soit la carte). Leur empreinte
perceptuelle est donc identique, et `identification_cache` (une vraie fonctionnalité de
production, pas un artefact de la simulation) résout les huit détections suivantes sans
repasser par le fournisseur simulé après le premier appel : les neuf exemplaires confirmés sont
neuf « Sarmuraï » (doublons), pas neuf cartes distinctes. Une diversité réelle demanderait des
photos distinctes, indisponibles sur chimera (même contrainte que `v3-detection`). Le filtre de
collection est quand même exercé dans les deux sens (une recherche qui trouve, une qui ne trouve
rien) ; la fiche carte n'est vérifiée que sur ses onglets Valeur/État/Mes exemplaires — Histoire/
En jeu appelleraient un vrai wiki + la clé IA (schémas que `SimulatedProvider` ne simule pas),
déjà couverts sans réseau par `card-detail.spec.ts`.

Test d'accès croisé propre à ce lot : un second utilisateur reçoit 404 sur `GET /uploads/{id}` et
`GET /uploads/{id}/detections` de l'envoi réel du premier — isolation déjà couverte ailleurs sur
un résultat *semé*, jamais encore sur un envoi/détections produits par le vrai pipeline.

**Deux bogues trouvés en étant la première spec à exercer un vrai envoi de photo par le
navigateur** (les e2e précédentes sèment leur résultat directement en base) :
- La CSP `connect-src` du lot `v5-securite` (`apps/web/src/middleware.ts`) n'autorisait que
  `'self'` et l'origine de l'API — pas celle du stockage objet. Avec `STORAGE_BACKEND=s3` (MinIO
  en dev/CI), le navigateur dépose la photo brute par un `PUT` direct vers cette origine
  (présignée, `pbm_api.s3.ObjectStorage.presign_put`) : la CSP le bloquait, et **tout envoi de
  photo échouait silencieusement** (page affichant « L'envoi a échoué. », rien dans les journaux
  serveur puisque la requête n'atteint jamais l'API). Corrigé par `NEXT_PUBLIC_UPLOAD_ORIGIN`
  (voir plus haut) ajoutée à `connect-src` quand elle est définie.
- `/auth/register` est limité en débit par IP depuis `v5-securite`
  (`LOGIN_RATE_LIMIT_MAX_ATTEMPTS`/`_WINDOW_SECONDS`, un compteur Redis partagé avec `/auth/
  login`/`/auth/forgot`). Toutes les specs e2e tournent depuis la même IP contre la même
  instance API : `auth`+`validation`+`card-detail`+`parcours-complet` totalisaient déjà 5
  inscriptions dans une CI qui repart de zéro — pile à la limite par défaut (5), sans marge pour
  la moindre reprise (`retries: 1` en CI). `playwright.config.ts` relève `LOGIN_RATE_LIMIT_MAX_
  ATTEMPTS` pour cette seule instance e2e (jamais en UAT/PROD) ; le second utilisateur du test
  d'accès croisé de ce lot est en plus seedé directement en base
  (`scripts/seed_e2e_second_user.py`) plutôt que par `/auth/register`, pour ne pas alourdir ce
  compteur partagé.

## Decks : légalité et sauvegarde (lot `v7-decks-api`)

Routes (`apps/api/src/pbm_api/routers/decks.py`, préfixe `/me/decks`, toutes bornées au
propriétaire via la session — jamais un id reçu du client, un deck d'autrui renvoie 404, pas
403) : `POST /me/decks` (création, cartes initiales facultatives), `GET /me/decks` (liste +
légalité par deck), `GET /me/decks/{id}` (détail + rapport de légalité), `PATCH /me/decks/{id}`
(renommer), `DELETE /me/decks/{id}`, `POST /me/decks/{id}/duplicate`,
`PUT /me/decks/{id}/cards/{card_id}` (poser/mettre à jour une quantité, idempotent),
`DELETE /me/decks/{id}/cards/{card_id}`. Écritures protégées par `require_csrf`.

Modèle (`pbm_api.models.decks`) : `decks` (nom, propriétaire) et `deck_cards` (`card_id` du
CATALOGUE + `quantity`, unicité `(deck_id, card_id)`). `deck_cards` référence le catalogue, PAS
un `collection_items.id` : imposé par D10 (une Énergie de base fait partie d'un deck sans être
possédée) et robustesse — vendre un exemplaire rend le deck injouable mais le laisse lisible et
modifiable (risque du lot), ce qu'une FK vers la collection casserait. « Uniquement avec ses
cartes » est donc un CONTRÔLE DE LÉGALITÉ (possession comptée sur `collection_items`), pas une
clé étrangère.

Légalité (`pbm_api.decks.legality`, logique pure, testable sans base) — recalculée à CHAQUE
lecture, jamais mémorisée : une carte vendue rend le deck injouable sans aucune écriture
(« revalidation quand la collection change », mission point 3). Règles (D10) : exactement 60
cartes ; 4 exemplaires maximum par NOM (deux impressions d'un même nom cumulées), sauf Énergies
de base ; possession requise sauf Énergies de base ; rapport lisible (`issues`, codes
`deck_size`/`copy_limit`/`not_owned`/`unsupported_effect`).

Classement des Énergies (`pbm_api.decks.energy`, décision D10) : Énergie de BASE = illimitée,
fournie, jamais décomptée de la collection, hors règle des 4 (mais comptée dans les 60) ; Énergie
SPÉCIALE = carte comme les autres (possession + règle des 4). Source de vérité : `Card.energy_type`
(TCGdex `energyType`, colonne ajoutée par ce lot, peuplée à l'import) ; à défaut (cartes importées
avant la colonne, `energy_type IS NULL`), repli sur le nom — l'ensemble des Énergies de base est
fermé, calibré sur les 514 cartes `supertype = "Énergie"` du catalogue (l'Éclair s'écrit
« Énergie Électrique » ET « Énergie Electrik », la casse varie). Jamais sur la rareté (une Énergie
de base existe en « Commune » comme en « Magnifique rare »).

Effet non pris en charge : la vérification « une carte dont l'effet n'est pas géré par le moteur
(`v7-regles-cartes`) est refusée » est câblée (`legality.unsupported_card_ids`, code
`unsupported_effect`) mais NEUTRE tant que ce moteur n'existe pas dans le dépôt — sans moteur,
tout effet serait « non pris en charge » et aucun deck ne serait jamais légal. S'activera en
remplaçant le corps de cette fonction par un appel au moteur, sans autre changement — report
explicite dans le compte rendu, pas un repli silencieux.

Migration `d1c7a3f0b2e4` (tables `decks`/`deck_cards` + colonne `cards.energy_type`, nullable).
Tests : `apps/api/tests/test_deck_legality.py` (moteur pur : D10, 60/4/possession),
`apps/api/tests/test_deck_routes.py` (CRUD, accès croisé B→404, revalidation après vente, CSRF).
Aucun écran dans ce lot (back-end) : le constructeur est `v7-decks-ui` (couloir CH5).

## Decks : légalité, formats et sévérités (lot `v7-decks-legalite`)

Étend le contrôle de légalité de `v7-decks-api` — une **seule** implémentation
(`pbm_api.decks.legality.evaluate`), exposée telle quelle par l'API et destinée à l'écran, jamais
deux logiques qui divergent (risque du lot). Quatre ajouts :

- **Sévérité** par constat (`LegalityIssue.severity` : `bloquant` / `avertissement`). Seul un
  constat bloquant retire la légalité (`DeckLegality.legal = aucun bloquant`) ; un avertissement
  informe sans interdire.
- **Au moins un Pokémon de base** (`legality.is_basic_pokemon`, `Card.stage` = TCGdex "Base") :
  un deck sans Pokémon de base est injouable (bloquant, code `no_basic_pokemon`) — ajouté
  seulement si le deck contient au moins une carte (un deck vide échoue déjà sur la taille, on ne
  double pas le bruit).
- **Légalité par format** (`pbm_api.decks.formats` : Standard / Étendu / Illimité) déduite du
  catalogue (`Card.legal_standard`/`legal_expanded`). Format **choisi par le joueur**
  (`Deck.format`, défaut `standard`, posé au `POST` et modifiable au `PATCH /me/decks/{id}`). Une
  carte explicitement hors format (légalité `False`) est signalée (bloquant, code
  `out_of_format`, avec l'explication) ; une légalité inconnue (`None`, vieilles cartes non
  réévaluées) ne bloque pas — bénéfice du doute, jamais un repli qui bloquerait par défaut ; les
  Énergies de base sont toujours autorisées.
- **Contrefaçons exclues** : `service._owned_counts` sépare, en une requête, la possession (hors
  contrefaçon) et les exemplaires signalés contrefaçon (`CollectionItem.counterfeit_suspected`,
  `v6-contrefacon`). Les contrefaçons ne comptent pas dans la possession ; leur exclusion est un
  avertissement (code `counterfeit_excluded`) qui explique un décompte plus bas — et peut donc
  entraîner un `not_owned` bloquant.

Point d'extension `v7-regles-cartes` inchangé et toujours neutre (`legality.unsupported_card_ids`
retourne l'ensemble vide tant que le moteur n'existe pas — report explicite, pas un repli
silencieux). Migration `a4e9c1d7b3f5` (`cards.stage`, `decks.format` défaut `standard`, alimentés
à l'import par `catalog/import_service.py`). Schémas : `PATCH /me/decks/{id}` accepte `name`
et/ou `format` (`UpdateDeckRequest`, partiel) ; `DeckCardOut` porte
`is_basic_pokemon`/`in_format`/`counterfeit_excluded`, `DeckLegalityOut` porte
`format`/`format_label` et chaque `issue` sa `severity`. Tests : `tests/test_deck_legality.py`
(33 cas purs, dont les pièges de la mission : 5ᵉ exemplaire d'un même nom sous deux illustrations,
Énergie spéciale non possédée, deck sans Pokémon de base, carte contrefaite),
`tests/test_deck_routes.py` (format choisi + carte hors format, contrefaçon exclue, sévérités,
accès croisé B→404, CSRF). Back-end seul ; le constructeur qui les affiche est `v7-decks-ui`
(couloir CH5).

## Decks : import et export d'une liste (lot `v7-decks-import-export`)

Récupérer un deck vu ailleurs ou partager le sien, sans tout ressaisir. Back-end seul (comme
`v7-decks-api`/`v7-decks-legalite`) — l'écran qui consomme ces routes est `v7-decks-ui` (couloir
CH5, pas encore livré).

**Import** (`POST /me/decks/import`, session + CSRF, `pbm_api.decks.import_service.import_deck`) :
une liste collée (`text`) → un deck « à compléter » + un rapport ligne par ligne. ⛔ Risque du lot :
**une liste importée ne crée JAMAIS de cartes dans la collection** — elle ne touche que `decks`/
`deck_cards` (catalogue), aucun `CollectionItem` (test `test_import_never_creates_collection_items`).
- Analyseur tolérant (`pbm_api.decks.parsing`, logique pure) : quantité en tête (`3`, `3x`, `x3`,
  implicite → 1 signalé), puces, en-têtes de section (`Pokémon: 12`, `Trainer`, `Total Cards: 60`)
  ignorés, commentaires (`#`, `//`), extension + numéro de fin facultatifs (`PAF 234`, `234/197`,
  `(PAF 234)`). Rien n'est rejeté en silence : toute ligne non triviale devient une entrée `card`.
- Rapprochement : réutilise **tel quel** `catalog.search.match_candidates` (`v2-recherche`) — nom
  (trigram FR/EN, tolérant aux fautes de frappe) + numéro (filtre strict), avec un **repli
  progressif** noté sur la ligne (on lâche l'extension collée d'un autre site si elle ne
  correspond pas à nos codes, puis le numéro). Statut par ligne : `matched` / `ambiguous`
  (meilleure retenue + alternatives) / `not_found` (introuvable au catalogue, **non ajoutée**) /
  `section`. Possession (`owned`/`missing`) comptée par le **même** chemin que la légalité
  (`service._owned_counts` + `energy.is_basic_energy` : une Énergie de base n'est jamais manquante).
- `dry_run=true` : rapport seul, aucun deck créé (aperçu avant validation). Garde-fou :
  `MAX_IMPORT_LINES` = 400 (au-delà, tronqué **et signalé**), quantité écrêtée à 60 par carte.

**Export** (`GET /me/decks/{id}/export?fmt=text|pdf`, borné au propriétaire → 404 sinon,
`pbm_api.decks.export`) :
- **texte** : `quantité nom EXTENSION numéro`, groupé par type, en-tête en commentaire (`#`).
  Volontairement **re-lisible par l'analyseur d'import** — un export ré-importé redonne le même
  deck (`test_export_text_round_trips`).
- **PDF** (`fpdf2`, ajouté aux dépendances) : vignettes + liste. Les images (basse définition,
  `cards/{id}/low.webp` du stockage objet, même clé que le proxy `/img/cards/{id}`) sont
  **préchargées en async dans la route** puis passées à un rendu synchrone ; une carte sans
  vignette montre un **cadre nommé**, jamais un trou ni un 500. Police cœur Helvetica (pas de TTF
  à télécharger sur le réseau lent de chimera) ; textes réduits au latin-1 pour ne jamais faire
  échouer le rendu sur un caractère hors jeu.

Aucune migration (ni table ni colonne) : le lot ne fait que lire le catalogue et écrire des decks
via le modèle existant. Tests : `test_deck_parsing.py` (analyseur pur), `test_deck_import.py`
(import, accès croisé B→404, jamais la collection, liste de tournoi avec sections, fautes de
frappe, carte hors catalogue, dry-run, CSRF), `test_deck_export.py` (round-trip texte, PDF valide,
vignette réellement embarquée, 404).

## Règles de la flotte applicables ici (résumé de `~/.claude/CLAUDE.md`)

- On construit sur chimera (32 Go, 16 threads) et on ne construit jamais sur la machine qui sert.
- Le réseau de chimera plafonne à ~250 Ko/s : éviter les téléchargements/images Docker inutiles.
- Session autonome (`claude -p`) : jamais de `git stash`, jamais `git add -A`, commits ciblés,
  compte rendu obligatoire même en cas d'échec ou de blocage.
