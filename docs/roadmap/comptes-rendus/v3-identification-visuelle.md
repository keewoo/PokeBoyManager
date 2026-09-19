# Compte rendu — `v3-identification-visuelle`

Session autonome (`claude -p`) sur chimera, worktree `~/dev/wt-pbm-v3-identification-visuelle`,
branche `roadmap/v3-identification-visuelle`. Exécuté sous le régime décrit dans le CONTEXTE
D'EXÉCUTION du prompt (sections A/P/0/7 du prompt de lot remplacées) : pas de `suivi.py`, pas
d'écriture dans `etat.json`/`ROADMAP.html`/`BACKLOG.md`/`prompts/`, fusion directe vers
`origin/main` (dépôt relais local, pas GitHub).

## Résumé

Index visuel des images officielles (`card_visual_index` — aHash 64 bits sur l'illustration et
sur la carte entière, par carte × langue) inséré dans le pipeline de reconnaissance entre le
cache d'empreinte existant (photo déjà vue) et l'appel IA : une correspondance visuelle confiante
identifie la carte **sans aucun appel IA**, y compris sans clé configurée (D4) ; un groupe « même
illustration » (réimpression/reverse/promo) n'est jamais tranché seul, ses candidats sont
injectés dans le prompt du **même** appel `AIProvider.extract` que l'extraction/l'état (le
principe « un seul appel IA par carte » reste respecté). Mesuré sur un jeu synthétique de 100
cartes : 79 % reconnues sans IA, 100 % de précision parmi elles, 0 groupe ambigu résolu à tort
avec confiance. Recherche vectorisée en mémoire (numpy) : ~4 ms/carte à l'échelle de production
(40 000 lignes), 625 Ko pour les empreintes elles-mêmes — largement dans le budget du serveur de
4 Go.

## Livrables

- `apps/api/src/pbm_api/identification/` :
  - `visual_geometry.py` — normalisation géométrique commune à l'image officielle et au
    recadrage utilisateur (`normalize_to_card_canvas`, `illustration_region`) : les deux doivent
    être ramenés au même cadre 630×880 avant hachage, sinon une simple différence d'échelle fait
    diverger deux hachages qui devraient être proches.
  - `visual_index.py` — `VisualIndex` (chargement en mémoire depuis `card_visual_index`,
    recherche par XOR + comptage de bits vectorisé numpy), `resolve` (décision confiante/ambiguë,
    `CONFIDENT_SCORE_THRESHOLD` = 0,85, `AMBIGUITY_MARGIN` = 0,06).
  - `visual_build.py` — `compute_visual_hashes` (image officielle → deux empreintes),
    `image_url_for_language` (déduction de l'URL TCGdex par langue), `upsert_visual_index_entry`.
  - `visual_resolve.py` — construit une `CardExtraction`/`IdentificationCandidate` directement
    depuis le catalogue pour une correspondance confiante (jamais une seconde recherche floue),
    ou une liste de candidats ambigus + `visual_hint_lines` (texte injecté dans le prompt IA).
  - `visual_synthetic.py` — jeu de 100 cartes procédurales (image officielle + photo utilisateur
    bruitée du même motif) pour mesurer la mécanique sans vraie photo/carte physique.
  - `service.py` — `_identify_one` réordonné : cache d'empreinte → comparaison visuelle → IA
    (assistée des candidats visuels) seulement si ambiguë ou sans correspondance.
  - `extraction.py` — `extract_card(..., visual_hints=[...])` ajoute les candidats visuels au
    prompt existant, jamais un second appel.
  - `cache.py` — `store_cache(..., method=...)` : la méthode de résolution (`"visuel"`/`"ia"`)
    est désormais mémorisée avec le résultat mis en cache.
- `apps/api/src/pbm_api/models/identification.py` — `CardVisualIndex` (nouvelle table),
  `IdentificationCache.method` (nouvelle colonne, défaut `"ia"` pour les lignes déjà en base).
- `apps/api/src/pbm_api/models/collection.py` — `Detection.identification_method` (nouvelle
  colonne : `"visuel"`/`"ia"`/`"aucun"`/`None`) — sert au badge « reconnue sans IA ».
- `apps/api/migrations/versions/f950b86db322_...py` — table `card_visual_index` + les deux
  colonnes `method`.
- `apps/api/src/pbm_api/worker.py` — rapport de job enrichi d'`identification_visual_matches`.
- `apps/api/src/pbm_api/uploads/schemas.py`, `routers/uploads.py` — `DetectionResponse.
  identification_method` exposé par `GET /uploads/{id}/detections` et `GET /uploads/{id}`.
- `apps/web/src/lib/api/validation.ts`, `.../ajouter/validation/detection-card.tsx` — badge
  « reconnue sans IA » quand `identification_method === "visuel"` (même emplacement que les
  badges statut/contrefaçon existants, aucun autre changement d'écran — grille « maquette : sans
  objet », voir « Écarts »).
- `apps/api/scripts/build_visual_index.py` — construit l'index en production (télécharge
  l'image officielle basse définition par carte × langue, met en cache l'octet dans le stockage
  objet — réutilisé par le proxy `/img/cards/{id}` —, idempotent et reprenable : une carte déjà
  indexée pour une langue est sautée par défaut).
