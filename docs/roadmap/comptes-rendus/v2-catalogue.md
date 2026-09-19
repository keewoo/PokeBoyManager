# Compte rendu — `v2-catalogue`

Session autonome (`claude -p`) sur chimera, worktree `~/dev/wt-pbm-v2-catalogue`, branche
`roadmap/v2-catalogue`. Exécuté sous le régime décrit dans le CONTEXTE D'EXÉCUTION du prompt
(sections A/P/0/7 du prompt de lot remplacées) : pas de `suivi.py`, pas d'écriture dans
`etat.json`/`ROADMAP.html`/`BACKLOG.md`/`prompts/`, fusion directe vers `origin/main`
(dépôt relais local, pas GitHub).

## Résumé

Job `import_catalogue` (arq) idempotent qui importe extensions et cartes FR+EN depuis
[TCGdex](https://api.tcgdex.net) (public, sans clé), les rapproche de
[Pokémon TCG API](https://pokemontcg.io) (`ptcg_id`) via une table de correspondance des cas
particuliers construite et testée depuis les deux API en direct, et sert les images officielles
via un proxy qui les met en cache dans MinIO/S3 au premier accès. Cron hebdomadaire (nouvelles
extensions). Testé en conditions réelles : import de 3 extensions (362 cartes, 362 noms FR + 362
EN), proxy d'image (premier accès réseau 3,2 s → deuxième accès cache 11 ms), job arq déclenché
via une vraie file Redis.

## Livrables

- `apps/api/src/pbm_api/catalog/tcgdex_client.py` — client TCGdex v2 (`list_sets`, `get_set`,
  `get_card`, `fetch_image_bytes`).
- `apps/api/src/pbm_api/catalog/ptcg_client.py` — client Pokémon TCG API avec retry/backoff
  (3 tentatives) et `PtcgUnavailableError` explicite plutôt qu'un échec silencieux — nécessaire
  car l'API s'est montrée flaky (500/502 intermittents) pendant toute la session, y compris en
  pleine liste `/sets`.
- `apps/api/src/pbm_api/catalog/reconciliation.py` — `SET_ID_OVERRIDES` : 43 correspondances
  TCGdex → Pokémon TCG API capturées le 2026-09-19 en comparant `GET /v2/en/sets` (TCGdex, 220
  extensions) et `GET /v2/sets` (Pokémon TCG API, 176 extensions) par nom, puis en isolant les id
  différents (ex : `hgssp` → `hsp`, tous les `svNN`/`svNN.5` → `svN`/`svNpt5`, les McDonald's
  Collection `20NNxy` → `mcdNN`...). `normalize_card_number`/`match_card_number` pour le
  rapprochement carte-à-carte par numéro (zéros de tête ignorés).
- `apps/api/src/pbm_api/catalog/import_service.py` — `import_catalogue()` : upsert par
  `tcgdex_id` (idempotent), commit par extension (reprise sur erreur — une extension ou une carte
  en échec est consignée dans le rapport, n'interrompt pas le reste), mode `full` (toutes les
  extensions ou une liste `set_ids`) et `incremental` (extensions absentes de la base). Récupère
  en une fois par extension les noms localisés (`get_set(lang, id).cards[].name`) plutôt qu'un
  appel `get_card` par langue et par carte — sur un lien à ~250 ko/s, l'écart est significatif.
- `apps/api/src/pbm_api/worker.py` — `WorkerSettings` arq : `import_catalogue_task` (déclenché),
  `weekly_incremental_import` (cron `weekday=0, hour=6, minute=0`), `queue_name` préfixé
  `pbm:v2-catalogue:` (isolation Redis du lot). Chaque exécution crée/actualise une ligne `jobs`
  (`type=import_catalogue`, `payload`, `result`, `error`, `started_at`/`finished_at`).
- `apps/api/src/pbm_api/s3.py` — `ObjectStorage` : enveloppe `boto3` (synchrone, déléguée à un
  thread) autour de MinIO/S3, `get`/`put`/`ensure_bucket`.
- `apps/api/src/pbm_api/routers/images.py` — `GET /img/cards/{id}?size=high|low` : 404 si la
  carte est inconnue ou sans image, 502 si l'image officielle est injoignable (pas de repli
  silencieux), sinon sert depuis le cache S3 ou le peuple au premier accès.
- `apps/api/src/pbm_api/models/catalog.py` — `Set.tcgdex_id` (unique) ; `Card.tcgdex_id`
  (unique), `Card.ptcg_id`, `Card.illustrator`, `Card.attacks`/`abilities` (JSONB),
  `Card.legal_standard`/`legal_expanded`. `Card.image_url` redéfini comme l'URL de base TCGdex
  sans extension (le proxy y ajoute `/high.webp` ou `/low.webp`).
- `apps/api/migrations/versions/1d51087de4ae_…` — migration additive (colonnes + contraintes
  nommées `uq_cards_tcgdex_id`/`uq_sets_tcgdex_id` pour un `downgrade()` valide ; l'autogénération
  Alembic produit des noms `None` qui échouent au downgrade, corrigé à la main).
- `apps/api/pyproject.toml` — dépendances ajoutées : `arq`, `boto3`, `httpx` (déplacé des
  dépendances de dev vers les dépendances principales, utilisé en production par les clients
  catalogue) ; `uv.lock` régénéré.
- `.github/workflows/ci.yml` — ajout de MinIO au job `api` : **pas** via le bloc `services:`
  (celui-ci ne permet pas de surcharger la commande du conteneur, or l'image `minio/minio`
  exige `server /data` en argument) mais via une étape `docker run -d` explicite, avec
  attente de `/minio/health/live`. Variables `S3_*` ajoutées à l'environnement du job.
- `docs/ARCHITECTURE.md` — section « Catalogue (lot `v2-catalogue`) » ajoutée.
- Bases/bucket/préfixe dédiés créés sur l'infra partagée `pbm-shared` : `pbm_v2_catalogue` (dev),
  `pbm_v2_catalogue_test` (tests), bucket `pbm-v2-catalogue`, préfixe Redis `pbm:v2-catalogue:`.

## Tests

- `tests/test_reconciliation.py` — pur, sans réseau : cas connus figés (`hgssp`→`hsp`,
  `sv03.5`→`sv3pt5`), correspondance directe sans override, id non rapprochable → `None` (pas une
  exception), normalisation de numéro.
- `tests/test_import_service.py` — TCGdex/Pokémon TCG API remplacés par des doublures fidèles à
  la forme réelle des réponses (capturée en direct, voir ci-dessus). `test_import_catalogue_
  creates_sets_cards_and_names` est le test qui **échoue sans ce lot** (colonnes
  `tcgdex_id`/`ptcg_id`/`illustrator`/`attacks`/`abilities`/`legal_*` inexistantes avant la
  migration : `UndefinedColumnError`) et passe avec. Couvre aussi : idempotence (deuxième import
  → 0 création, uniquement des mises à jour), dégradation propre si Pokémon TCG API est
  indisponible (`ptcg_id` reste nul, l'import réussit quand même), reprise après l'échec d'une
  seule carte (l'autre carte de l'extension est importée, l'échec est dans `errors`), mode
  incrémental (extensions déjà connues ignorées).
- `tests/test_images.py` — MinIO/S3 réel (bucket du lot), TCGdex remplacé par une doublure qui
  compte ses appels : premier accès → 1 appel réseau + mise en cache, deuxième accès → 0 appel
  (servi depuis S3), 404 sans image, 502 si la source officielle est injoignable.
- **Accès croisé (§6)** : sans objet — confirmé par la grille de clôture du prompt
  (« sécurité : sans objet, données publiques »). Le catalogue n'est rattaché à aucun `user_id` ;
  aucune route de ce lot ne dépend de la session utilisateur.
- **Maquette (§6)** : sans objet — confirmé par la grille (« maquette : sans objet, back-end »).

```
$ cd apps/api && uv run ruff check .
All checks passed!

$ uv run pytest -q
27 passed in 1.4s
```

## Preuves en conditions réelles (réseau + bases + MinIO, pas de mock)

Import échantillon (`scripts/run_sample_import.py hgssp base1`, 250 ko/s chimera) :

```
$ time uv run python scripts/run_sample_import.py hgssp base1
{
  "sets_seen": 2, "sets_created": 2, "cards_created": 127,
  "cards_by_language": {"fr": 127, "en": 127},
  "ptcg_reconciliation": "ok", "cards_matched_ptcg": 25, "cards_unmatched_ptcg_count": 0,
  "errors": ["rapprochement base1 : Pokémon TCG API indisponible après 3 tentatives sur /cards : …500…"]
}
real  0m36.105s
```
→ import réussi malgré la panne (déjà documentée) de Pokémon TCG API sur `base1` : preuve de la
dégradation propre (§4 « limites de débit » du prompt). Les 25/25 cartes de `hgssp` sont bien
rapprochées via l'override `hgssp → hsp`, confirmant le cas particulier en conditions réelles.

Vérification base (`psql pbm_v2_catalogue`) :

```
 code  |    name     | cartes        language | count
-------+-------------+--------      ----------+-------
 hgssp | Promo HGSS  |     25             en   |   127
 base1 | Set de Base |    102             fr   |   127
```

Proxy image, sur un serveur uvicorn réel (`Card` Dracaufeu `base1-4`) :

```
$ curl .../img/cards/<id>?size=high      → HTTP 200, 78222 octets, 3,218 s   (fichier WebP valide)
$ curl .../img/cards/<id>?size=high      → HTTP 200, 78222 octets, 0,011 s   (identique, depuis MinIO)
```

Job arq via une vraie file Redis (`pbm:v2-catalogue:queue`) :

```
$ uv run arq pbm_api.worker.WorkerSettings --burst
20:49:27: Starting worker for 2 functions: import_catalogue_task, cron:weekly_incremental_import
20:49:30: ← import_catalogue_task {'sets_created': 1, …}
$ psql … SELECT type, status, result FROM jobs
import_catalogue | succeeded | {"cards_created": 0, …}   -- extension "wp" : voir écart ci-dessous
```

Mode incrémental (`mode="incremental"`, sans `set_ids`) déclenché réellement puis **arrêté
volontairement** après ~25 s (`timeout 300` + `kill`) : sans filtre, il aurait tenté d'importer
les ~217 extensions restantes du catalogue mondial, hors du périmètre « échantillon pour le dev »
du CONTEXTE D'EXÉCUTION et disproportionné vu le débit de 250 ko/s de chimera. Preuve que
l'arrêt en cours de route ne perd rien (reprise sur erreur, §mission point 1) : 5 extensions
supplémentaires (`base2`, `basep`, `base3`, `jumbo`, `base5`) avaient déjà été validées
(committées) avant l'arrêt — total final observé : **8 extensions, 362 cartes, 362 noms FR + 362
noms EN**. La ligne `jobs` de cette exécution tuée reste au statut `running` (processus arrêté
avant sa mise à jour finale) : limitation connue, voir « reste à faire ».

Aucun secret : aucune clé IA impliquée (TCGdex/Pokémon TCG API sont publics, sans clé — la
consigne « script d'essai manuel avec vraie clé » du CONTEXTE D'EXÉCUTION concerne la
reconnaissance par IA, pas ce lot) ; recherche de motifs de clé sur les fichiers ajoutés → aucun
résultat.

## Choix techniques faits (autonomes, dans le cadre de `docs/ARCHITECTURE.md`)

- **Légalités, illustrateur, attaques/talents lus directement sur TCGdex**, pas via Pokémon TCG
  API : TCGdex les expose déjà par carte (`legal.standard`/`expanded`, `illustrator`, `attacks`,
  `abilities`), ce qui évite un appel réseau supplémentaire par carte et rend l'import indépendant
  de la disponibilité de Pokémon TCG API pour ces champs. `ptcg_id` reste utile pour un futur lot
  de relevé de prix (Pokémon TCG API expose aussi les prix TCGplayer par `id`), non exploité ici
  (hors périmètre mission : le relevé de prix est un job distinct selon `docs/ARCHITECTURE.md`).
- **Table de correspondance en constante Python testée**, pas en table SQL : ce sont des données
  de réconciliation versionnées avec le code (revue en revue de code, pas en migration), pas des
  données utilisateur ; plus simple à auditer et à corriger qu'une table à migrer.
- **Noms localisés récupérés via `get_set(lang, id).cards[].name`**, pas via un `get_card` par
  langue et par carte : un seul appel supplémentaire par extension et par langue secondaire,
  au lieu d'un appel par carte — décisif sur un lien à ~250 ko/s.
- **`image_url` réutilisé comme URL de base sans extension** (`.../sv/sv03.5/006`) plutôt que
  deux colonnes `image_url_high`/`image_url_low` : c'est exactement la convention TCGdex
  (`{base}/high.webp`, `{base}/low.webp}`), et évite de dupliquer une URL qui ne diffère que par
  son suffixe.
- **`PtcgUnavailableError` explicite avec retry/backoff (3 tentatives)**, pas un simple
  `try/except` avalé : l'indisponibilité observée en direct pendant la session (500/502
  intermittents, y compris en pleine liste) devait être **visible** dans le rapport d'import
  (`ptcg_reconciliation`) plutôt que silencieuse — conforme à l'interdiction du repli silencieux
  (`CLAUDE.md`).
- **Commit par extension** dans `import_catalogue` (pas une transaction unique pour tout
  l'import) : un import de plusieurs centaines d'extensions doit pouvoir être interrompu (arrêt
  volontaire, panne réseau, timeout) sans perdre le travail déjà validé — vérifié en conditions
  réelles (voir preuves : 5 extensions conservées après un arrêt forcé).
- **MinIO démarré par une étape `docker run` en CI**, pas par le bloc `services:` de GitHub
  Actions : celui-ci ne permet pas de surcharger la commande d'un conteneur, or l'image
  `minio/minio` n'a pas de `CMD` par défaut utilisable tel quel (elle exige `server /data`).
- **`boto3` synchrone délégué à un thread** (`asyncio.to_thread`) plutôt qu'un client S3 async
  dédié (`aioboto3`) : une dépendance de moins à télécharger sur un lien à ~250 ko/s, et le volume
  d'opérations S3 de ce lot (une image à la fois) ne justifie pas un client asynchrone natif.

## Écarts au plan

- **Import réel limité à un échantillon** (3 extensions au total sur la session : `hgssp`,
  `base1`, puis 5 de plus en mode incrémental avant arrêt volontaire), pas tout le catalogue
  mondial (~220 extensions TCGdex, plusieurs dizaines de milliers de cartes × 2 langues) :
  explicitement couvert par le CONTEXTE D'EXÉCUTION (« catalogue en échantillon pour le dev »,
  réseau chimera ~250 ko/s). Le job est prêt pour un import complet (`mode="full"` sans
  `set_ids`, ou `incremental` en continu via le cron) ; le lancer en entier revient au pilote ou à
  une session ultérieure avec un budget réseau/temps dédié.
- **Pokémon TCG API réellement flaky pendant toute la session** (500/502 intermittents,
  y compris `/sets` en pleine liste, y compris en re-tentant plusieurs fois) : le rapprochement
  `ptcg_id` a donc été démontré à la fois en succès (`hgssp`, 25/25) et en dégradation
  (`base1`, échec après 3 tentatives, import quand même réussi) — les deux chemins sont couverts
  par les tests automatisés (doublures) et par une preuve réelle.
- **Une extension TCGdex sans cartes énumérées** (`wp`, « W Promotional » : `cardCount.official=7`
  mais `cards: []` côté TCGdex) rencontrée en conditions réelles : traitée sans erreur (extension
  créée, 0 carte), c'est une limite de données de la source, pas un bug du job — consigné ici en
  cas de question du pilote sur les « 0 carte » visibles dans le job correspondant.
- **CI non exécutée sur GitHub** (dépôt relais local, pas de remote GitHub depuis chimera) : la
  configuration MinIO a été validée par un `docker run` manuel identique à l'étape CI, en plus des
  tests automatisés qui tournent contre ce MinIO — le pilote déclenchera la vraie CI au push.

## Reste à faire (pour les lots suivants)

- **Import complet du catalogue** (les ~220 extensions, toutes langues) : à lancer avec un budget
  réseau/temps dédié (le job lui-même est prêt, idempotent et reprenable).
- **Relevé de prix quotidien** (Cardmarket/TCGplayer → `card_prices_daily`) : `ptcg_id` et les
  identifiants `thirdParty` déjà exposés par TCGdex (non stockés ici, hors périmètre mission) sont
  prêts à être exploités par ce futur job.
- **Reconciliation des jobs orphelins** : un worker arq tué en cours de route laisse sa ligne
  `jobs` au statut `running` sans `finished_at` (observé en conditions réelles, voir preuves) —
  pas de mécanisme de détection/nettoyage des jobs bloqués dans ce lot.
- **Endpoint HTTP de déclenchement manuel de l'import** : ce lot expose le job via arq
  (`enqueue_job`) mais aucune route API pour le déclencher depuis le futur back-office —
  non demandé par la mission, à évaluer avec le pilote si besoin.
- **Rapport d'import exposé** : le rapport (`Job.result`) existe et est complet, mais aucune route
  API ne le sert encore côté front — reviendra avec le back-office ou la fiche carte.

## Décisions provisoires utilisées

D3 (sources de prix gratuites — TCGdex/Pokémon TCG API, toutes deux gratuites et sans clé, sont
la source retenue par ce lot ; l'historique par relevés propres reste pour un futur lot de prix).
D4 (pas de clé IA disponible — sans objet ici, ce lot n'en utilise aucune). D7 (stockage S3
compatible — `ObjectStorage`/MinIO utilisés tels quels pour le cache d'images). D2/D8 hors
périmètre, confirmé (aucun déploiement, aucune tâche `release_uat`/`release_prod` traitée).
