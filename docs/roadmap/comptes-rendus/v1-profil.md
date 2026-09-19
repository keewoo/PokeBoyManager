# Compte rendu — `v1-profil`

Session autonome (`claude -p`) sur chimera, worktree `~/dev/wt-pbm-v1-profil`, branche
`roadmap/v1-profil`. Exécuté sous le régime décrit dans le CONTEXTE D'EXÉCUTION du prompt
(sections A/P/0/7 du prompt de lot remplacées) : pas de `suivi.py`, pas d'écriture dans
`etat.json`/`ROADMAP.html`/`BACKLOG.md`/`prompts/`, dépendances `v1-pages-auth` et `v1-byok`
déjà fusionnées dans `origin/main` (dépôt relais local, pas GitHub).

## Résumé

Page `/profil` complète en 4 onglets (Identité, Sécurité, Mon IA, Mes données), conforme à la
maquette (`docs/roadmap/ROADMAP.html`, fonction `V.profil`). Routes back manquantes posées :
`GET/PATCH /me` (pseudo), `POST /me/avatar` (recadrage carré côté serveur), `GET /me/avatar`,
`POST /me/email` + `POST /me/email/confirm` (re-vérification, ancienne adresse notifiée),
`POST /me/password` (rotation des autres sessions, session courante conservée),
`GET /me/sessions` + `DELETE /me/sessions/{id}`, `DELETE /me` (suppression du compte, mot de
passe requis). Front : onglet « Mon IA » branché sur les routes déjà posées par `v1-byok`
(`/me/ai-keys`, `/me/ai-settings`, `/me/ai-usage`) — aucun front n'existait encore pour elles.

Stockage des photos utilisateur (avatar) derrière une interface à deux implémentations
(`pbm_api.photo_storage.PhotoStorage`, `STORAGE_BACKEND=s3` en dev/CI ou `local` pour
l'UAT/PROD sans Docker), comme prescrit par le contexte d'exécution et
`docs/infra/SERVEUR-POKEBOY.md` (disque local recommandé pour le lancement).

## Livrables

**Back (`apps/api`)**
- `pbm_api/photo_storage.py` — `PhotoStorage` (backends `s3`/`local`), `pbm_api/s3.py` complété
  d'un `delete`.
- `pbm_api/profile/` — `avatar.py` (recadrage centré en carré + redimensionnement 512×512 +
  ré-encodage JPEG via Pillow, nouvelle dépendance), `errors.py`, `schemas.py`, `service.py`
  (logique métier pure, comme `pbm_api.auth.service`).
- `pbm_api/routers/profile.py` — 11 routes sous `/me`, toutes dérivées du cookie de session
  (`get_current_user`), CSRF exigé sur toute écriture (`require_csrf`, comme `ai_keys.py`).
- `pbm_api/models/users.py` — `pseudo` (unique), `avatar_key`, `pending_email` ; `EmailTokenKind`
  gagne `change_email`.
- `pbm_api/config.py` — `storage_backend`, `photos_storage_path`.
- Migration `3221843f145c` (colonnes + `ALTER TYPE email_token_kind ADD VALUE 'change_email'` —
  non réversible côté downgrade, documenté dans la migration : Postgres ne sait pas retirer une
  valeur d'un type énuméré).
- `pbm_api/main.py` — routeur `profile` branché.
- Tests : `test_profile.py` (20 cas dont isolation croisée), `test_avatar.py` (4, recadrage),
  `test_storage.py` (4, ajouté après rebase — voir § Rebase avant fusion). 28 au total.

**Front (`apps/web`)**
- `lib/api/client.ts` — client HTTP partagé (`apiGet`/`apiJson`/`apiUpload`, en-tête
  `X-CSRF-Token` automatique) ; `lib/api/auth.ts` refactoré dessus sans changer son API
  publique. Aucune route de ce dépôt n'envoyait encore le jeton CSRF depuis le front au moment
  où ce module a été écrit (connexion/inscription/mot de passe oublié sont toutes non
  authentifiées) — le rebase a montré que `v3-upload` avait, la même semaine, posé sa propre
  logique équivalente dans `lib/api/uploads.ts` sans le savoir (voir § Rebase avant fusion) —
  `lib/config.ts` gagne `getCsrfCookieName()`.
- `lib/api/profile.ts`, `lib/api/ai-keys.ts`, `lib/validation/profile.ts`.
- `components/profile/` — `profile-tabs.tsx` (nav + état des onglets), `identity-tab.tsx`,
  `avatar-picker.tsx`, `security-tab.tsx`, `ai-tab.tsx` (3 fournisseurs, statut valide/
  invalide/quota déduit du message d'erreur normalisé — voir Choix techniques —, fournisseur
  par défaut, liens vers les consoles Anthropic/Google/OpenAI, usage agrégé), `data-tab.tsx`
  (export : lien vers le futur lot RGPD, désactivé ; suppression du compte avec confirmation
  par mot de passe).
- `app/profil/page.tsx` — remplace l'`EmptyState` de `v0-design-system`.
- `app/confirmer-email/` — page de confirmation du changement d'adresse (hors garde
  `middleware.ts`, comme `/verifier` et `/reinitialiser` : le jeton est l'autorité, pas la
  session).
- Tests : `__tests__/profil.test.tsx` (5), `__tests__/confirmer-email.test.tsx` (3).

## Choix techniques

- **Recadrage de l'avatar côté serveur (Pillow), pas d'éditeur de recadrage côté front.** La
  maquette ne montre qu'un bouton « Changer la photo » et le texte « recadrée en carré », pas
  d'interface de recadrage manuel — centrer sur le plus petit côté puis redimensionner à 512 px
  est reproductible et évite d'ajouter un composant de crop interactif (canvas, glisser-déposer
  de zone) non demandé par la mission.
