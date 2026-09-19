# Compte rendu — `v4-anecdotes`

Session autonome (`claude -p`) sur chimera, worktree `~/dev/wt-pbm-v4-anecdotes`, branche
`roadmap/v4-anecdotes`. Exécuté sous le régime décrit dans le CONTEXTE D'EXÉCUTION du prompt
(sections A/P/0/7 du prompt de lot remplacées) : pas de `suivi.py`, pas d'écriture dans
`etat.json`/`ROADMAP.html`/`BACKLOG.md`/`prompts/`, fusion directe vers `origin/main` (dépôt
relais local, pas GitHub).

## Résumé

`GET /cards/{card_id}/insights` : trois à cinq anecdotes courtes par carte, sourcées sur des
pages Poképédia/Bulbapedia récupérées côté serveur (liste blanche fixe de deux domaines
MediaWiki, jamais une URL fournie par le client), générées avec la clé IA de l'utilisateur qui
ouvre la fiche la première fois, mises en cache dans `card_insights` (partagé entre tous les
utilisateurs) et jamais régénérées ensuite pour la même carte. Toute anecdote dont `source_url`
n'appartient pas au contexte réellement récupéré est rejetée, y compris si le modèle a ignoré la
consigne du prompt (défense en profondeur contre le risque « hallucinations » de la mission).
`POST /cards/{card_id}/insights/report` : bouton « Signaler une erreur », un signalement par
utilisateur et par carte.

## Livrables

- `apps/api/src/pbm_api/insights/context.py` — `MediaWikiClient` (recherche + extrait texte brut
  via l'API MediaWiki publique de `POKEPEDIA_API_URL`/`BULBAPEDIA_API_URL`, jamais d'URL externe
  reçue), `collect_context` (au mieux 4 pages : carte + extension × 2 wikis, dédupliquées par URL,
  résiliente à un wiki muet ou en panne — ne lève jamais).
- `apps/api/src/pbm_api/insights/generation.py` — `AnecdoteItem`/`AnecdotesExtraction` (schéma
  Pydantic passé à `AIProvider.extract`), `build_prompt` (liste explicitement les pages
  disponibles et leurs URLs, interdit tout fait absent du contexte).
- `apps/api/src/pbm_api/insights/service.py` — `get_or_create_card_insight` : cache
  (`cached_until`, positif 180 j / négatif 1 j — jamais un échec permanent silencieux), verrou
  consultatif Postgres (`pg_advisory_xact_lock`) pour qu'une carte jamais vue ne déclenche qu'un
  seul appel IA même sous requêtes concurrentes, filtre `allowed_urls` sur les anecdotes reçues,
  clé du fournisseur par défaut de l'utilisateur (`users.ai_default_provider`, invariant déjà
  posé par `v1-byok` : un défaut choisi a toujours une clé). `report_card_insight` : upsert du
  signalement. Collaborateurs réseau (wikis, fabrique de fournisseur IA) injectés en paramètres,
  pas construits en dur — testables sans réseau.
- `apps/api/src/pbm_api/routers/card_insights.py` — les deux routes, dépendances FastAPI
  `get_pokepedia_client`/`get_bulbapedia_client`/`get_ai_provider_factory` (même pattern que
  `ProviderKeyTester` pour le coffre de clés) remplacées par des doubles dans la suite
  automatisée.
- `apps/api/src/pbm_api/models/catalog.py` — `CardInsightReport` (nouveau modèle ; `CardInsight`
  existait déjà depuis `v0-schema`, table `card_insights` inchangée, voir écarts).
- `apps/api/migrations/versions/7fc6cd5efc72_card_insight_reports.py` — table
  `card_insight_reports` (`card_id`, `user_id`, `reason`, contrainte unique `(card_id, user_id)`).
- `apps/api/src/pbm_api/main.py` — routeur `card_insights` enregistré.
- `apps/api/tests/test_insights_context.py` — `MediaWikiClient`/`collect_context` en isolation
  (recherche sans résultat, wiki en panne, déduplication, un seul wiki qui répond).
- `apps/api/tests/test_card_insights.py` — routes HTTP complètes : authentification, carte
  inconnue, D4 (pas de clé → `status: "no_ai_key"`), filtrage des anecdotes hors contexte, cache
  (deuxième appel sans nouvel appel IA), carte sans contexte, cache partagé entre deux
  utilisateurs (équivalent accès croisé pour cette donnée partagée, voir tests), signalement
  (CSRF, upsert, isolation par utilisateur, carte inconnue).
