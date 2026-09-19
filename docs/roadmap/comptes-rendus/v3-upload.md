# Compte rendu — `v3-upload`

Session autonome (`claude -p`) sur chimera, worktree `~/dev/wt-pbm-v3-upload`, branche
`roadmap/v3-upload`. Exécuté sous le régime décrit dans le CONTEXTE D'EXÉCUTION du prompt
(sections A/P/0/7 du prompt de lot remplacées) : pas de `suivi.py`, pas d'écriture dans
`etat.json`/`ROADMAP.html`/`BACKLOG.md`/`prompts/`, fusion directe vers `origin/main`
(dépôt relais local, pas GitHub).

## Résumé

Page `/ajouter` : glisser-déposer ou sélection de plusieurs photos, bouton appareil photo
(`capture=environment`), aperçus, retrait avant envoi, estimation avant lancement, progression
par photo. Back-end : `POST /uploads` (cible d'envoi par fichier — URL présignée S3 en dev/CI,
route locale signée en backend `local`), le navigateur envoie les octets directement au
stockage, `POST /uploads/{id}/complete` revérifie le type réel (magic bytes via décodage
Pillow, pas l'en-tête déclaré), supprime l'EXIF (position GPS incluse), convertit HEIC → JPEG,
et crée un `Job` de reconnaissance (`type=detect_cards`, `status=queued`) seulement si
l'utilisateur a une clé IA personnelle (D4 : sinon photo conservée, reconnaissance désactivée,
ajout manuel possible — hors périmètre de ce lot).

D7 appliquée à la lettre : `pbm_api.storage` expose deux implémentations
(`ObjectStorage`/MinIO pour `STORAGE_BACKEND=s3`, `LocalObjectStorage`/disque pour
`STORAGE_BACKEND=local`) derrière la même surface `get`/`put`/`ensure_bucket`, aucune route ne
suppose l'une ou l'autre. Testé en conditions réelles pour les deux : envoi bout en bout par une
vraie requête HTTP `PUT` présignée contre MinIO (`localhost:59000`), et par la route
`PUT /uploads/{id}/raw` (jeton signé HMAC à expiration, `pbm_api.security.upload_tokens`) contre
un disque temporaire pour le backend local.

## Livrables

- `apps/api/src/pbm_api/uploads/` — `service.py` (création par lot, validation, cible d'envoi,
  complétion), `processing.py` (vérification magic bytes + suppression EXIF + conversion HEIC
  via Pillow/`pillow-heif`), `schemas.py`, `errors.py`.
- `apps/api/src/pbm_api/routers/uploads.py` — `POST /uploads`, `PUT /uploads/{id}/raw`,
  `POST /uploads/{id}/complete`, branché dans `main.py`.
- `apps/api/src/pbm_api/storage/` — `LocalObjectStorage` (disque, D7) + `build_storage()`
  (bascule sur `STORAGE_BACKEND`). `pbm_api/s3.py` — `ObjectStorage.presign_put` ajouté
  (présignage PUT, existant enrichi, pas remplacé — `images.py`/`test_images.py` inchangés).
- `apps/api/src/pbm_api/security/upload_tokens.py` — jeton HMAC signé à expiration pour la
  cible d'envoi du backend `local` (pas de service de présignage séparé à qui déléguer : l'API
  se présigne une URL vers sa propre route `PUT /uploads/{id}/raw`, même contrat d'usage qu'un
  présignage S3 — voir « Choix techniques »).
- `apps/api/src/pbm_api/config.py` — `storage_backend` (déf. `s3`), `photos_storage_path`,
  `upload_max_size_bytes` (20 Mo), `upload_max_files_per_batch` (30).
- `apps/web/src/app/ajouter/upload-view.tsx` — page conforme à la maquette (copie exacte
  reprise de `V.ajouter` dans `ROADMAP.html` : stepper, zone de dépôt, boutons, estimation) ;
  bannière + lien `/profil` si aucune clé IA (D4).
- `apps/web/src/lib/api/uploads.ts` — client API (cible d'envoi, envoi des octets, complétion,
  lecture du cookie CSRF non-`HttpOnly`). `apps/web/src/lib/uploads-constraints.ts` — validation
  client (type/taille/lot), miroir des contraintes serveur, jamais la seule ligne de défense.