- **Un seul appel IA `/test` par clic, aucun état de validité persisté.** `AiCredential` n'a pas
  de colonne « dernier statut connu » (vérifié dans `pbm_api/models/users.py`) : le statut
  affiché (valide/invalide/quota) est un état local du composant, réinitialisé au chargement de
  la page — fidèle à ce que l'API peut réellement garantir (un `/test` réel coûte un appel
  fournisseur, jamais déclenché automatiquement au chargement). La distinction « quota » vs
  « invalide » se fait sur le message renvoyé par `AiKeyTestResponse.message`
  (`QuotaExceededError.user_message` contient « Quota » — voir `pbm_api/ai/errors.py`, lot
  `v3-ia-providers`) : pas de champ dédié dans le contrat API, donc inférence textuelle plutôt
  qu'un nouveau champ qui aurait débordé sur le contrat déjà posé par un autre lot.
- **Changement de mot de passe : rotation des *autres* sessions, la session courante est
  gardée.** Différent de `reset_password` (mot de passe oublié), qui révoque tout y compris la
  session courante — là, aucune session de confiance n'existe encore. Ici l'utilisateur vient de
  prouver son mot de passe actuel depuis une session déjà authentifiée : la déconnecter en plus
  aurait été une régression d'ergonomie non demandée par la mission.
- **Changement d'e-mail anti-énumération, comme `/auth/register`.** `POST /me/email` renvoie le
  même message générique que l'adresse cible soit déjà prise par un autre compte ou non, et
  n'envoie l'e-mail de confirmation que si elle est libre — un attaquant authentifié ne doit pas
  pouvoir sonder les adresses existantes via cette route. Testé explicitement
  (`test_change_email_gives_the_same_response_whether_the_address_is_taken_or_not`).
- **Page `/confirmer-email` hors du garde `middleware.ts`** (comme `/verifier`,
  `/reinitialiser`) : le lien envoyé par e-mail peut être ouvert depuis un navigateur sans
  session active (autre appareil) — le jeton opaque à usage unique est l'autorité, pas le cookie
  de session. Le lien pointe vers `/confirmer-email`, pas `/profil/confirmer-email`, précisément
  pour rester hors du préfixe gardé (`/profil/:path*`).
- **`lib/api/client.ts` extrait de `lib/api/auth.ts`** plutôt que dupliquer la logique fetch/CSRF
  dans `lib/api/profile.ts` et `lib/api/ai-keys.ts` : c'est le premier lot à avoir besoin du
  jeton CSRF côté front, donc le premier endroit légitime pour poser ce module partagé.
  `lib/api/auth.ts` garde exactement la même API publique (vérifié par la suite de tests
  existante, inchangée et toujours verte).
