# Compte rendu — `v3-detection`

Session autonome (`claude -p`) sur chimera, worktree `~/dev/wt-pbm-v3-detection`, branche
`roadmap/v3-detection`. Exécuté sous le régime décrit dans le CONTEXTE D'EXÉCUTION du prompt
(sections A/P/0/7 du prompt de lot remplacées) : pas de `suivi.py`, pas d'écriture dans
`etat.json`/`ROADMAP.html`/`BACKLOG.md`/`prompts/`, fusion directe vers `origin/main` (dépôt
relais local, pas GitHub).

## Résumé

Pipeline de détection et découpage des cartes d'une photo (`pbm_api.detection`) : contours
OpenCV (Canny + `approxPolyDP`, filtrage par ratio 63×88 mm ±12 %) puis redressement perspective
vers un recadrage fixe 630×880 px, en ordre de lecture ligne par ligne (classeur 3×3). Repli par
boîtes englobantes demandées au LLM (un seul appel par **photo**, jamais par carte) quand un
second passage sur les mêmes contours (`has_unclaimed_regions`) signale une zone de la taille
d'une carte laissée sans quadrilatère retenu — cartes qui se touchent, contour fusionné rejeté,
fond clair sans contraste. Chaque boîte du LLM est ensuite affinée par le même OpenCV dans sa
sous-image.

Le job `detect_cards` créé par `v3-upload` (`POST /uploads/{id}/complete`) était jusqu'ici une
ligne `Job` inerte : ce lot le met réellement en file (`pbm_api.queue.get_arq_pool`, **premier
job du dépôt enfilé depuis une route HTTP** — les autres sont en cron ou CLI direct) et l'exécute
(`pbm_api.worker.detect_cards_task` → `pbm_api.detection.service.run_detection_for_upload`), qui
écrit les `Detection` (déjà modélisées depuis `v0-schema`), les recadrages et une image annotée
de contrôle dans le stockage, puis alimente `ai_usage_monthly` si le repli a été utilisé.
Résultat consultable par `GET /uploads/{id}/detections` et
`GET /uploads/{id}/detections/{detection_id}/crop`, bornés au propriétaire de l'envoi.

## Livrables

