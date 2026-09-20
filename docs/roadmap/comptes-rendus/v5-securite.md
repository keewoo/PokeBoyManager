# Compte rendu — `v5-securite`

Session autonome (`claude -p`) sur chimera, worktree `~/dev/wt-pbm-v5-securite`, branche
`roadmap/v5-securite`. Exécuté sous le régime décrit dans le CONTEXTE D'EXÉCUTION du prompt
(sections A/P/0/7 du prompt de lot remplacées) : pas de `suivi.py`, pas d'écriture dans
`etat.json`/`ROADMAP.html`/`BACKLOG.md`/`prompts/`, fusion directe vers `origin/main` (dépôt
relais local, pas GitHub).

## Résumé

Revue de sécurité avant ouverture au public, sur l'ensemble des routes du MVP déjà fusionnées
(dépendances `v4-fiche`/`v5-rgpd`/`v3-validation` déjà dans `origin/main`, ordre garanti par
l'ordonnanceur). Quatre axes de la mission traités : accès croisé (IDOR), en-têtes/cookies/
CORS/débit/taille d'envoi, journaux, dépendances — plus SSRF et envoi de fichiers malveillants
(risques explicitement cités par le plan). Détail complet, avec preuves, dans
`docs/SECURITE.md`.

**Verdict global : posture déjà solide sur l'isolation entre comptes** (chaque lot précédent
avait bien posé son test d'accès croisé, conformément à la règle du dépôt). Les vrais manques
étaient ailleurs : aucun en-tête de sécurité de réponse (CSP/HSTS/frame-ancestors/nosniff)
n'existait sur aucune des deux applications avant ce lot, et une taille d'envoi non bornée côté
stockage S3 (dev/CI, pas la cible PROD) aurait pu épuiser la mémoire de l'API.

## Livrables

- `apps/api/src/pbm_api/security/headers.py` (nouveau) — `SecurityHeadersMiddleware`,
  en-têtes défensifs + CSP sur toute réponse de l'API (sauf `/docs`/`/redoc`/`/openapi.json`).
- `apps/api/src/pbm_api/main.py` — middleware branché, `install_secret_url_redaction()` appelé
  au démarrage.
- `apps/api/src/pbm_api/security/log_filter.py` — `install_secret_url_redaction`/
  `redact_secret_urls` (jetons d'URL masqués dans les journaux, même mécanisme que la
  redaction de clé IA déjà en place ; factorisé en un seul `_install_redaction` commun aux deux).
- `apps/web/src/middleware.ts` — élargi à toutes les pages, CSP avec nonce par requête sur
  `script-src`, en-têtes défensifs.
- `apps/web/src/app/layout.tsx` — le script inline (anti-flash de thème) porte désormais le
  nonce de la requête (`headers()`/`next/headers`).
- `apps/api/src/pbm_api/routers/auth.py` — `/auth/register` limité en débit par IP.
- `apps/api/src/pbm_api/routers/collection.py` — `GET /me/collection/{item_id}` reroutée par
  `service.get_owned_item` (cohérence avec le reste du fichier, pas une faille observée).
- `apps/api/src/pbm_api/s3.py`, `apps/api/src/pbm_api/storage/local.py` — méthode `head()`
  (taille sans téléchargement) sur les deux backends de stockage.
- `apps/api/src/pbm_api/uploads/service.py`, `routers/uploads.py`, `uploads/errors.py` —
  `UploadTooLargeError`/413 : un objet plus gros que `upload_max_size_bytes` déposé via une URL
  présignée S3 est détecté et supprimé avant d'être chargé en mémoire, jamais après.
- `apps/api/src/pbm_api/catalog/import_service.py` — `_is_safe_image_url` (défense en
  profondeur SSRF sur `Card.image_url`, schéma + IP privée/loopback/lien-local).
- Tests : `test_security_headers.py` (nouveau, 4 tests), `test_log_filter.py` (+4),
  `test_validation_routes.py` (+1, accès croisé `reject`), `test_ai_keys.py` (+1, accès croisé
  `/test`), `test_auth.py` (+1, limitation de débit `/auth/register`), `test_uploads.py` (+1,
  objet surdimensionné sur le backend S3), `test_import_service.py` (+6, garde SSRF),
  `apps/web/src/__tests__/middleware.test.ts` (+4).
- `.github/workflows/ci.yml` — `pip-audit` (job `api`, bloquant) et `pnpm audit` (job `web`,
  non bloquant, voir raison dans `docs/SECURITE.md`).
- `docs/SECURITE.md` (nouveau) — rapport complet : ce qui a été testé, corrigé, laissé en
  l'état et pourquoi.
- Bases dédiées créées sur l'infra partagée `pbm-shared` : `pbm_v5_securite` (dev),
  `pbm_v5_securite_test` (tests), `pbm_v5_securite_e2e` (preuve en conditions réelles),
  `apps/api/.env` local (gitignored), `REDIS_PREFIX=pbm:v5-securite:`, bucket
  `pbm-v5-securite`.

## Preuves

Voir `docs/SECURITE.md` § Preuves pour le détail complet (541 tests API, 84 tests web, lint/
type-check/build propres, `pip-audit`/`pnpm audit`, en-têtes et nonce vérifiés en conditions
réelles par requêtes HTTP directes contre un `next start` + `uvicorn` réels). Résumé :

```
$ cd apps/api && uv run ruff check . && TEST_DATABASE_URL=postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v5_securite_test \
  TZ=Europe/Paris uv run pytest -q
All checks passed!
541 passed, 2 deselected in ~214s
# déselectionnés : test_catalogue_seed.py, pg_dump absent de cette machine (préexistant, sans
# rapport avec ce lot — voir « Écarts »)

$ cd apps/web && pnpm --filter @pbm/web lint && pnpm --filter @pbm/web type-check \
  && pnpm --filter @pbm/web test && pnpm --filter @pbm/web build
# aucune erreur — 25 fichiers, 84 tests passés — build de production réussi (18 routes)
```

## Choix techniques faits (autonomes, dans le cadre de `docs/ARCHITECTURE.md`)

- **CSP par nonce plutôt que `'unsafe-inline'` sur `script-src`** (`apps/web`) : le mécanisme
  documenté par Next.js (middleware génère un nonce, le pose sur l'en-tête `x-nonce` de la
  requête *et* dans la CSP de la réponse ; Next.js l'applique alors automatiquement à tous les
  scripts qu'il génère) — vérifié en conditions réelles que le nonce de l'en-tête et celui de
  chaque balise `<script>` rendue coïncident exactement. `style-src` garde `'unsafe-inline'`
  (deux composants posent une couleur dynamique via l'attribut `style`, qui ne peut pas porter
  de nonce) — compromis documenté, une injection CSS pèse nettement moins qu'une injection JS.
- **`pip-audit` bloquant, `pnpm audit` non bloquant** : asymétrie voulue. `pip-audit` ne remonte
  aucune faille (état atteignable, une régression doit bloquer). `pnpm audit` remonte 11
  vulnérabilités déjà présentes dans les devDependencies de build (`vite`/`vitest`/`postcss`/
  `esbuild`), dont un vrai correctif exigerait un saut de version majeure partagé par tout
  `apps/web` pendant que d'autres lots y travaillent en parallèle — bloquer la CI dessus
  aurait empêché **tout** merge futur pour une faille sans impact production (devDependencies,
  jamais expédiées dans le bundle). Rendu visible plutôt que masqué : c'est le sens de « non
  bloquant », pas « ignoré ».
- **Rejet du dépôt surdimensionné après coup (`head` + suppression), pas un refus à l'écriture**
  côté S3 : un présignage POST avec condition `content-length-range` aurait vraiment empêché le
  dépôt, mais change le contrat front/back du flux d'envoi (`POST /uploads` renverrait une
  méthode/des champs différents) — hors budget de cette revue, et sans impact PROD puisque le
  backend réel y est `local` (déjà protégé en amont, `PUT /uploads/{id}/raw` vérifie
  `Content-Length` avant d'écrire).
- **`_is_safe_image_url` par schéma + IP privée, pas liste blanche stricte du domaine
  `assets.tcgdex.net`** : une liste blanche stricte aurait cassé les doublures de test
  existantes (`https://x/...`, `tests/test_import_service.py`, fidèles en forme mais pas en
  domaine) sans que ce lot ait le périmètre pour les retoucher toutes. Le contrôle retenu
  bloque quand même le scénario réaliste (SSRF vers métadonnées cloud/réseau interne).
- **Redaction des jetons d'URL factorisée avec celle des clés IA** (`log_filter.py`) : même
  mécanisme (`logging.setLogRecordFactory`, chaîné), motifs distincts, pour ne pas mélanger deux
  familles de secrets dans une seule expression régulière — `_install_redaction` commun,
  extrait pendant ce lot (le code d'origine dupliquait la boucle de fabrique).

## Écarts au plan

- **Aucune capture de conformité maquette** : ce lot n'a posé aucun nouvel écran (mission « sans
  objet : sans écran », grille `maquette` du plan). Sans objet, pas un écart.
- **Vérification CSP en navigateur réel non faite** : le Chromium headless de Playwright ne
  démarre pas sur cette machine (`libnspr4.so` manquant, `playwright install-deps` exige un
  `sudo` avec mot de passe indisponible en session autonome — limitation déjà rencontrée et
  documentée par `v5-rgpd`). Contournée par une vérification directe des en-têtes HTTP et du
  nonce rendu (serveur `next start` + `uvicorn` réels, voir preuves) : confirme le câblage,
  mais ne constate pas l'absence d'erreur CSP dans une vraie console de navigateur — la CI
  (`e2e`, runner complet avec dépendances système) fait foi pour ce dernier point.
- **`test_catalogue_seed.py` (2 tests, hors périmètre de ce lot)** échoue localement :
  `pg_dump` absent de cette machine (`postgresql-client` non installé, pas de `sudo`).
  Préexistant, sans rapport avec les changements de ce lot (vérifié : fichier non touché).
  GitHub Actions (`ubuntu-latest`) fournit `postgresql-client` de base — la CI n'est pas
  affectée. Déselectionnés explicitement pour la preuve locale.
- **`pnpm audit` : 11 vulnérabilités non corrigées** (devDependencies de build) — voir
  `docs/SECURITE.md` § Reste à faire pour le détail et pourquoi ce n'est pas traité ici.

## Reste à faire

Voir `docs/SECURITE.md` § 7 (Reste à faire) pour le détail complet. Résumé :
- Dépendances JS de build (`vite`/`vitest`/`postcss`/`esbuild`) à mettre à jour par un lot dédié
  (saut de version majeure, hors budget d'une revue de sécurité ponctuelle) — suivi par l'étape
  `pnpm audit` non bloquante ajoutée à la CI.
- Limitation de débit sur `POST /me/ai-keys/{provider}/test` (faible priorité).
- Présignage S3 avec vraie limite de taille imposée à l'écriture (`content-length-range`), au
  lieu du rejet après coup actuel — sans impact PROD (backend réel = `local`).
- Capture réelle en navigateur du comportement CSP, dès qu'un environnement avec Chromium
  fonctionnel est disponible (ou en CI, qui l'a déjà).

## Décisions provisoires utilisées

D2/D8 (hébergement, ouverture) hors périmètre, confirmé : aucun déploiement dans ce lot. Le
reste (D3/D4/D5/D6/D7) sans objet pour cette revue — aucune source de prix, reconnaissance IA,
classement ou politique d'e-mail retouchés ; D7 (stockage S3/local) directement concerné par le
correctif de taille d'envoi, appliqué symétriquement aux deux backends.