- **`PhotoStorage` avec un paramètre `local_root` explicite** (pas seulement lu depuis
  `settings`) pour permettre aux tests d'isoler chaque cas dans un `tmp_path` sans dépendre
  d'une variable d'environnement globale mutable pendant la suite.

## Décisions provisoires utilisées

- **D7** (stockage S3 compatible, MinIO en dev) — respectée pour le backend `s3`, complétée par
  le backend `local` explicitement prescrit par le contexte d'exécution de ce lot pour
  l'UAT/PROD sans Docker (`docs/infra/SERVEUR-POKEBOY.md`, recommandation (a) retenue).
- **D4** (pas de clé IA réelle disponible) — l'onglet « Mon IA » et ses tests utilisent le même
  double déterministe que `v1-byok`/`v3-ia-providers` (`ProviderKeyTester`, substitué en test) ;
  aucun appel réel n'a été fait depuis ce lot.

## Rebase avant fusion — collision avec `v3-upload`

`origin/main` avait avancé de 5 commits pendant la session (`v2-recherche`, `v3-upload` fusionnés
entre-temps). Le rebase a produit des conflits **de conception convergente**, pas de simple
texte : `v3-upload` avait posé, en parallèle et sous le même mandat (« aucune fonctionnalité ne
doit supposer Docker en production »), sa propre interface de stockage à deux implémentations
(`pbm_api.storage.build_storage`/`StorageBackend`, `LocalObjectStorage`) — quasi identique à
celle de ce lot (`PhotoStorage`), même noms de réglages (`STORAGE_BACKEND`,
`PHOTOS_STORAGE_PATH`), même bucket implicite. Plutôt que garder les deux, `pbm_api/
photo_storage.py` (et son fichier de test) a été supprimé après le rebase, et `pbm_api/profile/
service.py`/`pbm_api/routers/profile.py` migrés sur `pbm_api.storage` (celle déjà utilisée par
`pbm_api.routers.uploads`) : un seul stockage de photos pour l'avatar et les photos de cartes,
comme le commentaire de tête de `pbm_api/storage/__init__.py` le prescrit désormais. Deux
méthodes manquaient côté `v3-upload` pour couvrir le besoin de ce lot (remplacer un avatar,
purger celui d'un compte supprimé) : `delete` ajoutée à `LocalObjectStorage` et à
`pbm_api.s3.ObjectStorage`, testées dans le nouveau `tests/test_storage.py` (la partie `get`/
`put` était déjà couverte par `tests/test_uploads.py`, pas dupliquée ici). `config.py` et
`.env.example` avaient chacun gagné un bloc `STORAGE_BACKEND`/`PHOTOS_STORAGE_PATH` en double
après l'auto-merge de Git (deux définitions Python de la même variable, la seconde écrasant
silencieusement la première) — dédoublonné manuellement, ce n'était visible qu'en relisant le
fichier après le rebase, pas signalé comme conflit par Git. `apps/web/src/lib/config.ts` avait la
même duplication exacte de `getCsrfCookieName()` (les deux lots ont dû envoyer leur premier
en-tête CSRF front au même moment) — dédoublonnée aussi.

**Non traité, signalé plutôt que corrigé en silence** : `apps/web/src/lib/api/uploads.ts` (lot
`v3-upload`, déjà fusionné, sans conflit avec ce lot) définit sa propre copie de `ApiError`/
`readCookie`/`getCsrfToken`/`parseErrorMessage` — une duplication presque identique à
`apps/web/src/lib/api/client.ts` posé par ce lot-ci. Toucher un fichier d'un autre lot déjà
fusionné, hors de toute obligation de résolution de conflit, sortait du périmètre d'une fusion ;
laissé pour un futur lot de nettoyage front (voir Reste à faire).

`uv.lock` régénéré (`uv lock`) après fusion de `pyproject.toml` plutôt que fusionné à la main.
`packages/api-client/src/schema.d.ts` régénéré (`pnpm gen:api`) après la fusion complète du
back — la version du dépôt distant ne connaissait ni les routes `/me/*` de ce lot ni celles de
`v3-upload`/`v2-recherche` en même temps. Suite complète (back 255 tests, front 59 tests) rejouée
après rebase — voir Preuves.

