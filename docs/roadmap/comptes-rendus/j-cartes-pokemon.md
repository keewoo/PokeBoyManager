# Compte rendu — `j-cartes-pokemon`

**Statut : livré (recette locale chimera verte, CI à confirmer sur la PR).**
Jalon J1 · piste Effets & cartes · couloir J-EFF (chimera).

## Résumé

Les cartes Pokémon deviennent jouables **depuis le catalogue**, sans aucune caractéristique écrite
en dur dans le moteur (D9). Le lot livre : le descripteur `DefinitionCarte` (pur, validé), les
transitions `poser` et `evoluer` (pile d'évolution, conservation/effacement, gardes R-6.5/7.3/7.4
et chaîne R-7.1), et l'adaptateur `catalogue → moteur` côté `apps/api`. Un marqueur de règle inconnu
ou un champ manquant **bloque** la carte au lieu d'être deviné.

## Livrables

- **Moteur** (`apps/game/src/pbm_game/`) :
  - `cartes/modele.py` — `DefinitionCarte`, `AttaqueDef`, stades (`base`/`stade1`/`stade2`),
    `definition_depuis_dict` ; validation (marqueur inconnu refusé, chaîne d'évolution, PV, type).
  - `cartes/transitions.py` — transitions `poser` (R-5.3, banc/actif, R-3.2/R-3.3) et `evoluer`
    (R-7.1 conserve énergies/Outil/compteurs, R-7.2 retire les états, chaîne par `nom_base`),
    enregistrées dans le `REGISTRE`.
  - `state/modele.py` — nouveau champ `Tour.evolues_ce_tour` (R-7.4) ; `SCHEMA_VERSION` 1 → 2 ;
    `serialisation.py` le sérialise/relit.
  - `tour/drapeaux.py` + `tour/contraintes.py` — `pokemon_evolue_ce_tour`/`marquer_evolution` ;
    `peut_evoluer` gagne R-7.4.
  - `journal/modele.py` — actions `poser`/`evoluer`, événements `pokemon_pose`/`evolution`.
- **Adaptateur** (`apps/api/src/pbm_api/jeu/catalogue.py`) — `definition_depuis_card` : lit
  `attacks`, `weaknesses`, `resistances`, `retreat_cost`, `prize_marker`, `stage`, `hp`, `type` ;
  bloque les champs manquants ; `apps/api` dépend désormais de `pbm-game` (chemin local, éditable).
- **Tests** : `docs/jeu/cas-executables/evolution.yaml` (6 cas), `apps/game/tests/test_cartes.py`
  (19 tests), `apps/api/tests/test_jeu_catalogue.py` (9 tests). `couverture-exceptions.yaml` :
  R-7.1 et R-7.4 retirés (désormais couverts par des cas exécutables), R-5.3 actualisé.
- **Doc** : `docs/jeu/CARTES.md`.

## Preuves (recette locale chimera, worktree `roadmap/j-cartes-pokemon`)

- `apps/game` : `uv run ruff check .` **OK** ; `uv run pytest -q` → **575 passed** (551 avant + 24).
- `apps/api` : `uv run ruff check src/pbm_api/jeu/ tests/test_jeu_catalogue.py` **OK** ;
  `uv run pytest -q tests/test_jeu_catalogue.py` → **9 passed** (pur, sans base).
- Les six cas d'évolution couvrent R-7.1 (conserve énergies+compteurs), R-7.2/R-11.9 (réveille le
  Sommeil), R-7.3 (interdite le tour de pose), R-7.4 (interdite deux fois), R-6.5 (interdite au
  premier tour), R-13.2 (K.O. défausse toute la pile). La CI GitHub (`game` + `api`) fait foi.

## Critères d'acceptation

- [x] **Aucune caractéristique de Pokémon n'est écrite en dur dans le moteur** — tout vient d'une
      `DefinitionCarte` fournie par le service ; `test_cartes.py` et `test_jeu_catalogue.py`.
- [x] **Une carte au marqueur de règle inconnu est refusée** avec un message clair, jamais jouée —
      `test_marqueur_de_regle_inconnu_refuse` (moteur et adaptateur).
- [x] **Les tests d'évolution couvrent les six cas** — `cas-executables/evolution.yaml`.

## Écarts au plan / décisions

- **R-7.4 modélisé par un champ d'état dédié** `Tour.evolues_ce_tour` (schéma 1 → 2), distinct de
  `entres_en_jeu_ce_tour` : une évolution n'interdit qu'une **seconde** évolution, pas l'attaque ni
  la retraite du tour. Choix fait pour que le refus cite la bonne règle (R-7.4 vs R-7.3).
- **Le générateur d'actions légales** (`actions_legales`) ne liste **pas encore** `poser`/`evoluer` :
  les énumérer demande de croiser la main avec le catalogue, ce que `actions_legales(etat, joueur)`
  ne reçoit pas — ce câblage relève du service de parties (`j-partie-service`). Les transitions et
  leur validation serveur sont livrées et testées ; `valider()` refuse encore ces coups en citant
  R-15.12 (non approximé, D9). **Reste à faire, nommé.**

## Reste à faire (hors périmètre, signalé)

- **Catalogue** : importer la chaîne d'évolution (`evolveFrom` TCGdex) et garantir la colonne
  `stage` sur toutes les bases — sans quoi l'adaptateur **bloque** (volontairement) les cartes
  d'évolution. Les cartes de base complètes se chargent déjà.
- **Générateur** : familles `FamillePoser` / `FamilleEvoluer` quand le service portera le catalogue.
- **release_prod** : aucun déploiement (la PROD se livre à part, par devAI).
