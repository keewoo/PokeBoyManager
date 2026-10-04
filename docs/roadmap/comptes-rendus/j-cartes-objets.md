# Compte rendu — `j-cartes-objets`

**Lot** : Cartes Objet, dont les appâts qui forcent l'échange de l'actif adverse · piste Effets &
cartes · jalon J2 · couloir J-EFF (chimera) · P0.

**Machine** : exécuté sur **chimera** (WSL Ubuntu-24.04), piloté depuis **devAI**. Worktree
`~/dev/wt-j-cartes-objets`, branche `roadmap/j-cartes-objets` depuis `github/main`.

## Résumé

Les cartes **Objet** sont désormais jouables, scriptées dans le langage d'effets — aucune ne
demande de code spécifique (D9). Cinq familles sont couvertes avec **trois cartes réelles chacune**
(recherche, pioche, soin, changement d'Actif de son côté, appât). L'**appât** (forcer l'Actif
adverse à changer) est traité comme un **échange forcé** (R-8.8) : sans coût, sans consommer la
retraite du tour, autorisé même sous Sommeil/Paralysie (R-16.12), avec nettoyage de l'Actif qui
descend (R-8.6). Le **passage par le bus** réclamé par la fiche est en place et testé : un appât
note le Pokémon qui monte au front, et `publier_devient_actif` réveille les déclencheurs « quand ce
Pokémon devient Actif… ». Un Objet **sans cible valide n'est pas jouable**, et le refus cite la
raison ; un Objet joué **pendant une demande de décision est refusé** (garde centrale d'`appliquer`).

Tout le travail vit dans le **moteur pur `pbm_game`** (plus un traducteur de journal côté `apps/web`)
— aucune base, aucun service touché : testable par le job CI `game` seul.

## Livrables

- **DSL / appât** : `changer_actif` nettoie l'Actif qui descend (R-8.6, porte partagée
  `soigner_etats_speciaux`) et **note** chaque passage dans `ResultatProgramme.devenus_actifs`
  (`effets/dsl/primitives.py`, `execution.py`, `interprete.py`).
- **Bus** : `pbm_game.effets.bus.publier_devient_actif` publie `EJ_DEVIENT_ACTIF` et résout la pile
  des réactions.
- **Jouabilité** : `pbm_game.effets.dsl.jouabilite.programme_jouable` (statique, pur) + `cout_payable`
  exposé par l'interprète (une seule porte, partagée avec la transition).
- **Jouer un Objet** : action `jouer_objet` (`effets/objets.py`, enregistrée au `REGISTRE`),
  `FamilleJouerObjet` + `DefinitionObjet` + `CatalogueJeu.objets` (`actions/familles_jeu.py`),
  événement `EVT_OBJET_JOUE` + son projecteur public + son traducteur front.
- **Cartes réelles scriptées** (15) : Great/Ultra/Quick Ball ; Bicycle/Acro Bike/Roller Skates ;
  Potion/Moomoo Milk/Full Heal ; Switch/Switch Cart/Escape Rope ; Gust of Wind/Pokémon
  Catcher/Pokémon Reversal.
- **Doc** : `docs/jeu/CARTES-OBJETS.md`.
- **Tests** : `apps/game/tests/test_cartes_objets.py` (29 cas), `test_effets_devient_actif.py` (4 cas).

## Preuves

- Suite `game` complète sur chimera : **969 passed**, `ruff check .` → **All checks passed**
  (`uv run pytest -q`, `uv run ruff check .`, apps/game, Python 3.12). La CI GitHub fait foi.
- Critères d'acceptation :
  - *l'appât change l'Actif adverse sans retraite ni énergie* →
    `test_appat_ne_consomme_pas_la_retraite_du_tour`, `test_appat_nettoie_le_descendant_et_marche_sous_sommeil`
    (l'Actif descendu garde ses énergies, l'échange marche Endormi) ;
  - *chaque famille a ≥ 3 cartes réelles scriptées et testées* →
    `test_chaque_famille_a_trois_cartes_chargeables` + un test de comportement par carte ;
  - *un Objet sans cible valide n'est pas jouable, et la raison s'affiche* →
    `test_objet_sans_cible_non_liste_et_refus_motive`, `test_programme_jouable_appat_banc_vide_refuse_avec_raison`.
- Tests de la fiche :
  - appât sur banc vide → `test_appat_banc_vide_ne_fait_rien_et_le_dit` (`EVT_EFFET_SANS_CIBLE`) ;
  - appât suivi d'une attaque → `test_appat_puis_attaque_frappe_le_nouvel_actif` ;
  - Objet joué pendant une demande → `test_jouer_objet_refuse_pendant_une_demande`,
    `test_objet_non_liste_pendant_une_demande`.
- Passage par le bus → `test_publier_devient_actif_reveille_les_reacteurs` (un réacteur abonné à
  `EJ_DEVIENT_ACTIF` empile son effet, la pile se résout).
- Le test qui **mord sans le changement** : `test_appat_nettoie_le_descendant_*` (avant ce lot,
  `changer_actif` ne nettoyait pas le descendant et ne notait aucun passage) ; la parité
  projecteurs/traducteurs casse si `EVT_OBJET_JOUE` n'est pas déclaré.

## Écarts au plan

- **Déplacement d'énergie** et **retrait d'outil** ne sont **pas** revendiqués comme familles : un
  seul Objet courant (*Energy Switch*) se met proprement dans la première, et le vocabulaire fermé
  n'a pas de primitive pour retirer un Outil attaché (D9 — on ne l'approxime pas). À traiter dans un
  lot ultérieur (ajout de primitive). Les six familles cleanement exprimables sont couvertes.
- Le **câblage service du bus** (`bus → appliquer` pour rejouer les réactions `devient_actif`
  pendant le replay) et l'injection d'une `strategie_demande` dans `jouer_objet` (pour que le choix
  de la cible d'un appât devienne une vraie demande) restent à faire côté `apps/api` — cohérent avec
  l'état actuel du dépôt, où le bus n'est branché que via les fenêtres de la machine à tour et où le
  DSL n'est pas encore câblé dans le service HTTP. Le **mécanisme et ses tests existent** : le risque
  nommé par la fiche (« déclencheurs oubliés ») est traité par conception, pas reporté.

## Reste à faire

- Lot ultérieur : primitive de retrait d'Outil, famille déplacement d'énergie à ≥ 3 cartes.
- Côté service (`apps/api`) : alimenter `CatalogueJeu.objets` depuis `card_scripts`, brancher
  `publier_devient_actif` dans l'orchestrateur après `jouer_objet`, injecter la demande de décision.
- Semis des 15 scripts d'Objet dans le registre `card_scripts` (commande `scripts_effets.py importer`).
