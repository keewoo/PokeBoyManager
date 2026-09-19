# Compte rendu — `v3-identification`

Session autonome (`claude -p`) sur chimera, worktree `~/dev/wt-pbm-v3-identification`, branche
`roadmap/v3-identification`. Exécuté sous le régime décrit dans le CONTEXTE D'EXÉCUTION du
prompt (sections A/P/0/7 du prompt de lot remplacées) : pas de `suivi.py`, pas d'écriture dans
`etat.json`/`ROADMAP.html`/`BACKLOG.md`/`prompts/`, fusion directe vers `origin/main` (dépôt
relais local, pas GitHub).

## Résumé

Extraction par carte et rapprochement catalogue (`pbm_api.identification`), chaînés dans le même
job `detect_cards` que la détection (`v3-detection`) — pas un second aller-retour par la file.
Pour chaque `Detection` en attente : empreinte perceptuelle du recadrage (aHash 64 bits) ;
touchée dans un cache partagé entre utilisateurs, le résultat est réutilisé sans appel IA ; sinon
un appel `AIProvider.extract` (schéma `CardExtraction` : nom, numéro, total, code d'extension,
langue, PV, type, variante, confiance par champ) puis rapprochement catalogue en cascade (numéro
+ extension exacts, sinon numéro + nom, sinon recherche floue sur le nom seul), top 3 avec score
combiné et présélection au-delà de 0,9. Résultat écrit sur `Detection.extraction`/
`Detection.candidates`, exposé par la route déjà bornée au propriétaire de l'envoi
(`GET /uploads/{id}/detections`, `v3-detection`).

## Livrables

- `apps/api/src/pbm_api/identification/` :
  - `schemas.py` — `CardExtraction` (sortie IA, un champ de confiance par valeur),
    `CardVariantGuess`, `IdentificationCandidate` (forme stockée dans `Detection.candidates`).
  - `extraction.py` — prompt et `extract_card` (`AIProvider.extract`, un appel par carte).
  - `reconciliation.py` — `reconcile` : cascade numéro+extension → numéro+nom → nom seul,
    score combiné, présélection (`PRESELECTION_THRESHOLD = 0.9`).
  - `fingerprint.py` — `compute_phash` (aHash 64 bits sur le recadrage 630×880), `hamming_
    distance`, conversion en entier signé 64 bits (stockage `bigint`).
  - `cache.py` — `find_cached`/`store_cache` sur `identification_cache` (XOR + `bit_count`
    Postgres, distance de Hamming ≤ 6).
  - `service.py` — `run_identification_for_upload` : orchestration DB/stockage, indépendante
    d'arq, appelée par le worker juste après la détection.
  - `synthetic.py` — jeu de 100 cartes étiquetées (mission point 5, voir « Tests »).
- `apps/api/src/pbm_api/models/identification.py` — `IdentificationCache` (nouvelle table).
- `apps/api/src/pbm_api/models/collection.py` — `Detection.extraction` (JSONB, nouvelle
  colonne) : sortie brute de l'extraction, utile à l'écran de validation même sans candidat
  présélectionné.
- `apps/api/migrations/versions/054d503ae627_...py` — table `identification_cache` + colonne
  `detections.extraction`.
- `apps/api/src/pbm_api/worker.py` — `_run_detect_cards` appelle désormais `run_identification_
  for_upload` juste après `run_detection_for_upload`, dans le même `Job`.
- `apps/api/src/pbm_api/uploads/schemas.py`, `routers/uploads.py` — `DetectionResponse.
  extraction` exposé par `GET /uploads/{id}/detections`.
- `apps/api/scripts/measure_identification_rate.py` — mise au point palier par palier sur le jeu
  de 100 cartes (transaction annulée, aucune donnée laissée en base), écrit `report.json`.
- `apps/api/scripts/test_identification_manual.py` — essai manuel avec une vraie clé (mission
  « aucune clé IA réelle disponible »).
- `docs/ARCHITECTURE.md` § « Reconnaissance » points 2-3, `CLAUDE.md` § « Identification des
  cartes » — mis à jour.
- Bases/bucket/préfixe dédiés créés sur `pbm-shared` : `pbm_v3_identification` (dev),
  `pbm_v3_identification_test` (tests), bucket S3 `pbm-v3-identification`, préfixe Redis
  `pbm:v3-identification:` (déclarés en local — `conftest.py` porte encore le défaut d'un lot
  précédent, `TEST_DATABASE_URL` toujours explicite dans mes commandes, voir « Écarts »).
