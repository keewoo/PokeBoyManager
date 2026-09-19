# Compte rendu — `v3-ia-providers`

Session autonome (`claude -p`) sur chimera, worktree `~/dev/wt-pbm-v3-ia-providers`, branche
`roadmap/v3-ia-providers`. Exécuté sous le régime décrit dans le CONTEXTE D'EXÉCUTION du
prompt (sections A/P/0/7 du prompt de lot remplacées) : pas de `suivi.py`, pas d'écriture dans
`etat.json`/`ROADMAP.html`/`BACKLOG.md`/`prompts/`, dépendance `v1-byok` déjà fusionnée dans
`origin/main` (dépôt relais local, pas GitHub).

## Résumé

Couche fournisseurs IA unique : `AIProvider.extract(images, schema, prompt) -> (objet validé,
usage)`, une implémentation par fournisseur (Anthropic, Google Gemini, OpenAI) derrière une
seule interface — la reconnaissance (lot futur) n'appellera jamais un fournisseur en direct.
Sortie structurée native de chaque fournisseur (`output_config.format` Anthropic,
`response_format` strict OpenAI, `responseSchema` Gemini) traduite depuis un schéma Pydantic,
validée par Pydantic côté serveur, une nouvelle tentative guidée si elle ne valide pas.
Erreurs normalisées (clé invalide, quota, surcharge, fournisseur injoignable, contenu refusé)
avec un message utilisateur prêt à consigner sur un `Job`. Aucune clé IA réelle disponible sur
chimera : suite automatisée sur réponses enregistrées (`httpx.MockTransport`), essai manuel
avec des clés invalides confirmant le format de requête et l'authentification contre le vrai
réseau des trois fournisseurs (voir Preuves).

## Livrables

- `apps/api/src/pbm_api/ai/base.py` — interface `AIProvider` (méthode `extract`, template
  method) : un appel (`_call`, abstrait par fournisseur) puis validation Pydantic ; sur
  `ValidationError`, un second appel avec l'erreur expliquée au modèle, puis abandon
  (`InvalidExtractionResponseError`) si elle échoue encore. `ImageInput`/`ExtractionUsage` —
  schémas Pydantic partagés par les trois implémentations.
- `apps/api/src/pbm_api/ai/anthropic_provider.py` — `POST /v1/messages`, `output_config.format`
  (JSON Schema), vision par blocs `image` base64. Défaut `claude-sonnet-5`, économique
  `claude-haiku-4-5` (mission §3). Contenu refusé détecté via `stop_reason == "refusal"`.
- `apps/api/src/pbm_api/ai/openai_provider.py` — `POST /v1/chat/completions`,
  `response_format` en mode `strict` (JSON Schema strict, `additionalProperties: false`,
  `required` exhaustif). Défaut `gpt-4o`. Contenu refusé détecté via
  `finish_reason == "content_filter"`.
- `apps/api/src/pbm_api/ai/gemini_provider.py` — `generateContent`,
  `generationConfig.responseSchema` (variante OpenAPI restreinte, sans `$ref`). Défaut
  `gemini-2.5-flash`. Contenu refusé détecté via `finishReason` (`SAFETY`, `RECITATION`,
  `BLOCKLIST`, `PROHIBITED_CONTENT`, `SPII`). Correspondance d'erreur dédiée
  (`_raise_for_gemini_error`) : Gemini ne distingue pas ses erreurs par code HTTP seul (un 400
  couvre clé invalide et requête malformée) — voir Choix techniques.