## Preuves — commandes lancées, résultats chiffrés

```
$ cd apps/api && uv run ruff check .
All checks passed!

$ TEST_DATABASE_URL=postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v1_profil_test uv run pytest -q
........................................................................ [ 28%]
........................................................................ [ 56%]
........................................................................ [ 84%]
.......................................                                  [100%]
255 passed, 2 warnings in 27.68s
```
(227 tests déjà présents après fusion de `v2-recherche`/`v3-upload` + 28 de ce lot :
`test_profile.py` (20), `test_avatar.py` (4), `test_storage.py` (4, posé après le rebase).)

Rejoué avec les variables d'environnement de la CI (base éphémère `pbm_v1_profil_citest`, comme
`.github/workflows/ci.yml` : `DATABASE_URL`/`TEST_DATABASE_URL` dédiés, `S3_BUCKET=pbm-v1-profil-
citest`, `TZ=Europe/Paris`), migration puis suite complète :
```
$ DATABASE_URL=…/pbm_v1_profil_citest TEST_DATABASE_URL=…/pbm_v1_profil_citest \
    REDIS_URL=redis://localhost:56379/0 S3_BUCKET=pbm-v1-profil-citest TZ=Europe/Paris \
    uv run alembic upgrade head
Running upgrade  -> 5e0d551b788e, initial schema
Running upgrade 5e0d551b788e -> 1d51087de4ae, catalog reconciliation and image fields
Running upgrade 1d51087de4ae -> 8565c4640de8, exchange rates daily and user preferred currency
Running upgrade 8565c4640de8 -> d42b0620077e, ai settings and usage
Running upgrade d42b0620077e -> 3221843f145c, profile: pseudo, avatar, pending email

$ (mêmes variables) uv run ruff check .
All checks passed!

$ (mêmes variables) uv run pytest -q
255 passed, 2 warnings in 23.95s
```
(base éphémère supprimée après coup.)

