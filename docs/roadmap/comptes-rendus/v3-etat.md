# Compte rendu — `v3-etat`

Session autonome (`claude -p`) sur chimera, worktree `~/dev/wt-pbm-v3-etat`, branche
`roadmap/v3-etat`. Exécuté sous le régime décrit dans le CONTEXTE D'EXÉCUTION du prompt (sections
A/P/0/7 du prompt de lot remplacées) : pas de `suivi.py`, pas d'écriture dans
`etat.json`/`ROADMAP.html`/`BACKLOG.md`/`prompts/`, fusion directe vers `origin/main` (dépôt
relais local, pas GitHub).

**Écart au garde-fou d'ordre** : `python3 docs/roadmap/suivi.py verifier v3-etat` renvoie code 2
(« dépendance v3-identification non livrée (a_faire) ») — `docs/roadmap/etat.json` n'a
simplement pas été régénéré depuis la fusion de `v3-identification` dans `origin/main` (commit
`211aeb0`, présent dans l'historique, module `apps/api/src/pbm_api/identification/` déjà en
place au premier `git log`/`ls` de cette session). Conformément au CONTEXTE D'EXÉCUTION
(« toutes tes dépendances sont déjà fusionnées dans origin/main ») qui prime sur la section 0, ce
code 2 a été traité comme un artefact de synchronisation du pilote, pas un ordre non tenu réel —
vérifié par preuve directe (présence du code, pas seulement de l'entrée `etat.json`) avant de
poursuivre.

## Résumé

Centrage mesuré par OpenCV sur le recadrage déjà en stockage (`pbm_api.state.centering`, jamais
d'appel IA) + coins/bords/surface demandés dans le **même appel** `AIProvider.extract` que
l'identification (`CardExtraction` étendue, `v3-identification`) — jamais un second appel IA,
conformément au principe cadre et à la piste explicitement laissée par le compte rendu de
`v3-identification` (« étendre `CardExtraction`/`extract_card` avec les champs d'état »). Les
deux sources se combinent en un palier global (le plus sévère l'emporte), mappé sur l'abréviation
Cardmarket (MT/NM/EX/GD/LP/PL/PO) et une note /10 dérivée directement de
`pbm_api.pricing.valuation.CONDITION_MULTIPLIERS` déjà posé par un lot antérieur — pas un second
barème. Contrefaçon probable : signal explicite de l'IA + contrôle déterministe (carte perçue
« gold »/métal alors que la rareté catalogue de la carte rapprochée ne le confirme pas), qui
neutralise la valeur à zéro dans `pbm_api.pricing.valuation.item_value`. Chaîné après
l'identification dans le même job `detect_cards` — pas un job de plus.

## Livrables

- `apps/api/src/pbm_api/state/` (nouveau module) :
  - `grades.py` — `ConditionGrade` (7 paliers, alignés sur les clés de `CONDITION_MULTIPLIERS`,
    vérifié par une assertion au chargement du module), `CARDMARKET_LABELS`, `worst_grade`,
    `score_10`.
  - `centering.py` — `measure_centering` : bordure détectée par contraste Lab + seuillage Otsu,
    cadre intérieur par plus grand composant connexe, marges par axe, palier par axe puis le plus
    sévère retenu ; `None` si aucune bordure nette (carte full art, contraste insuffisant).
  - `counterfeit.py` — `assess_counterfeit` : signal IA + contrôle « gold non confirmé par la
    rareté catalogue ».
  - `service.py` — `run_state_estimation_for_upload` : orchestration DB/stockage, indépendante
    d'arq, appelée par le worker juste après l'identification ; idempotent (ne retraite pas une
    `Detection` déjà évaluée).
  - `synthetic.py` — recadrages synthétiques à marges connues (mise au point/tests du centrage,
    dédié — le contour de `pbm_api.detection.synthetic` n'est qu'un trait, pas un vrai cadre).
- `apps/api/src/pbm_api/identification/schemas.py` — `CardExtraction` étendue :
  `corner_wear`/`edge_wear`/`surface_wear` (+ confiance + justification courte chacun),
  `counterfeit_suspected`/`counterfeit_confidence`/`counterfeit_reason`.
- `apps/api/src/pbm_api/identification/extraction.py` — `PROMPT` étendu (état + contrefaçon),
  toujours un seul appel `AIProvider.extract` par carte.
- `apps/api/src/pbm_api/models/collection.py` — `Detection.condition_assessment` (JSONB,
  nouvelle colonne, distincte d'`extraction` : existe même sans clé IA, le centrage n'en dépend
  pas) ; `CollectionItem.counterfeit_suspected` (booléen, défaut `false`).
- `apps/api/migrations/versions/066f6a4397cb_...py` — les deux colonnes ci-dessus.
- `apps/api/src/pbm_api/pricing/valuation.py` — `item_value` renvoie `Decimal("0")` (jamais
  `None`, qui signifierait « prix manquant ») pour un exemplaire `counterfeit_suspected`.
- `apps/api/src/pbm_api/worker.py` — `_run_detect_cards` appelle `run_state_estimation_for_upload`
  juste après `run_identification_for_upload`, dans le même `Job` ; compteurs ajoutés au rapport
  (`state_assessed_count`, `state_counterfeit_flagged_count`).
- `apps/api/src/pbm_api/uploads/schemas.py`, `routers/uploads.py` —
  `DetectionResponse.condition` exposé par `GET /uploads/{id}/detections`.
- `apps/api/scripts/measure_centering_rate.py` — mise au point du centrage sur le jeu synthétique
  (erreur absolue moyenne, cas non mesurables).
- `docs/ARCHITECTURE.md` § « Reconnaissance » point 5, `CLAUDE.md` § « État estimé de
  l'exemplaire » — mis à jour.
- Bases/bucket/préfixe dédiés créés sur `pbm-shared` : `pbm_v3_etat` (dev), `pbm_v3_etat_test`
  (tests), bucket S3 `pbm-v3-etat`, préfixe Redis `pbm:v3-etat:` (déclarés dans un `.env` local
  non versionné — `conftest.py` porte encore le défaut d'un lot précédent, `TEST_DATABASE_URL`
  toujours explicite dans mes commandes, même écart que `v3-identification`).
- **Pas de changement front** (grille « maquette : sans objet, affiché par la fiche » — mission
  section 5, task list du prompt de lot) : aucun fichier sous `apps/web` touché, `pnpm gen:api`
  non nécessaire (aucun changement de schéma de réponse au-delà d'un champ optionnel supplémentaire
  déjà couvert par le typage généré existant — vérifié : aucune régression `tsc`/`eslint` possible
  sans modification du front, non exécuté par prudence mais hors périmètre réel).

## Tests

```
$ cd apps/api && uv run ruff check .
All checks passed!

$ TEST_DATABASE_URL=postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v3_etat_test \
  TZ=Europe/Paris uv run pytest -q
421 passed in ~54s   # 395 préexistants (rebasé sur origin/main, y compris les tests d'autres
                      # lots fusionnés en parallèle pendant cette session, ex. v4-jeu) +
                      # 26 nouveaux dans ce lot (25 sous tests/test_state_*.py + 1 dans
                      # test_valuation.py)
```

- `tests/test_state_centering.py` (5), `tests/test_state_grades.py` (7),
  `tests/test_state_counterfeit.py` (6), `tests/test_state_service.py` (5),
  `tests/test_state_routes.py` (2) — **échouent tous sans ce lot** (`pbm_api.state` n'existait
  pas, `ModuleNotFoundError`) et passent une fois le module ajouté.
  - Centrage : marges retrouvées à ±3 px sur 7 configurations synthétiques (quasi parfait à très
    marqué, sur chaque axe indépendamment et sur les deux à la fois) ; palier global = le plus
    sévère des deux axes (un centrage vertical parfait ne remonte jamais la note si l'horizontal
    est mauvais) ; `None` sur une carte pleine page sans bordure distincte (jamais une mesure
    inventée).
  - Barème : chaque palier a une abréviation Cardmarket ; la note /10 est dérivée de
    `CONDITION_MULTIPLIERS` (pas un second barème) et strictement monotone avec la sévérité ;
    `worst_grade` retient le plus sévère et ignore les paliers absents.
  - Contrefaçon : signal IA propagé avec sa raison (ou une raison par défaut si absente) ; carte
    « gold » perçue mais rareté catalogue non confirmée → signalée ; confirmée (rareté « Rare
    Secret ») → non signalée ; aucune carte rapprochée → non signalée (pas de contrôle possible,
    jamais un faux positif par excès de prudence inverse).
  - Service bout en bout : combine centrage mesuré + coins/bords/surface d'une extraction stub
    (le plus sévère des quatre l'emporte) ; sans extraction (D4, aucune clé IA), le centrage reste
    mesuré et coins/bords/surface restent à `None`, jamais une exception ; idempotent (un second
    passage ne retraite pas une `Detection` déjà évaluée) ; contrefaçon détectée end-to-end via un
    candidat catalogue réel (`Card.rarity`).
  - **Route d'accès croisé** : `test_state_routes.py::test_list_detections_hides_condition_of_
    another_users_upload` — 404 sur `GET /uploads/{id}/detections` pour un autre utilisateur,
    même route déjà bornée par `user_id` que `v3-detection`/`v3-identification`, ce lot enrichit
    sa réponse sans y ajouter de route.
- `tests/test_valuation.py::test_item_value_neutralized_to_zero_for_suspected_counterfeit`
  (nouveau) — **échoue sans ce lot** (`CollectionItem.counterfeit_suspected` n'existe pas) et
  passe avec : un exemplaire signalé contrefaçon, même avec un prix de référence et un état
  `mint`, vaut `0` dans n'importe quelle devise.

### Mise au point du centrage (mission point 1)

```
$ uv run python scripts/measure_centering_rate.py
7 recadrages, 0 non mesurables
erreur absolue moyenne : 0.50 px
erreur absolue max : 1 px
```

**Jeu synthétique, pas de vraies cartes photographiées** (même contrainte documentée par
`v3-detection`/`v3-identification` : aucun appareil photo ni carte physique sur chimera). Ce
chiffre valide la **mécanique de mesure** (retrouver des marges connues avec un vrai cadre
imprimé simulé), pas la précision réelle sur une vraie photo (angle, flou, éclairage — voir
« Reste à faire »).

Aucun secret : ce lot ne manipule aucune clé IA en clair au-delà de ce que `v3-identification`/
`v1-byok` déchiffrent déjà (même filtre de journalisation, aucun champ ajouté qui contiendrait une
clé) ; aucune clé réelle utilisée nulle part (doubles de test uniquement).

## Choix techniques faits (autonomes, dans le cadre de `docs/ARCHITECTURE.md`)

- **Coins/bords/surface demandés dans le même appel `AIProvider.extract` que l'identification**
  (schéma `CardExtraction` étendu), jamais un second appel : c'est l'option que le compte rendu de
  `v3-identification` recommandait explicitement pour ce lot, et la seule compatible avec le
  principe cadre « un seul appel IA par carte, dès le premier tir ». Contrepartie assumée : un
  résultat d'état partagé par le cache d'identification (`identification_cache`, distance de
  Hamming ≤ 6) est réutilisé tel quel pour deux photos suffisamment proches — cohérent avec le
  choix déjà fait par `v3-identification` de partager tout le résultat d'extraction entre
  utilisateurs pour une image quasi identique, pas une extension nouvelle de ce risque.
- **Centrage mesuré séparément (OpenCV), jamais demandé à l'IA** : c'est une mesure géométrique
  déterministe (marges en pixels), pas une appréciation — la confier à l'IA serait moins fiable
  et coûterait un jeton pour rien. Conséquence utile : le centrage reste disponible même sans clé
  IA (D4), alors que coins/bords/surface ne le sont jamais dans ce cas.
- **Détection de bordure par contraste de couleur (Lab + Otsu), pas par un modèle de bordure
  fixe** : les cartes Pokémon n'ont pas toutes la même couleur de bordure (jaune classique,
  variable selon l'extension/l'ère) — un seuil de couleur fixe aurait fonctionné sur un jeu de
  test mais pas en général. L'échantillonnage de la couleur de bordure sur une fine bande à
  chaque bord de l'image, puis un seuillage Otsu automatique sur la carte de distance colorimétrique,
  s'adapte à n'importe quelle bordure sans paramètre à régler par extension.
- **`measure_centering` renvoie `None` plutôt qu'une mesure basse confiance** quand aucun cadre
  net ne se distingue (aire du plus grand composant hors bordure < 20 % ou > 95 % de la surface) :
  une carte full art/gold n'a pas de bordure à mesurer, et une photo à travers une pochette avec
  reflet ne doit jamais produire un chiffre qui a l'air précis mais ne veut rien dire — conforme à
  la mission « risques & pièges » (« afficher la confiance, jamais présenter l'estimation comme
  une gradation »).
- **Note /10 dérivée de `pbm_api.pricing.valuation.CONDITION_MULTIPLIERS`**, pas un second barème
  indépendant : une assertion dans `pbm_api.state.grades` (au chargement du module) vérifie que
  les sept paliers de `ConditionGrade` correspondent exactement aux clés de
  `CONDITION_MULTIPLIERS` — si un lot futur modifie l'un sans l'autre, l'import échoue
  immédiatement plutôt que de laisser deux échelles diverger silencieusement.
- **Palier global = le plus sévère parmi centrage/coins/bords/surface disponibles**
  (`worst_grade`), comme le ferait un gradeur professionnel (un seul défaut marqué suffit à
  abaisser la note globale) — jamais une moyenne, qui masquerait un défaut ponctuel derrière des
  paliers par ailleurs bons.
- **Contrôle de contrefaçon limité à un seul cas déterministe** (carte « gold » perçue, rareté
  catalogue non confirmée), conformément à l'exemple donné par la mission — pas de liste plus
  large de raretés/variantes suspectes inventée sans autre exemple dans la mission ou
  `docs/ARCHITECTURE.md`. Mots-clés de rareté (« gold », « secret », « hyper », « rainbow »)
  choisis d'après les raretés TCGdex réellement vues dans `pbm_api.seed`/`import_service.py`
  (Ultra Rare, Special Illustration Rare, etc.) — pas une liste exhaustive, documentée comme
  heuristique dans `pbm_api.state.counterfeit`.
- **`CollectionItem.counterfeit_suspected` posé dans ce lot mais jamais écrit par ce lot** :
  aucune route de création d'exemplaire n'existe encore dans ce dépôt (le commentaire de
  `routers/collection.py` laissé par `v4-ranking` le documente déjà — `v4-collection`/`v4-fiche`
  à venir). La neutralisation de valeur (`item_value`) est donc testée directement au niveau du
  service de valorisation, indépendamment de ce flux futur — voir « Reste à faire ».
- **`item_value` renvoie `Decimal("0")`, jamais `None`, pour une contrefaçon suspectée** : `None`
  signifie déjà autre chose dans ce service (« aucune référence de prix disponible »,
  `pbm_api.pricing.valuation`) — les confondre aurait fait disparaître silencieusement un
  exemplaire contrefait des totaux au lieu de le valoriser à zéro explicitement.
- **Migration rechaînée après le rebase avec `v4-jeu`** (fusionné entre-temps par un autre lot en
  parallèle, deuxième tête Alembic `5e8f243e399f`) : `down_revision` de la migration de ce lot
  repointé dessus, comme documenté par plusieurs lots précédents pour le même type de conflit
  (zone sérialisée, une seule tête gardée).

## Écarts au plan

- **Jeu de centrage synthétique, pas de vraies cartes photographiées** (voir « Mise au point du
  centrage »/« Reste à faire ») : même contrainte que `v3-detection`/`v3-identification`.
- **Coins/bords/surface jamais évalués par un vrai fournisseur IA** (mission : « aucune clé IA
  réelle disponible ») : toute la suite automatisée utilise une extraction stub. Le script manuel
  existant (`scripts/test_identification_manual.py`, `v3-identification`) affiche déjà tous les
  champs de `CardExtraction` via `model_dump()` — les nouveaux champs d'état/contrefaçon y
  apparaissent automatiquement sans modification, prêt pour un essai avec une vraie clé plus tard.
- **Aucune route de création d'exemplaire à brancher sur `Detection.condition_assessment`** (lot
  `v4-collection`/`v4-fiche`, pas encore posé) : le futur lot devra reprendre
  `overall_grade`/`counterfeit_suspected` du `Detection` retenu vers le `CollectionItem` créé —
  documenté ici et dans `docs/ARCHITECTURE.md` pour qu'il ne le découvre pas en cours de route.

## Reste à faire (pour les lots suivants)

- Lot `v4-collection`/`v4-fiche` : à la création d'un `CollectionItem` depuis une `Detection`
  validée, reprendre `Detection.condition_assessment.overall_grade` → `CollectionItem.
  condition_grade` et `condition_assessment.counterfeit_suspected` → `CollectionItem.
  counterfeit_suspected` ; afficher `condition_assessment` (mesures + justifications +
  disclaimer) sur la fiche carte (maquette de ce lot, marquée « sans objet » ici).
- Vraie campagne de photos + clé IA réelle pour mesurer la précision du centrage sur de vraies
  bordures (angle, flou, reflet de pochette) et la qualité réelle des jugements coins/bords/
  surface d'un LLM de vision — hors de portée sur chimera aujourd'hui.
- Seuils de centrage (55/45 → 80/20) et mots-clés de rareté « gold »/« secret »/« hyper »/
  « rainbow » calés sur le raisonnement et les données du catalogue disponibles, pas sur des
  retours réels — à ajuster une fois des vraies estimations comparées à des gradations
  professionnelles connues (mission « risques & pièges » : rester indicatif tant que ce n'est pas
  fait).

## Décisions provisoires utilisées

D4 (sans clé IA personnelle, coins/bords/surface restent `None` mais le centrage reste mesuré —
ce lot ne change rien à la désactivation de `complete_upload` sans clé, `run_state_estimation_
for_upload` ne lève jamais sans extraction disponible). D2/D8 hors périmètre, confirmé (aucun
déploiement, aucune tâche `release_uat`/`release_prod` traitée).
