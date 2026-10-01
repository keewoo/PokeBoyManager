# Compte rendu — `j-effets-architecture`

**Pile d'effets et déclencheurs : l'architecture qui accueille toutes les cartes** · jalon J2 ·
piste Effets & cartes · exécuté sur **chimera** (WSL Ubuntu-24.04), piloté depuis **devAI**.

## Résumé

Livré le **cadre d'effets** du moteur de jeu : le paquet pur `pbm_game.effets`, qui porte le
*bus d'événements*, la *pile d'effets* (LIFO + interruptions), les *effets continus* (des
modificateurs dérivés, jamais des mutations) et les *verrous nommés* (avec portées et
expiration). Il se **branche sur les points d'accroche existants du socle** (les fenêtres de
`pbm_game.tour.fenetres` et les listes de modificateurs de `pbm_game.combat`) **sans en modifier
une ligne** — critère d'acceptation n°4 vérifié par `git diff` (aucun fichier du socle touché)
et par un test (`test_importer_effets_ne_modifie_pas_le_socle`).

Aucune carte n'est scriptée (D9) : c'est le rôle des lots que celui-ci débloque
(`j-effets-dsl`, `j-cartes-outils`, `j-cartes-stades`, `j-cartes-talents`,
`j-cartes-attaques-effets`). Les registres (`RegistreEffets`, `RegistreContinus`, `Bus`,
`DECLENCHEURS`) sont **vides par défaut** : importer le paquet laisse le comportement du socle
strictement inchangé.

## Livrables

- `apps/game/src/pbm_game/effets/` — le paquet (6 modules) :
  - `evenements.py` — les **onze moments de jeu** (`EvenementJeu`, `EVENEMENTS_JEU`), liste
    fermée (D9), + les quatre mécanismes (déclenché / continu / activé / attaque) ;
  - `pile.py` — `PileEffets`, `resoudre_pile` (LIFO, interruptions, garde anti-boucle), chaque
    résolution journalisée avec sa **source** (`EVT_EFFET_RESOLU`) ; effet sans cible journalisé
    (`EVT_EFFET_SANS_CIBLE`), jamais muet ; type inconnu refusé (D9) ;
  - `continus.py` — `EffetContinu`, `collecter_effets_continus` (dérive les modificateurs de ce
    qui est en jeu), `modificateurs_degats`, `seuil_ko` (PV continus → seuil de K.O.) ;
  - `verrous.py` — `Verrou`, `JeuDeVerrous` (poser / est_verrouille / source_du_verrou /
    expirer_au_checkup / retirer_sources_absentes), les trois verrous de la fiche + `pas_de_retraite` ;
  - `bus.py` — `Bus` (réacteurs par événement) et `declencheur_fenetre`, **le pont** vers le socle ;
  - `__init__.py` — API publique, sans effet de bord à l'import.
- `docs/jeu/EFFETS.md` — l'architecture + **trois exemples de bout en bout** (Outil continu,
  talent déclenché via bus/pile, verrou posé/refusé/expiré) + l'étude des 200 cartes.
- `apps/game/tools/classer_echantillon.py` — l'outil d'étude (hors paquet pur) + échantillon gelé
  `apps/game/tests/donnees/echantillon_200_effets.json`.
- 7 fichiers de tests (`apps/game/tests/test_effets_*.py`).

## Preuves

- **Tests** : `uv run pytest -q` sur `apps/game` → **614 passés** (dont 7 suites d'effets neuves,
  toutes échouant sans le changement). `uv run ruff check .` → clean.
- **Critère n°1** (200 cartes exprimables sans nouvel événement) : échantillon **déterministe**
  de 200 cartes porteuses d'effet du catalogue de référence, classé → **0 déclencheur non
  reconnu**. Moments déclenchés observés dans les talents : `pose`, `evolution`,
  `attachement_energie` ; mécanismes : 188 attaque, 23 activé, 14 continu, 8 déclenché. Vérifié
  en CI sans la base par `test_effets_echantillon` (sa dent : échec si un déclencheur sort du
  vocabulaire). `devient_actif` ajouté au vocabulaire (réclamé par `j-cartes-objets`), étude
  refaite — comme le prévoit le critère.
- **Critère n°2** (retrait d'un effet continu restaure le calcul) :
  `test_retrait_d_un_outil_restaure_exactement_le_calcul_r37` (50→70 avec Outil, 50 sans),
  `test_remplacement_d_un_stade_restaure_le_calcul_r35`, et le seuil de K.O. qui redescend au
  retrait d'un Outil de PV (`…abaisse_le_seuil_de_ko_r131`). Vrai **par construction** (dérivation).
- **Critère n°3** (chaque résolution journalisée avec sa source) :
  `test_chaque_resolution_est_journalisee_avec_sa_source` (`EVT_EFFET_RESOLU` porte la source).
- **Critère n°4** (socle non modifié) : `git diff` ne touche aucun fichier de
  `pbm_game/{tour,combat,journal,state,checkup,…}` ; branchement prouvé par injection dans
  `declencher(..., declencheurs=…)` et `resoudre_checkup(..., declencheurs=…)` — les points que le
  socle expose déjà (`test_le_bus_se_branche_sur_la_fenetre_fin_de_tour_du_socle`,
  `…sur_l_expiration_du_checkup`). Le moteur reste **pur** (test statique `rglob` du corpus +
  `test_import_effets_ne_tire_aucune_dependance_lourde`).

## Écarts au plan

- **Le catalogue ne porte pas le texte d'effet des Dresseurs ni des Énergies** (2766 des 2873
  Dresseurs ont `abilities`/`attacks` vides). Les moments `ko`, `avant_degats`, `apres_degats`,
  `pioche`, `debut_tour`, `fin_tour`, `entre_tours` sont donc justifiés par la liste explicite de
  la fiche et le corpus de règles (R-10/R-12.3/R-13.1), non par ce texte absent. Écart **réel,
  consigné** (EFFETS.md), à combler par `j-effets-catalogue-compilation` ; voir
  `docs/catalogue/COMPLETUDE.md`.
- La **publication** des événements de dégâts/pose/K.O. dans le socle n'est **pas** câblée (ce
  serait le modifier, interdit par le critère n°4) : chaque lot de résolution publiera sur le bus
  au bon endroit. Le cadre est livré et testé par injection.
- **Anomalie rencontrée dans le worktree, sans rapport avec ce lot** : à la création du worktree
  (depuis `github/main` @ 8d9916a), `apps/api/src/pbm_api/catalog/prize_marker.py` et son test
  apparaissaient **modifiés** (le correctif `fix-marqueur-stades` du 02/10 retiré du working
  tree). Mon travail ne touche pas `apps/api`. Ces deux fichiers ont été **restaurés à HEAD**
  (`git checkout --`) pour ne pas risquer d'emporter cette régression ; seuls mes fichiers ont
  été commités. À signaler à JF : cause non élucidée.

## Reste à faire

- `j-effets-dsl` : l'interpréteur de primitives au-dessus de la pile.
- `j-effets-choix` : suspendre un effet dans l'état (la pile est déjà sérialisable pour cela).
- Les lots de cartes : enregistrer leurs producteurs/résolveurs/réacteurs dans les registres vides.
- Câbler la publication des événements (dégâts, pose, évolution, K.O., attachement, pioche) dans
  les lots de résolution correspondants.