**Preuve ciblée « un test qui échoue sans le changement, passe avec » (§6)**, rejouée avant le
rebase avec `v3-upload`/`v2-recherche` (même mécanique, non ré-exécutée après — le rebase n'a fait
que déplacer `app.include_router(profile_router)` d'une ligne, jamais changer son contenu, `git
diff` sur `main.py` le confirme post-rebase) : `app.include_router(profile_router)` temporairement
commenté dans `pbm_api/main.py`, puis `uv run pytest -q tests/test_profile.py` :

```
18 failed, 2 passed in 4.15s
```
(les 2 tests encore verts n'attendent qu'un 401 générique, déjà couvert par le reste de l'API —
tous les tests qui exercent une route réellement nouvelle de ce lot échouent sans elle.) Ligne
restaurée, suite complète repassée au vert avant de poursuivre.

**Preuve dédiée au stockage local** (§ contexte d'exécution, « aucune fonctionnalité ne doit
supposer Docker en production ») — `tests/test_storage.py`, backend `local` sur un répertoire
temporaire, `delete` (ajoutée par ce lot) puis roundtrip complet, **sans MinIO ni Docker** :
```
tests/test_storage.py::test_local_storage_delete_removes_the_file PASSED
tests/test_storage.py::test_local_storage_delete_of_a_missing_key_does_not_raise PASSED
tests/test_storage.py::test_local_storage_rejects_path_traversal PASSED
```
Le même fichier prouve `delete` sur le backend `s3` (MinIO réel) — les deux implémentations
respectent le même contrat, code appelant (`pbm_api.profile.service`) inchangé entre les deux ;
`get`/`put` restent couverts par `tests/test_uploads.py` (lot `v3-upload`), non dupliqués ici.

**Test d'accès croisé (§6)** — trois angles couverts dans `test_profile.py` :
- `test_cross_user_isolation_on_sessions` : B ne voit pas la session de A dans sa propre liste
  et reçoit 404 (pas 204) en tentant de la révoquer en devinant son identifiant.
- `test_cross_user_isolation_on_pseudo_update` : `PATCH /me` de B n'affecte jamais le profil de
  A (dérivé du cookie de session de l'appelant, jamais d'un identifiant transmis).
- `test_patch_me_rejects_a_pseudo_already_taken` : cas croisé sur la contrainte d'unicité.

**Front — lint/types/build/tests** (après rebase, `v3-upload` inclus) :
```
$ pnpm --filter @pbm/web lint     → (rien, 0 erreur)
$ pnpm --filter @pbm/web type-check → (rien, 0 erreur)
$ pnpm --filter @pbm/web test -- --run
Test Files  20 passed (20)
     Tests  59 passed (59)
$ pnpm --filter @pbm/web build
✓ Generating static pages (17/17)
```
(51 tests déjà présents après fusion de `v3-upload` (dont `upload-view.test.tsx`, 7 cas) + 5 dans
`profil.test.tsx` + 3 dans `confirmer-email.test.tsx` de ce lot.)

**Client TypeScript régénéré** : `pnpm gen:api` relancé après les nouvelles routes,
`packages/api-client/src/schema.d.ts` commité (11 nouvelles routes visibles sous `/me`).

## Écarts au plan

- **Capture d'écran de la maquette non produite.** Playwright (déjà en devDependency,
  navigateurs déjà téléchargés) a été utilisé pour scripter inscription → vérification (via
  l'API Mailpit) → connexion → `/profil`, mais **la capture d'écran elle-même échoue** dans cette
  session : le lancement du navigateur exige des bibliothèques système (`libnspr4`, etc.)
  absentes de l'image et l'installation (`playwright install-deps`) demande `sudo`, indisponible
  ici (session non élevée). Contournement partiel testé (extraction manuelle des `.deb` déjà
  présents dans `/tmp/pw-libs/debs/` sans `dpkg`, `LD_LIBRARY_PATH` pointé dessus) : le
  navigateur se lance et navigue (`page.goto` réussit, connexion effectuée), mais
  `page.screenshot()` expire systématiquement après le chargement des polices — cause non
  identifiée avec certitude (bibliothèque de rendu manquante non couverte par les `.deb`
  disponibles). Conformité vérifiée autrement : les 4 onglets, leurs libellés exacts, les textes
  d'aide et la structure (barre latérale 200 px + contenu) reproduisent terme à terme la
  fonction `V.profil` de `docs/roadmap/ROADMAP.html` ; `profil.test.tsx` vérifie au niveau DOM
  que ces libellés et cette structure s'affichent réellement (pas seulement dans le code source).
  **Reste à faire** : capture réelle, à produire depuis une machine/session avec les paquets
  système Playwright installés (ou navigateur non-headless local).
- Aucun autre écart sur la mission §3 (routes back, page en 4 onglets, onglet Mon IA).

## Reste à faire

- Capture d'écran de la maquette (voir Écarts au plan).
- **Export des données (onglet « Mes données »)** : bouton affiché mais désactivé — l'export
  ZIP (JSON + CSV + photos) est explicitement du ressort du lot RGPD (`v5-rgpd`), qui dépend de
  `v1-profil` d'après le plan (aboutissant, pas tenant) ; seule la suppression du compte est
  dans le périmètre de ce lot et est pleinement fonctionnelle.
- **Sélection de modèle par fournisseur IA** (ex. `claude-sonnet-5` vs `claude-haiku-4-5`,
  visible dans la maquette) non ajoutée à l'onglet « Mon IA » : la mission §3 ne demande que
  « fournisseur par défaut », pas un modèle par défaut par fournisseur, et `AiSettingsResponse`
  expose déjà `default_model` côté API (lot `v1-byok`) si un futur lot veut l'exposer côté front.
- **Confirmation manuelle des e-mails de changement d'adresse via Mailpit** : les tests
  automatisés couvrent le contenu du corps (présence du jeton, destinataire) mais aucune capture
  d'écran de l'e-mail réel dans l'interface Mailpit n'a été produite (même contrainte que la
  capture de la maquette).
- **`apps/web/src/lib/api/uploads.ts` (lot `v3-upload`) duplique `apps/web/src/lib/api/
  client.ts`** posé par ce lot (`ApiError`/`readCookie`/`getCsrfToken`/`parseErrorMessage`
  quasi identiques) — repéré pendant le rebase (voir § Rebase avant fusion), non corrigé ici
  car hors du fichier en conflit et hors du périmètre de la mission `v1-profil`. À consolider
  dans un futur lot de nettoyage front une fois `v3-upload` stabilisé.