- `packages/api-client/src/schema.d.ts` régénéré (`pnpm gen:api`) pour le champ `extraction`.

## Tests

```
$ cd apps/api && uv run ruff check .
All checks passed!

$ TEST_DATABASE_URL=postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v3_identification_test \
  TZ=Europe/Paris uv run pytest -q
321 passed in ~37s   # 302 préexistants (rebasé sur origin/main) + 19 nouveaux
```

- `tests/test_identification_reconciliation.py` (6), `test_identification_fingerprint.py` (4),
  `test_identification_cache.py` (5), `test_identification_service.py` (3),
  `test_identification_synthetic_dataset.py` (1) — **échouent tous sans ce lot**
  (`pbm_api.identification` n'existait pas, `ModuleNotFoundError`) et passent une fois le module
  ajouté.
  - Cascade de rapprochement : numéro + extension désambiguïse deux cartes de même numéro dans
    des extensions différentes ; sans code d'extension, retombe sur numéro + nom (les deux
    candidats homonymes remontent) ; un numéro faux retombe sur le nom seul (le numéro erroné
    n'est **jamais** gardé au dernier palier — testé explicitement, c'est la correction faite
    lors de l'écriture : un premier jet gardait le numéro à chaque palier et cassait le repli).
    Présélection au-delà de 0,9 avec confiance haute, jamais avec confiance basse.
  - Empreinte perceptuelle : deux recadrages identiques → hash identique ; un recadrage à peine
    bruité → distance ≤ 6 (seuil du cache) ; deux cartes visuellement différentes → distance > 6 ;
    la valeur reste dans la plage `bigint` signée quel que soit le bit de poids fort.
  - Cache DB : recherche exacte et approchée (XOR + `bit_count` Postgres) ; un hash au-delà du
    seuil ne remonte rien ; un hash négatif (bit de poids fort à 1) se stocke et se relit sans
    erreur de conversion.
  - Service bout en bout (détection réelle → identification, double de fournisseur IA) : premier
    appel identifie et enregistre l'usage (`ai_usage_monthly`) ; **un second envoi de la même
    photo, par un autre utilisateur, ne rappelle jamais l'IA** (mission point 4, `ai_calls == 0`,
    `cache_hits == 1`, un seul appel du double au total pour les deux envois) ; sans clé IA, le
    service ne lève jamais, ne laisse simplement rien d'identifié (D4).
  - **Route d'accès croisé** : déjà couverte par `test_detections_routes.py` (`v3-detection`,
    404 sur `GET /uploads/{id}/detections` pour un autre utilisateur) — ce lot n'ajoute aucune
    route, il enrichit la réponse d'une route déjà bornée par `user_id`, donc déjà testée.

### Précision top-1/top-3 (mission point 5, objectif top-3 ≥ 95 %)

```
$ uv run python scripts/measure_identification_rate.py --out /tmp/identification-tuning-check
100 cartes — rapport dans /tmp/identification-tuning-check/report.json
top-1 : 93/100 = 93.0%
top-3 : 99/100 = 99.0% (objectif >= 95%)
paliers : {'nom_flou': 34, 'numero_extension': 26, 'numero_nom': 40}
```

La même mesure est **vérifiée par la CI** à chaque exécution
(`tests/test_identification_synthetic_dataset.py::test_identification_precision_on_synthetic_
dataset_meets_target`, échoue si le taux top-3 descend sous 95 %) — pas seulement publiée ici,
suivant le précédent posé par `v3-detection` pour son propre taux de détection.