- `apps/api/src/pbm_api/detection/` :
  - `geometry.py` — ordre de correction des coins, ordre de lecture ligne par ligne, redressement
    perspective vers 630×880 px.
  - `opencv_pipeline.py` — détection de quadrilatères (Canny, `approxPolyDP`, filtre de ratio,
    déduplication par recouvrement), `has_unclaimed_regions` (signal de repli).
  - `annotate.py` — image de contrôle annotée (contours + numéro d'ordre), encodage JPEG partagé.
  - `llm_fallback.py` — schéma Pydantic des boîtes normalisées, prompt, appel
    `AIProvider.extract`.
  - `pipeline.py` — `run_detection` : orchestration OpenCV → repli → affinage → recadrages.
  - `service.py` — `run_detection_for_upload` : DB/stockage (crops, image de contrôle,
    `Detection`, usage IA), indépendant d'arq.
  - `synthetic.py` — générateur de photos synthétiques (voir « Écarts au plan »).
  - `errors.py` — `DetectionSourceMissingError`.
- `apps/api/src/pbm_api/queue.py` — pool `arq` pour enfiler un job depuis une route HTTP
  (`get_arq_pool`).
- `apps/api/src/pbm_api/worker.py` — `detect_cards_task`, branché dans
  `WorkerSettings.functions` ; erreurs `AIProviderError` consignées via `user_message` sur le
  `Job` (jamais `detail`, réservé aux journaux serveur — mission `v3-ia-providers` point 3).
- `apps/api/src/pbm_api/uploads/service.py` — `complete_upload` met désormais réellement le job
  en file (`arq_pool.enqueue_job("detect_cards_task", ...)`) ; `list_detections`,
  `get_detection_crop` (isolation par `user_id`, jamais un `upload_id` seul).
- `apps/api/src/pbm_api/routers/uploads.py` — `GET /uploads/{id}/detections`,
  `GET /uploads/{id}/detections/{detection_id}/crop`.
- `apps/api/src/pbm_api/ai/service.py` — `get_default_credential` (choix clé/fournisseur pour un
  appel worker), `record_usage` (alimente `ai_usage_monthly`, jusqu'ici lecture seule) ; correctif
  `calls_count`/`tokens_count` initialisés à 0 à la construction (SQLAlchemy ne pose les défauts
  de colonne qu'à l'insert, un `+= 1` avant flush levait `TypeError` — trouvé par le test dédié).
- `apps/api/pyproject.toml` — `opencv-python-headless`, `numpy`.
- `apps/api/scripts/measure_detection_rate.py` — mise au point en lot (mission point 4), écrit
  une image annotée par photo + `report.json`.
- `docs/roadmap/comptes-rendus/echantillons-v3-detection/` — 5 images annotées de contrôle
  (une par famille) + `report.json` complet, preuve visuelle jointe (mission « livrables »).
- `docs/ARCHITECTURE.md` § « Reconnaissance » point 1, `CLAUDE.md` § « Détection de cartes » —
  mis à jour.
- Bases/bucket/préfixe dédiés créés sur `pbm-shared` : `pbm_v3_detection` (dev),
  `pbm_v3_detection_test` (tests), bucket S3 `pbm-v3-detection`, préfixe Redis
  `pbm:v3-detection:` (déclarés en local, convention déjà en place lot après lot — voir
  `v2-recherche`/`v3-upload`) ; `conftest.py` ne porte que le défaut `TEST_DATABASE_URL`.
- Aucune nouvelle migration Alembic : `detections`/`jobs` existent déjà depuis `v0-schema` avec
  exactement les colonnes nécessaires (`bbox`, `crop_s3_key`, `candidates`, `status`).
- `packages/api-client/src/schema.d.ts` régénéré (`pnpm gen:api`) pour les deux nouvelles routes.

## Tests

```
$ cd apps/api && uv run ruff check .
All checks passed!

$ uv run pytest -q
245 passed in ~22s   # 194 préexistants (rebasé sur origin/main) + 51 nouveaux
```

Rejoué avec les variables d'environnement de la CI (postgres/redis/minio sur les ports et noms
exacts de `.github/workflows/ci.yml`, `TZ=Europe/Paris`, conteneurs Docker dédiés démarrés puis
détruits pour ce test) : `245 passed`, aucune régression liée aux noms de variables ou aux
ports.

- `tests/test_detection_geometry.py`, `test_detection_opencv_pipeline.py`,
  `test_detection_pipeline.py`, `test_detection_service.py`, `test_detection_synthetic_dataset.py`,
  `test_detections_routes.py` — **échouent tous sans ce lot** (`pbm_api.detection` n'existait pas,
  `ModuleNotFoundError`, ou route 404) et passent une fois le pipeline ajouté.
  - Ordre de correction des coins et ordre de lecture (grille 3×3 mélangée reconstruite
    correctement).
  - Ratio 63/88 : un carré n'est jamais retenu comme carte.
  - `has_unclaimed_regions` : `False` sur une grille entièrement détectée, `True` sur deux cartes
    qui se chevauchent partiellement (sous-comptées par OpenCV seul).
  - Orchestration : OpenCV seul quand plausible (**zéro appel IA gaspillé**, vérifié par un
    compteur d'appels sur le double de fournisseur) ; repli + affinage quand incohérent, avec
    `ai_usage` renseigné et méthode `"llm_fallback"` ; D4 sans clé IA → résultat OpenCV seul
    renvoyé tel quel, jamais d'exception.
  - Service DB/stockage : `Detection` créées avec le bon nombre, recadrage 630×880 relisible
    depuis le stockage, image de contrôle présente ; usage IA enregistré dans
    `ai_usage_monthly` quand le repli a servi (a révélé et corrigé le bug `calls_count`
    ci-dessus).
  - Routes HTTP : liste + recadrage accessibles au propriétaire ; **accès croisé** → 404 sur
    les deux routes pour un autre utilisateur, 404 pour un envoi inconnu — jamais 403 (pas de
    fuite d'existence, même convention que `v3-upload`).
  - **Jeu de test de 30 photos et taux de détection** (mission point 3, détail ci-dessous).

### Taux de détection (mission point 3, objectif ≥ 95 %)

```
$ uv run python scripts/measure_detection_rate.py --out /tmp/detection-tuning-check
30 photos — images annotées et rapport dans /tmp/detection-tuning-check/
taux OpenCV seul     : 19/30 = 63.3%
taux avec repli SIMULÉ : 30/30 = 100.0%
```

Détail par famille (OpenCV seul → avec repli) : `carte_seule` 7/8 → 8/8, `classeur_3x3` 6/6 →
6/6, `classeur_3x3_reflets` 6/6 → 6/6, `table` (cartes en vrac, 2 à 5) 0/6 → 6/6, `fond_clair`
0/4 → 4/4. Rapport complet et 5 images annotées (une par famille) commitées dans
`docs/roadmap/comptes-rendus/echantillons-v3-detection/`.

**Le repli est simulé** dans cette mesure (voir « Écarts au plan ») : le double de fournisseur
renvoie les boîtes exactes de la photo synthétique plutôt qu'une vraie inférence vision. Le
chiffre de 95 % valide donc la **mécanique** du pipeline (le second passage détecte bien les
zones incohérentes, l'affinage OpenCV dans une boîte reconstruit le bon quadrilatère, le
recadrage et l'ordre de lecture sont corrects) — pas la précision réelle d'un LLM de vision sur
une vraie photo, qui reste à mesurer (voir « Reste à faire »).

```
$ pnpm --filter @pbm/web lint && pnpm --filter @pbm/web type-check && pnpm --filter @pbm/web test
✓ eslint . (aucune erreur)
✓ tsc --noEmit (aucune erreur)
✓ 18 fichiers, 51 tests passés (aucun changement front dans ce lot, non-régression vérifiée)
```

Aucun secret : ce lot ne manipule aucune clé IA en clair au-delà de ce que `v1-byok` déchiffre
déjà (même filtre de journalisation, déjà en place) ; aucune clé réelle utilisée nulle part
(doubles de test uniquement, comme `v3-ia-providers`).

## Choix techniques faits (autonomes, dans le cadre de `docs/ARCHITECTURE.md`)

- **Heuristique de repli = zone non réclamée**, pas seulement « zéro carte trouvée » : un second
  passage sur les mêmes contours (`has_unclaimed_regions`) cherche une région de la taille d'une
  carte qu'aucun quadrilatère retenu ne recouvre à plus de 70 % — signal direct de « nombre ou
  forme incohérent » (mission point 2) sans dépendre d'un nombre de cartes attendu, que le
  pipeline ne connaît jamais à l'avance. Mesuré : ce choix évite un appel IA inutile sur les
  photos propres (carte seule, classeur 3×3 — 0 appel) tout en déclenchant le repli sur les cas
  difficiles (table, fond clair). Seuil de recouvrement (70 %) et marge basse sur l'aire (60 % du
  seuil d'acceptation normal) calés empiriquement sur le jeu synthétique — **à retenir comme
  candidats de réglage** une fois de vraies photos disponibles (mission point 4, en continu).
- **Repli LLM = un seul appel par photo entière**, jamais par carte ni par boîte : conforme au
  principe JF du 19/09 (« un seul appel IA par carte, dès le premier tir ») qui vise
  l'identification — la détection est un cas différent (localiser, pas identifier) mais applique
  la même discipline de coût : une photo difficile ne coûte qu'un appel, quel que soit son
  nombre de cartes.
- **Premier job du dépôt enfilé depuis une route HTTP** (`pbm_api.queue.get_arq_pool`, pool par
  appel comme `pbm_api.security.rate_limit.get_redis`) : tous les jobs précédents (`import_
  catalogue`, `daily_prices`, `daily_exchange_rates`) sont en cron ou déclenchés en CLI direct —
  `v3-upload` créait la ligne `Job` mais ne la mettait jamais en file (documenté dans son
  compte rendu comme « reste à faire »). Ce lot comble ce manque plutôt que d'ajouter un
  mécanisme de dispatch parallèle : `arq_pool.enqueue_job("detect_cards_task", str(job.id))`
  juste après la création du `Job`, dans la même fonction `complete_upload`.
- **Repli affiné dans une sous-image, pas sur la photo entière** : `_refine_box_with_opencv`
  ne relance `find_card_quads` que dans la boîte du LLM (+ marge 8 %) — une boîte imprécise
  n'entraîne jamais un contour d'une autre carte, et l'affinage retombe sur le rectangle brut
  du LLM (mieux qu'aucune détection) si OpenCV ne trouve toujours rien dans la sous-image
  (pochette/reflet trop marqué).
- **Ordre de lecture reconstruit par regroupement de lignes** (tolérance = moitié de la hauteur
  moyenne des cartes détectées), pas par un simple tri Y puis X global : un tri global casserait
  l'ordre dès qu'une carte de la ligne du bas a un centre Y légèrement inférieur à une carte mal
  positionnée de la ligne du haut (léger flou/rotation) — le regroupement en lignes tolère ce
  bruit tant qu'il reste sous la moitié d'une hauteur de carte.
- **`estimated_cost_eur` laissé à 0** dans `record_usage` (premier appelant réel de cette
  fonction) : aucune table de tarification par modèle n'existe dans ce dépôt (ni dans
  `v1-byok`, ni `v3-ia-providers`) — inventer un barème dans ce lot aurait été hors périmètre.
  Compteurs d'appels et de jetons fiables dès aujourd'hui, coût estimé documenté en reste à
  faire.
- **`GET /uploads/{id}/detections` et `.../crop` ajoutées** bien que non explicitement listées
  dans la mission (silencieuse sur toute route HTTP) : nécessaires pour un test d'accès croisé
  significatif (mission § 6) et pour que les lots suivants (identification, validation humaine)
  aient un point d'entrée déjà borné par utilisateur plutôt que d'inventer le leur — cohérent
  avec la grille de clôture qui marque `maquette: sans objet (back-end)`, donc aucune page
  n'était attendue ici.

## Écarts au plan

- **Jeu de test « 30 photos réelles » remplacé par 30 photos synthétiques**
  (`pbm_api.detection.synthetic.generate_dataset`, graine fixe) : chimera n'a ni appareil photo
  ni carte Pokémon physique, et aucune photo de classeur n'était disponible dans le dépôt. Le
  générateur construit des scènes ressemblant aux quatre familles demandées (carte seule,
  classeur 3×3 en toploaders, table, reflets) plus le cas « fond clair » listé dans les risques
  du lot, avec un nombre de cartes connu par photo. **Conséquence directe** : le taux de 95 %
  mesuré valide la mécanique du pipeline sur des cas construits, pas la précision réelle
  d'OpenCV ni d'un LLM sur une vraie photo de classeur (reflets réels, pochettes en plastique
  réelles, éclairage réel). Non réductible depuis cette session : nécessite soit un appareil
  photo et des cartes physiques (aucun sur chimera), soit un lot de vraies photos fourni par JF.
- **Repli LLM jamais appelé avec une vraie clé** (mission : « aucune clé IA réelle disponible ») :
  toute la suite automatisée et le script de mise au point utilisent un double de fournisseur
  (boîtes exactes ou fixes, aucun réseau). Le script `scripts/measure_detection_rate.py` accepte
  déjà `--provider`/`--api-key` pour un essai manuel futur avec une vraie clé, sur de vraies
  photos une fois disponibles.
- **`estimated_cost_eur` non calculé** (voir « Choix techniques »).
- **Seuils OpenCV calés sur le jeu synthétique uniquement** (ratio ±12 %, recouvrement 70 % pour
  `has_unclaimed_regions`, marge de repli 8 %) : la mission prévoit une « mise au point » en
  continu sur chimera — ce lot pose l'outillage (`measure_detection_rate.py`) mais le réglage
  fin sur de vraies photos reste à faire une fois disponibles.
- **Aucune validation humaine ni rapprochement catalogue** (points 3-4 de la section
  « Reconnaissance » de `docs/ARCHITECTURE.md`) : hors mission de ce lot, dépendance déclarée du
  lot suivant (identification).

## Reste à faire (pour les lots suivants)

- Lot d'identification : consommer `Detection.bbox`/`crop_s3_key`, appeler `AIProvider.extract`
  pour nom/numéro/extension/langue/PV/variante (un seul appel par carte, principe JF du 19/09),
  rapprocher via `pbm_api.catalog.search.match_candidates` (déjà réutilisable, lot
  `v2-recherche`), écrire `Detection.candidates`/`selected_card_id`.
- Vraie campagne de photos (appareil + cartes physiques, hors chimera) pour mesurer le taux de
  détection réel et recalibrer les seuils OpenCV (`_RATIO_TOLERANCE`, seuil de recouvrement de
  `has_unclaimed_regions`, marge de `_refine_box_with_opencv`).
- Essai du repli avec une vraie clé IA (`scripts/measure_detection_rate.py --provider --api-key`)
  une fois une clé disponible.
- Table de tarification par modèle pour `estimated_cost_eur` (`ai_usage_monthly`) — inexistante
  dans tout le dépôt à ce jour, pas seulement ce lot.
- Front : aucune page attendue ici (« maquette : sans objet »), mais le lot d'identification ou
  de validation humaine consommera `GET /uploads/{id}/detections`/`.../crop` tels quels.

## Décisions provisoires utilisées

D4 (sans clé IA personnelle, reconnaissance désactivée dès `complete_upload` — ce lot ne change
rien à cette règle, il consomme le `Job` qu'elle conditionne déjà). D2/D8 hors périmètre,
confirmé (aucun déploiement, aucune tâche `release_uat`/`release_prod` traitée).
