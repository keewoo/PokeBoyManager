# Compte rendu — `v2-recherche`

Session autonome (`claude -p`) sur chimera, worktree `~/dev/wt-pbm-v2-recherche`, branche
`roadmap/v2-recherche`. Exécuté sous le régime décrit dans le CONTEXTE D'EXÉCUTION du prompt
(sections A/P/0/7 du prompt de lot remplacées) : pas de `suivi.py`, pas d'écriture dans
`etat.json`/`ROADMAP.html`/`BACKLOG.md`/`prompts/`, fusion directe vers `origin/main` (dépôt
relais local, pas GitHub).

## Résumé

`GET /catalog/search?q=&set=&lang=` : recherche dans le catalogue par nom (trigram + `unaccent`
sur `card_names`, FR/EN, casse et accents ignorés) ou par numéro (simple, zéro-rempli, formats
promo/galerie `TG05`/`GG10`/`SV107`/`XY121`, format `numéro/total`). `match_candidates`
(`pbm_api.catalog.search`) est la fonction interne de rapprochement, écrite pour être réutilisée
telle quelle par la reconnaissance (lot futur) : donné un nom et/ou un numéro déjà extraits, plus
des indices optionnels d'extension et de total, elle renvoie les cartes candidates classées par
score. 50 requêtes de référence en test (paramétrées, contre un vrai Postgres avec `pg_trgm`/
`unaccent`) + 16 tests directs de `match_candidates`/`parse_query`.

## Livrables

- `apps/api/src/pbm_api/catalog/search.py` — `parse_query` (numéro vs nom), `match_candidates`
  (scoring pondéré : similarité de nom × 0.5, présence d'un numéro filtré × 0.4, indice
  d'extension bruité × 0.15, bonus total de l'extension × 0.1 — poids choisis par jugement, voir
  choix techniques), `CardCandidate` (dataclass de résultat).
- `apps/api/src/pbm_api/routers/catalog.py` — `GET /catalog/search`, `_search_by_name` (essaie
  chaque découpage `<nom> <indice d'extension>` d'une requête libre et garde le meilleur score
  par carte — gère le cas "Pikachu VMAX Voltage Éclatant" de la mission).
- `apps/api/src/pbm_api/main.py` — routeur `catalog` enregistré.
- `apps/api/tests/test_catalog_search.py` — 50 requêtes de référence paramétrées (`CATALOG_QUERIES`,
  vérifié `len(...) >= 50` en dur dans le fichier) + 2 tests de route (existence, `q` manquant →
  422).
- `apps/api/tests/test_catalog_match_candidates.py` — `parse_query` (numéro, numéro/total, promo/
  galerie, nom, chaîne vide) et `match_candidates` appelée directement (sans HTTP) : score exact,
  filtre strict par numéro, bonus total, filtre langue, filtre `set_code`, requête sans critère,
  nom inconnu.
- `docs/ARCHITECTURE.md` — section « Recherche catalogue (lot `v2-recherche`) ».
- Bases dédiées créées sur l'infra partagée `pbm-shared` : `pbm_v2_recherche` (dev),
  `pbm_v2_recherche_test` (tests, migrées via `alembic upgrade head`), `apps/api/.env` local
  (gitignored) pointant dessus. Pas de bucket S3 ni de préfixe Redis dédiés : ce lot ne touche à
  aucune photo ni file de jobs.

## Tests

```
$ cd apps/api && uv run ruff check .
All checks passed!

$ uv run pytest -q
148 passed in 10.20s   # 80 préexistants + 68 nouveaux

$ uv run pytest -q tests/test_catalog_search.py tests/test_catalog_match_candidates.py -v | tail -5
52 passed   # dont 50 requêtes de référence paramétrées
16 passed
```

Rejoué avec les variables d'environnement de la CI (surcharge des valeurs par défaut, comme
`.github/workflows/ci.yml`) : `DATABASE_URL`/`TEST_DATABASE_URL`/`REDIS_URL`/`S3_*`/
`TZ=Europe/Paris` → 148 passed, aucune régression liée aux noms de variables.

