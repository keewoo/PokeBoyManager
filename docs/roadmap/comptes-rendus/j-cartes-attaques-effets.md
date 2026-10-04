# Compte rendu — `j-cartes-attaques-effets`

**Lot** : Attaques à effet (pile ou face, dégâts variables, blocages, états infligés) — jalon J2,
piste Effets & cartes, couloir chimera.
**Machine** : construit et testé sur **chimera** (WSL Ubuntu-24.04), piloté depuis devAI.

## Résumé

Les attaques à effet sont désormais **câblées** : une attaque qui porte un script DSL (ou des
dégâts variables) n'est plus refusée — elle se résout. Le script s'exécute **entre `avant_degats`
et `apres_degats`** (il peut poser un état, blesser le banc, se blesser, poser un verrou, ou
**annuler** les dégâts), puis les dégâts principaux sont posés sur l'Actif adverse (faiblesse /
résistance appliquées). Les familles demandées sont scriptées et testées contre des cartes
construites pour le lot, et la CI du dépôt fait foi (937 tests du moteur verts ici).

## Livrables

- **Câblage du script d'attaque** — `apps/game/src/pbm_game/combat/attaque.py` :
  `resoudre_attaque_declaree` consomme un `script` (DSL) et/ou des dégâts variables, exécute le
  script, fusionne les verrous posés dans `etat.verrous`, respecte le drapeau « dégâts annulés »,
  puis pose les dégâts principaux et résout les K.O. (y compris auto-dégâts et dégâts au banc).
- **Dégâts variables** — nouveau module pur `apps/game/src/pbm_game/combat/valeur.py`
  (`ValeurDynamique`) : `max(0, base + par × compte)`, borné par `plafond`, calculé **à la
  résolution**. Compteurs : énergies attachées, cartes en main, PV manquants, compteurs posés,
  récompenses restantes, Pokémon de banc.
- **Blocage du tour suivant** — `EtatPartie.verrous` (champ **rétro-compatible**, ne bump pas la
  version de schéma) + sérialisation (`JeuDeVerrous.en_json/depuis_json`, `Verrou.depuis_json`) +
  expiration **orientée par le propriétaire** au Pokémon Checkup (`JeuDeVerrous.
  expirer_au_checkup_oriente`, câblée dans `checkup/resolution.py`, R-12.5) + garde côté
  `declarer_attaque` qui refuse l'attaque **en nommant la carte** (R-5.7).
- **DSL** : `pile_ou_face` « jusqu'à échec » (champ `jusqu_a_echec`), condition `type_cible` (effet
  conditionné au type de la cible, lue dans les métadonnées de catalogue), défausse d'énergie en
  coût (`deplacer` vers la zone `defausse`). Vocabulaire, chargement **strict**, schéma JSON et
  interprète mis à jour de concert ; le test de non-divergence schéma ↔ validateur reste vert.
- **Catalogue** : `AttaqueDef` porte `script` et `degats_variables` (validés **à la construction**
  — un script incohérent bloque la carte, D9), round-trip JSON ; `FamilleAttaquer` liste les
  attaques scriptées et transporte script, dégâts (secs ou variables) et métadonnées dans l'action.
- **Tests** : `apps/game/tests/test_cartes_attaques_effets.py` (25 tests) + docs/jeu.

## Preuves

- `uv run ruff check .` (apps/game) : **All checks passed!**
- `uv run pytest -q` (apps/game) : **937 passed** (dont les 25 nouveaux).
- Le test qui **mord sans le lot** : `test_une_attaque_scriptee_resout_son_effet` (avant,
  l'attaque à effet levait R-15.12/D9 ; après, elle se résout).
- Familles couvertes par des tests : dégâts variables (3 compteurs : énergies, cartes en main,
  compteurs posés), calcul **à la résolution** (défausse après le calcul), dégâts au banc,
  auto-dégâts (**KO**), soins, états spéciaux (empoisonné / endormi / confus), pile ou face (une,
  plusieurs, **jusqu'à échec**) **rejouables depuis la graine**, effet conditionné au type de la
  cible, blocage du prochain tour (pose, refus nommé, **expiration au bon Checkup avec sa ligne de
  journal**), sérialisation des verrous (reprise après F5).

## Écarts au plan / décisions prises (à relire par JF)

- **Dégâts variables au niveau de l'attaque, pas du `nombre` générique du DSL.** La base variable
  (vers l'Actif adverse, avec faiblesse/résistance) est portée par le champ `degats` de l'attaque
  (entier **ou** formule) et évaluée dans `combat.attaque`. Cela réutilise `resoudre_degats`
  (ordre R-10) et évite d'étendre le `nombre` de chaque primitive (donc le schéma, la parité et la
  couverture des 500 textes restent intacts). Conséquence : une attaque dont les **dégâts au banc**
  seraient eux-mêmes variables n'est pas couverte en v1 (les dégâts d'effet du script restent à
  valeur fixe) — à ajouter si une carte réelle l'exige.
- **`EtatPartie.verrous` ne bump pas `SCHEMA_VERSION`** (laissé à 4), à dessein : le champ est
  **rétro-compatible** (absent = aucun verrou), donc une partie en cours sérialisée en base reste
  lisible sans migration — on ne casse pas les parties vivantes en PROD. La convention « un champ =
  un bump » est donc volontairement écartée ici ; un futur changement réellement incompatible, lui,
  incrémentera la version. **Point à valider par JF.**
- **Ordre** : le script d'effet s'exécute **avant** la pose des dégâts principaux (un `annuler` ou
  un « si pile, ne fait rien » doit pouvoir supprimer les dégâts) ; la base variable, elle, est
  calculée **avant** le script (donc avant une défausse d'énergie en effet) — c'est le piège nommé
  par la fiche, couvert par un test dédié.

## Reste à faire

- **Couverture « ≥ 3 cartes réelles par famille »** : les familles sont scriptées et testées, mais
  avec des cartes **construites pour le lot** (le catalogue ne porte pas encore les scripts). Le
  branchement texte→script du vrai catalogue est le lot `j-effets-catalogue-compilation` ; 3 vraies
  cartes par famille y seront gelées.
- Dégâts d'effet (banc / auto) **variables** si une carte réelle le réclame (voir écarts).
- Livraison PROD : hors périmètre de ce lot (la PROD se livre à part, par devAI).
