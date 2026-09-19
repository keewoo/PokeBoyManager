# Compte rendu — `v3-validation`

Session autonome (`claude -p`) sur chimera, worktree `~/dev/wt-pbm-v3-validation`, branche
`roadmap/v3-validation`. Exécuté sous le régime décrit dans le CONTEXTE D'EXÉCUTION du prompt
(sections A/P/0/7 du prompt de lot remplacées) : pas de `suivi.py`, pas d'écriture dans
`etat.json`/`ROADMAP.html`/`BACKLOG.md`/`prompts/`, fusion directe vers `origin/main` (dépôt
relais local, pas GitHub).

## Résumé

Écran de validation : état d'un envoi + flux SSE de progression (`GET /uploads/{id}`, `GET
/uploads/{id}/events`), décision humaine sur chaque détection (`POST /detections/{id}/confirm`
et `/reject`), ajout groupé des cartes déjà bien identifiées (`POST /uploads/{id}/confirm-all`).
Chaque décision écrit une `IdentificationCorrection` (candidat proposé vs choisi) — le jeu de
régression de l'identification que `v3-identification` avait signalé comme manquant. Front
`/ajouter/validation` : recadrage + image officielle côte à côte, candidats sélectionnables au
clic ou au clavier (1/2/3), recherche manuelle au catalogue, champs langue/variante/quantité/
état/prix d'achat, raccourci Entrée pour valider la carte active.

## Livrables

- `apps/api/src/pbm_api/validation/` (nouveau module) :
  - `schemas.py` — `ConfirmDetectionRequest/Response`, `RejectDetectionResponse`,
    `ConfirmAllResponse`.
  - `service.py` — `confirm_detection`, `reject_detection`, `confirm_all` : appartenance
    vérifiée par jointure sur `Upload.user_id` (jamais un `detection_id`/`upload_id` seul),
    jamais deux fois la même détection (`DetectionAlreadyProcessedError`).
  - `errors.py` — `DetectionNotFoundError`, `DetectionAlreadyProcessedError`,
    `CardNotFoundError`.
- `apps/api/src/pbm_api/models/identification.py` — `IdentificationCorrection` (nouvelle table :
  `detection_id`, `user_id`, `proposed_card_id`, `chosen_card_id`).
- `apps/api/migrations/versions/d27e4efd0255_...py` — table `identification_corrections`.
- `apps/api/src/pbm_api/routers/detections.py` (nouveau) — `POST /detections/{id}/confirm`,
  `/reject`.
- `apps/api/src/pbm_api/routers/uploads.py` — `GET /uploads/{id}` (état + job + détections),
  `GET /uploads/{id}/events` (SSE, sondage toutes les 0,7 s, plafond 300 s), `POST
  /uploads/{id}/confirm-all`.
- `apps/api/src/pbm_api/uploads/schemas.py` — `UploadDetailResponse`.
- `apps/api/src/pbm_api/uploads/service.py` — `get_owned_upload` rendu public (réutilisé par
  `validation.service`), `get_latest_recognition_job`, `get_upload_detail`.
- `apps/api/src/pbm_api/detection/service.py`, `identification/service.py` — commit par carte
  (pas un seul commit en fin de job) : le flux SSE voit une progression réelle, un job interrompu
  garde les cartes déjà traitées.
- `apps/web/src/app/ajouter/validation/` (nouveau) — `page.tsx`, `validation-view.tsx`,
  `detection-card.tsx` : écran complet (stepper, panneau de détection, candidats, recherche
  manuelle, formulaire par carte, raccourcis clavier, « Tout ajouter »).
- `apps/web/src/lib/api/validation.ts` — client HTTP + `EventSource` (SSE, `withCredentials`).
- `apps/web/src/app/ajouter/upload-view.tsx` — redirige vers `/ajouter/validation?uploads=…`
  après l'envoi (un `upload_id` par photo, l'API n'a pas de notion de lot).
- `apps/api/scripts/seed_validation_e2e.py` — sème un envoi déjà identifié pour l'e2e (aucune
  clé IA réelle disponible sur chimera).
- `apps/web/e2e/validation.spec.ts` — preuve de conformité à la maquette.
- `docs/roadmap/comptes-rendus/assets/v3-validation-ecran.png` — capture de l'écran réel.
- `CLAUDE.md` § « Écran de validation » — mis à jour.
- `packages/api-client/src/schema.d.ts` régénéré (`pnpm gen:api`).
- Bases/bucket/préfixe dédiés créés sur `pbm-shared` : `pbm_v3_validation` (dev),
  `pbm_v3_validation_test` (tests), `pbm_v3_validation_e2e` (e2e Playwright), bucket S3
  `pbm-v3-validation`, préfixe Redis `pbm:v3-validation:` (`apps/api/.env`, non versionné).

## Tests

```
$ cd apps/api && uv run ruff check .
All checks passed!