- `apps/api/scripts/test_insights_manual.py` — essai manuel avec une vraie clé IA (comme
  `test_ai_extraction_manual.py`), jamais exécuté par pytest.
- `apps/api/scripts/prove_insights_20_cards.py` — preuve du livrable sur 20 cartes réelles
  (résultats collés ci-dessous), pas exécuté par pytest (réseau réel vers les deux wikis).
- `docs/ARCHITECTURE.md` — section « Anecdotes sourcées (lot `v4-anecdotes`) ».
- `packages/api-client/src/schema.d.ts` régénéré (`pnpm gen:api`).
- Base dédiée créée sur l'infra partagée `pbm-shared` : `pbm_v4_anecdotes` (dev),
  `pbm_v4_anecdotes_test` (tests, migrées via `alembic upgrade head`), `apps/api/.env` local
  (gitignored) pointant dessus, `REDIS_PREFIX=pbm:v4-anecdotes:`. Pas de bucket S3 dédié : ce lot
  ne touche à aucune photo.

## Tests

```
$ cd apps/api && uv run ruff check .
All checks passed!

$ TZ=Europe/Paris TEST_DATABASE_URL=postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v4_anecdotes_test \
  uv run pytest -q
272 passed in 25.56s   # 255 préexistants (après rebase sur origin/main) + 17 nouveaux

$ uv run pytest -q tests/test_card_insights.py tests/test_insights_context.py
17 passed in 2.52s
```

- `test_get_insights_requires_authentication`/`test_get_insights_returns_404_for_unknown_card`
  **échouent sans ce lot** (`404 Not Found` de FastAPI faute de routeur, pas le 404 métier attendu
  par le second test) et passent une fois branché.
- **Preuve ciblée « rejet des anecdotes non sourcées » (risque « hallucinations », mission point
  2/4)** : `test_get_insights_filters_out_anecdotes_without_a_source_in_context` — vérifié en
  retirant temporairement le filtre `if item.source_url in allowed_urls` dans
  `pbm_api.insights.service.get_or_create_card_insight` : le test échoue alors en recevant les
  deux anecdotes (dont celle à l'URL inventée) au lieu d'une seule ; remis en place, il repasse.
  Aucun autre test de la suite n'est affecté par ce retrait ponctuel.
- **Cache** : `test_get_insights_uses_cache_on_second_call_without_calling_ai_again` — un deuxième
  appel sur la même carte ne recrée aucun fournisseur IA (`len(created) == 1` après deux requêtes
  HTTP).
- **Accès croisé** : `card_insights` est un cache **partagé** entre utilisateurs par conception
  (`docs/ARCHITECTURE.md`, confirmé par le schéma posé dès `v0-schema` : `UniqueConstraint("card_id")`,
  pas de `user_id`) — pas de 404 à tester ici. L'équivalent pour cette donnée est
  `test_second_user_reads_the_shared_cache_without_owning_a_key` : un utilisateur B sans clé IA lit
  les anecdotes générées par un utilisateur A, sans jamais voir son fournisseur/modèle
  (`source_model` absent de `CardInsightsResponse`). Le signalement, lui, est bien scopé par
  utilisateur : `test_report_card_insight_is_scoped_per_user` — A et B qui signalent la même carte
  produisent deux lignes distinctes, chacune avec sa propre raison.
- **Maquette** : sans objet, back-end seul — affichée par la fiche carte (lot futur `v4-fiche`,
  route placeholder déjà posée par `v0-design-system`, `apps/web/src/app/carte/[id]/page.tsx`).

Rejoué avec les variables d'environnement de la CI (surcharge des valeurs par défaut, comme
`.github/workflows/ci.yml`) : `DATABASE_URL`/`TEST_DATABASE_URL`/`REDIS_URL`/`S3_*`/
`TZ=Europe/Paris` → suite complète verte, aucune régression liée aux noms de variables.

Migration : `alembic upgrade head` puis `alembic downgrade -1` puis `alembic upgrade head` sur
`pbm_v4_anecdotes_test` → aller-retour propre, aucune erreur.

Recherche de motifs de clé/secret sur les fichiers ajoutés → aucun résultat (ce lot ne stocke ni
ne journalise aucune clé IA ; il ne fait que lire la clé déjà déchiffrée par
`pbm_api.security.crypto.decrypt_api_key`, comme les lots précédents).

## Preuve du livrable « anecdotes sourcées sur 20 cartes de test » (réseau réel)

