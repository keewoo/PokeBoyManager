# Compte rendu — `j-cartes-stades`

**Jalon J2 — Toutes les cartes du deck sont vraiment jouées.** Piste Effets & cartes, couloir
chimera (travail sur chimera, pilotage/CI/fusion depuis devAI).

## Résumé

Les **Stades** sont jouables de bout en bout : une **zone partagée** (déjà dans le modèle d'état),
une **règle de remplacement** (jouer un Stade défausse le précédent chez son propriétaire, un Stade
de même nom est refusé, un seul par tour), et des **effets continus symétriques** exprimés comme des
modificateurs *consultés au calcul* — donc retirés *par construction* au remplacement. Trois Stades
réels sont scriptés et testés, dont un qui modifie le **coût de retraite des deux camps**.

Le cadre d'effets continus livré par `j-cartes-talents` gérait déjà la zone Stade pour les dégâts et
les PV ; ce lot a ajouté le **coût de retraite** à ce cadre, la **transition `jouer_stade`** (+ son
drapeau de tour, sa contrainte, sa famille de coups), et les **cartes réelles**.

## Livrables

- **Transition `jouer_stade`** (`apps/game/src/pbm_game/effets/stades.py`) : zone partagée,
  remplacement R-3.5, défausse chez le propriétaire, drapeau `Tour.stade_joue` (R-5.5), événement
  `EVT_STADE_JOUE`. Enregistrée dans le `REGISTRE` du journal (import dans `pbm_game/__init__.py`).
- **Coût de retraite continu** (`effets/continus.py`) : champ `EffetContinu.cout_retraite`,
  `delta_cout_retraite`, `cout_retraite_effectif` (plancher à 0) ; câblé dans
  `FamilleRetraite.generer` via `CatalogueJeu.registre_continus` (vide par défaut, D9).
- **`DefinitionStade` + `FamilleJouerStade`** (`actions/familles_jeu.py`) : liste les Stades
  jouables, R-3.5 « même nom » autoritaire (via le catalogue, recalculé par `valider`).
- **Trois Stades réels** : Stade en Liesse (`sv08-180`, +30 PV aux Pokémon de base), Montagne
  Gravité (`sv08-177`, −30 PV aux Niveau 2), Hôtel « Au paradis des Pokémon » (`svp-224`, retraite
  des Psykokwak −1). Producteurs-fabriques liés à la métadonnée catalogue.
- **Drapeau de tour** `stade_joue` : modèle d'état, sérialisation (round-trip), `tour/drapeaux.py`,
  `tour/contraintes.py` (`peut_jouer_stade`).
- **Parité événements** : `EVT_STADE_JOUE` ajouté à `PROJECTEURS` (public) et au registre
  `TRADUCTEURS` du front (`apps/web/src/lib/game/journal.ts`), avec sa fixture de test.
- **Fiche** : `docs/jeu/STADES.md`. **Tests** : `apps/game/tests/test_cartes_stades.py` (11 tests).

## Preuves

- `uv run ruff check .` : **All checks passed** (apps/game).
- `uv run pytest -q` (apps/game) : **1033 passed** — dont les deux tests de parité
  (`test_parite_evenements_projecteurs`, `test_parite_journal_front`) et les 11 tests de
  `test_cartes_stades.py`.
- Critères d'acceptation :
  - *le retrait d'un Stade restaure exactement les calculs antérieurs* →
    `test_stade_en_liesse_donne_30_pv_aux_deux_camps_et_le_retrait_restaure_r35` (seuil de K.O.
    revient de 90 à 60 au remplacement).
  - *le Stade appartient à la partie, les deux camps en subissent les effets* → le même test
    (+30 PV pour les deux Actifs) et `test_stade_appartient_a_la_partie_le_remplacement_defausse_\
chez_le_proprietaire_r35`.
  - *trois Stades réels scriptés et testés* → tests dédiés pour Liesse, Montagne et Hôtel.
  - *Stade identique refusé* → `test_stade_de_meme_nom_refuse_a_la_liste_et_par_valider_r35`.
  - *Stade qui modifie le coût de retraite des deux camps* →
    `test_hotel_rend_la_retraite_moins_chere_dans_les_coups_legaux_des_deux_camps_r82`.
- CI GitHub Actions : voir la PR (elle fait foi).

## Écarts au plan

- **Les producteurs de Stade sont des fabriques liées à une métadonnée catalogue** (`ref →
  {stade, nom}`), car le moteur pur ne lit pas le catalogue (D9) et les conditions des cartes
  portent sur l'espèce / le stade. C'est le même branchement que les talents ; le service
  assemblera `CatalogueJeu.registre_continus` depuis les decks le jour où une partie réelle jouera
  ces cartes (hors périmètre de ce lot, comme pour `j-cartes-talents`).
- **R-3.5 « même nom »** : autoritaire au générateur (catalogue → noms, recalculé par `valider`) ;
  la transition ajoute un filet par **référence** (couvre le rejeu, où seuls des coups déjà validés
  reviennent).

## Reste à faire

- Câbler `registre_continus` dans le service de partie (apps/api) depuis les decks — lot ultérieur,
  aligné sur le câblage des Outils et talents.
- Front : rendu visuel de la zone Stade sur le plateau (le journal traduit déjà `stade_joue`).
