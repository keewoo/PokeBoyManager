# Compte rendu — `j-effets-dsl`

**Lot** : Langage d'effets — décrire ce qu'une carte fait, sans code par carte.
**Jalon** : J2 (toutes les cartes du deck vraiment jouées). **Piste** : Effets & cartes.
**Machine** : travail sur **chimera** (WSL Ubuntu-24.04), pilotage depuis **devAI**.

## Résumé

Livré un **langage déclaratif d'effets** (`pbm_game.effets.dsl`), pur, posé **au-dessus de la pile
d'effets** livrée par `j-effets-architecture`. Un script d'effet est une donnée JSON (version +
coût + liste d'instructions), **validée au chargement** par un schéma, **sérialisable** et
**rejouable**. 18 primitives + 2 structures de contrôle + sélecteurs + conditions, dégagées d'un
**dépouillement de 500 textes réels** du catalogue. **Aucune primitive « code libre »** (D9).

## Livrables

- **Vocabulaire fermé** : `src/pbm_game/effets/dsl/vocabulaire.py` — source unique des primitives,
  zones, propriétaires, catégories, positions, conditions, et de la version du langage.
- **Modèle** : `modele.py` (`Programme`, `Instruction`, `Selecteur`, `Condition`, figés, sérialisables).
- **Chargement validant** : `chargement.py` (`charger_programme` → `ProgrammeInvalide`), strict,
  versionné (refuse une version future, garde la lecture des versions passées).
- **Schéma JSON** formel (Draft 2020-12) : `schema.json` — spécification publiée, vérifiée en CI
  contre le validateur Python (test de non-divergence).
- **Sélection** : `selection.py` (résolution des sélecteurs, filtres via métadonnées de catalogue).
- **Contexte & exécution** : `contexte.py`, `execution.py` (stratégie de choix injectable, défaut
  déterministe).
- **Primitives** : `primitives.py` — une fonction pure par verbe, cas « aucune cible » partout.
- **Interprète** : `interprete.py` — flux de contrôle (`si`, `repeter`, `pile_ou_face`, `choisir`),
  coût atomique, et **pont vers la pile** (`compiler_en_effet`, `resolveur_dsl`, `registre_dsl`).
- **Outils d'étude** : `tools/extraire_effets_dsl.sql`, `tools/classer_dsl.py`.
- **Échantillon gelé** : `tests/donnees/echantillon_500_dsl.json` (500 cartes, couverture 94,8 %).
- **Doc** : `docs/jeu/DSL.md` (chaque primitive, ses paramètres, un exemple de carte réelle).
- **Tests** : 7 suites (`test_dsl_chargement`, `_selection`, `_primitives`, `_interprete`,
  `_couverture`, `_schema_json`, `_purete`) + fabrique `fabrique_dsl.py`.

## Critères d'acceptation — preuves

1. **≥ 80 % des 500 textes couverts, sans primitive « code libre »** → ✅ **couverture mesurée
   94,8 %** (474/500), gelée et vérifiée en CI (`test_dsl_couverture`). Histogramme : les 18
   primitives sont toutes exercées par des cartes réelles. Les 26 non couvertes sont listées
   (énergies spéciales, « votre tour ne se termine pas », dés-évolution, modificateurs de
   Faiblesse) — honnêtement hors v1, jamais approximées.
2. **Chaque primitive a ses tests unitaires, y compris « aucune cible »** → ✅ `test_dsl_primitives`
   : pour chaque primitive, un test « elle agit » + un test « cible vide → `effet_sans_cible` »,
   sans blocage de la partie.
3. **Un script non conforme est refusé au chargement, pas en pleine partie** → ✅
   `test_dsl_chargement` (op inconnu, clé parasite, zone/état/verrou inconnus, cible/nombre requis,
   dégâts non multiples de 10, `si` sans condition…) + `test_dsl_schema_json` (schéma et validateur
   d'accord).
4. **Le langage est versionné** → ✅ `version` obligatoire, version future refusée, aller-retour
   JSON stable (`test_dsl_chargement::test_aller_retour_json_est_stable`).

## Preuves d'exécution (chimera)

- `uv run ruff check .` → **All checks passed!**
- `uv run pytest -q` → **751 passed in ~14 s** (dont ~80 tests DSL ; aucune régression sur les 670
  tests du moteur existant).
- Moteur **pur** : `test_dsl_purete` prouve que l'import du DSL ne tire aucune dépendance lourde et
  **ne modifie pas** le socle (`REGISTRE`/`DECLENCHEURS` intacts) ; `dependencies = []` reste vrai
  (jsonschema est en groupe **dev** uniquement, pour tester le schéma publié).

## Écarts / limites assumées (D9, jamais masquées)

- **Choix d'un joueur** : la stratégie par défaut est déterministe ; la vraie demande de décision
  (suspension) est le lot `j-effets-choix`. La primitive `choisir` est implémentée ; seule la
  *politique* est branchable.
- **Verrous via la pile** : `resolveur_dsl` trace `verrou_pose` mais ne rend pas le `JeuDeVerrous`
  (hors `EtatPartie` — hors périmètre) ; un script posant un verrou s'exécute par
  `executer_programme`, qui le rend.
- **`deplacer`** v1 déplace des énergies (pas des compteurs de dégâts) ; filtres `categorie`/`stade`
  exigent les métadonnées de catalogue (sinon la carte n'est pas retenue, jamais devinée).
- 26/500 textes non couverts — nommés dans le fichier gelé, à reprendre par les lots de cartes.

## Reste à faire (hors lot)

Lots débloqués : `j-cartes-attaques-effets`, `j-cartes-regles-speciales`,
`j-effets-catalogue-compilation`, `j-effets-choix`, `j-simulation-bots`. Le savoir durable est dans
`docs/jeu/DSL.md`.