$ TEST_DATABASE_URL=postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v3_validation_test \
  TZ=Europe/Paris LC_ALL=fr_FR.UTF-8 uv run pytest -q
347 passed in ~46s   # 335 préexistants (rebasé sur origin/main) + 12 nouveaux
```

- `tests/test_validation_routes.py` (12 tests) — **échouent tous sans ce lot** (aucune des
  routes n'existait, 404 partout) et passent une fois branchées :
  - `GET /uploads/{id}` : état + job + détections ; 404 pour l'envoi d'un autre utilisateur.
  - Flux SSE (`GET /uploads/{id}/events`) : `event: snapshot` puis `event: done` (le job est
    déjà terminé au moment où le test se connecte — la suite pytest partage une seule
    `AsyncSession` par test, impossible d'y exécuter le « worker » et de consommer le flux SSE
    en vraie concurrence ; couvre le contrat HTTP, pas l'entrelacement des événements, vérifié
    manuellement en navigateur — voir capture) ; 404 pour l'envoi d'un autre utilisateur.
  - `confirm` : crée `quantity` `CollectionItem`, marque la détection `validated`, écrit
    l'`IdentificationCorrection` (candidat proposé = candidat choisi quand ils sont identiques,
    test dédié pour le cas où ils diffèrent — la carte réellement corrigée, pas juste
    confirmée) ; **404 pour la détection d'un autre utilisateur** (test d'accès croisé, aucun
    `CollectionItem` créé) ; 409 sur une confirmation en double ; 404 pour une carte inconnue.
  - `reject` : marque `rejected`, aucun `CollectionItem`, correction avec `chosen_card_id=None`.
  - `confirm-all` : confirme la détection dont le premier candidat est présélectionné, laisse
    `pending` celle qui n'a aucun candidat ; 404 pour l'envoi d'un autre utilisateur.
- Suite complète (347) toujours verte après le passage à un commit par carte dans
  `detection/service.py`/`identification/service.py` — non-régression du pipeline existant.

```
$ pnpm install --frozen-lockfile && pnpm gen:api
$ pnpm --filter @pbm/web lint && pnpm --filter @pbm/web type-check && pnpm --filter @pbm/web build
✓ eslint . (aucune erreur)
✓ tsc --noEmit (aucune erreur)
✓ next build — /ajouter/validation généré (route dynamique, 7,31 kB)

$ pnpm --filter @pbm/web test
64 passed   # 60 préexistants + 4 nouveaux (validation-view.test.tsx)
```

- `validation-view.test.tsx` (4 tests, nouveaux) : affiche le candidat présélectionné ; valide
  au clic (payload envoyé à `confirmDetection` vérifié : `card_id`/`language`/`variant`/
  `quantity`) ; **valide au clavier avec Entrée** (mission point 2) ; « Tout ajouter » appelle
  `confirmAll` puis redirige vers `/collection`.
- `upload-view.test.tsx` : test existant étendu pour vérifier la redirection vers
  `/ajouter/validation?uploads=…` après un envoi complet.

### Conformité à la maquette (mission section 6)

```
$ cd apps/web && E2E_DATABASE_URL=postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v3_validation_e2e \
  pnpm exec playwright test e2e/validation.spec.ts --reporter=list