- `test_search_catalog_route_exists` **échoue sans ce lot** (`404 Not Found`, aucune route
  `/catalog/search` avant) et passe avec.
- **Accès croisé** : sans objet — catalogue public, aucun `user_id` sur `cards`/`card_names`/
  `sets` (confirmé par `docs/ARCHITECTURE.md`, ces tables sont partagées entre utilisateurs
  depuis `v0-schema`/`v2-catalogue`). Documenté dans la grille (`securite`).
- **Maquette** : sans objet, back-end seul (comme `v2-catalogue`/`v2-prix`).
- **50 requêtes de référence** (`CATALOG_QUERIES`) : noms FR/EN exacts et partiels, cross-langue
  (interroger en anglais retrouve la carte FR et vice-versa), casse, accents avec/sans, tirets,
  espaces superflus, apostrophe non gênante, ambiguïté assumée (plusieurs cartes "Pikachu"),
  inconnu → vide ; numéros simples/zéro-remplis, numéros partagés entre extensions désambiguïsés
  par le total (`163/198` vs `163/163`), formats promo/galerie ; filtres explicites `set` (code ou
  nom exact, strict) et `lang` (strict) ; requêtes combinant nom de carte + nom d'extension dans
  une seule chaîne (l'exemple de la mission, "Pikachu VMAX Voltage Éclatant").

## Preuve en conditions réelles (serveur HTTP réel, pas seulement `ASGITransport` des tests)

```
$ uv run uvicorn pbm_api.main:app --port 18321 &   # contre pbm_v2_recherche (dev), 2 cartes semées
$ curl "http://127.0.0.1:18321/catalog/search?q=mewtwo"
[{"number":"006","name":"Mewtwo","matched_name":"Mewtwo","language":"fr","set_name":"151","score":0.5}]
$ curl "http://127.0.0.1:18321/catalog/search?q=025"
[{"number":"025","name":"Pikachu","matched_name":"Pikachu","language":null,"set_name":"151","score":0.4}]
$ curl "http://127.0.0.1:18321/catalog/search?q=25/165"
[{"number":"025","name":"Pikachu",...,"score":0.5}]   # bonus total (165 = total_cards du set)
$ curl "http://127.0.0.1:18321/catalog/search?q=piikachu"
[{"number":"025","name":"Pikachu","matched_name":"Pikachu","language":"fr",...,"score":0.35}]
```

→ recherche fonctionnelle de bout en bout contre un vrai Postgres avec `pg_trgm`/`unaccent`, y
compris la tolérance à une faute de frappe (`piikachu`). Données de démonstration supprimées
après vérification (`DELETE` du set de test, base de dev laissée propre).

Recherche de motifs de clé/secret sur les fichiers ajoutés → aucun résultat (cette route ne touche
à aucune donnée utilisateur ni credential).

## Choix techniques faits (autonomes, dans le cadre de `docs/ARCHITECTURE.md`)

- **`set_hint` (bruité, pondère) vs `set_code` (exact, filtre)** : deux paramètres distincts sur
  `match_candidates`. La reconnaissance future extrait un indice d'extension par OCR, peu fiable
  (mission « pièges » : accents, formats variables) — un mauvais indice ne doit jamais faire
  disparaître la bonne carte, seulement influencer son classement. Un filtre `set` choisi
  explicitement dans une liste (UI) est en revanche fiable et filtre strictement. Même logique
  pour `total` (bonus de score, jamais un filtre) : le nombre après `/` dans `236/217` désambiguïse
  entre extensions partageant un numéro, mais une mauvaise lecture du total ne doit pas exclure la
  bonne carte si elle reste la seule à matcher le numéro.
- **Découpage `<nom> <indice d'extension>` essayé à toutes les positions** (`_search_by_name`,
  jusqu'à `len(q.split())` requêtes SQL par recherche) plutôt qu'une règle de séparation figée
  (virgule, tiret) : la mission donne l'exemple « Pikachu VMAX Voltage Éclatant » sans séparateur
  identifiable, et les noms d'extension français font 1 à 4 mots. Coût acceptable au volume actuel
  (recherche interactive, pas un traitement de masse) ; à revoir avec une requête SQL unique si la
  latence devient sensible en production (`docs/ARCHITECTURE.md`, note de risque déjà posée).
- **Poids du score choisis par jugement** (nom ×0.5, numéro ×0.4, indice d'extension ×0.15, total
  ×0.1 — non exclusifs, pas de barème fourni par le plan) : calibrés en conditions réelles contre
  Postgres (pas seulement en théorie) sur des cas volontairement ambigus (numéro partagé entre
  extensions, nom court `Pikachu` vs `Pikachu V`/`Pikachu VMAX` dans la même extension) jusqu'à ce
  que l'ordre produit corresponde à l'intuition d'un utilisateur — voir les tests
  `filtre-set-par-code` et `nom-casse-majuscules` où l'ordre "naturel" par similarité pure
  (un nom plus court gagne sur un nom plus long avec le même préfixe) a été accepté tel quel
  plutôt que forcé, cette dégradation étant raisonnable et non une panne.
- **Plancher de similarité `NAME_SCORE_THRESHOLD = 0.15`** : sans lui, toute requête remonterait
  la totalité du catalogue triée par un score proche de zéro (`gibberish` non filtré). Valeur
  choisie empiriquement (assez basse pour tolérer une faute de frappe comme `piikachu`, assez
  haute pour exclure `qwjkzxqvwp`) — à ajuster si un lot ultérieur observe trop/pas assez de bruit
  sur le vrai catalogue (actuellement vide sur cette base de dev, voir écarts).

## Écarts au plan

- **Catalogue de dev vide au démarrage de ce lot** (bases isolées par lot, comme `v2-prix`) : les
  50 requêtes de référence et les preuves en conditions réelles utilisent des jeux de données
  construits pour ce lot (fixtures de test, ou 2 cartes semées manuellement pour la preuve HTTP),
  pas le catalogue TCGdex réel importé par `v2-catalogue`. Le comportement du plancher de
  similarité et des poids de score n'a donc pas été validé contre le volume et le bruit réels
  (dizaines de milliers de cartes) — à revalider une fois `v2-catalogue` rejoué sur une base
  partagée avec ce lot, ou en production.
- **Client TypeScript (`packages/api-client`) non régénéré** : `pnpm gen:api` nécessite
  `pnpm install` sur le monorepo complet (Next.js, Tailwind, shadcn…), un téléchargement
  disproportionné sur le lien à ~250 ko/s de chimera pour un lot sans périmètre front (`maquette`
  sans objet, D2/D8 hors périmètre). Le schéma OpenAPI de `/catalog/search` est à jour côté API
  (`app.openapi()` l'expose déjà, testé manuellement) ; seul le fichier généré `src/schema.d.ts`
  est en retard — à régénérer par le premier lot qui construira le front de recherche.
- **Pas de pagination/curseur sur `/catalog/search`** : la mission ne la demande pas (« route de
  recherche », limite fixe `DEFAULT_LIMIT=25`) ; à ajouter si un écran de recherche en a besoin.

## Reste à faire (pour les lots suivants)

- Revalider seuils/poids de score contre le catalogue réel importé (voir écart ci-dessus).
- Régénérer `packages/api-client` (`pnpm gen:api`) dès qu'un lot installe les dépendances du
  monorepo pour de vraies raisons front.
- Écran de recherche (front, maquette « Recherche ») : consomme cette route, hors périmètre ici.
- Brancher `match_candidates` sur la reconnaissance (lot futur), avec `nom`/`numero`/`set_hint`
  extraits par OCR plutôt que par `parse_query` d'une chaîne libre.

## Décisions provisoires utilisées

D2/D8 hors périmètre, confirmé (aucun déploiement, aucune tâche `release_uat`/`release_prod`
traitée). D3/D4/D5/D6/D7 sans objet pour ce lot (aucune source de prix, IA, e-mail, classement ni
stockage de photo touché).