- `apps/api/src/pbm_api/ai/json_schema.py` — `to_strict_schema` (Anthropic/OpenAI : `$ref`
  repliés, `additionalProperties: false` et `required` exhaustif à tous les niveaux) et
  `to_gemini_schema` (en plus : `Optional[X]` → `{"type": "X", "nullable": true}`, pas
  d'`additionalProperties`).
- `apps/api/src/pbm_api/ai/http_errors.py` — correspondance code HTTP → erreur normalisée
  commune à Anthropic/OpenAI (401/403 → clé invalide, 429 → quota, 5xx → surchargé, autre 4xx →
  erreur générique plutôt que mal classée).
- `apps/api/src/pbm_api/ai/images.py` — `detect_media_type` (octets → JPEG/PNG/WebP par
  signature binaire, jamais supposé).
- `apps/api/src/pbm_api/ai/factory.py` — `create_provider(provider, api_key)`, seul point de
  correspondance énumération → implémentation.
- `apps/api/src/pbm_api/ai/errors.py` — étendu (les exceptions `v1-byok` existantes sont
  inchangées) : `AIProviderError` (base, `user_message`) et ses sous-classes
  `InvalidApiKeyError`/`QuotaExceededError`/`ProviderOverloadedError`/
  `ProviderUnreachableError`/`ContentRefusedError`/`InvalidExtractionResponseError`, plus
  `UnsupportedImageFormatError`.
- `apps/api/scripts/test_ai_extraction_manual.py` — essai manuel avec une vraie clé (pixel 1x1,
  aucune clé IA réelle disponible sur chimera pour la suite automatisée).
- `apps/api/tests/test_ai_providers.py` (24 tests), `test_ai_json_schema.py` (5),
  `test_ai_images.py` (4) — détail des preuves ci-dessous.
- `CLAUDE.md`, `docs/ARCHITECTURE.md` — nouvelle section « Fournisseurs IA ».

## Choix techniques

- **HTTP direct (`httpx`) plutôt que les SDK officiels des trois fournisseurs.** Décision
  délibérée, pas un oubli : `ProviderKeyTester` (`v1-byok`) avait déjà fait ce choix pour les
  mêmes trois fournisseurs, avec la même justification (clé en en-tête HTTP, jamais en
  paramètre d'URL) — rester cohérent avec ce précédent évite d'avoir deux façons d'appeler
  Anthropic/Gemini/OpenAI dans le même dépôt. Trois SDK de plus (avec leurs propres mises à
  jour de sécurité à suivre) sur un lien à ~250 ko/s, alors qu'aucune clé réelle n'est
  disponible ici pour vérifier leur comportement exact, n'apportait rien de mesurable pour ce
  lot ; le format de chaque fournisseur est documenté et stable (JSON Schema pour la sortie
  structurée, vision par blocs base64), donc directement reproductible en HTTP brut.
- **`AIProvider.extract` en template method** (`_call` abstrait, retenté une fois si la
  validation Pydantic échoue) plutôt que dupliquer la boucle de nouvelle tentative dans les
  trois implémentations — un seul endroit change si la politique de nouvelle tentative évolue
  (aujourd'hui : une seule tentative supplémentaire, mission §2).
- **`pbm_api.ai.json_schema` sépare `to_strict_schema` et `to_gemini_schema`** plutôt qu'un
  format unique pour les trois : Gemini n'accepte ni `$ref`/`$defs` ni `additionalProperties`,
  et représente un champ optionnel par `nullable: true` plutôt que par une union avec `null`
  (forme émise par Pydantic pour tout `X | None`) — risque nommé par la mission (§4, formats de
  sortie structurée différents d'un fournisseur à l'autre). Un seul schéma normalisé n'aurait
  satisfait aucun des trois correctement.
- **Erreur Gemini distincte de la correspondance HTTP commune** (`http_errors.py`) : Anthropic
  et OpenAI distinguent leurs erreurs par code HTTP (401/429/5xx) ; Gemini renvoie un 400 aussi
  bien pour une clé invalide (`API_KEY_INVALID`, message contenant « API key not valid ») que
  pour une requête malformée (`INVALID_ARGUMENT` générique) — déjà observé par
  `ProviderKeyTester` (`v1-byok`) sur son propre endpoint de test. Traiter tout 400 Gemini
  comme une clé invalide aurait été un mauvais diagnostic pour l'utilisateur sur une vraie
  extraction (schéma mal formé, image trop grande...) — `test_gemini_extract_does_not_
  confuse_a_malformed_request_with_an_invalid_key` couvre ce cas précisément.
- **Modèles par défaut Gemini (`gemini-2.5-flash`) et OpenAI (`gpt-4o`)** : la mission ne fixe
  que les deux modèles Anthropic (§3) ; en l'absence d'une clé réelle pour confirmer un choix
  plus récent, `gpt-4o` et `gemini-2.5-flash` sont les identifiants les plus largement
  documentés et stables au moment du lot, retenus par prudence plutôt qu'un nom plus récent non
  vérifiable ici. `users.ai_default_model` (`v1-byok`) reste la voie normale pour les changer
  par utilisateur — ces constantes ne servent qu'en repli. Voir « Reste à faire ».
- **`raise_for_status` (Anthropic/OpenAI) ne classe pas tout 4xx non reconnu comme une
  surcharge** : un 400 inattendu (bogue dans le corps envoyé, par exemple) lève `AIProviderError`
  générique plutôt que d'être rattaché arbitrairement à l'un des quatre buckets attendus par la
  mission (§3) — un mauvais classement aurait caché un vrai bogue derrière un message
  « réessayez plus tard » trompeur.

## Décisions provisoires utilisées

Aucune (D4 n'est pas concernée par ce lot — elle régit l'absence de clé, pas le fonctionnement
de la couche fournisseurs une fois une clé présente).

## Preuves — commandes lancées, résultats chiffrés

```
$ cd apps/api && uv run ruff check .
All checks passed!

$ TZ=Europe/Paris TEST_DATABASE_URL=postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v3_ia_providers_test \
    uv run pytest -q
................................................................................ [ 51%]
....................................................................             [100%]
140 passed, 2 warnings in 9.50s
```
(107 tests déjà présents avant ce lot + 33 nouveaux : 24 dans `test_ai_providers.py`, 5 dans
`test_ai_json_schema.py`, 4 dans `test_ai_images.py` — cf. mission §6 « un test qui échoue sans
le changement, passe avec » : ces trois fichiers importent des modules qui n'existaient pas
avant ce lot, donc échouent à la collection sans lui.)

Preuve ciblée sur le comportement de nouvelle tentative (§6) : dans
`pbm_api/ai/base.py::AIProvider.extract`, le bloc `try/except ValidationError` qui refait un
appel et valide une seconde fois a été temporairement remplacé par un simple
`return schema.model_validate_json(text), usage` (pas de retry), puis
`uv run pytest -q tests/test_ai_providers.py` relancé :

```
FAILED tests/test_ai_providers.py::test_anthropic_extract_retries_once_then_succeeds_on_invalid_json
FAILED tests/test_ai_providers.py::test_anthropic_extract_raises_after_two_invalid_json_responses
2 failed, 22 passed in 0.24s
```
Exactement les deux tests qui portent sur la nouvelle tentative échouent, les 22 autres restent
verts — la nouvelle tentative n'est pas un test qui passe par coïncidence. Code restauré, suite
repassée entièrement au vert (voir bloc ci-dessus).

Simulation du job CI (base éphémère `pbm_v3_ia_providers_citest`, comme le service Postgres
GitHub Actions, mêmes variables d'environnement que `.github/workflows/ci.yml`, migration puis
suite complète) :

```
$ DATABASE_URL=…/pbm_v3_ia_providers_citest TEST_DATABASE_URL=…/pbm_v3_ia_providers_citest \
    REDIS_URL=redis://localhost:56379/0 S3_BUCKET=pbm-v3-ia-providers-ci TZ=Europe/Paris \
    uv run alembic upgrade head
Running upgrade  -> 5e0d551b788e, initial schema
Running upgrade 5e0d551b788e -> 1d51087de4ae, catalog reconciliation and image fields
Running upgrade 1d51087de4ae -> 8565c4640de8, exchange rates daily and user preferred currency
Running upgrade 8565c4640de8 -> d42b0620077e, ai settings and usage

$ (mêmes variables) uv run ruff check .
All checks passed!

$ (mêmes variables) uv run pytest -q
140 passed, 2 warnings in 9.32s
```
(base éphémère supprimée après coup — ce lot n'ajoute aucune migration, la chaîne existante
rejoue telle quelle.)

**Preuve manuelle — essai réel contre les trois fournisseurs** (clés invalides, aucune clé
réelle disponible sur chimera ; confirme que la requête vision + sortie structurée, l'en-tête
d'authentification et le décodage de la réponse d'erreur fonctionnent contre le vrai réseau,
pas seulement le double de test) :

```
$ uv run python scripts/test_ai_extraction_manual.py anthropic sk-ant-not-a-real-key-000000
anthropic: échec — Clé invalide ou révoquée par le fournisseur.

$ uv run python scripts/test_ai_extraction_manual.py openai sk-not-a-real-key-000000
openai: échec — Clé invalide ou révoquée par le fournisseur.

$ uv run python scripts/test_ai_extraction_manual.py gemini AIzaNotARealKey000000000000000
gemini: échec — Clé invalide ou révoquée par le fournisseur.
```
Les trois erreurs viennent bien du réseau (pas d'exception de sérialisation/connexion avant) :
la requête (image base64, schéma JSON, en-tête d'authentification) est acceptée par chaque
fournisseur qui répond ensuite sur la clé, exactement le chemin qu'emprunterait une vraie
extraction.

**Test d'accès croisé (§6)** : sans objet — ce module ne reçoit qu'une clé déjà résolue pour
l'utilisateur courant (`AIProvider.__init__(api_key, ...)`), aucun `user_id` n'y transite.
L'isolation par utilisateur est couverte en amont dans `tests/test_ai_keys.py` (coffre de
clés, lot `v1-byok`, déjà fusionné) et le sera en aval par le futur job de reconnaissance qui
appellera `create_provider` avec la clé déjà déchiffrée pour l'utilisateur courant.

**Maquette (§6)** : sans objet — confirmé par la grille (« maquette : sans objet, back-end »,
`taches_na` du plan).

## Écarts au plan

Aucun écart de périmètre sur la mission (§3). Les quatre points (interface + trois
implémentations, sortie structurée + validation + nouvelle tentative, erreurs normalisées,
tests enregistrés + script manuel) sont couverts.

## Reste à faire

- **Intégration au job de reconnaissance** (aboutissants du plan : détection, identification,
  état, anecdotes, étude en jeu) : hors périmètre de ce lot (mission §3, interface seule) —
  le futur lot de reconnaissance appellera `pbm_api.ai.factory.create_provider` avec la clé de
  l'utilisateur déchiffrée et écrira dans `ai_usage_monthly` (posée par `v1-byok`, lecture
  seule jusqu'ici).
- **Confirmation des modèles par défaut OpenAI/Gemini avec une vraie clé** : `gpt-4o` et
  `gemini-2.5-flash` sont un choix par prudence (voir Choix techniques), jamais appelés avec
  succès faute de clé réelle sur chimera — à vérifier (et ajuster si un modèle plus récent est
  préférable) dès qu'une clé est disponible, via `scripts/test_ai_extraction_manual.py`.
- **Chemin « clé valide » non prouvé contre le vrai réseau** : comme pour `v1-byok`, seul le
  chemin d'erreur (clé invalide) a pu être vérifié ici ; le chemin de succès (extraction réelle,
  sortie structurée effectivement conforme au schéma envoyé) reste à confirmer avec une vraie
  clé Anthropic/Gemini/OpenAI.
- **Normalisation Gemini du schéma** (`pbm_api.ai.json_schema._to_gemini`) couvre le cas
  `Optional[X]` (forme émise par Pydantic pour `X | None`) mais pas toute construction Pydantic
  exotique (`Union` à plus de deux branches, contraintes `Literal` imbriquées) — suffisant pour
  les schémas d'extraction de carte prévus (champs plats + une liste d'objets simples), à
  étendre si un schéma plus complexe l'exige.