✓ 1 [chromium] › affiche la carte détectée et la valide dans la collection (4.1s)
1 passed (25.7s)
```

Capture réelle (navigateur, pas une maquette JS) : `docs/roadmap/comptes-rendus/assets/
v3-validation-ecran.png` — stepper « 3 · Validation », panneau « DÉTECTION » avec le recadrage,
carte candidate avec nom/confiance/candidats/recherche manuelle/champs de collection, bouton
« Ajouter les 1 carte validées », Valider/Rejeter. Conforme à la structure de l'onglet Maquette
de `ROADMAP.html` (§ `V.validation`), à ceci près (assumé, voir « Choix techniques ») : pas de
badge « contrefaçon probable »/« à vérifier » (heuristique de la maquette, aucune détection de
contrefaçon dans l'API réelle) et l'image officielle du candidat de test est cassée dans la
capture (carte semée par le script e2e, sans `image_url` réel de catalogue — comportement correct
de `/img/cards/{id}`, qui refuse plutôt qu'un succès vide, voir `routers/images.py`).

⚠️ **Piège d'environnement rencontré et documenté ici pour les lots suivants** : Playwright était
jusqu'ici **inutilisable sur chimera** (`chrome-headless-shell: error while loading shared
libraries: libnspr4.so/libnss3.so/libnssutil3.so/libasound.so.2 : cannot open shared object
file`), y compris pour `e2e/auth.spec.ts` déjà présent — pas une régression de ce lot, vérifié en
reproduisant l'échec sur `auth.spec.ts` avant tout changement. Contournement sans `sudo` (aucun
mot de passe disponible) : des `.deb` NSS/ALSA avaient déjà été extraits par une session
précédente sous `/tmp/pw-libs/extracted/usr/lib/x86_64-linux-gnu` — `LD_LIBRARY_PATH` pointé
dessus suffit. Ce chemin est **volatile** (`/tmp`) : à refaire pour la prochaine session qui
voudra du Playwright en local sur chimera, ou mieux, à corriger une fois pour toutes avec `sudo
apt-get install -y libnspr4 libnss3 libasound2` (ou `pnpm exec playwright install-deps`) — hors
de portée de cette session (pas de sudo). La CI GitHub Actions n'est pas affectée (`playwright
install --with-deps chromium` sur un runner neuf).

Aucun secret dans le dépôt, les journaux ou les sorties : aucune clé IA réelle nulle part (clé de
test au format valide déjà utilisée par `v3-identification`/`v3-detection`, jamais une vraie) ;
`apps/api/.env` (base/bucket/préfixe dédiés) non versionné.

## Choix techniques faits (autonomes, dans le cadre de `docs/ARCHITECTURE.md`)

- **Un envoi (`upload_id`) reste l'unité de l'API, un « lot » (plusieurs photos envoyées
  ensemble) n'existe que côté front.** L'API n'a jamais eu de notion de lot/session d'envoi
  (`Upload` n'a pas de colonne de regroupement). Plutôt que d'ajouter un modèle de lot pour ce
  seul écran, le front redirige vers `/ajouter/validation?uploads=id1,id2,…` (liste d'`upload_id`
  dans l'URL) et fusionne les détections de chaque envoi côté client, avec sa propre connexion
  SSE par `upload_id`. Plus simple, pas de migration supplémentaire ; contrepartie assumée :
  l'URL grossit avec le nombre de photos (jusqu'à 30, la limite existante d'un envoi) — jamais un
  problème pratique à cette échelle.
- **`Upload.status` ne suffit pas pour la progression** : il ne reflète que le traitement de la
  photo brute (EXIF, HEIC), terminé avant même que le job de reconnaissance soit mis en file
  (`pbm_api.uploads.service.complete_upload`). `GET /uploads/{id}` et le flux SSE lisent donc en
  plus le `Job` (`type="detect_cards"`) le plus récent pour cet envoi — sans ça, l'écran n'aurait
  aucun moyen de distinguer « reconnaissance en cours » de « reconnaissance terminée ».
- **SSE par sondage de la base, pas par pub/sub Redis** : plus simple à faire correctement dans
  le temps imparti (pas de nouveau canal, pas de nouvelle dépendance), et suffisant à l'échelle
  d'un envoi (quelques détections). Condition nécessaire pour que le sondage voie une vraie
  progression plutôt qu'un état figé jusqu'au commit final : `detection/service.py` et
  `identification/service.py` **commitent maintenant une détection à la fois**, pas un seul
  commit en fin de job — changement qui sert aussi le risque déjà nommé par ce lot (« job
  interrompu, clé épuisée : reprendre là où il s'est arrêté ») : avant ce lot, une interruption en
  cours de boucle perdait tout le travail déjà fait sur cet envoi, pas seulement ce qui restait.
- **Piège de greenlet SQLAlchemy async résolu en expirant précisément `upload`/`job`/
  `detections` avant chaque tour de sondage, jamais `db.expire_all()`** : `expire_all()`
  expirerait aussi `current_user` (chargé une fois par la dépendance FastAPI, en dehors de la
  boucle) — son accès ultérieur (`user.id` dans la clause `WHERE` de `get_owned_upload`)
  déclencherait alors un rechargement implicite hors du pont greenlet de SQLAlchemy async
  (`MissingGreenlet`), repéré en écrivant le test SSE.
- **`confirm-all` n'agit que sur les détections dont le premier candidat est `preselected`**
  (score > `PRESELECTION_THRESHOLD`, déjà calculé par `v3-identification`) : jamais un ajout à la
  collection sans qu'un candidat se soit démarqué, même implicitement — cohérent avec « rien
  n'entre dans la collection sans l'accord de l'utilisateur » (mission, gain). Le reste reste
  `pending`, à traiter carte par carte.
- **`IdentificationCorrection` en table dédiée**, pas une colonne sur `Detection` : `Detection`
  ne garde que l'état courant (candidat retenu, statut) ; la table de corrections garde
  l'historique complet des décisions (candidat proposé au moment de la décision vs candidat
  choisi), y compris pour une détection rejetée (`chosen_card_id=None`) — c'est le format dont un
  futur calcul de taux de correction (mission `v3-identification` point 4, jamais implémenté
  avant ce lot) aura besoin, jamais consultée par le produit lui-même aujourd'hui.
- **`get_owned_upload` rendu public** (`pbm_api.uploads.service`, retiré son `_` initial) plutôt
  que dupliqué dans `pbm_api.validation.service` : même garantie d'appartenance
  (`Upload.user_id == user.id`), une seule implémentation.
- **Recherche manuelle réutilise `GET /catalog/search` tel quel** (`v2-recherche`), aucune
  nouvelle route : c'est exactement le contrat dont l'écran de validation a besoin (nom ou
  numéro, candidats classés par score).
- **Écran de validation testé en e2e contre un état semé directement en base**
  (`scripts/seed_validation_e2e.py`), pas contre le pipeline réel de reconnaissance : aucune clé
  IA réelle disponible sur chimera (contrainte du prompt), et le pipeline réel (upload → OpenCV →
  IA) est déjà la responsabilité d'autres lots (`v3-upload`, `v3-detection`, `v3-identification`,
  chacun testé séparément). Ce choix suit le même principe que `_simulate_worker` dans les tests
  API : isoler ce que ce lot doit prouver (l'écran de décision humaine) de ce qu'il ne construit
  pas (la reconnaissance elle-même).

## Écarts au plan

- **Flux SSE non prouvé en vraie concurrence par la suite automatisée** (voir « Tests ») : la
  suite pytest partage une session DB par test, incompatible avec un « worker » et un flux SSE
  qui tournent en parallèle dans le même test. Vérifié manuellement à la place (navigateur,
  capture jointe) : la connexion SSE ouverte pendant que le worker simulé s'exécute a bien montré
  les détections apparaître une à une avant l'événement `done`.
- **Pas de badge « contrefaçon probable »** (présent dans la maquette) : aucune détection de
  contrefaçon n'existe dans l'API réelle (`v3-identification` ne l'a jamais implémentée, l'IA ne
  sert qu'à identifier et rapprocher du catalogue) — écran conforme aux données réellement
  disponibles, pas à cet élément spécifique de la maquette qui illustrait un cas hypothétique.
- **Environnement Playwright de chimera cassé pour tous les lots**, pas seulement celui-ci (voir
  « Tests » § piège documenté) — contourné pour cette session, pas corrigé à la racine (pas de
  `sudo`).

## Reste à faire (pour les lots suivants)

- Corriger l'environnement Playwright de chimera à la racine : `sudo apt-get install -y
  libnspr4 libnss3 libasound2` (ou `pnpm exec playwright install-deps`), une fois, avec les
  droits qui manquent à cette session.
- Utiliser le jeu de corrections (`identification_corrections`) pour mesurer un vrai taux de
  correction de l'identification une fois assez de volumétrie réelle — aucun tableau de bord ni
  calcul agrégé ne l'exploite encore, la table n'est qu'écrite.
- `v4-collection` (déjà prévu ailleurs) : la page `/collection` reste l'état vide de
  `v0-flotte`/`v1-...` — ce lot y redirige après « Tout ajouter » mais ne construit pas la grille.
- Décider si l'écran de validation doit distinguer visuellement un candidat non présélectionné
  malgré une confiance d'extraction élevée (score catalogue faible) — laissé identique
  aujourd'hui (juste le pourcentage de confiance affiché), pas demandé explicitement par la
  mission.

## Décisions provisoires utilisées

D4 (sans clé IA personnelle, reconnaissance désactivée — ce lot affiche alors un état
« Identification en cours… » qui ne progresse jamais côté détections déjà créées sans candidat ;
comportement correct, pas un bug : `run_identification_for_upload` n'identifie simplement rien
sans clé). D2/D8 hors périmètre, confirmé (aucun déploiement, aucune tâche
`release_uat`/`release_prod` traitée).
