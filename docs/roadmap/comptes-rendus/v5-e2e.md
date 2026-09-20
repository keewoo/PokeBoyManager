# Compte rendu — lot `v5-e2e` (Parcours e2e Playwright en CI)

## Résumé

Parcours e2e complet exercé de bout en bout par le navigateur : inscription → vérification
(Mailpit) → clé IA (simulée) → envoi de la photo de référence 3×3 → validation → collection
filtrée → fiche carte (`apps/web/e2e/parcours-complet.spec.ts`).

Contrairement aux e2e des lots précédents (`validation.spec.ts`, `card-detail.spec.ts`), dont le
résultat de reconnaissance est semé directement en base (aucune clé IA réelle disponible sur
chimera), ce lot fait tourner le **vrai** pipeline de bout en bout : un vrai fichier envoyé par le
navigateur, une vraie détection OpenCV, une vraie identification + rapprochement catalogue via un
vrai worker arq. Seul l'aller-retour réseau vers le fournisseur IA est remplacé par un fournisseur
simulé, jamais activé hors e2e.

## Livrables

- `apps/api/src/pbm_api/ai/simulated_provider.py` — `SimulatedProvider(AIProvider)`, activé par le
  drapeau `AI_SIMULATED_PROVIDER` (`pbm_api.config.Settings`, faux par défaut, jamais en UAT/PROD).
  Un seul point de fabrication modifié (`pbm_api/ai/factory.py::create_provider`) : aucun appel
  réseau, réponses déterministes (les neuf cartes de `pbm_api.seed.DEMO_CARDS`, servies dans
  l'ordre d'appel). Tout schéma non simulé (repli LLM de la détection, insights, étude en jeu) lève
  une erreur explicite plutôt qu'une réponse inventée.
- `apps/web/playwright.config.ts` — troisième entrée `webServer` : un vrai worker arq
  (`uv run arq pbm_api.worker.WorkerSettings`), nécessaire depuis que ce lot enfile un vrai job de
  reconnaissance (aucune autre spec n'en avait besoin jusqu'ici). `workers: 1` (au lieu du
  parallélisme par défaut de Playwright entre fichiers) et `timeout: 60_000` — voir « Écarts ».
- `apps/api/scripts/generate_e2e_reference_photo.py` — écrit la « photo de référence » du classeur
  3×3 (`pbm_api.detection.synthetic.make_binder_grid(glare=False)`, classeur propre).
- `apps/api/scripts/seed_e2e_reference_catalog.py` — sème (idempotent) les neuf cartes de
  démonstration + un historique de prix minimal, rafraîchit `card_value_rank`.
- `apps/api/tests/test_ai_providers.py` — trois tests unitaires sur `SimulatedProvider`/le drapeau
  de fabrique (isolés, sans navigateur).
- Correction d'un bogue latent trouvé en relançant `pbm_api.seed.seed()` : `User` exige
  `last_name`/`birth_date`/`terms_version`/`terms_accepted_at` depuis le lot `v1-identite`
  (migration `328aef94ea58`), postérieur à ce module jamais rejoué depuis — `seed()` échouait sur
  une contrainte NOT NULL. Corrigé avec les mêmes valeurs par défaut que
  `pbm_api.admin create-user` (consentement porté par JF).
- `CLAUDE.md` — section « Parcours e2e complet (lot v5-e2e) ».

## Preuves

- `uv run pytest -q` (apps/api, `TZ=Europe/Paris`, `TEST_DATABASE_URL=…/pbm_v5_e2e_test`) :
  **527 passed, 2 failed** — les 2 échecs (`test_catalogue_seed.py`, export/import) sont
  `pg_dump: command not found`, un binaire PostgreSQL client absent de cette session chimera (rien
  à voir avec ce lot ; CI l'installe via l'image officielle). `uv run ruff check .` : clean.
- `apps/api/tests/test_ai_providers.py` : 27 passed (dont les 3 nouveaux, un échoue sans la
  branche ajoutée à `create_provider` : `test_create_provider_returns_simulated_when_flag_enabled`
  renverrait `AnthropicProvider` au lieu de `SimulatedProvider`).
- `pnpm --filter @pbm/web lint|type-check|test|build` : clean, **81 passed** (vitest), build
  Next.js réussi (18 routes).
- `pnpm exec playwright test` (7 specs, `workers: 1`, worker arq + fournisseur simulé) :
  **6 passed, 1 failed** — le seul échec est `auth.spec.ts` (case CGU instable sous charge), déjà
  documenté comme pré-existant et sans rapport avec un lot précis dans
  `docs/roadmap/comptes-rendus/v4-fiche.md`. `parcours-complet.spec.ts` seul, isolé (aucune charge
  concurrente) : **1 passed** en 1,9 min, log worker arq :
  `detections_count: 9, method: 'opencv', identified_count: 9`.
- Test d'accès croisé propre à ce lot (dans `parcours-complet.spec.ts`) : un second utilisateur
  reçoit **404** sur `GET /uploads/{id}` et `GET /uploads/{id}/detections` de l'envoi réel du
  premier — jusqu'ici, l'isolation n'était exercée que sur un résultat *semé* directement en base
  (`validation.spec.ts`/`card-detail.spec.ts`), jamais sur un envoi/des détections produits par le
  vrai pipeline.