**Le jeu de 100 cartes est synthétique** (voir « Écarts au plan ») : il simule directement la
sortie de l'extraction IA (`CardExtraction`) à partir d'une carte connue de la base, avec un
bruit contrôlé et reproductible (numéro décalé ou absent ~30 % du temps, nom sans accents/en
majuscules ~20 % du temps, code d'extension absent ~40 % ou faux ~15 % du temps) — ce chiffre
valide donc la **mécanique du rapprochement** (la cascade retombe bien sur le bon palier, le
score combiné départage correctement, la recherche floue retrouve la carte même numéro perdu),
pas la précision réelle d'un LLM de vision sur une vraie carte photographiée, hors de portée sans
clé IA réelle (voir « Reste à faire »).

```
$ pnpm install --frozen-lockfile && pnpm gen:api
$ pnpm --filter @pbm/web lint && pnpm --filter @pbm/web type-check
✓ eslint . (aucune erreur)
✓ tsc --noEmit (aucune erreur, client API régénéré compatible)
```

Aucun changement de page front dans ce lot (grille « maquette : sans objet », back-end pur) —
non-régression vérifiée par lint + type-check contre le client régénéré.

Aucun secret : ce lot ne manipule aucune clé IA en clair au-delà de ce que `v1-byok`/
`v3-detection` déchiffrent déjà (même filtre de journalisation) ; aucune clé réelle utilisée nulle
part (doubles de test uniquement, comme `v3-ia-providers`/`v3-detection`).

## Choix techniques faits (autonomes, dans le cadre de `docs/ARCHITECTURE.md`)

- **Point 3 de la mission (« comparaison visuelle recadrage/image officielle des 3 candidats par
  le LLM ») délibérément non implémenté** : un second appel IA par carte contredirait le principe
  cadre « un seul appel IA par carte, dès le premier tir » (`docs/ARCHITECTURE.md` § « la base
  sait, l'IA reconnaît »), qui l'emporte sur ce point de la mission en cas de contradiction
  (section 1 du prompt de lot : « le cadre l'emporte »). À la place, un score combiné sous le
  seuil de présélection renvoie tout de même les trois candidats avec leur score pour la
  validation humaine (lot `v3-validation`) — la mission qualifiait déjà ce point d'« optionnel
  si doute ».
- **Identification chaînée dans le même job `detect_cards`**, pas un second job/route mise en
  file : les deux étapes du pipeline de reconnaissance partagent le fournisseur IA de
  l'utilisateur déjà déchiffré pour la photo, et « un appel IA par carte, dès le premier tir »
  se lit comme un appel par carte détectée — pas un aller-retour de plus par la file d'attente
  par carte. Contrepartie assumée : un échec du fournisseur pendant l'identification (clé
  révoquée en cours de lot, quota) marque le `Job` entier en échec même si la détection avait
  réussi — acceptable, les `Detection` déjà créées (crops) restent consultables et l'ajout manuel
  reste possible (D4), et `record_usage` commet après chaque carte réussie : les cartes déjà
  identifiées avant l'échec ne sont pas perdues.
- **Cache d'identification par empreinte perceptuelle, partagé entre utilisateurs** (table
  dédiée `identification_cache`, pas une colonne sur `Detection`) : comme `card_insights`, le
  résultat d'une identification ne dépend que de l'image photographiée, jamais de qui l'a
  envoyée — deux utilisateurs qui photographient la même carte physique (deux exemplaires
  identiques, ou une recherche/collection croisée) ne paient qu'une fois. Hachage moyen (aHash)
  64 bits plutôt qu'un hachage cryptographique : le recadrage est déjà redressé à taille fixe
  (630×880 px), ce qui le rend stable d'une photo à l'autre malgré de petites variations de
  luminosité/flou — un hachage exact (SHA-256 des octets JPEG) aurait raté toute recompression.
  Recherche par XOR + `bit_count` (cast en `bit(64)`, `bit_count(bigint)` n'existe pas en
  Postgres — seulement `bit_count(bit)`/`bit_count(bytea)` depuis PG14, découvert en écrivant le
  test) : compatible PG16 (dev) et PG18 (cible production).
- **Score combiné = score catalogue × confiance moyenne des champs utilisés par le palier
  retenu**, pas un simple `min`/`max` ni un poids fixe par champ : un candidat catalogue exact
  mais lu avec une confiance IA basse (carte floue, angle) ne doit pas se présélectionner
  automatiquement — la présélection (> 0,9) exige donc à la fois un rapprochement catalogue fort
  **et** une lecture que l'IA elle-même juge fiable.
- **Palier final (recherche floue) omet délibérément le numéro**, même s'il a été lu : les
  paliers précédents, qui le filtrent strictement, viennent déjà d'échouer à ce stade — le garder
  écarterait la bonne carte si c'est justement le numéro qui a été mal lu (le cas que ce palier
  est censé couvrir). Couvert par un test dédié (`test_reconcile_falls_back_to_fuzzy_name_when_
  number_matches_nothing`) : un premier jet gardait le numéro à chaque palier, ce test échouait.