- `apps/web/src/lib/config.ts` — `getCsrfCookieName()` (première route du front à écrire, donc
  premier besoin de relire ce cookie côté client).
- Bases/bucket/préfixe dédiés créés sur `pbm-shared` : `pbm_v3_upload` (dev), `pbm_v3_upload_test`
  (tests), bucket S3 `pbm-v3-upload`, préfixe Redis `pbm:v3-upload:` (déclarés en local pour ce
  lot ; `apps/api/src/pbm_api/config.py`/`conftest.py` ne portent que le défaut `TEST_DATABASE_URL`
  — convention déjà en place lot après lot, voir `v2-recherche`).
- Aucune nouvelle migration Alembic : `uploads`/`jobs` existent déjà depuis `v0-schema`, exactement
  avec les colonnes nécessaires (`s3_key`, `content_type`, `size_bytes`, `status`).

## Tests

```
$ cd apps/api && uv run ruff check .
All checks passed!

$ uv run pytest -q
126 passed in 16.39s   # 109 préexistants + 17 nouveaux (tests/test_uploads.py)
```

- `tests/test_uploads.py` — `test_create_uploads_returns_one_presigned_target_per_file`
  **échoue sans ce lot** (404, aucun routeur `uploads`) et passe avec.
  - Cibles d'envoi : une par fichier, lot > 30 refusé, type non accepté refusé, taille > 20 Mo
    refusée, CSRF exigé.
  - **Bout en bout réel** (pas de mock) : `PUT` HTTP direct contre le présignage MinIO réel
    (`localhost:59000`), JPEG avec EXIF GPS construit par Pillow → `complete` → relecture de
    l'objet stocké → `Image.getexif()` vide (position GPS supprimée). HEIC construit via
    `pillow-heif` → `complete` → `content_type == "image/jpeg"`. PNG → reste PNG, sans EXIF.
  - Magic bytes : texte brut renommé en `.jpg` → `complete` refusé (400), `Upload.status`
    passe à `failed`.
  - `complete` sans octets reçus → 409 ; rejoué une seconde fois → 409 (non rejouable).
  - Clé IA présente (`PUT /me/ai-keys/anthropic` réel) → `Job` créé (`type=detect_cards`,
    `status=queued`, `payload={"upload_id": ...}`) ; absente → `recognition_enabled: false`,
    aucun job, photo tout de même conservée (D4).
  - **Accès croisé** : `complete` sur l'envoi d'un autre utilisateur → 404 (jamais 403, pas de
    fuite d'existence).
  - **Backend local (D7)** : cible d'envoi = route locale signée, écrit réellement sur un
    disque temporaire (`tmp_path`), jeton invalide/pour un autre envoi/expiré → 403.

```
$ pnpm --filter @pbm/web lint && pnpm --filter @pbm/web type-check && pnpm --filter @pbm/web test && pnpm --filter @pbm/web build
✓ eslint . (aucune erreur)
✓ tsc --noEmit (aucune erreur)
✓ 18 fichiers, 51 tests passés (7 nouveaux dans src/__tests__/upload-view.test.tsx)
✓ next build — /ajouter : 5.44 kB (120 kB First Load JS)
```

- `src/__tests__/upload-view.test.tsx` — bannière D4 sans clé IA (lien `/profil`) ; zone de
  dépôt conforme à la maquette (copie exacte, boutons) avec clé IA ; ajout d'une photo valide +
  estimation affichée ; rejet client d'un fichier > 20 Mo et d'un type non accepté ; envoi
  complet (cible → octets → complétion, mocks du client API) affiche « Envoyée » ; erreur par
  photo si l'envoi échoue (le lot continue les autres photos, pas d'arrêt global).

Rejoué avec les variables d'environnement de la CI (`DATABASE_URL`/`TEST_DATABASE_URL`/
`REDIS_URL`/`S3_*`/`TZ=Europe/Paris` comme `.github/workflows/ci.yml`) contre l'infra partagée
locale : même résultat, aucune régression liée aux noms de variables. `STORAGE_BACKEND` n'est
pas fixé par la CI (`api` job) : le défaut `s3` s'applique, cohérent avec le MinIO démarré par
ce job.

