# Compte rendu — `v2-prix`

Session autonome (`claude -p`) sur chimera, worktree `~/dev/wt-pbm-v2-prix`, branche
`roadmap/v2-prix`. Exécuté sous le régime décrit dans le CONTEXTE D'EXÉCUTION du prompt
(sections A/P/0/7 du prompt de lot remplacées) : pas de `suivi.py`, pas d'écriture dans
`etat.json`/`ROADMAP.html`/`BACKLOG.md`/`prompts/`, fusion directe vers `origin/main`
(dépôt relais local, pas GitHub).

## Résumé

Relevé quotidien de prix (`card_prices_daily`, table déjà présente depuis `v0-schema`) : deux
jobs arq cron 06:00 (heure locale du process, même convention que le cron hebdomadaire de
`v2-catalogue`) — `daily_prices_task` (Cardmarket via TCGdex + TCGplayer via Pokémon TCG API,
idempotent, reprise à la carte/au set près) et `daily_exchange_rates_task` (taux BCE quotidiens,
nouvelle table `exchange_rates_daily`). Service `valuation` : valeur d'un exemplaire (référence
Cardmarket sinon TCGplayer converti, décote par état, écrêtage d'une tendance aberrante) et
valeur d'une collection à une date, dans la devise demandée. Testé par 33 tests (doublures pour
TCGdex/Pokémon TCG API/BCE) **et** en conditions réelles : relevé réel de 2 cartes connues
(Dracaufeu-ex, Charizard), taux BCE réels (29 devises), jobs déclenchés via une vraie file Redis
arq, valorisation calculée sur ces données réelles avec conversion EUR→USD.

## Livrables

- `apps/api/src/pbm_api/pricing/extract.py` — `extract_cardmarket_prices`/
  `extract_tcgplayer_prices` : lecture des blocs de prix bruts capturés en direct le 2026-09-19
  (`pricing.cardmarket` de TCGdex, `tcgplayer.prices.<variante>` de Pokémon TCG API) vers nos
  variantes (`PriceVariant`). Une variante absente/nulle/à zéro n'écrit jamais une fausse valeur.
- `apps/api/src/pbm_api/pricing/service.py` — `collect_daily_prices()` : une ligne
  `card_prices_daily` par carte × source × variante × jour (upsert sur la contrainte unique
  existante), TCGdex appelé carte par carte (borné à 5 en parallèle, pas d'endpoint de prix en
  masse connu), TCGplayer groupé par extension déduite du suffixe de `ptcg_id`
  (`list_cards_in_set`, un seul appel par extension). Reprise sur erreur à la carte/au set près.
  `EmptyPriceRunError` (mission point 4, sonde) si aucun prix n'a pu être écrit alors que le
  catalogue contient des cartes.
- `apps/api/src/pbm_api/pricing/exchange_rates.py` — `EcbClient` (flux XML quotidien BCE,
  public, sans clé), `store_daily_rates` (upsert idempotent), `get_rate_to_eur` (dernier taux
  connu à une date ou avant, jamais une extrapolation — la BCE ne publie pas le week-end).
- `apps/api/src/pbm_api/pricing/valuation.py` — `reference_price_eur` (tendance Cardmarket,
  sinon TCGplayer converti — mission point 2), `_sanitize_trend` (écrête une tendance à 3× le
  prix moyen du même relevé — risque documenté « ne doit pas faire exploser la valeur d'une
  collection »), `CONDITION_MULTIPLIERS` (barème M/NM/EX/GD/LP/PL/PO, décote documentée),
  `item_value`/`collection_value` (filtrés par `user_id` reçu en paramètre, jamais un identifiant
  client).
- `apps/api/src/pbm_api/models/pricing.py` — `ExchangeRateDaily` (`day`, `currency`, `rate` =
  unités de devise pour 1 EUR, contrainte unique `(day, currency)`).