- **`Detection.extraction` ajouté en plus de `Detection.candidates`** (déjà posé par `v0-schema`
  pour ce lot) : la sortie brute de l'extraction (nom/numéro/PV/variante tels que lus, avec
  confiance) reste utile à l'écran de validation même quand aucun candidat catalogue ne dépasse
  le seuil de présélection, ou quand aucun candidat n'est trouvé du tout (`tier =
  "aucun_indice"`) — sans cette colonne, ce cas ne laisserait aucune trace de ce que l'IA a lu.
- **Variante de carte (`CardVariantGuess`) en énumération séparée**, distincte de `PriceVariant`
  (`pbm_api.models.catalog`, partagée par la tarification) : évite de faire dépendre le schéma
  d'extraction IA d'un type Postgres partagé entre plusieurs lots, et couvre des cas que l'IA
  peut décrire visuellement (full art, gold) sans qu'une variante de prix correspondante existe
  encore.
- **Migration Alembic nettoyée d'un diff hors périmètre** : `alembic revision --autogenerate`
  proposait aussi un changement de type sur `card_insight_reports.created_at`
  (`TIMESTAMP(timezone=True)` → `DateTime()`, artefact du comparateur sur une colonne posée par
  `v4-anecdotes`, même type Postgres réel) — retiré de la migration générée, documenté en
  commentaire, pour ne toucher que le périmètre de ce lot.

## Écarts au plan

- **Jeu de « 100 cartes étiquetées » synthétique, pas de vraies photos** (voir « Tests ») : même
  contrainte que `v3-detection` (aucun appareil photo ni carte physique sur chimera). Le module
  `pbm_api.identification.synthetic` simule directement des extractions bruitées plutôt que des
  images, ce qui valide le rapprochement catalogue mais pas la lecture visuelle réelle d'un LLM.
- **Coût moyen par carte non mesurable en euros** : aucune clé IA réelle disponible sur chimera,
  et aucune table de tarification par modèle dans ce dépôt à ce jour (déjà documenté comme
  manquant par `v3-detection` pour `ai_usage_monthly.estimated_cost_eur`, toujours vrai ici — pas
  un écart introduit par ce lot). `record_usage` (déjà posé par `v3-detection`) compte fidèlement
  appels et jetons dès qu'une vraie clé sera utilisée ; `scripts/test_identification_manual.py`
  permet de mesurer les jetons réels par carte une fois disponible.
- **Repli LLM jamais appelé avec une vraie clé** (mission : « aucune clé IA réelle disponible ») :
  toute la suite automatisée utilise un double de fournisseur. `scripts/
  test_identification_manual.py` est prêt pour un essai manuel futur.
- **Comparaison visuelle (mission point 3) non implémentée** (voir « Choix techniques »).

## Reste à faire (pour les lots suivants)

- Lot `v3-validation` : écran de validation humaine — corriger `Detection.extraction`/
  `Detection.candidates`, choisir un candidat (`Detection.selected_card_id`, colonne déjà posée
  par `v0-schema`, jamais écrite par ce lot), créer/mettre à jour `collection_items`. Chaque
  correction devrait idéalement alimenter un jeu de régression (mission `v3-identification`
  point 4) — aucun mécanisme de ce type n'existe encore.
- Lot `v3-etat` : estimation de l'état (centrage, coins, bords, surface). Le principe « un seul
  appel IA par carte, dès le premier tir » (JF, 19/09) dit que l'identification et l'état
  devraient partager le même appel — ce lot n'ajoute que l'identification (mission de ce lot,
  schéma `CardExtraction` sans champs d'état). Si `v3-etat` ajoute son propre appel IA, ce
  principe cadre sera de nouveau en tension ; deux options pour le lot suivant : étendre
  `CardExtraction`/`extract_card` avec les champs d'état (un seul appel, comme voulu), ou
  documenter explicitement pourquoi un second appel est fait malgré le principe. Non tranché ici
  : hors périmètre de ce lot (mission section 3 ne liste pas l'état), mais signalé pour que
  `v3-etat` ne le découvre pas en cours de route.
- Vraie campagne de photos + clé IA réelle pour mesurer la précision top-1/top-3 réelle (au-delà
  de la mécanique du rapprochement validée ici) et le coût moyen par carte en euros.
- Table de tarification par modèle pour `estimated_cost_eur` — toujours absente du dépôt.
- Réglage du seuil de présélection (0,9) et du seuil de distance de Hamming du cache (6) une fois
  de vraies photos disponibles — calés ici sur le jeu synthétique et le raisonnement du calcul de
  score, pas sur des données réelles.

## Décisions provisoires utilisées

D4 (sans clé IA personnelle, reconnaissance désactivée dès `complete_upload` — ce lot ne change
rien à cette règle : `run_identification_for_upload` ne lève jamais sans clé, il n'identifie
simplement rien). D2/D8 hors périmètre, confirmé (aucun déploiement, aucune tâche
`release_uat`/`release_prod` traitée).