Aucun secret : recherche de motifs de clé sur les fichiers ajoutés → aucun résultat. La clé IA
utilisée en test (`sk-ant-api03-abc…`) est une valeur factice déjà présente dans
`test_ai_keys.py`, jamais journalisée (filtre `pbm_api.security.log_filter` déjà en place).

## Choix techniques faits (autonomes, dans le cadre de `docs/ARCHITECTURE.md`)

- **Backend `local` = présignage vers l'API elle-même** (`PUT /uploads/{id}/raw?token=…`, jeton
  HMAC signé à expiration, `pbm_api.security.upload_tokens`) plutôt qu'un flux différent en
  UAT/PROD : il n'existe pas de service de stockage séparé à qui déléguer un vrai présignage
  quand les photos vivent sur le disque du serveur (D7) — le contrat côté navigateur reste
  identique aux deux backends (`{method, url, headers}`, un `PUT` direct), seule la cible change.
  Le jeton n'exige pas de cookie de session (comme un présignage S3 n'en exige pas) : sa
  possession suffit, à durée limitée (15 min).
- **`Upload.s3_key` réutilisé tel quel pour l'objet final** (pas de clé séparée
  original/processed) : `complete` écrase l'objet brut par la version traitée (EXIF supprimé,
  HEIC converti) au même endroit — plus simple, et l'original avec ses métadonnées n'a aucune
  raison d'être conservé après le contrôle (mission : « données de position EXIF supprimées à
  l'envoi », pas « conservées à part »).
- **`Job` créé en base sans enqueue `arq`** : `pbm_api.worker.WorkerSettings.functions` ne
  connaît encore aucune tâche `detect_cards` (elle revient au lot `v3-identification`, qui
  dépend de celui-ci). Créer la ligne `jobs` (`status=queued`) est la même convention que le
  reste du dépôt (`import_catalogue`, `daily_prices` — voir `worker.py`) : le lot suivant n'a
  qu'à la consommer, aucun changement de schéma nécessaire. Documenté ci-dessous en « reste à
  faire » pour éviter toute ambiguïté.
- **Type réel vérifié par décodage Pillow (`Image.open(...).load()`)**, pas une librairie de
  détection de magic bytes dédiée (`python-magic`, absente du dépôt) : Pillow refuse déjà tout
  contenu qu'il ne peut décoder (`UnidentifiedImageError`/`OSError`), qui est exactement le test
  demandé par la mission (« vérification du type réel »). Évite une dépendance système
  supplémentaire (`libmagic`) sur une machine au réseau à ~250 ko/s.
- **EXIF supprimé par réenregistrement sans repasser `exif=`**, pas par copie manuelle des
  pixels : vérifié directement (voir « Tests ») que `Image.save(..., format=...)` sans le
  paramètre `exif=` explicite n'embarque pas `image.info["exif"]` même s'il est présent après
  l'ouverture — plus rapide qu'une recopie pixel par pixel (importe pour les grandes photos, pas
  de `putdata()` sur des millions de pixels).
- **Estimation avant lancement volontairement simple** (« 1 carte par photo », coût = cartes ×
  0,006 €, constante calée sur le ratio de la maquette 10 cartes ≈ 0,06 €) : ce lot ne sait pas
  compter les cartes avant reconnaissance réelle (lot `v3-identification`), l'estimation est
  affichée comme une approximation (« estimation avant analyse, coût réel mesuré ensuite »), pas
  comme un calcul précis. Documenté en « reste à faire ».
- **Aucune compression côté client** (risque listé par la mission : « photos lourdes (12 Mo) :
  compression côté client ») : aucune librairie de compression d'image n'est présente dans le
  dépôt, le budget de ce lot a priorisé le contrôle serveur (taille max, conversion HEIC, EXIF)
  qui protège déjà contre le risque documenté (une photo de 12 Mo passe, une de 25 Mo est
  refusée avant tout envoi réseau). Documenté en « reste à faire ».