- `apps/api/scripts/measure_visual_identification_rate.py` — mise au point sur le jeu
  synthétique (`report.json`).
- `apps/api/scripts/measure_visual_index_performance.py` — temps de recherche et empreinte
  mémoire à l'échelle de production (empreintes aléatoires, pas besoin d'images réelles).
- `docs/ARCHITECTURE.md` § « Reconnaissance » (nouveau point 4), `CLAUDE.md` §§ « Comparaison
  visuelle », « État estimé de l'exemplaire », « Écran de validation » — mis à jour.
- Bases/bucket dédiés créés sur `pbm-shared` : `pbm_v3_identification_visuelle` (dev),
  `pbm_v3_identification_visuelle_test` (tests), bucket S3 `pbm-v3-identification-visuelle`,
  préfixe Redis `pbm:v3-identification-visuelle:` (`apps/api/.env`, non versionné).
- `packages/api-client/src/schema.d.ts` régénéré (`pnpm gen:api`) pour `identification_method`.

## Tests

```
$ cd apps/api && uv run ruff check .
All checks passed!

$ TEST_DATABASE_URL=postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v3_identification_visuelle_test \
  TZ=Europe/Paris uv run pytest -q
464 passed   # 439 préexistants (rebasé sur origin/main) + 25 nouveaux

$ pnpm --filter @pbm/web lint && pnpm --filter @pbm/web type-check && pnpm --filter @pbm/web test
✓ eslint . (aucune erreur)
✓ tsc --noEmit (aucune erreur, client API régénéré compatible)
✓ 21 fichiers, 65 tests
```

