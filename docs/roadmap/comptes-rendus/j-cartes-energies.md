# Compte rendu — `j-cartes-energies`

**Lot** : Énergies : de base fournies, spéciales possédées · **jalon** J1 · **couloir** J-EFF (chimera)
**Machine** : pilotée depuis devAI, exécutée sur chimera (WSL Ubuntu-24.04, worktree `../wt-j-cartes-energies`).
**Statut** : livré (recette locale sur chimera verte ; CI GitHub fait foi).

## Résumé

Le moteur sait désormais traiter l'énergie **en jeu** comme une capacité générique, pas comme un
type figé, et payer un coût d'attaque en **expliquant la combinaison retenue**. Une grande part
de l'histoire « énergie » était déjà livrée par les lots précédents (voir « Écarts ») ; ce lot
apporte les deux pièces qui manquaient au moteur et branche les effets d'énergie spéciale sur la
pile d'effets.

## Livrables

- **Fourniture d'énergie générique** — `pbm_game.cartes.energie.DefinitionEnergie` : une carte
  Énergie *fournit* `{type: unités}` (Énergie de base `{"feu":1}`, Double Énergie Incolore
  `{"incolore":2}`, spéciale bi-type `{"feu":1,"eau":1}`, spéciale mono-type). Fourniture vide ou
  malformée refusée (D9). `definition_energie_depuis_dict` pour l'alimentation par le service.
- **Paiement de coût expliqué** — `pbm_game.combat.cout.payer_cout` → `PaiementCout` : trouve une
  combinaison valide (colorés d'abord par type exact, incolores ensuite par n'importe quelle
  unité), la décrit (`Affectation` : quel symbole payé par quelle énergie) et la rend lisible
  (`detail`), journalisable via `EVT_COUT_PAYE`. `cout_satisfait` inchangé (verdict partagé).
- **Effets d'énergie spéciale sur la pile** — `DefinitionEnergie.effets_en_attente(instance_id)`
  produit des `EffetEnAttente` empilables (`pbm_game.effets.pile`), attribués à l'énergie comme
  source ; le résolveur de chaque effet reste à la charge des lots d'effets (D9).
- **Doc** : `docs/jeu/ENERGIES.md` (nouvelle fiche mécanique).
- **Tests** : `apps/game/tests/test_cartes_energies.py` (18 tests).

## Preuves

- Recette locale chimera : `apps/game` → `uv run ruff check .` + `uv run pytest -q` **verts**
  (détail dans le journal du lot). Commit : voir branche `roadmap/j-cartes-energies`.
- Critère « le paiement trouve une combinaison et l'explique » :
  `test_paiement_trouve_une_combinaison_et_la_nomme_r92`,
  `test_cout_mixte_paye_par_une_double_energie_incolore_r92`,
  `test_evenement_cout_paye_porte_le_detail_et_la_combinaison`.
- Critère « une unité incolore ne paie jamais un symbole coloré » (piège combinatoire) :
  `test_unite_incolore_ne_paie_jamais_un_symbole_colore_r92`.
- Critère « énergies de base jamais dans le décompte de la collection » (D10) :
  `apps/api/tests/test_deck_legality.py::test_basic_energy_exempt_from_ownership` et
  `::test_basic_energy_exempt_from_four_copy` (déjà livré par `v7-decks-api`/`v7-decks-legalite`).
- Critère « énergies spéciales soumises à la règle des 4, vérifié avec le service de légalité » :
  `apps/api/tests/test_deck_legality.py::test_four_copy_rule_applies_to_non_basic` et
  `::test_special_energy_requires_ownership`.
- Défausse d'énergie à la retraite (R-8.2) :
  `apps/game/tests/test_retraite_banc.py::test_retraite_defausse_les_energies_choisies_et_echange_lactif_r82`
  (déjà livré par `j-retraite-banc`).

## Écarts au plan

- **Les critères d'acceptation 2 et 3 (décompte collection, règle des 4) étaient déjà
  implémentés** par le service de légalité des decks (`apps/api/decks/{energy,legality}.py`,
  lots `v7-decks-api`/`v7-decks-legalite`) et déjà testés. Ce lot les **vérifie** et les cite,
  sans les réécrire — une seule source de vérité pour la légalité (pas deux logiques divergentes).
- De même, la **défausse d'énergie à la retraite** et la **vérification de faisabilité d'un
  coût** (`cout_satisfait`, multi-unités, bi-type, incolore) préexistaient (`j-retraite-banc`,
  `j-degats-resolution`). L'apport propre du lot est : la fourniture **générique** côté carte, le
  paiement **expliqué** (combinaison + journal), et le branchement des **effets** sur la pile.
- **Modèle de fourniture** : additif `{type: unités}`, fidèle au corpus (R-9.2, « on compte les
  unités fournies »). Les énergies « 1 unité au choix parmi plusieurs types » (type Arc-en-ciel)
  ne sont pas modélisées — aucune règle du corpus ni carte scriptée ne les introduit au J1 ; les
  ajouter serait anticiper un besoin inexistant (D9). Documenté dans `docs/jeu/ENERGIES.md`.

## Reste à faire (hors périmètre de ce lot)

- Câbler `payer_cout` dans la **déclaration d'attaque** (lot `j-cartes-attaques`) pour émettre
  `EVT_COUT_PAYE` dans le journal de partie réel.
- Scripter les **résolveurs** d'effets d'énergie spéciale (soin, dégâts supplémentaires, coût de
  retraite modifié) dans les lots d'effets, chacun testé (D9).
- Dériver les `EnergieAttachee` depuis les `Carte` d'énergie attachées via le catalogue
  (adaptateur côté `apps/api`), quand l'attache d'énergie sera jouable (`j-cartes-pokemon`).