- **`Content-Type` déclaré au moment de `POST /uploads` jamais fait confiance seul** : contrôlé
  contre la liste blanche à la création (`image/jpeg`, `image/png`, `image/heic`, `image/heif`),
  puis **revérifié** par le décodage réel à `complete` — un client qui mentirait sur le type
  déclaré n'obtient que le refus à `complete`, jamais une carte corrompue en base.

## Écarts au plan

- **Pas de screenshot du navigateur joint** (§6 : « Front → conformité à l'écran de la maquette,
  capture jointe au compte rendu ») : Playwright est installé (`apps/web/node_modules`,
  navigateurs Chromium déjà en cache sur chimera pour la CI), mais les bibliothèques système
  qu'il requiert (`libnspr4.so` et consorts) ne sont pas installées dans **cette** session WSL
  interactive, et cette session n'a ni root ni `sudo` sans mot de passe pour les poser (règle de
  la machine : Claude Code refuse `--dangerously-skip-permissions` en root, et je n'ai pas
  d'autorisation pour contourner). La CI GitHub Actions, elle, installe ces dépendances via
  `playwright install --with-deps` — mais son job `e2e` ne couvre aujourd'hui que le parcours
  authentification (`e2e/auth.spec.ts`), pas `/ajouter` : je n'ai pas élargi son périmètre
  (ajouter MinIO au job `e2e` pour un flux d'envoi réel aurait été un changement plus large que
  ce lot, décision documentée plutôt que silencieuse). Conformité vérifiée autrement : copie
  extraite verbatim de `V.ajouter` dans `ROADMAP.html` (stepper, zone de dépôt, boutons,
  estimation), reprise à l'identique dans `upload-view.tsx`, et couverte par
  `upload-view.test.tsx` (chaque texte de la maquette est asserté). Vérifié manuellement en
  conditions quasi réelles : `apps/api`/`apps/web` lancés en local, utilisateur inscrit/vérifié/
  connecté par le vrai flux HTTP (Mailpit), clé IA ajoutée par `PUT /me/ai-keys/anthropic`,
  page `/ajouter` chargée avec succès (`curl` sur le HTML servi + logs serveur sans erreur) —
  seule la capture d'écran navigateur manque.
- **Compression côté client non implémentée** (voir « Choix techniques »).
- **Job de reconnaissance créé mais jamais consommé** (voir « Choix techniques ») : le worker
  `arq` n'a pas de fonction `detect_cards`, c'est la mission explicite du lot `v3-identification`
  (dépendant de celui-ci dans `roadmap.json`).
- **Estimation de coût approximative** (voir « Choix techniques »).

## Reste à faire (pour les lots suivants)

- `v3-identification` : consommer les `Job(type="detect_cards", status=queued)` créés ici,
  brancher un worker `arq` réel, exposer `GET /uploads/{id}` (état + détections) — hors mission
  de ce lot, dépendance déjà déclarée dans `roadmap.json`.
- Lien « Profil → Mon IA » : pointe aujourd'hui sur `/profil` (page encore un `EmptyState`, lot
  `v1-byok` côté back déjà livré mais pas son front) — à préciser vers l'ancre exacte une fois
  la page profil construite.
- Compression côté client des photos lourdes (risque documenté par la mission).
- Capture d'écran navigateur de `/ajouter` (voir écart ci-dessus) — à obtenir depuis une machine
  qui a les dépendances système de Playwright (ou après leur installation ici, avec les
  autorisations nécessaires).
- Estimation de coût affinée une fois `v3-identification` livré (comptage réel de cartes par
  photo, coût mesuré via `ai_usage_monthly` plutôt qu'une constante).

## Décisions provisoires utilisées

D4 (sans clé IA personnelle, reconnaissance désactivée, ajout manuel possible — la révision du
19/09 concerne une clé plateforme pour un lot distinct, `v4-insights-batch`, sans effet sur ce
lot). D7 (deux implémentations de stockage, appliquée à la lettre — voir « Résumé »). D2/D8 hors
périmètre, confirmé (aucun déploiement, aucune tâche `release_uat`/`release_prod` traitée).
