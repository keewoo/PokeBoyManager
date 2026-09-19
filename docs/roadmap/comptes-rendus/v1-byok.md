# Compte rendu — `v1-byok`

Session autonome (`claude -p`) sur chimera, worktree `~/dev/wt-pbm-v1-byok`, branche
`roadmap/v1-byok`. Exécuté sous le régime décrit dans le CONTEXTE D'EXÉCUTION du prompt
(sections A/P/0/7 du prompt de lot remplacées) : pas de `suivi.py`, pas d'écriture dans
`etat.json`/`ROADMAP.html`/`BACKLOG.md`/`prompts/`, dépendance `v1-auth` déjà fusionnée dans
`origin/main` (dépôt relais local, pas GitHub).

## Résumé

Coffre de clés IA par utilisateur (Anthropic, Gemini, OpenAI) : ajouter/tester/remplacer/
supprimer une clé par fournisseur, choisir le fournisseur et le modèle par défaut, lire
l'usage (appels/jetons/coût estimé par fournisseur et par mois). Chiffrement AES-256-GCM avec
`user_id` en données associées (une clé copiée dans un autre compte ne se déchiffre pas), la
clé n'est jamais renvoyée ni journalisée en clair. Le test d'une clé fait un vrai appel réseau
minimal (liste de modèles) contre le fournisseur — vérifié en direct contre les trois API
réelles depuis chimera (voir Preuves). D4 appliquée telle quelle : sans clé personnelle, la
reconnaissance reste désactivée (pas de clé plateforme, pas de quota d'essai) ; ce lot ne
touche pas à la reconnaissance elle-même, seulement au coffre qui l'alimentera.

## Livrables

- `apps/api/src/pbm_api/routers/ai_keys.py` — `GET/PUT/DELETE /me/ai-keys[/{provider}]`,
  `POST /me/ai-keys/{provider}/test`, `GET/PATCH /me/ai-settings`, `GET /me/ai-usage`. Toutes
  dérivent l'utilisateur du cookie de session (`get_current_user`, lot `v1-auth`), jamais d'un
  identifiant fourni par le client ; `require_csrf` posé sur toute écriture, y compris `/test`
  (déclenche un appel réseau au nom de l'utilisateur).
- `apps/api/src/pbm_api/ai/` — logique métier indépendante de FastAPI :
  - `service.py` : upsert/suppression/liste des clés, test (clé fournie ou clé stockée
    déchiffrée), mise à jour des réglages (refuse un fournisseur par défaut sans clé
    enregistrée), lecture de l'usage.
  - `providers.py` : `ProviderKeyTester`, injecté par dépendance FastAPI — un aller-retour
    « liste de modèles » par fournisseur (coût nul), clé transmise en en-tête HTTP (jamais en
    paramètre d'URL, moins exposé aux journaux d'une bibliothèque tierce).
  - `errors.py`, `schemas.py` — exceptions du domaine, schémas Pydantic.
- `apps/api/src/pbm_api/security/crypto.py` — AES-256-GCM (`cryptography`), nonce aléatoire
  par appel, `user_id` en données associées, masque présentable (`sk-ant-a…4f2a`). Rotation
  documentée en commentaire de module (déchiffrer avec l'ancienne clé maître, rechiffrer avec
  la nouvelle).
- `apps/api/src/pbm_api/security/log_filter.py` — anti-fuite de clé dans les journaux, via
  `logging.setLogRecordFactory` (couvre tout logger, pas seulement `root` — un simple
  `logger.addFilter` sur `root` n'aurait pas intercepté les loggers nommés qui se contentent
  de propager, cas le plus courant en pratique).
- `apps/api/src/pbm_api/security/validation_errors.py` — anti-fuite de clé dans les réponses
  422 (trouvé en auto-révision, voir « Choix techniques »).
- `apps/api/src/pbm_api/models/users.py` — `User.ai_default_provider`/`ai_default_model` ;
  `apps/api/src/pbm_api/models/ai_usage.py` — `AiUsageMonthly` (unique par utilisateur ×
  fournisseur × mois).
- `apps/api/migrations/versions/d42b0620077e_ai_settings_and_usage.py` — nouvelle table +
  deux colonnes ; réutilise le type Postgres `ai_provider` existant (`create_type=False`,
  sinon `DuplicateObjectError` puisque `v0-schema` l'a déjà créé pour `ai_credentials`).
- `apps/api/scripts/test_ai_key_manual.py` — essai manuel avec une vraie clé (aucune clé IA
  réelle disponible sur chimera pour la suite automatisée).
- `apps/api/tests/test_ai_keys.py` (25 tests), `test_crypto.py` (5), `test_log_filter.py` (5) —
  détail des preuves ci-dessous.
- `apps/api/tests/test_schema.py` — `ai_usage_monthly` ajoutée aux tables/`user_id` FK+index
  attendus (fichier partagé avec d'autres lots ; ajouts en fin de listes, pas de conflit
  attendu au rebase).
- `.env.example`, `CLAUDE.md`, `docs/ARCHITECTURE.md` — `AI_KEY_ENCRYPTION_KEY` documentée,
  nouvelle section coffre de clés.
- Bases dédiées créées sur l'infra partagée : `pbm_v1_byok` (dev) et `pbm_v1_byok_test`
  (tests).

## Choix techniques

- **Clé transmise en en-tête HTTP à chaque fournisseur, jamais en paramètre d'URL** — y
  compris pour Gemini, dont l'exemple public utilise `?key=...` : l'API accepte aussi
  l'en-tête `x-goog-api-key`, vérifié en direct. Une URL de requête peut se retrouver
  journalisée par un proxy/une bibliothèque tierce bien plus facilement qu'un en-tête.
- **`ProviderKeyTester` injecté par dépendance FastAPI** (comme `CompromisedPasswordChecker`
  dans `v1-auth`) plutôt qu'importé en dur dans `service.py` : la suite automatisée le
  remplace par un double déterministe (aucune clé IA réelle disponible ici), sans mock global
  ni dépendance à un service tiers dans les tests.
- **Filtre de log par `setLogRecordFactory`, pas `logger.addFilter(root)`** : vérifié que ce
  dernier ne couvre pas les loggers nommés qui se contentent de propager vers `root` (le cas
  de `uvicorn.access`/`uvicorn.error` et de toute bibliothèque tierce) — seul le logger
  d'origine voit son propre `filter()` appelé par `Logger.handle()`, pas les ancêtres de la
  hiérarchie de propagation.
- **Redacteur de réponses 422 (`validation_errors.py`), trouvé en auto-révision** : le
  comportement par défaut de FastAPI sérialise la valeur soumise dans `detail[].input` sur
  toute erreur de validation. Une clé trop courte/longue (`AiKeyUpsertRequest.api_key`,
  8–512 caractères) revenait donc en clair dans le corps de la réponse 422 — j'ai d'abord
  essayé `pydantic.ConfigDict(hide_input_in_errors=True)` (suggéré par une revue de sécurité
  dédiée) : **vérifié inefficace** en pratique — cette option ne redacte que la représentation
  texte de l'exception (`str(exc)`), pas les dictionnaires structurés que FastAPI extrait et
  sérialise. Remplacé par un gestionnaire d'exception global qui redacte `input` pour tout
  champ listé dans `SENSITIVE_FIELD_NAMES` (`schemas.py`) — testé (`test_put_ai_key_never_
  echoes_a_rejected_raw_key_in_the_422_body`) et vérifié manuellement (voir Preuves).
- **Gemini renvoie 400 `API_KEY_INVALID` sur une clé invalide, pas 401/403** — contrairement à
  Anthropic et OpenAI. Vérifié en direct contre l'API réelle (`scripts/test_ai_key_manual.py`)
  avant d'écrire `ProviderKeyTester` : les trois codes (400, 401, 403) sont traités comme un
  refus de clé, le reste comme une réponse inattendue.
- **`AiUsageMonthly` posée par ce lot mais alimentée par personne pour l'instant** : la
  mission demande la table et sa lecture (`GET /me/ai-usage`) ; l'écriture viendra du worker
  de reconnaissance (lot futur), hors périmètre ici — testée en écrivant directement des
  lignes depuis les tests.
- **`PATCH /me/ai-settings` refuse un fournisseur par défaut sans clé enregistrée** (400) —
  non demandé explicitement par le prompt, mais laisser un défaut pointer vers un fournisseur
  sans clé produirait un échec silencieux au moment de l'appel réel ; le modèle par défaut,
  lui, n'est pas contraint (aucune notion de « modèles valides » posée dans ce lot).
- **Suppression d'une clé ne touche pas le fournisseur par défaut** si celui-ci pointait
  dessus : pas demandé, et une clarification de comportement (auto-effacement du défaut)
  aurait été une extension de périmètre non sollicitée — l'app échouera proprement à l'appel
  suivant (fournisseur par défaut sans clé), à corriger si un lot futur le juge nécessaire.
- **`pnpm gen:api` non relancé** : `node_modules` de `packages/api-client` n'est pas installé
  dans ce worktree et ce lot est un back-end pur (l'écran est porté par `v1-profil`, maquette
  « sans objet » pour `v1-byok`) — un `pnpm install` complet aurait été un téléchargement
  inutile sur le lien à ~250 ko/s de chimera pour un client TS que personne ne consomme
  encore. Le lot front qui consommera ces routes régénérera le client à ce moment-là.

## Décisions provisoires utilisées

- D4 : sans clé IA personnelle, reconnaissance désactivée, aucune clé plateforme — n'affecte
  pas directement ce lot (pas de reconnaissance ici) mais confirme qu'aucun mécanisme de quota
  plateforme n'était à prévoir dans le coffre.

## Preuves — commandes lancées, résultats chiffrés

```
$ cd apps/api && uv run ruff check .
All checks passed!

$ TZ=Europe/Paris TEST_DATABASE_URL=postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v1_byok_test \
    uv run pytest -q
.........................................................                [100%]
57 passed, 2 warnings in 6.96s
```

Preuve « un test échoue sans le changement, passe avec » (§6) — `app.include_router(ai_keys_router)`
retiré de `main.py`, seule `tests/test_ai_keys.py` relancée :

```
15 failed, 2 passed in 3.22s
  (2 passent par coïncidence : `test_delete_ai_key_returns_404_when_no_key_is_stored` et
  `test_test_route_returns_404_without_a_stored_key_and_none_given` attendent un 404 — sans
  le routeur, la route elle-même n'existe pas et FastAPI renvoie aussi 404, pour la mauvaise
  raison. Tous les autres échouent, y compris `test_ai_keys_routes_require_authentication`
  qui attend 401 et obtient 404.)
  FAILED test_ai_keys_routes_require_authentication
  FAILED test_put_ai_key_stores_it_encrypted_and_never_returns_the_raw_key
  FAILED test_put_ai_key_never_echoes_a_rejected_raw_key_in_the_422_body
  FAILED test_put_ai_key_requires_csrf_token
  FAILED test_put_ai_key_replaces_the_previous_key_for_the_same_provider
  FAILED test_get_ai_keys_lists_only_masks
  FAILED test_delete_ai_key_removes_it
  FAILED test_test_route_validates_a_key_not_yet_saved
  FAILED test_test_route_tests_the_stored_key_when_none_is_given
  FAILED test_get_ai_settings_defaults_to_null
  FAILED test_patch_ai_settings_rejects_default_provider_without_a_stored_key
  FAILED test_patch_ai_settings_updates_default_provider_and_model_independently
  FAILED test_get_ai_usage_returns_entries_for_the_current_user
  FAILED test_cross_user_isolation_on_ai_keys
  FAILED test_cross_user_isolation_on_ai_usage
```
puis `app.include_router(ai_keys_router)` restauré → les 57 tests repassent au vert (ci-dessus).

Simulation du job CI (base éphémère `pbm_v1_byok_citest`, comme le service Postgres GitHub
Actions, migration puis suite complète) :

```
$ uv run alembic upgrade head
Running upgrade  -> 5e0d551b788e, initial schema
Running upgrade 5e0d551b788e -> d42b0620077e, ai settings and usage

$ TZ=Europe/Paris DATABASE_URL=…/pbm_v1_byok_citest TEST_DATABASE_URL=…/pbm_v1_byok_citest \
    REDIS_URL=redis://localhost:56379/0 uv run pytest -q
57 passed, 2 warnings in 6.79s
```
(base éphémère supprimée après coup.)

**Non-régression du type Postgres partagé** : vérifié que la migration échoue avec
`DuplicateObjectError: type "ai_provider" already exists` sans `create_type=False` (générée
par défaut par `alembic revision --autogenerate`), corrigée avant de committer.

**Chiffrement — clé liée au compte** (`test_decrypt_fails_when_user_id_does_not_match_the_one_
used_to_encrypt`) : chiffrement avec `user_id` A, tentative de déchiffrement avec `user_id` B
→ `cryptography.exceptions.InvalidTag`, jamais un déchiffrement silencieux incorrect.

**Test de non-fuite dans les journaux** (`test_installed_filter_masks_a_key_logged_via_a_
named_logger`) : une clé Anthropic journalisée via un logger nommé (`pbm_api.ai.providers`,
pas `root`) ressort masquée (`***CLE_IA_MASQUEE***`) — couvre le cas que `logger.addFilter
(root)` aurait manqué.

**Test d'accès croisé** (`test_cross_user_isolation_on_ai_keys`) : B ne voit aucune clé de A
(`GET /me/ai-keys` vide) et une suppression de B visant le fournisseur configuré par A
seulement échoue en 404 (`test_delete_ai_key_returns_404_when_no_key_is_stored` couvre le cas
générique, `test_cross_user_isolation_on_ai_keys` le cas croisé) — jamais un 204 qui agirait
sur la ligne de A. `test_cross_user_isolation_on_ai_usage` : B ne voit aucune ligne d'usage de
A (`GET /me/ai-usage` vide malgré une ligne existante pour A).

**Preuve manuelle — essai réel contre les trois fournisseurs** (clés invalides, aucune clé
réelle disponible sur chimera ; confirme que l'appel réseau et le décodage de la réponse
fonctionnent, pas seulement le double de test) :

```
$ uv run python scripts/test_ai_key_manual.py anthropic sk-ant-not-a-real-key-000000
anthropic: valide=False — Clé refusée par le fournisseur.

$ uv run python scripts/test_ai_key_manual.py openai sk-not-a-real-key-000000
openai: valide=False — Clé refusée par le fournisseur.

$ uv run python scripts/test_ai_key_manual.py gemini AIzaNotARealKey000000000000000
gemini: valide=False — Clé refusée par le fournisseur.
```
(Gemini renvoyait d'abord « Réponse inattendue du fournisseur (400) » avant correction — voir
Choix techniques.)

**Revue de sécurité dédiée** (agent indépendant, focalisé sur ce diff) : crypto (nonce jamais
réutilisé, AAD `user_id` correcte, pas de déchiffrement silencieux), autorisation (toutes les
routes scopées par `get_current_user`, CSRF sur toute écriture), SSRF (URL fournisseur
strictement l'une des trois codées en dur, `provider` validé par l'énumération avant d'
atteindre le handler), injection (aucune, ORM partout) — jugés solides. Un finding confirmé
(fuite de la clé soumise dans une réponse 422) : corrigé et vérifié (voir Choix techniques).

## Écarts au plan

Aucun écart de périmètre sur la mission (§3). Les quatre routes/groupes de routes demandées
sont posées, le chiffrement enveloppe et le filtre de journalisation (§4) sont en place, la
table d'usage existe. `pnpm gen:api` non relancé (justifié ci-dessus, pas un écart de
périmètre au sens du prompt — aucune route front ne dépend de ce client dans ce lot).

## Reste à faire

- **Front** (`v1-profil`, selon le plan) : écran de gestion des clés — la maquette est portée
  par ce lot, pas `v1-byok`.
- **Écriture de `ai_usage_monthly`** : ce lot pose la table et sa lecture seule ; le worker de
  reconnaissance (lot futur) devra l'incrémenter à chaque appel réel.
- **Essai avec une vraie clé** (`scripts/test_ai_key_manual.py`) : fait avec des clés
  invalides (aucune clé réelle disponible ici) — à relancer avec une vraie clé Anthropic/
  Gemini/OpenAI dès qu'une est disponible, pour confirmer le chemin « clé valide » (200) que
  la suite automatisée ne peut pas prouver contre le vrai réseau.
- **`pnpm gen:api`** : à relancer par le prochain lot qui consomme `/me/ai-keys` côté front
  (regénère `packages/api-client/src/schema.d.ts`).
- **Rotation de la clé maître `AI_KEY_ENCRYPTION_KEY`** : documentée en commentaire
  (`security/crypto.py`) mais aucun script de rotation écrit — à faire le jour où elle sera
  réellement tournée (hors périmètre MVP).
- Aucune CI GitHub Actions déclenchée depuis cette session (dépôt relais local, pas GitHub) —
  la simulation locale du job `api` (migration + suite complète sur base éphémère) est
  documentée ci-dessus en attendant que le pilote synchronise vers GitHub.