`scripts/prove_insights_20_cards.py` interroge les vrais Poképédia/Bulbapedia pour 20 cartes
réelles (Dracaufeu, Pikachu, Mewtwo, Évoli, Léviator, Rayquaza, Lugia, Ronflex, Dracolosse,
Tortank, Florizarre, Sulfura, Artikodin, Électhor, Gardevoir, Ectoplasma, Metaglinite, Farfuret,
Miaouss, Roucarnage). Aucune clé IA réelle sur chimera (D4) : la génération est simulée par une
fonction qui pioche une phrase du contexte réel comme anecdote « correcte », et une carte sur
trois une URL fabriquée hors contexte, pour vérifier le filtre `allowed_urls` sur du contenu réel
plutôt que sur des pages fabriquées par les tests.

```
$ uv run python scripts/prove_insights_20_cards.py
Dracaufeu            status=ready       pages=2 anecdotes=2 rejetées=1
Pikachu              status=ready       pages=2 anecdotes=2 rejetées=0
[...18 autres cartes, toutes status=ready...]
Ectoplasma           status=ready       pages=1 anecdotes=1 rejetées=1

20/20 cartes avec au moins une anecdote sourcée.
7 anecdote(s) hors contexte correctement rejetée(s) par le filtre.
```

→ collecte de contexte fonctionnelle de bout en bout contre les deux vrais wikis pour 20/20
cartes de test, et le filtre anti-hallucination rejette bien les 7 anecdotes hors contexte
injectées sur du contenu réel (pas seulement les pages fabriquées des tests unitaires).

## Preuve en conditions réelles (serveur HTTP réel, vrai Postgres, vrai Mailpit)

```
$ uv run uvicorn pbm_api.main:app --port 18327 &   # contre pbm_v4_anecdotes (dev)
$ curl -X POST .../auth/register -d '{"email":"...","password":"..."}'   # 202
$ # token de vérification récupéré via l'API Mailpit (localhost:58025), pas RecordingEmailSender
$ curl -X POST .../auth/verify-email -d '{"token":"..."}'                # 200
$ curl -c cookies.txt -X POST .../auth/login -d '{"email":"...","password":"..."}'  # 200
$ curl .../cards/<uuid-inconnu>/insights                                 # 401 (sans cookie)
{"detail":"Non authentifié"}
$ curl -b cookies.txt .../cards/<uuid-inconnu>/insights                  # 404
{"detail":"Carte introuvable."}
$ curl -b cookies.txt .../cards/<carte-de-preuve>/insights               # 200, sans clé par défaut
{"card_id":"...","status":"no_ai_key","anecdotes":[],"generated_at":null}
$ curl -b cookies.txt -X POST .../cards/<carte-de-preuve>/insights/report -d '{}'  # 403 sans CSRF
{"detail":"Jeton CSRF invalide"}
$ curl -b cookies.txt -H "X-CSRF-Token: ..." -X POST .../insights/report -d '{"reason":"..."}'  # 204
```

→ vérifié en base (`SELECT * FROM card_insight_reports`) que la ligne est bien écrite avec la
bonne raison. Utilisateur, extension, carte et signalement de preuve supprimés juste après
vérification (base de dev laissée propre — comptes vérifiés en base : 0 ligne restante sur les
quatre tables touchées).

## Choix techniques faits (autonomes, dans le cadre de `docs/ARCHITECTURE.md`)

- **Contexte via l'API MediaWiki publique (`action=query`), pas un scraping HTML** : Poképédia et
  Bulbapedia tournent tous deux sur MediaWiki ; l'API `search` + `extracts` donne un texte brut
  déjà nettoyé (pas de balisage wiki à parser) et une URL canonique fiable (`inprop=url`) — plus
  robuste qu'un scraping HTML face à un changement de thème, et strictement conforme à la mission
  (« récupération serveur, liste blanche de domaines »› les deux constantes d'URL sont des
  littéraux du module, jamais construites depuis une entrée utilisateur).
