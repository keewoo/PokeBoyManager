# Compte rendu — `v4-insights-batch`

Session autonome (`claude -p`) sur chimera, worktree `~/dev/wt-pbm-v4-insights-batch`, branche
`roadmap/v4-insights-batch`. Exécuté sous le régime décrit dans le CONTEXTE D'EXÉCUTION du
prompt (sections A/P/0/7 du prompt de lot remplacées) : pas de `suivi.py`, pas d'écriture dans
`etat.json`/`ROADMAP.html`/`BACKLOG.md`/`prompts/`, fusion directe vers `origin/main` (dépôt
relais local, pas GitHub).

**Deux têtes Alembic divergentes trouvées sur `origin/main` avant tout code** (`216ae1bf9f95`
« merge v2-catalogue-complet heads » et `d27e4efd0255` « identification corrections journal »,
toutes deux filles de `066f6a4397cb`, jamais rejointes) : `uv run alembic heads` en renvoyait
deux, ce que ce lot ne pouvait pas contourner (sa propre migration a besoin d'une tête unique).
Corrigé par une migration de fusion vide (`684d2afd5fe7`, même patron que `216ae1bf9f95` déjà
présente dans l'historique) **avant** d'ajouter la migration propre à ce lot — pas une décision
de ce lot en tant que telle, un préalable technique bloquant trouvé en chemin.

## Résumé

Pipeline `pbm_api.insights_batch` : un seul appel Anthropic par carte (Message Batches API,
remise -50 %) rend ensemble anecdotes sourcées FR + EN et étude d'utilisation en jeu (légalités,
forces/limites, note de jouabilité), écrit dans `card_insights` — la même table que
`v4-anecdotes`/`v4-jeu` lisent déjà à la demande. Ces routes à la demande deviennent
automatiquement un repli pour une carte pas encore couverte : **aucune modification de leur
code**, leur logique de cache existante (`_fresh`/`_study_fresh`) suffit dès lors que ce lot
écrit dans les mêmes colonnes avec les mêmes conventions de fraîcheur.

Clé Anthropic **plateforme** (jamais une clé d'utilisateur) et budget cumulé plafonné, tous deux
absents sur chimera (D4, « à fournir par JF ») — le pipeline refuse alors de dépenser quoi que ce
soit plutôt que de se comporter en mode dégradé silencieux. Sélection idempotente et
incrémentale : une carte reste candidate tant que ses anecdotes ou son étude en jeu manquent,
qu'elle soit neuve (nouvelle extension) ou jamais traitée.

## Livrables

- `apps/api/src/pbm_api/insights_batch/combined_generation.py` — schéma combiné
  (`CombinedCardInsightExtraction` : `anecdotes_fr`/`anecdotes_en`/`game_study`) et
  `build_combined_prompt`, réutilisant telles quelles les briques de `v4-anecdotes`
  (`pbm_api.insights.context.collect_context`) et `v4-jeu` (`pbm_api.ingame.rules`,
  `InGameStudyExtraction`) — seul l'assemblage en un unique prompt est nouveau.
- `apps/api/src/pbm_api/insights_batch/anthropic_batches.py` — client fin de la Message Batches
  API (`POST /v1/messages/batches`, `GET .../{id}`, résultats `.jsonl` streamés), absent du
  reste du dépôt (`AIProvider.extract` est volontairement synchrone). Rapprochement des
  résultats par `custom_id` uniquement (Anthropic documente un ordre non garanti).
- `apps/api/src/pbm_api/insights_batch/pricing.py` — tarifs Batch **vérifiés** (pas devinés) le
  20/09/2026 sur `claude.com/pricing` + `platform.claude.com/docs/en/build-with-claude/
  batch-processing` : Haiku 4.5 (modèle par défaut de ce lot) 0,50 $/2,50 $ le Mtok
  entrée/sortie, Sonnet 5 1 $/5 $, remise Batch -50 % déjà appliquée dans la table.
- `apps/api/src/pbm_api/insights_batch/ledger.py` — grand livre local
  (`var/insights_batch/ledger.json`, non versionné) : dépense cumulée en EUR, lot Anthropic en
  cours (reprise sans double soumission), lots déjà comptabilisés (pas de double comptage de
  coût si le script est interrompu entre l'écriture en base et la clôture du lot).
- `apps/api/src/pbm_api/insights_batch/runner.py` — orchestration (`run_once`) : sélection,
  préparation (contexte réel + faits déterministes), plafonnement par budget restant avant
  soumission, soumission/sondage/application, mise à jour du grand livre.
- `apps/api/src/pbm_api/models/catalog.py` — `CardInsight.anecdotes_en` (nouvelle colonne
  JSONB, même forme que `anecdotes`) : colonne **séparée** plutôt que mélanger les langues dans
  la liste déjà exposée par `GET /cards/{id}/insights` — un mélange aurait fait apparaître du
  texte anglais sans prévenir sur un produit francophone. Non exposée par une route pour
  l'instant (aucun écran ne les consomme encore, voir « Reste à faire »).
- `apps/api/migrations/versions/684d2afd5fe7_...py` (fusion préalable, voir ci-dessus) et
  `99492e449606_card_insights_anecdotes_en.py` (colonne, aller-retour upgrade vérifié sur
  `pbm_v4_insights_batch` **et** `pbm_v4_insights_batch_test`).
- `apps/api/src/pbm_api/insights/context.py` — `MediaWikiClient` envoie désormais un
  `User-Agent` identifié (ASCII strict, un en-tête HTTP n'accepte pas les accents) : risque
  « débit raisonnable » propre à ce lot, profite aussi à la collecte à la demande de
  `v4-anecdotes` qui partage la classe.
- `apps/api/src/pbm_api/config.py` — `PLATFORM_ANTHROPIC_API_KEY` (vide par défaut),
  `INSIGHTS_BUDGET_EUR` (0 par défaut), `INSIGHTS_BATCH_MODEL`, `INSIGHTS_BATCH_CHUNK_SIZE`,
  `INSIGHTS_BATCH_POLL_INTERVAL_SECONDS`/`_MAX_ATTEMPTS`.
- `apps/api/scripts/run_insights_batch.py` — lance un passage (`--loop` jusqu'à couverture
  complète ou budget épuisé, avec pause entre sondages).
- `apps/api/scripts/measure_insights_batch_cost.py` — mesure exigée par la mission (résultat
  ci-dessous) ; `--live` relance le même script pour la mesure réelle facturée dès que la clé
  plateforme existera.
- `CLAUDE.md` — section « Insights par lots (lot `v4-insights-batch`) » et entrée dans
  « Configuration par variables d'environnement ». `.env.example` — nouvelles variables.
- Base dédiée sur l'infra partagée `pbm-shared` : `pbm_v4_insights_batch` (dev),
  `pbm_v4_insights_batch_test` (tests), `apps/api/.env` local (gitignored), bucket/préfixe non
  utilisés par ce lot (aucune photo, aucun Redis touché).

## Tests

```
$ cd apps/api && uv run ruff check .
All checks passed!

$ TZ=Europe/Paris TEST_DATABASE_URL=postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v4_insights_batch_test \
    uv run pytest -q
466 passed, 2 failed in 72.37s
```

Les 2 échecs (`tests/test_catalogue_seed.py::test_seed_export_then_restore_into_empty_database`,
`::test_seed_import_is_idempotent`) sont **préexistants et sans rapport** avec ce lot : `pg_dump`
n'est pas installé sur cette machine (`pg_dump: command not found`), un binaire absent de chimera
plutôt qu'une régression de code — confirmé en isolant la cause (`which pg_dump` : rien, sur
toutes les autres worktrees aussi). `ubuntu-latest` (runner GitHub Actions) a `pg_dump`
préinstallé : la CI doit rester verte sur ces deux tests, seul chimera est affecté. Non traité
(hors périmètre de ce lot, appartient à `v2-catalogue-complet`).

Détail des nouveaux tests, isolément :

```
$ uv run pytest tests/test_insights_batch_runner.py tests/test_insights_batch_anthropic_client.py \
    tests/test_insights_batch_pricing.py tests/test_insights_batch_combined_generation.py -q
35 passed in 1.4s
```

- Avant ce lot, `pbm_api.insights_batch` n'existe pas : les quatre fichiers de test échouent
  entièrement à la collection (`ModuleNotFoundError`) et passent une fois le paquet ajouté.
- **Preuve ciblée « budget dépassé »** (mission point 2) :
  `test_run_once_stays_under_the_remaining_budget_and_says_so` — un budget restant proche de
  zéro doit refuser de soumettre une carte dont le coût estimé le dépasse déjà, statut
  `budget_insuffisant`, aucun appel Anthropic (`RaisingBatchClient` lève si sollicité).
- **Preuve ciblée « coût traité comme gratuit »** (risque non écrit dans la mission mais trouvé
  en concevant le plafond) : `test_run_once_refuses_silently_defaulting_cost_when_no_exchange_rate`
  — sans taux USD→EUR connu (`pbm_api.pricing.exchange_rates`), le lot doit s'arrêter
  (`taux_de_change_indisponible`) plutôt que de convertir un coût réel en 0 € par défaut, ce
  qui aurait rendu le plafond de budget inopérant en silence.
- **Preuve ciblée « défense en profondeur anti-hallucination »** (même garde-fou que
  `pbm_api.insights.service`, v4-anecdotes) :
  `test_run_once_rejects_anecdote_with_url_outside_context` — une anecdote citant une URL hors
  du contexte fourni est rejetée même si le modèle a mal respecté la consigne du prompt.
- **Idempotence/incrémentalité** : `test_run_once_second_pass_finds_nothing_left_to_cover` (une
  carte déjà couverte ne redevient pas candidate, aucune re-dépense).
- **Reprise sans double soumission** :
  `test_run_once_resumes_an_in_flight_batch_still_processing` (un lot Anthropic déjà soumis et
  encore en traitement se contente d'un sondage, jamais resoumis).
- **Mesure sans budget configuré** (régression trouvée en écrivant
  `scripts/measure_insights_batch_cost.py`, voir ci-dessous) :
  `test_run_once_dry_run_ignores_a_zero_budget` — le mode `dry_run` (qui ne dépense rien) ne doit
  pas exiger un `INSIGHTS_BUDGET_EUR` déjà configuré, sans quoi la mesure servant justement à le
  calibrer serait impossible à lancer sur la valeur de dev (0).
- **Rapprochement par `custom_id`, jamais par position** (`tests/test_insights_batch_
  anthropic_client.py::test_iter_results_matches_results_by_custom_id_not_by_order`) : Anthropic
  documente explicitement un ordre non garanti des résultats.
- **Tarifs** (`tests/test_insights_batch_pricing.py`) : calcul figé (les prix eux-mêmes ne se
  vérifient qu'en relisant la doc Anthropic, pas par un test), refus explicite
  (`UnknownModelPricingError`) plutôt qu'un coût inventé pour un modèle sans tarif connu.
- Pas de route HTTP dans ce lot (script/cron interne) : aucun test d'accès croisé utilisateur
  propre à ajouter — `card_insights` reste le même cache partagé sans notion de propriétaire,
  déjà couvert par `tests/test_card_insights.py`/`tests/test_in_game_study.py`.

Suites impactées par les changements partagés (`MediaWikiClient`, `card_insights`) rejouées
sans régression : `tests/test_insights_context.py`, `tests/test_card_insights.py`,
`tests/test_in_game_study.py` — 40 passés.

Recherche de motifs de clé/secret sur les fichiers ajoutés → aucun résultat. La clé plateforme
ne transite que dans l'en-tête `x-api-key` de la requête HTTP vers Anthropic, jamais journalisée
ni incluse dans un message d'erreur (`BatchApiError` ne reprend que le corps de la **réponse**
Anthropic, jamais la requête).

## Mesure sur 100 cartes représentatives (mission point 3)

```
$ uv run python scripts/measure_insights_batch_cost.py --out /tmp/insights_batch_measure_100.json
100 cartes représentatives semées (transaction non validée).
{
  "mode": "estimation_dry_run",
  "cartes_traitees": 100,
  "cartes_avec_contexte": 100,
  "cartes_sans_contexte": 0,
  "taux_sans_contexte": 0.0,
  "duree_secondes": 99.3,
  "cout_usd": "0.3181270",
  "cout_eur": "0.2775977312390924956369982548",
  "statut": "dry_run",
  "detail": "requêtes préparées, aucun appel Anthropic effectué",
  "cout_par_carte_eur": "0.002775977312390924956369982548",
  "extrapolation_5000_cartes_eur": "13.87988656195462478184991274",
  "extrapolation_15000_cartes_eur": "41.63965968586387434554973822",
  "extrapolation_30000_cartes_eur": "83.27931937172774869109947644"
}
```

**⚠️ Coût ESTIMÉ, pas mesuré/facturé** : aucune clé Anthropic réelle n'est disponible sur
chimera (D4) — `run_once(dry_run=True)` collecte le contexte réel (100 requêtes Poképédia +
100 Bulbapedia, réseau réel, 99,3 s) et construit les 100 prompts réels, mais n'appelle jamais
l'API Anthropic. Le coût vient d'une heuristique caractères/jeton documentée et non calibrée
(`pbm_api.insights_batch.runner._ESTIMATED_CHARS_PER_TOKEN`/`_ESTIMATED_OUTPUT_TOKENS`) —
probablement dans le bon ordre de grandeur (les 100 requêtes ont un contenu et une longueur
réels) mais **pas une facture**. Le taux de change (USD→EUR = 1,146, BCE 2026-09-18) est lui
réel, récupéré depuis le vrai flux `eurofxref-daily.xml` pour pouvoir lancer cette mesure.

100/100 cartes ont trouvé au moins une page de contexte (0 % de « sans contexte ») — sur cet
échantillon volontairement composé de cartes iconiques bien documentées, pas représentatif d'un
catalogue complet qui contient aussi des cartes obscures/promos peu couvertes par les deux
wikis ; un taux réel sur le catalogue complet sera probablement inférieur.

Extrapolation à titre indicatif (le nombre exact de cartes du catalogue dépend de l'import réel
de `v2-catalogue-complet`, non consulté par ce script) : **≈ 14 € pour 5 000 cartes, ≈ 42 € pour
15 000, ≈ 83 € pour 30 000** — sur ESTIMATION, à revalider par un `--live` avec la clé plateforme
avant d'arrêter un budget définitif.

Dès que `PLATFORM_ANTHROPIC_API_KEY` sera fournie : `uv run python
scripts/measure_insights_batch_cost.py --live` relance exactement la même mesure avec un coût
RÉEL (usage facturé par Anthropic), à comparer à l'estimation ci-dessus.

## Choix techniques

- **Modèle par défaut : Haiku 4.5, pas Sonnet 5** — texte d'anecdotes/étude en jeu, pas une
  tâche qui demande le modèle le plus capable ; catalogue complet en dizaines de milliers de
  cartes, la différence de prix (5× moins cher côté sortie) domine largement le budget total.
  Reste configurable (`INSIGHTS_BATCH_MODEL`).
- **Sélection incrémentale sur contenu manquant, pas sur version de prompt** : une carte déjà
  couverte par une génération à la demande (avant ce lot) n'est **pas** re-traitée par le lot
  tant qu'elle a des anecdotes et une étude en jeu, même si son `source_model` ne porte pas le
  marqueur `:batch:v1`. Économise du budget sur les fiches déjà utilisables ; le prix est que les
  anecdotes EN ne sont pas ajoutées rétroactivement à ces cartes-là (voir « Reste à faire »).
- **`anecdotes_en` en colonne séparée, jamais mélangée à `anecdotes`** — voir livrables
  ci-dessus : éviter un mélange FR/EN visible immédiatement sur un produit francophone, sans
  bloquer ce lot sur une évolution du front qui n'est pas dans son périmètre.
- **Budget et taux de change fail-closed, jamais un repli silencieux à 0** : deux gardes-fous
  distincts (`pas_de_cle_plateforme`, `taux_de_change_indisponible`) plutôt que de laisser le
  pipeline continuer avec un coût compté comme nul — un budget qui ne compte pas vraiment la
  dépense n'est pas un plafond, c'est un mensonge. Le taux utilisé à la soumission est **figé
  dans le grand livre** (`InFlightBatch.usd_to_eur_rate`) et réutilisé tel quel à la clôture du
  lot, plutôt que d'en chercher un nouveau qui pourrait manquer ce jour-là.
- **Grand livre JSON local, pas une table de plus** — ce lot n'expose aucune route HTTP (script
  interne), et le principal besoin (reprise, budget cumulé, lot en cours) est purement de l'état
  d'exécution d'un outil, pas une donnée produit. Une table aurait ajouté une migration et une
  gestion de concurrence pour un besoin qu'un fichier local résout simplement (le script ne
  tourne jamais en parallèle de lui-même, un seul worktree/une seule machine).
- **Coût réel compté une seule fois par lot Anthropic** (`Ledger.completed_batch_ids`) : un
  script interrompu entre l'écriture des résultats en base et la clôture du grand livre reprend
  au prochain lancement, réapplique les mêmes écritures (idempotent, sans effet) mais ne
  recompte jamais le coût une seconde fois.
- **Client Message Batches dédié, pas une extension de `AIProvider`** : `AIProvider.extract`
  (mission `v3-ia-providers`) est un aller-retour synchrone par construction (utilisé par tout
  le reste du dépôt à la demande) — l'API Batch est fondamentalement asynchrone (soumettre,
  attendre, récupérer). Les mélanger aurait cassé cette hypothèse partout ailleurs pour un
  besoin propre à ce seul lot.
- **User-Agent identifié sur `MediaWikiClient`, sans URL ni contact inventés** : le projet n'a
  encore aucun domaine public (D2/D8 hors périmètre) — un faux domaine/e-mail aurait été plus
  trompeur pour les opérateurs de Poképédia/Bulbapedia qu'un simple nom de projet honnête.

## Écarts au plan

Aucune réduction de périmètre sur les livrables demandés (pipeline testé, mesure sur 100 cartes,
plafond vérifié, CI). Deux écarts documentés explicitement :

- La mesure de coût est une **estimation**, pas une mesure facturée (aucune clé plateforme
  disponible, D4) — `--live` est prêt, non exécuté.
- Les anecdotes EN sont produites et stockées (`anecdotes_en`) mais **aucune route ne les
  expose encore** — pas demandé par la définition de fini de ce lot (back-end seul, comme
  `v4-anecdotes`/`v4-jeu`/`v4-ranking`), cohérent avec le reste du dépôt.

## Reste à faire (pour les lots suivants)

- Lancer `scripts/run_insights_batch.py`/`measure_insights_batch_cost.py --live` dès que JF
  fournit `PLATFORM_ANTHROPIC_API_KEY` et `INSIGHTS_BUDGET_EUR` (D4) — confirmer le coût réel
  contre l'estimation ci-dessus avant d'arrêter un budget définitif pour le catalogue complet.
- Un futur lot front pourrait exposer `anecdotes_en` (déjà en base) si un besoin bilingue est
  confirmé — non demandé ici.
- Revalider `_ESTIMATED_CHARS_PER_TOKEN`/`_ESTIMATED_OUTPUT_TOKENS`
  (`pbm_api.insights_batch.runner`) contre un vrai `usage` une fois `--live` lancé : l'heuristique
  ne sert aujourd'hui qu'à ne pas dépasser le budget restant avant soumission, jamais à compter
  le coût réel — mais un écart trop grand la rendrait inutilement conservatrice ou risquée.
- Rétro-couvrir les cartes déjà traitées à la demande (avant ce lot) avec les anecdotes EN si le
  besoin bilingue se confirme (actuellement hors sélection, voir « Choix techniques »).

## Décisions provisoires utilisées

D4 (révisée 19/09, « autant tout prendre dès le premier tir ») : appliquée à la lettre — clé
plateforme distincte de toute clé d'utilisateur, budget plafonné, fail-closed sans l'une ou
l'autre. D3 (sources de prix gratuites + historique par nos relevés) : sans objet direct pour ce
lot (aucun prix touché), mais le même esprit (sources publiques gratuites, pas de nouveau
fournisseur payant) s'applique à la collecte de contexte, inchangée depuis `v4-anecdotes`. D2/D8
hors périmètre, confirmé (aucun déploiement, `release_uat`/`release_prod` sans objet). D5/D6/D7
sans objet pour ce lot (aucun e-mail, aucun classement, aucune photo touchés).