## Choix techniques

- **Fournisseur simulé plutôt que clé réelle** : la mission (§4) demande explicitement un
  « fournisseur simulé en e2e » — jamais de vraie clé/appel réseau vers un fournisseur IA depuis
  une CI publique ou depuis chimera (aucune clé disponible). `SimulatedProvider` s'insère au même
  point que les trois fournisseurs réels (`create_provider`), donc le reste du pipeline (détection,
  identification, rapprochement catalogue, cache) tourne identiquement à la production.
- **Un vrai worker arq dans `webServer`** plutôt qu'un `execFileSync` bloquant dans le test :
  cohérent avec la façon dont l'API et le front sont déjà démarrés dans ce fichier, partagé par
  toutes les specs sans changer leur fonctionnement (elles n'enfilent jamais de job).
- **Photo de référence = classeur 3×3 propre (sans reflets)** : `make_binder_grid(glare=False)`
  est détecté à 100 % par OpenCV seul (mesuré par `v3-detection`), donc le repli LLM de la
  détection n'est jamais exercé par ce test — `SimulatedProvider` n'a besoin de simuler que
  `CardExtraction` (identification/état), pas le schéma de bounding-boxes du repli.
- **Neuf cartes identifiées ⇒ neuf « Sarmuraï », pas neuf cartes distinctes** : les recadrages du
  classeur synthétique sont visuellement indiscernables (mêmes couleurs/formes,
  `pbm_api.detection.synthetic.draw_card`, pensé pour la géométrie de détection, pas pour
  l'identification). Leur empreinte perceptuelle est donc identique, et
  `identification_cache` (une vraie fonctionnalité de production, pas un artefact de la
  simulation) résout les huit détections suivantes sans repasser par le fournisseur après le
  premier appel. Plutôt que de contourner ce comportement réel, le test l'assume : neuf exemplaires
  confirmés (doublons), filtre de collection exercé dans les deux sens (une recherche qui trouve
  une carte présente, une qui n'en trouve aucune).
- **`workers: 1`** : toutes les specs e2e partagent une unique instance API/DB/Redis/S3 (les trois
  entrées `webServer`) — Playwright lance par défaut plusieurs workers en parallèle sur des
  fichiers différents, ce qui a fait cohabiter deux transactions concurrentes sur la même carte de
  catalogue (`Sarmuraï`, partagée par `parcours-complet.spec.ts` et le seed de
  `validation.spec.ts`) : un `DeadlockDetectedError` Postgres reproductible en 4 workers, disparu
  en 1. Bénéfice pour l'ensemble de la suite, pas seulement ce lot.
- **`timeout: 60_000`** (au lieu des 30 s par défaut) : chimera héberge plusieurs lots autonomes en
  parallèle (`~/dev/lots/pbm-scheduler.sh`) ; sous charge partagée, une action DOM ordinaire peut
  dépasser 30 s sans régression réelle (déjà observé par `v4-fiche` sur `auth.spec.ts`, reproduit
  ici sur les sept specs à la fois). La CI GitHub Actions (runner dédié, sans cette contention)
  reste l'autorité finale.
- **Bouton « Tester » de la clé IA volontairement non cliqué** : il appellerait réellement le
  fournisseur (`ProviderKeyTester`, un aller-retour HTTP distinct de `create_provider`) — la
  mission (§4) réserve les appels réels à « un test manuel par semaine », jamais à l'e2e
  automatisé.
- **Onglets Histoire/En jeu de la fiche carte hors périmètre** : ils appelleraient un vrai wiki et
  la clé IA pour des schémas que `SimulatedProvider` ne simule pas (il ne simule que
  `CardExtraction`, seul schéma réellement exercé par ce parcours) — déjà couverts sans réseau par
  `card-detail.spec.ts` (résultat seedé avec cache d'insights pré-rempli).

## Écarts au plan

- La mission attendait implicitement une diversité de cartes en collection (« collection
  filtrée ») ; le résultat réel est neuf exemplaires de la même carte, pour la raison exposée
  ci-dessus (empreinte perceptuelle identique des recadrages synthétiques). Le filtre est quand
  même prouvé dans les deux sens. Une diversité réelle demanderait des photos physiquement
  distinctes, indisponibles sur chimera (même contrainte que documentée par `v3-detection`).
- `test_catalogue_seed.py` (2 tests, pré-existants, hors périmètre de ce lot) échoue sur ce poste
  faute de `pg_dump` — non installé dans cette session chimera. Signalé, non corrigé (nécessiterait
  d'installer `postgresql-client`, hors périmètre e2e).
- `auth.spec.ts` reste flaky sous charge concurrente sur chimera (case CGU) — pré-existant,
  documenté par `v4-fiche`, confirmé de nouveau ici. `timeout: 60_000` réduit le bruit mais ne
  l'élimine pas complètement ; la CI GitHub Actions fait foi.

## Reste à faire

- Rien d'identifié dans le périmètre de ce lot. Le test manuel hebdomadaire avec une vraie clé IA
  (mission §4) reste, comme pour les lots précédents, à la charge de JF hors chimera.

## Décisions provisoires utilisées

D4 (sans clé IA → reconnaissance désactivée, ajout manuel toujours possible) — confirmée par
construction : `SimulatedProvider` ne contourne cette règle qu'en e2e, jamais en production.