- **Nom anglais de la carte pour Bulbapedia** : `card.name`/`Set.name` sont en français (fixé par
  `v2-catalogue`, confirmé en lisant `import_service.py` — `fr_detail`/`detail` proviennent du
  passage FR de l'import) ; chercher le nom français sur le wiki anglais aurait dégradé le taux de
  succès de la recherche. `CardName.language == "en"` est utilisé quand disponible, sinon repli
  sur `card.name` (import partiel/incomplet plutôt qu'un manque total de contexte).
- **Verrou consultatif Postgres (`pg_advisory_xact_lock`) plutôt qu'une contrainte unique seule** :
  la contrainte unique sur `card_insights.card_id` empêche une ligne dupliquée, mais pas deux
  appels IA concurrents facturés à deux utilisateurs différents pour la même carte jamais vue
  (mission point 2 : « clé de l'utilisateur qui ouvre la fiche la première fois », un coût réel).
  Le verrou est tenu le temps de la transaction (relecture du cache après acquisition) — non
  testé en concurrence réelle (deux connexions séparées, hors de portée d'un test unitaire simple
  sur une session en savepoint), documenté en écart.
- **Cache négatif court (1 jour) plutôt qu'illimité** : une carte sans contexte aujourd'hui (wiki
  en panne, contenu pas encore écrit) peut en trouver un demain — un échec de collecte ne doit
  jamais devenir un échec permanent silencieux (règle du dépôt sur les replis silencieux).
- **`ai_default_provider`/`ai_default_model` (déjà posés par `v1-byok`) plutôt qu'un choix de
  fournisseur par requête** : invariant déjà garanti côté service (`update_settings` refuse un
  défaut sans clé stockée, `DefaultProviderWithoutKeyError`) — réutilisé tel quel, aucune clé
  plateforme dans ce lot (D4 : sans clé, génération désactivée, jamais un décompte scellé au
  format de la carte).
- **Collaborateurs réseau injectés par dépendance FastAPI** (`get_pokepedia_client`/
  `get_bulbapedia_client`/`get_ai_provider_factory`), même pattern que `ProviderKeyTester` du
  coffre de clés — nécessaire ici puisque `pbm_api.insights.service` est le premier consommateur
  de `AIProvider.extract` en dehors des tests du lot `v3-ia-providers` : sans ce point d'injection,
  toute la suite HTTP dépendrait du réseau réel (deux wikis + un fournisseur IA), ce que le dépôt
  évite systématiquement ailleurs.
- **`in_game_study` (étude en jeu) non touché** : la mission de ce lot ne porte que sur
  `anecdotes` ; `docs/roadmap/roadmap.json` (`v4-fiche.tenants`) mentionne un lot séparé pour
  l'étude en jeu — colonne laissée `NULL`, aucune route de ce lot ne l'écrit ni ne la lit.

## Écarts au plan

- **`card_insights` sans dimension « langue »/« version »** : la mission liste « Cache
  `card_insights` (langue, version, date) », mais la table (posée par `v0-schema`, avant ce lot)
  a `UniqueConstraint("card_id")` seule — une ligne par carte, pas par langue. Plutôt que
  d'élargir un schéma déjà partagé par plusieurs lots fusionnés (`v2-prix`, `v1-byok`...) sans
  décision explicite, ce lot respecte le schéma existant : les anecdotes sont générées une fois
  par carte (langue de rédaction non figée dans le schéma — en pratique le prompt écrit en
  français). La dimension « date » est bien couverte (`generated_at`/`cached_until`) ; « version »
  (ex : invalider le cache après une amélioration du prompt) ne l'est pas — à traiter par un lot
  ultérieur si besoin, ou en vidant manuellement `card_insights` après un changement de prompt.
- **Verrou consultatif non testé en concurrence réelle** : voir choix techniques — le comportement
  attendu (dé-duplication de l'appel IA) est démontré par construction (relecture du cache après
  acquisition du verrou) et par le test de cache séquentiel, pas par un test à deux connexions
  concurrentes.
- **Preuve des 20 cartes avec fournisseur simulé, pas une vraie clé IA** : conforme au cadre
  (« Aucune clé IA réelle n'est disponible : tests avec réponses enregistrées ou fournisseur
  simulé ») — `scripts/test_insights_manual.py` est prêt pour l'essai avec une vraie clé plus
  tard, non exécuté ici.
- **Client TypeScript régénéré, mais aucune page front ne le consomme encore** : `v4-fiche`
  (dépendant de ce lot) affichera les anecdotes ; la route `/carte/[id]` reste le placeholder posé
  par `v0-design-system`.

## Reste à faire

- `v4-fiche` : consommer `GET /cards/{id}/insights` sur la fiche carte, bouton « Signaler une
  erreur » côté front (l'API existe, l'UI n'existe pas encore — hors périmètre `maquette: sans
  objet` de ce lot).
- Décision explicite si une dimension « langue »/« version » doit être ajoutée à `card_insights`
  (voir écarts) — actuellement une ligne par carte, contenu en français.
- Test de concurrence réelle du verrou consultatif (deux connexions séparées), si un lot futur en
  a besoin pour une preuve plus forte que le raisonnement par construction ci-dessus.
