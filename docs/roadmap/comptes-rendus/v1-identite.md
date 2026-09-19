# Compte rendu — `v1-identite`

Session autonome (`claude -p`) sur chimera, worktree `~/dev/wt-pbm-v1-identite`, branche
`roadmap/v1-identite`. Exécuté sous le régime décrit dans le CONTEXTE D'EXÉCUTION du prompt
(sections A/P/0/7 du prompt de lot remplacées) : pas de `suivi.py`, pas d'écriture dans
`etat.json`/`ROADMAP.html`/`BACKLOG.md`/`prompts/`, dépendance `v1-profil` déjà fusionnée dans
`origin/main` (dépôt relais local, pas GitHub).

## Résumé

Identité du compte : prénom (facultatif), nom, date de naissance et acceptation horodatée des
conditions sur `/inscription` (validation d'âge ≥ 15 ans, RGPD art. 8) et dans Profil → Identité
(sans contrainte d'âge, un compte existant reste éditable). Commande d'administration
`create-user` pour créer un compte déjà vérifié (mot de passe par entrée standard ou généré,
changement forcé optionnel à la première connexion) — pose le socle pour le compte d'Aymeric à la
mise en PROD.

## Livrables

**Back (`apps/api`)**
- `pbm_api/models/users.py` — `first_name` (nullable), `last_name`, `birth_date`,
  `terms_version`, `terms_accepted_at`, `must_change_password` (`server_default='false'`).
- `pbm_api/legal.py` — `CURRENT_TERMS_VERSION`, `MINIMUM_AGE_YEARS` (15).
- `pbm_api/auth/service.py` — `register_user` valide conditions obligatoires, date de naissance
  passée, âge minimum (inscription libre uniquement) ; `age_years()` réutilisée par
  `pbm_api.profile.service`. Nouvelles erreurs (`auth/errors.py`) :
  `TermsNotAcceptedError`/`InvalidBirthDateError`/`UnderageWithoutParentalConsentError`, chacune
  mappée en 400 par `routers/auth.py` avec un message dédié.
- `pbm_api/profile/service.py` — `update_identity` (remplace `update_pseudo`) : pseudo + prénom +
  nom + date de naissance en un seul appel, sans contrainte d'âge minimum ; `change_password`
  remet `must_change_password` à `False`.
- `pbm_api/routers/auth.py` — `POST /auth/login` renvoie `must_change_password` (front : bascule
  la redirection post-connexion).
- `pbm_api/routers/profile.py` — `GET/PATCH /me` exposent et acceptent les trois champs
  d'identité (`UpdateProfileRequest`, ex-`UpdatePseudoRequest`).
- `pbm_api/admin.py` — `python -m pbm_api.admin create-user` (argparse) : validations dédiées
  (e-mail, date, mot de passe), compte créé déjà vérifié, mot de passe jamais en argument ni
  journalisé.
- Migration `328aef94ea58` (down_revision `7fc6cd5efc72`, tête précédente) — colonnes `NOT NULL`
  sans valeur de repli pour `last_name`/`birth_date`/`terms_version`/`terms_accepted_at` :
  acceptable, `users` est vide à ce stade du projet (aucun déploiement encore fait, voir
  périmètre du lot). L'autogénération Alembic avait aussi détecté une dérive préexistante et
  sans rapport (`card_insight_reports.created_at`, `TIMESTAMP(timezone=True)` vs `DateTime()`) —
  retirée de la migration, hors périmètre de ce lot.
- Tests : `test_identity.py` (18 cas neufs : validation d'âge/conditions/date, `PATCH /me`,
  isolation croisée sur l'identité, `must_change_password`, commande `create-user` — testée en
  sous-processus réel via `uv run python -m pbm_api.admin`, pas un mock). `test_auth.py`/
  `test_profile.py`/`test_ai_keys.py`/`test_card_insights.py`/`test_collection.py`/
  `test_detections_routes.py`/`test_uploads.py` mis à jour (les nouveaux champs sont désormais
  requis par `POST /auth/register`). `test_schema.py`/`test_ranking.py`/`test_valuation.py`/
  `test_detection_service.py`/`test_cross_user_isolation.py` : leurs `User(...)` construits
  directement par l'ORM (hors API) reçoivent les nouvelles colonnes obligatoires.

**Front (`apps/web`)**
- `lib/validation/auth.ts` — `lastNameSchema`, `firstNameSchema` (facultatif),
  `registrationBirthDateSchema` (date passée + âge ≥ 15 ans, réutilisée par `registerSchema`).
- `lib/validation/profile.ts` — `identitySchema` étendu (`firstName`/`lastName`/`birthDate`,
  `birthDateSchema` sans contrainte d'âge — cohérent avec le service back).
- `lib/api/auth.ts` — `registerAccount` prend un objet (`firstName`/`lastName`/`birthDate`/
  `acceptTerms`) plutôt que deux positionnels, pour rester lisible avec 6 champs.
- `lib/api/profile.ts` — `updateIdentity` remplace `updatePseudo`.
- `app/inscription/page.tsx` — champs Prénom (facultatif), Nom, Date de naissance avant l'e-mail,
  même style de champ (`Input`/`Label`) que l'existant.
- `components/profile/identity-tab.tsx` — mêmes champs dans Profil → Identité ; `updateIdentity`
  appelé dès que pseudo **ou** prénom **ou** nom **ou** date de naissance change (au lieu du seul
  pseudo).
- `app/connexion/connexion-form.tsx` — après connexion, si `must_change_password`, redirection
  vers `/profil?onglet=securite&mot-de-passe-a-changer=1` au lieu de `next`.
- `components/profile/profile-tabs.tsx` — lit `onglet`/`mot-de-passe-a-changer` dans l'URL (onglet
  initial, transmis à `SecurityTab`) ; `app/profil/page.tsx` gagne un `<Suspense>` (requis par
  `useSearchParams`, même pattern que `/connexion`).
- `components/profile/security-tab.tsx` — bandeau d'alerte si `forcePasswordChange`.
- Tests : `inscription.test.tsx`/`profil.test.tsx`/`connexion.test.tsx` mis à jour (nouveaux
  champs obligatoires, `updateIdentity`, redirection `must_change_password` — 1 cas neuf).
- `packages/api-client/src/schema.d.ts` régénéré (`pnpm gen:api`).

## Choix techniques

- **Âge minimum appliqué à l'inscription libre uniquement, pas à `PATCH /me`.** Un compte déjà
  existant peut appartenir à un mineur créé par l'administrateur (consentement du parent porté
  par JF) : bloquer toute édition ultérieure de son pseudo/nom sur une vérification d'âge aurait
  verrouillé ce compte en permanence pour une correction qui ne re-déclenche aucun consentement.
  Seule la contrainte « date dans le passé » reste commune aux deux chemins.
- **Une seule route `PATCH /me` pour pseudo + identité**, plutôt que deux routes séparées :
  la mission décrit un seul formulaire « Profil → Identité » (maquette), et `update_identity`
  reste un service pur (`db, user, pseudo, first_name, last_name, birth_date`) testable comme
  `update_pseudo` l'était.
- **`must_change_password` porté par `UserResponse.must_change_password`** (réponse de
  `POST /auth/login`) plutôt qu'un nouvel endpoint dédié : le front a besoin de cette information
  au moment précis où il décide de la redirection post-connexion, pas avant.
- **Commande `admin.py` testée en sous-processus réel** (`subprocess.run(["uv", "run", "python",
  "-m", "pbm_api.admin", …])`), pas en import direct de `create_user()` : la fonction utilise
  `pbm_api.db.async_session_factory`, lié à `settings.database_url` au chargement du module —
  l'appeler in-process aurait implicitement dépendu de l'alignement entre `DATABASE_URL` (dev) et
  `TEST_DATABASE_URL` (test), déjà vrai en CI mais pas garanti localement. Le sous-processus reçoit
  explicitement `DATABASE_URL=<TEST_DATABASE_URL>` et exerce aussi l'analyse des arguments et la
  lecture du mot de passe sur l'entrée standard — un test plus fidèle à l'usage réel décrit par la
  mission.
- **Mot de passe généré affiché une seule fois en sortie standard, jamais journalisé** : pas de
  dépendance à un canal de livraison (e-mail, Slack) hors périmètre de ce lot — l'administrateur
  (JF) le récupère directement depuis le terminal de la commande.
- **`CURRENT_TERMS_VERSION` en constante Python (`pbm_api/legal.py`), pas en variable
  d'environnement** : ce n'est pas un secret ni une valeur qui change par déploiement, c'est une
  version de contenu (`/conditions`) qui doit être identique en dev/UAT/PROD — une variable
  d'environnement aurait permis une désynchronisation accidentelle entre l'environnement et le
  texte réellement affiché.

## Décisions provisoires utilisées

Aucune des décisions D2 à D8 n'est directement engagée par ce lot (D2/D8 hors périmètre — aucun
déploiement depuis ici, cf. contexte d'exécution).

## Rebase avant fusion — collision de migration avec `v5-rgpd`

`origin/main` a reçu `v5-rgpd` (export/suppression RGPD) pendant la session. Rebase propre à un
conflit textuel près (`CLAUDE.md` : les deux lots ajoutent chacun une section juste avant
« Règles de la flotte » — les deux sections gardées, concaténées). Plus significatif : les deux
lots avaient posé une migration Alembic sur la **même tête** (`7fc6cd5efc72`, « card insight
reports ») — `v5-rgpd` avec `2e56ba32d5ed` (data exports), ce lot avec `328aef94ea58`. Deux têtes
de migration auraient cassé `alembic upgrade head` dès la fusion. Rechaîné manuellement :
`328aef94ea58.down_revision` pointe désormais sur `2e56ba32d5ed` — une seule tête (`uv run
alembic heads` confirme), bases dev/test recréées et migrées de zéro pour vérifier l'ordre complet
(voir Preuves).

Corrigé au passage, repéré en relisant le nouveau code de `v5-rgpd` pendant la résolution :
`pbm_api/export/service.py` construisait `profil.json` avec seulement `email`/`pseudo`/
`compte_cree_le` — sans `first_name`/`last_name`/`birth_date` que ce lot vient d'ajouter à
`users`. La mission de ce lot demande explicitement que « l'export RGPD les inclut » (§2) : plutôt
que de le noter comme un simple écart, corrigé directement (`prenom`/`nom`/`date_de_naissance`
ajoutés au dictionnaire `profile`) — aucun test de `v5-rgpd` ne dépend des clés exactes de
`profil.json` (vérifié : `tests/test_export.py` ne fait pas d'assertion sur son contenu), donc
aucune régression introduite.

`test_export.py::_register_verify_login` (un appel à `/auth/register`, comme dans sept autres
fichiers de tests) a aussi eu besoin des trois nouveaux champs obligatoires — repéré seulement
après rebase puisque ce fichier n'existait pas encore quand ce lot a démarré.

Suites complètes (back 331, front 61) et client TypeScript régénérés après rebase — voir Preuves.

**Second rebase, `v3-identification` fusionné entre-temps** — même mécanique de collision de
migration : `054d503ae627` (identification cache) posée sur la même tête `2e56ba32d5ed` que la
migration de ce lot. Rechaînée une seconde fois (`328aef94ea58.down_revision` →
`054d503ae627`, tête unique reconfirmée par `uv run alembic heads`) ; conflit textuel
supplémentaire sur `CLAUDE.md` (même cause : deux lots ajoutent chacun leur section au même
endroit), résolu en gardant les deux. `tests/test_identification_service.py` (nouveau fichier de
`v3-identification`) construisait aussi un `User(...)` sans les champs d'identité désormais
obligatoires — corrigé. Bases dev/test recréées, migrées de zéro (10 révisions) ; suites
complètes rejouées une troisième fois (back **350** tests, front **61**) et client TypeScript
régénéré (sans diff, déjà à jour) — voir Preuves.

## Preuves — commandes lancées, résultats chiffrés

```
$ cd apps/api && uv run ruff check .
All checks passed!

$ TZ=Europe/Paris TEST_DATABASE_URL=postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v1_identite_test \
    uv run pytest -q
........................................................................ [ 22%]
........................................................................ [ 45%]
........................................................................ [ 68%]
........................................................................ [ 90%]
..............................................................           [100%]
350 passed, 23 warnings in 42.56s
```
(332 tests déjà présents après les rebases avec `v5-rgpd` (export/suppression RGPD) et
`v3-identification` + 18 nouveaux dans `test_identity.py`. Rejoué à chaque rebase, bases dev/test
recréées de zéro — voir § Rebase avant fusion.)

**Preuve ciblée « un test qui échoue sans le changement, passe avec » (§6)** — `POST
/auth/register` sans les nouveaux champs (comportement avant ce lot) :
```
$ curl -s -X POST http://localhost:18100/auth/register -H "Content-Type: application/json" \
    -d '{"email":"trop.jeune@example.fr","password":"un-mot-de-passe-solide-2026","last_name":"Jeune","birth_date":"2018-01-01","accept_terms":true}'
{"detail":"L'inscription libre est réservée aux 15 ans et plus. En dessous, un parent peut demander la création du compte."}

$ curl -s -X POST http://localhost:18100/auth/register -H "Content-Type: application/json" \
    -d '{"email":"sans.conditions@example.fr","password":"un-mot-de-passe-solide-2026","last_name":"X","birth_date":"1990-01-01","accept_terms":false}'
{"detail":"Tu dois accepter les conditions pour créer un compte."}
```
Ces deux refus — et `test_register_rejects_registration_under_the_minimum_age`/
`test_register_rejects_missing_terms_acceptance` dans `test_identity.py` — échouent tous les deux
sans les validations de ce lot (l'inscription aurait simplement réussi).

**Commande d'administration — bout en bout, base réelle** :
```
$ echo "un-mot-de-passe-de-demo" | uv run python -m pbm_api.admin create-user \
    --email aymeric@example.fr --pseudo aymeric --last-name Fontaine --first-name Aymeric \
    --birth-date 1990-05-12 --accept-terms --password-stdin --must-change-password
Compte créé et vérifié : aymeric@example.fr
```
Vérifié en base (`email_verified_at` renseigné, `must_change_password=t`) ; rejets testés
(`--accept-terms` omis → sortie 1 ; e-mail déjà pris → sortie 1) ; un compte de moins de 15 ans
**accepté** par cette commande (contrairement à `/auth/register`), conforme à la mission §4.

**Test d'accès croisé (§6)** — `test_cross_user_isolation_on_identity_update` (`test_identity.py`) :
B ne peut jamais modifier l'identité de A, `PATCH /me` de B laissant `last_name` de A inchangé
(dérivé uniquement du cookie de session de l'appelant).

**Inscription réelle, bout en bout** (API dev + Mailpit du `pbm-shared`) :
```
$ curl -s -X POST http://localhost:18100/auth/register -H "Content-Type: application/json" \
    -d '{"email":"aymeric.demo@example.fr","password":"un-mot-de-passe-solide-2026","first_name":"Aymeric","last_name":"Fontaine","birth_date":"1990-05-12","accept_terms":true}'
{"message":"Si cette adresse n'est pas déjà utilisée, un e-mail de vérification vient d'être envoyé."}
```
Ligne confirmée en base (`first_name=Aymeric, last_name=Fontaine, birth_date=1990-05-12,
terms_version=2026-09-19, verified=f`) et e-mail reçu par Mailpit (`aymeric.demo@example.fr` dans
`/api/v1/messages`). Données de test supprimées après vérification.

**Front — lint/types/build/tests** :
```
$ pnpm --filter @pbm/web lint       → (rien, 0 erreur)
$ pnpm --filter @pbm/web type-check → (rien, 0 erreur)
$ pnpm --filter @pbm/web test
Test Files  20 passed (20)
     Tests  61 passed (61)
$ pnpm --filter @pbm/web build
✓ Generating static pages (17/17)
```
(59 tests déjà présents après rebase (dont le nouveau cas d'export de `v5-rgpd` dans
`profil.test.tsx`) + 1 nouveau dans `connexion.test.tsx` posé par ce lot — les autres tests
touchés remplacent des assertions existantes plutôt que d'en ajouter.)

**HTML réellement servi** (`curl` sur le serveur `next dev` de test) confirmant la présence des
nouveaux champs sur `/inscription` : `Prénom`, `Nom`, `Date de naissance`, `Créer mon espace`.

**Client TypeScript régénéré** : `pnpm gen:api`, `packages/api-client/src/schema.d.ts` commité
(`RegisterRequest`/`UpdateProfileRequest`/`ProfileResponse`/`UserResponse` gagnent les nouveaux
champs).

## Écarts au plan

- **Capture d'écran de la maquette non produite** — même contrainte d'environnement déjà
  documentée par `v1-profil` (voir son compte rendu) : le lancement d'un Chromium headless
  (`chromium-1243` et `chromium_headless_shell-1243`, tous deux déjà en cache) échoue avec
  `error while loading shared libraries: libnspr4.so: cannot open shared object file` —
  bibliothèque système absente, installable seulement via `playwright install-deps` (donc `sudo`,
  indisponible dans cette session non élevée). Conformité vérifiée autrement : HTML réellement
  servi par `next dev` (voir Preuves) confirmant la présence des champs et leurs libellés exacts,
  plus `inscription.test.tsx`/`profil.test.tsx` qui vérifient au niveau DOM (jsdom) que ces
  libellés et cette structure s'affichent, avec les mêmes composants `Input`/`Label` que le reste
  du formulaire (« même style de champ », mission §3). **Reste à faire** : capture réelle, à
  produire depuis une machine/session avec les paquets système Playwright installés.
- Aucun autre écart sur la mission §3 (migration, API, front, commande d'administration,
  redirection de changement de mot de passe forcé). L'export RGPD (mission §2, « l'export RGPD
  les inclut ») a fusionné dans `main` pendant cette session (`v5-rgpd`) ; corrigé pendant le
  rebase pour qu'il inclue `first_name`/`last_name`/`birth_date` (voir § Rebase avant fusion) —
  ce n'est donc plus un écart.

## Reste à faire

- Capture d'écran de la maquette (voir Écarts au plan).
- Aucune autre dette identifiée dans le périmètre de ce lot.