- `apps/api/src/pbm_api/models/users.py` — `User.preferred_currency` (ISO 4217, défaut `EUR`) :
  fonctionnalité explicite de la mission (« conversion en devise de l'utilisateur »), pas encore
  exposée par une route (aucune route de préférences n'existe dans le dépôt à ce jour).
- `apps/api/migrations/versions/8565c4640de8_…` — migration additive (`exchange_rates_daily`,
  `users.preferred_currency`).
- `apps/api/src/pbm_api/worker.py` — `daily_prices_task`, `daily_exchange_rates_task` ajoutés à
  `WorkerSettings.functions`/`cron_jobs` (06:00, tous les jours) ; chaque exécution crée/actualise
  une ligne `jobs` (`type=daily_prices`/`daily_exchange_rates`), échec = `Job.status=failed` +
  `Job.error` explicite (canal d'alerte de ce lot, voir écarts).
- `docs/ARCHITECTURE.md` — section « Prix (lot `v2-prix`) » réécrite avec les détails
  d'implémentation.
- Bases/préfixe dédiés créés sur l'infra partagée `pbm-shared` : `pbm_v2_prix` (dev),
  `pbm_v2_prix_test` (tests), préfixe Redis `pbm:v2-prix:` (pas de bucket S3 : ce lot ne touche
  à aucune photo).

## Tests

```
$ cd apps/api && uv run ruff check .
All checks passed!

$ uv run pytest -q
80 passed in 5.67s   # 47 préexistants + 33 nouveaux (voir détail par fichier)

$ uv run pytest -q tests/test_price_extract.py tests/test_pricing_service.py \
    tests/test_exchange_rates.py tests/test_valuation.py -v
tests/test_price_extract.py ......        [ 18%]   (6 tests)
tests/test_pricing_service.py ......      [ 36%]   (6 tests)
tests/test_exchange_rates.py .........    [ 63%]   (9 tests)
tests/test_valuation.py ............      [100%]   (12 tests)
33 passed in 1.37s
```

- `tests/test_price_extract.py` — extraction pure, sans réseau : normal/holo Cardmarket, holo
  absent (trend-holo=0 → pas d'entrée), 1st edition TCGplayer (holofoil préféré à normal), blocs
  vides.
- `tests/test_pricing_service.py` — TCGdex/Pokémon TCG API remplacés par des doublures fidèles à
  la forme réelle capturée en direct (comme `test_import_service.py` de `v2-catalogue`).
  `test_collect_daily_prices_writes_cardmarket_and_tcgplayer_rows` **échoue sans ce lot** (le
  module `pbm_api.pricing.service` n'existe pas) et passe avec. Couvre aussi : idempotence (deux
  relevés identiques → 2 lignes, pas de doublon), reprise après l'échec d'une carte, dégradation
  propre si Pokémon TCG API est indisponible, `EmptyPriceRunError` sur un relevé vide, aucune
  carte en base ne lève pas d'exception.
- `tests/test_exchange_rates.py` — `EcbClient` testé avec `httpx.MockTransport` (XML réel
  reproduit, erreur HTTP, corps illisible) ; `store_daily_rates`/`get_rate_to_eur` avec repli sur
  le dernier taux connu, `EUR` toujours à 1, taux inconnu → `None` (jamais inventé).
- `tests/test_valuation.py` — décote par état (connue, absente, inconnue → `near_mint`),
  priorité Cardmarket/repli TCGplayer converti, absence de taux de change → `None` (pas de valeur
  inventée), écrêtage d'une tendance aberrante (100 pour un prix moyen de 5 → bornée à 15),
  valeur d'un exemplaire, valeur d'une collection (total, comptage des exemplaires sans prix,
  conversion de devise). **Accès croisé** (§6 du prompt, pas de route HTTP dans ce lot comme dans
  `v2-catalogue` — voir `test_cross_user_isolation.py`) :
  `test_collection_value_is_isolated_by_user` — même carte, même prix, deux utilisateurs avec un
  nombre d'exemplaires différent : la valorisation de chacun reste strictement filtrée par son
  `user_id`.
- **Maquette (§6)** : sans objet — confirmé par la grille (« maquette : sans objet, back-end »).

## Preuves en conditions réelles (réseau + base, pas de mock)

Deux cartes réelles semées dans `pbm_v2_prix` (Dracaufeu-ex `sv03.5-006`/`sv3pt5-6`, Charizard
`base1-4`), relevé lancé contre les vraies API :

```
$ uv run python3 -c "... collect_daily_prices(session, tcgdex_reel, ptcg_reel) ..."
Échec relevé tcgplayer set base1 : Pokémon TCG API indisponible après 3 tentatives sur /cards :
  Server error '500 Internal Server Error' ...
{'day': '2026-09-19', 'cards_total': 2, 'cards_with_tcgdex': 2, 'cards_with_ptcg': 2,
 'prices_written_cardmarket': 3, 'prices_written_tcgplayer': 1, 'tcgplayer_status': 'ok',
 'errors': ["tcgplayer set base1 : Pokémon TCG API indisponible ..."]}
```

→ relevé réussi malgré la panne (déjà documentée par `v2-catalogue`) de Pokémon TCG API sur
`base1` : preuve de la reprise sur erreur en conditions réelles, pas seulement en doublure.

Vérification base (`psql pbm_v2_prix`) :

```
     name     |   source   | variant | currency | price_low | price_mid | price_trend |    day
--------------+------------+---------+----------+-----------+-----------+-------------+-----------
 Charizard    | cardmarket | normal  | EUR      |    102.00 |    523.53 |     1139.56 | 2026-09-19
 Charizard    | cardmarket | holo    | EUR      |           |           |      123.63 | 2026-09-19
 Dracaufeu-ex | cardmarket | normal  | EUR      |      4.00 |      8.74 |        8.74 | 2026-09-19
 Dracaufeu-ex | tcgplayer  | holo    | USD      |      4.49 |      9.27 |        8.01 | 2026-09-19
```

→ **premier relevé en base** (livrable de la mission).

Taux BCE réels :

```
$ uv run python3 -c "... EcbClient().fetch_daily_rates() ; store_daily_rates(...) ..."
2026-09-18 29 1.1460   # (jour publié, nb de devises écrites, taux USD)
```

Service `valuation` sur ces données réelles :

```
reference EUR (Dracaufeu-ex, normal) : 8.74
collection EUR (1 exemplaire, état near_mint) :
  {'total': Decimal('7.8660'), 'items_total': 1, 'items_priced': 1, 'items_missing_price': 0}
collection USD (même exemplaire, conversion) :
  {'total': Decimal('9.0144360000'), 'currency': 'USD', ...}
```

→ 8.74 × 0.90 (décote `near_mint`) = 7.866 ✓ ; 7.866 × 1.1460 = 9.014436 ✓.

Jobs arq via une vraie file Redis (`pbm:v2-prix:queue`) :

```
$ uv run arq pbm_api.worker.WorkerSettings --burst
21:17:03: Starting worker for 6 functions: import_catalogue_task, daily_prices_task,
  daily_exchange_rates_task, cron:weekly_incremental_import, cron:daily_prices_task,
  cron:daily_exchange_rates_task
21:17:04:  0.33s ← daily_exchange_rates_task ● {'day': '2026-09-18', 'rates_written': 29}
Échec relevé tcgplayer set sv3pt5 : ... 500 ...   # flaky, cette fois sur l'autre extension
21:17:14: 11.11s ← daily_prices_task ● {'day': '2026-09-19', 'cards_total': 2, ...}

$ psql pbm_v2_prix -c "SELECT type, status, result FROM jobs ORDER BY created_at DESC LIMIT 2"
 daily_exchange_rates | succeeded | {"day": "2026-09-18", "rates_written": 29}
 daily_prices         | succeeded | {"cards_total": 2, "prices_written_tcgplayer": 1, ...}
```

→ Pokémon TCG API a échoué sur `sv3pt5` cette fois-ci (et non plus `base1`, comme au relevé
précédent) : confirme le caractère réellement intermittent documenté par `v2-catalogue`, et que
le job absorbe la panne quel que soit le set touché — les deux jobs se terminent `succeeded`
malgré l'échec partiel, avec l'erreur consignée dans `result.errors`, jamais silencieuse.

Aucun secret : TCGdex/Pokémon TCG API/BCE sont publics, sans clé. Recherche de motifs de clé sur
les fichiers ajoutés → aucun résultat.

## Choix techniques faits (autonomes, dans le cadre de `docs/ARCHITECTURE.md`)

- **TCGplayer groupé par extension** (`list_cards_in_set`, un appel réseau par set), **Cardmarket
  carte par carte** (`get_card`, borné à 5 en parallèle) : TCGdex n'expose pas d'endpoint de prix
  en masse connu, alors que Pokémon TCG API accepte un filtre `set.id` — décisif sur un lien à
  ~250 ko/s (mission risque réseau, voir aussi `~/.claude/CLAUDE.md`).
- **Extension TCGplayer déduite du suffixe de `ptcg_id`** (`rsplit("-", 1)`) plutôt que stockée
  séparément : l'id Pokémon TCG API est toujours `{set}-{numéro}` (déjà la convention utilisée par
  `catalog/reconciliation.py`), pas besoin d'une colonne supplémentaire sur `Set`.
- **`EmptyPriceRunError` plutôt qu'un rapport vide silencieux** : le mission point 4 (sonde)
  interdit explicitement le succès silencieux ; sans mécanisme d'alerting externe dans ce dépôt
  (aucune infra dédiée — e-mail, Slack — n'existe encore), le canal choisi est `Job.status=failed`
  + `Job.error`, cohérent avec le seul mécanisme d'observation de panne déjà utilisé par
  `import_catalogue`. Documenté comme un choix provisoire dans « reste à faire ».
- **Écrêtage de la tendance à 3× le prix moyen du même relevé** (`OUTLIER_TREND_MULTIPLE`),
  seulement quand un prix moyen existe pour la comparer : une tendance sans aucune autre donnée du
  même relevé n'est pas bornée arbitrairement (marché trop fin pour juger, mieux vaut la garder
  que d'inventer une borne sans référence). Valeur `3` choisie par jugement (aucun barème fourni
  par le plan) — à ajuster si un lot ultérieur observe des faux positifs/négatifs en production.
- **État inconnu/absent → `near_mint` (0.90), pas `mint` (1.00)** : `collection_items` ne porte
  aujourd'hui que la saisie libre de l'utilisateur, aucune mesure automatique (mission de
  reconnaissance d'état, hors périmètre v2) — hypothèse conservatrice documentée plutôt qu'une
  pleine valeur non vérifiée.
- **`User.preferred_currency` ajouté à ce lot** (plutôt que reporté) : la mission liste
  explicitement « conversion en devise de l'utilisateur » dans ses fonctionnalités ; la colonne
  est la plus petite pièce manquante pour ça (le calcul de conversion existait déjà via
  `exchange_rates_daily`). Pas de route pour la modifier : aucune route de préférences
  utilisateur n'existe encore dans ce dépôt (hors périmètre — back-end seul ici).
- **Pas de route HTTP exposant `valuation`** : la mission ne liste que « service de valorisation
  testé » dans ses livrables (pas de route), et les aboutissants « collection valorisée » sont
  listés pour un lot ultérieur dans `roadmap.json`. Testé au niveau service, comme
  `test_cross_user_isolation.py` l'avait déjà fait pour `v2-catalogue`/collection.

## Écarts au plan

- **Relevé réel limité à 2 cartes** (Dracaufeu-ex, Charizard), pas tout le catalogue : le
  catalogue de dev (`pbm_v2_prix`) était vide au démarrage de ce lot (aucun import `v2-catalogue`
  n'y a été rejoué, bases isolées par lot) — deux cartes réelles suffisent à prouver le
  fonctionnement du job contre les vraies API, un relevé massif est disproportionné sur un lien à
  ~250 ko/s et hors du périmètre « service testé » de la mission. Le job est prêt pour tout le
  catalogue une fois `v2-catalogue` exécuté en entier sur la même base (aucun changement de code
  requis).
- **Pas de reverse_holo/first_edition côté Cardmarket** : la carte de test observée en direct
  (`sv03.5-006`) n'expose que `low`/`avg`/`trend` (normal) et leurs équivalents `*-holo` dans
  `pricing.cardmarket` — aucune clé `reverse-holo-*`/`1st-edition-*` n'y est apparue. La table de
  clés (`CARDMARKET_VARIANT_KEYS`) reste ouverte à compléter si TCGdex les expose pour d'autres
  cartes (risque documenté par la mission : « prix manquants pour les cartes rares »).
- **`1stEditionNormal`/`unlimited`/`unlimitedHolofoil` de TCGplayer non modélisés** : notre
  `PriceVariant` (hérité de `v0-schema`) n'a pas de case pour les éditions non-limitées ; ce sont
  des cartes vintage (Wizards of the Coast, avant 2003) hors du périmètre courant — gap documenté
  plutôt que d'étendre l'enum sans besoin exprimé par la mission.
- **Cron « 06:00 » sans fuseau horaire explicite** : comme le cron hebdomadaire existant de
  `v2-catalogue` (`cron(weekday=0, hour=6, minute=0)`), `arq.cron` n'a pas reçu de paramètre de
  fuseau — il s'applique à l'heure du process qui exécute le worker. Si ce process ne tourne pas
  en `Europe/Paris` en production, le relevé glissera d'un décalage fixe ; à vérifier par le lot
  de déploiement (`TZ=Europe/Paris` sur le service systemd du worker, cohérent avec les règles de
  test de la flotte `~/.claude/CLAUDE.md` § Kailo Location, transposable ici).

## Reste à faire (pour les lots suivants)

- **Alerting réel sur `EmptyPriceRunError`** : aujourd'hui seulement visible via
  `SELECT * FROM jobs WHERE status='failed'` — aucun canal (e-mail, Slack) ne notifie encore
  personne. À brancher par le lot qui posera la supervision.
- **Reverse holo / 1st edition Cardmarket** : à activer dès qu'une carte de test les expose
  réellement dans `pricing.cardmarket` (voir écart ci-dessus).
- **Les trois classements (D6)** et **courbe de la fiche** : listés comme aboutissants de ce lot
  dans `roadmap.json`, mais hors de sa mission explicite (route/API non demandées) — reviennent à
  un lot de fiche carte/collection.
- **Alertes de prix** (aboutissant du lot) : nécessitent une route + une notification, hors
  périmètre « service testé » de la mission `v2-prix`.
- **Import complet du catalogue en dev** avant de rejouer un relevé à grande échelle (voir écart
  ci-dessus) : aucun changement de code requis côté `v2-prix`.
- **Route de préférence utilisateur** pour `preferred_currency` : la colonne existe, aucune route
  ne la lit/l'écrit encore (hors périmètre back-end de ce lot).

## Décisions provisoires utilisées

D3 (sources de prix gratuites — Cardmarket via TCGdex, TCGplayer via Pokémon TCG API, toutes deux
gratuites et sans clé ; historique construit par nos relevés quotidiens à partir de ce lot).
D4 (pas de clé IA disponible — sans objet ici, ce lot n'en utilise aucune). D2/D8 hors périmètre,
confirmé (aucun déploiement, aucune tâche `release_uat`/`release_prod` traitée).