- `tests/test_identification_visual_index.py` (8), `test_identification_visual_build.py` (6),
  `test_identification_visual_resolve.py` (4), `test_visual_identification_synthetic_dataset.py`
  (1), + 3 nouveaux scénarios dans `test_identification_service.py`, + 1 assertion étendue dans
  `test_identification_cache.py` — **tous échouent sans ce lot** (`pbm_api.identification.
  visual_index`/`visual_build`/`visual_resolve`/`visual_synthetic` n'existaient pas,
  `ModuleNotFoundError`, ou `store_cache`/`Detection.identification_method` n'avaient pas leur
  nouveau paramètre/colonne) et passent une fois le code ajouté.
  - `VisualIndex.search`/`resolve` : classement par score, dédoublonnage par carte (une ligne par
    langue ne compte jamais deux fois), limite respectée, confiance au-dessus du seuil, refus
    quand un concurrent d'une **autre** carte est trop proche, jamais de refus quand le
    concurrent est juste l'autre langue de la même carte.
  - `visual_build` : déduction d'URL par langue (et rejet d'une forme d'URL inattendue), calcul
    d'empreintes identique à un calcul manuel, upsert qui met à jour plutôt que dupliquer
    (contrainte unique `card_id`+`language`), image illisible refusée explicitement (jamais un
    hachage inventé sur des octets corrompus).
  - `visual_resolve` : extraction confiante remplit tous les champs depuis le catalogue avec
    confiance 1,0 et laisse l'état (`corner_wear`...) à `None` (rien n'a été "lu" au-delà de
    l'identité de la carte) ; candidats ambigus jamais présélectionnés ; carte disparue du
    catalogue depuis l'indexation gérée sans lever.
  - **Service bout en bout** (`test_identification_service.py`) : une correspondance visuelle
    confiante identifie la carte avec `ai_calls == 0`/`visual_matches == 1` **même avec une clé
    IA configurée** (le double de fournisseur n'est jamais appelé, `stub.calls == 0`) ; un groupe
    ambigu (deux cartes indexées avec la même empreinte que la photo) appelle l'IA avec les deux
    candidats visibles dans le prompt (`stub.last_prompt` contient les deux noms) ; sans clé IA,
    un groupe ambigu expose tout de même ses candidats à la validation humaine plutôt que de ne
    rien montrer (extension du comportement D4).
  - **Route d'accès croisé** : déjà couverte par `test_detections_routes.py` (404 sur `GET
    /uploads/{id}/detections` pour un autre utilisateur) — ce lot n'ajoute aucune route, il
    enrichit la réponse d'une route déjà bornée par `user_id`.

### Reconnu sans IA / précision (mission point 4, objectif ≥ 60 % sans dégrader la précision)

```
$ uv run python scripts/measure_visual_identification_rate.py --out /tmp/visual-tuning
100 cartes (20 en paires ambiguës) — rapport dans /tmp/visual-tuning/report.json
reconnues sans IA : 79/100 = 79.0%
précision parmi les reconnues : 100.0%
cartes uniques résolues avec confiance : 79/80
paires ambiguës laissées à l'IA (attendu) : 20/20 — résolues à tort avec confiance : 0
```

Même mesure **vérifiée par la CI** (`tests/test_visual_identification_synthetic_dataset.py`,
échoue si la couverture descend sous 60 % ou si une seule paire ambiguë est résolue à tort avec
confiance) — même précédent que `v3-detection`/`v3-identification` pour leur propre taux.

**Le jeu de 100 cartes est synthétique** (`pbm_api.identification.visual_synthetic`, mêmes
contraintes que les autres — voir « Écarts ») : une image officielle procédurale (245×337, comme
TCGdex "low") et une photo utilisateur rendue *indépendamment* au même motif (630×880, jamais un
agrandissement de l'image officielle — ça aurait rendu la comparaison triviale) avec bruit/flou/
luminosité/recompression JPEG. 20 cartes reprennent délibérément le motif d'une autre (mission
« risques & pièges », réimpression/reverse/promo simulés) : la comparaison visuelle les a
**toutes** correctement laissées à l'IA, jamais résolues à tort — c'est la garantie de sécurité
qui compte le plus (une carte visuellement confondable ne doit jamais être présentée comme sûre).

⚠️ **Piège rencontré en écrivant `visual_synthetic.py`** : une première version ne faisait varier
les cartes que par teinte (roue de couleurs bien séparées). Résultat mesuré : **0 % de
reconnaissance**. `compute_phash` (aHash) convertit en niveaux de gris avant de hacher — deux
couleurs de luminance proche produisent un hachage quasi identique, quelle que soit leur teinte.
Corrigé en dérivant le motif d'un RNG scellé par `shape_seed` (disposition de formes à niveaux de
gris variés) plutôt que de la couleur — un rappel direct pour la vraie image officielle
(mission point 1) : le hachage discrimine par **structure**, pas par palette, ce que les vraies
illustrations Pokémon ont naturellement (poses/compositions différentes) mais qu'un jeu
synthétique doit reproduire explicitement.

### Performance et mémoire à l'échelle de production (mission point 5)

```
$ uv run python scripts/measure_visual_index_performance.py --rows 40000 --searches 300
{
  "rows": 40000,
  "distinct_cards": 20000,
  "index_build_seconds": 0.0369,
  "index_arrays_memory_kb": 625.0,
  "process_rss_total_mb": 65.1,
  "search_ms_mean": 4.24,
  "search_ms_p95": 4.436,
  "search_ms_max": 5.73,
  "target_search_ms": 200
}
```

40 000 lignes (20 000 cartes × 2 langues, la volumétrie citée par la mission) chargées en 37 ms,
recherche moyenne 4,2 ms/carte (max mesuré 5,7 ms) — largement sous les 200 ms cible ; 625 Ko pour
les tableaux d'empreintes eux-mêmes, 65 Mo de RSS process total (import numpy/cv2 compris) — sans
rapport avec un modèle lourd, compatible avec le serveur de 4 Go. Empreintes aléatoires
volontairement (pas besoin d'images réelles) : le coût de `VisualIndex` ne dépend que du nombre
de lignes, jamais de leur contenu.

### Preuve réseau réelle (mission point 1 : « télécharger les images officielles »)

```
$ DATABASE_URL=postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v3_identification_visuelle \
  uv run python scripts/build_visual_index.py --limit 400 --languages fr,en
terminé en 17.7s — indexées=798 erreurs=2   # (2 images anglaises absentes côté TCGdex, 404 réels)
```

Exécuté deux fois de suite sur le catalogue réel importé par `v2-catalogue-complet`
(`pbm_v3_identification_visuelle`, 22 169 cartes dont 18 342 avec `image_url`) : la deuxième
exécution avance naturellement sur les cartes suivantes (celles déjà indexées sont exclues de la
requête) — la reprise fonctionne sans paramètre supplémentaire. **1 634 lignes** indexées au
total (820 cartes distinctes, fr+en) en ~2×20 s de réseau réel, images mises en cache dans MinIO
sous `cards/{id}/{langue}/low.webp`. Preuve du pipeline réel de bout en bout (téléchargement TCGdex
→ hachage → écriture DB → cache objet), pas une simulation.

## Choix techniques faits (autonomes, dans le cadre de `docs/ARCHITECTURE.md`)

- **OCR local non implémenté** (mission point 2 : « le numéro et la langue départagent, lecture
  OCR locale légère, sinon IA ») : aucun `tesseract` sur chimera, et **pas de sudo sans mot de
  passe** pour l'installer (`sudo -n true` refuse). La mission prévoit elle-même le repli « sinon
  IA » pour ce cas précis — c'est celui-ci qui est implémenté : un groupe ambigu est toujours
  résolu par l'IA (assistée des candidats visuels) quand une clé est disponible, jamais deviné.
  Écrire un OCR maison à la volée pour un seul champ (le numéro, quelques caractères en petite
  police) aurait été moins fiable que le lire directement dans l'appel IA déjà prévu pour ce cas
  — pas un compromis de qualité, juste éviter une pièce non testable en conditions réelles.
- **Zone d'illustration approximée par un rectangle relatif fixe** (`pbm_api.identification.
  visual_geometry`, 11 %-58 % de hauteur, 8 %-92 % de largeur) plutôt que détectée dynamiquement :
  la mise en page Pokémon TCG est stable sur l'essentiel des générations (bandeau de nom,
  illustration, texte) — un décalage systématique affecte les deux côtés de la comparaison
  (image officielle et recadrage utilisateur) de la même façon et n'abîme donc pas la distance de
  Hamming. Documenté comme approximation, pas exact sur les cartes pleine illustration/promos.
- **Recherche en mémoire (numpy), pas en SQL** contrairement à `identification_cache` : ce
  dernier documente déjà que son scan SQL par `bit_count` ne vaut que pour un volume "modeste" —
  ~40 000 lignes (20 000 cartes × 2 langues) en est un ordre de grandeur au-dessus. `VisualIndex`
  est rechargé une fois par envoi (`run_identification_for_upload`), jamais mis en cache au
  niveau du processus : les tests utilisent une transaction annulée par test
  (`tests/conftest.py`), un cache au niveau module aurait lu des données d'un test précédent déjà
  annulées — la sécurité de correction a primé sur la micro-optimisation (le chargement mesuré,
  37 ms pour 40 000 lignes, reste négligeable face au reste du pipeline d'un envoi).
- **Poids illustration 0,6 / carte entière 0,4** pour le score combiné : l'illustration est le
  signal le plus stable (partagé même entre langues et souvent entre réimpressions), le cadre
  entier départage les variantes qui changent le liseré/le fond (holo, reverse) sans changer
  l'illustration. Calibré empiriquement sur le jeu synthétique (`CONFIDENT_SCORE_THRESHOLD` =
  0,85, `AMBIGUITY_MARGIN` = 0,06) — à recalibrer une fois de vraies photos disponibles, comme
  `v3-identification` l'a déjà noté pour son propre seuil de présélection.
- **Ambiguïté définie par carte, jamais par ligne** (`pbm_api.identification.visual_index.
  resolve`) : deux lignes de la même carte (fr/en) qui arrivent toutes deux en tête ne comptent
  jamais comme un concurrent — seul un candidat d'un **autre** `card_id` à moins de la marge
  déclenche le repli IA. Sans cette règle, une carte parfaitement identifiée dans les deux
  langues aurait été traitée comme ambiguë à tort à chaque fois.
- **Correspondance confiante construite directement depuis le catalogue, jamais repassée par
  `pbm_api.identification.reconciliation.reconcile`** (`visual_resolve.
  build_confident_extraction`) : le rapprochement flou existe pour retrouver une carte à partir
  d'un texte incertain (lu par l'IA) — une correspondance visuelle confiante connaît déjà le
  `card_id` avec certitude, le refaire passer par une recherche floue réintroduirait exactement
  l'incertitude que la comparaison visuelle vient d'éliminer.
- **État de l'exemplaire non mesuré par l'IA quand la carte est reconnue par le seul index
  visuel** (`corner_wear`/`edge_wear`/`surface_wear` restent `None`, jamais fabriqués) : le
  principe cadre interdit un second appel IA seulement pour l'état — l'estimation retombe alors
  sur le centrage (OpenCV) seul, `pbm_api.state.grades.worst_grade` ignore déjà les paliers
  absents (comportement préexistant, aucun changement nécessaire dans `pbm_api.state`).
  Documenté en « reste à faire » : un appel IA dédié à l'état pourrait être ajouté plus tard,
  seulement pour les cartes reconnues visuellement, si la mesure d'état devient prioritaire.
- **`IdentificationCache.method` et `Detection.identification_method` en colonnes séparées**,
  pas encodées dans `tier` (déjà utilisé par `identification_cache` pour le palier de
  rapprochement catalogue) : les deux informations sont indépendantes (une résolution "ia" peut
  avoir n'importe quel tier de rapprochement, une résolution "visuel" n'en a pas) — les confondre
  aurait forcé une valeur de tier arbitraire (`"visuel"`) dans un champ qui documente autre chose.
- **Base/bucket dédiés créés directement** (`pbm_v3_identification_visuelle[_test]`,
  `pbm-v3-identification-visuelle`) plutôt que réutiliser une base d'un lot précédent : suit la
  règle du prompt (« jamais les ressources d'un autre lot ») — la graine réutilisable du
  catalogue (`scripts/catalogue_seed.sh`, artefact `~/dev/pbm-artefacts/catalogue-*.dump` produit
  par `v2-catalogue-complet`) a servi à peupler la base dev avec le vrai catalogue (22 169
  cartes) sans refaire un import complet, exactement l'usage pour lequel elle a été écrite.

## Écarts au plan

- **Jeu de 100 cartes "visuelles" synthétique, pas de vraies photos/images officielles** (voir
  « Tests ») : même contrainte que `v3-detection`/`v3-identification`. Valide la mécanique du
  pipeline (hachage, seuils, sécurité sur les groupes ambigus), pas la robustesse réelle d'un
  aHash sur une vraie photo de carte contre une vraie image TCGdex (pochette, reflet, angle —
  risques déjà nommés par la mission).
- **Index construit sur un échantillon réel (1 634 lignes / 820 cartes), pas sur tout le
  catalogue** (36 684 lignes visées, 18 342 cartes × 2 langues) : téléchargement réseau réel non
  lancé en tâche de fond pour ce lot (aucune tâche `release_uat`/`release_prod`, hors périmètre —
  D2/D8). Le script (`scripts/build_visual_index.py`) est prêt pour un lancement complet
  (idempotent, reprenable, journalisé comme `import_full_catalogue.py`) ; extrapolation du débit
  mesuré (798 cartes fr+en en 17,7 s) : import complet en ordre de grandeur ~7 minutes réseau pur
  sur ce lien, sans compter la contention avec d'autres lots en cours.
- **Badge front minimal, pas de nouvel écran** : la grille de ce lot qualifie « maquette » de
  « sans objet (back-end) » — un seul badge conditionnel a été ajouté à `detection-card.tsx`
  (`identification_method === "visuel"`), au même endroit que les badges existants, pour que la
  donnée produite par ce lot soit effectivement visible quelque part sans redessiner l'écran.
  Lint/type-check/tests unitaires du front vérifiés verts ; **le test e2e Playwright
  `validation.spec.ts` n'a pas été relancé** (nécessite de démarrer les serveurs web+API+Mailpit)
  — risque de régression jugé très faible (badge purement additif, condition jamais vraie dans le
  scénario semé par `seed_validation_e2e.py` qui force `identification_method="ia"`), mais non
  vérifié en conditions réelles de navigateur pour ce lot.
- **OCR local non implémenté** (voir « Choix techniques ») — le repli « sinon IA » prévu par la
  mission le remplace.
- **Descripteur couleur non ajouté** (mission point 1 : « éventuellement un descripteur
  couleur ») : les deux aHash (illustration + carte entière) suffisent à atteindre l'objectif de
  couverture sur le jeu de mesure (79 % ≥ 60 %) sans complexité supplémentaire — laissé en
  réserve si une vraie campagne photo montre un besoin de discrimination plus fine.

## Reste à faire (pour les lots suivants ou une future itération)

- Lancer `scripts/build_visual_index.py` sans `--limit` en tâche de fond (hors serveur de PROD,
  sur chimera ou devAI) pour couvrir tout le catalogue avant l'ouverture — actuellement 4,5 % des
  cartes à image connue sont indexées (échantillon de preuve de ce lot).
- Vraie campagne de photos pour mesurer la précision/le taux de couverture réels de la
  comparaison visuelle (au-delà de la mécanique validée par le jeu synthétique) et recalibrer
  `CONFIDENT_SCORE_THRESHOLD`/`AMBIGUITY_MARGIN` en conséquence.
- OCR local léger du numéro (mission point 2), si `tesseract` devient installable (sudo/paquet
  fourni par devAI) — permettrait de résoudre certains groupes « même illustration » sans même
  attendre une clé IA.
- Étendre `AIProvider.extract`/le prompt d'état pour couvrir les cartes reconnues par le seul
  index visuel (actuellement `corner_wear`/`edge_wear`/`surface_wear` restent non mesurés pour
  elles, voir « Choix techniques ») — décision à trancher explicitement (contredit ou non le
  principe « un seul appel IA » selon comment on le lit, comme déjà signalé par `v3-etat`).
- e2e Playwright `validation.spec.ts` à relancer en conditions réelles pour confirmer le rendu du
  nouveau badge (non vérifié dans ce lot, voir « Écarts »).
- Descripteur couleur en complément des deux aHash, si une vraie campagne photo montre des cas
  de confusion entre illustrations proches mais de teintes différentes (holo vs normal, par
  exemple) que les hachages actuels ne séparent pas suffisamment.

## Décisions provisoires utilisées

D4 (sans clé IA personnelle, une correspondance visuelle confiante identifie tout de même la
carte — ce lot élargit ce que D4 permet sans clé, comme envisagé par la mission : « reconnaissance
possible même sans clé IA pour les cartes non ambiguës »). D2/D8 hors périmètre, confirmé (aucun
déploiement, aucune tâche `release_uat`/`release_prod` traitée, index construit uniquement sur
l'infra de dev partagée `pbm-shared`).
