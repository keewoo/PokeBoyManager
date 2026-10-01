# Compte rendu — `j-machine-tour`

**Lot** : Déroulé d'un tour — phases, contraintes du tour, et fin de tour.
**Piste** : Règles & moteur (couloir J-MOT, devAI) · **Jalon** J1 · P0 · palier 5.
**Branche** : `roadmap/j-machine-tour` · **Machine** : devAI (worktree `../wt-j-machine-tour`).

## Résumé

Livré le **squelette du déroulé d'un tour** du moteur `pbm_game`, en Python pur (aucune E/S,
ni HTTP, ni base, ni React). Sans lui les actions existaient mais aucune ne savait *quand*
elle avait le droit de survenir ; désormais la machine enchaîne les phases, tient les
drapeaux « une fois par tour », traite la pioche impossible comme une **défaite** (et non une
exception), et ouvre les **fenêtres de déclenchement** où la pile d'effets se branchera plus
tard. Tout est porté par l'état (`Tour`, figé et sérialisable), donc **repris après un F5**.

Conformément à **D9**, le lot ne mécanise que ce qui ne demande **aucune** donnée de carte :
le déroulé pioche → principale → attaque → checkup, la fin de tour, et les six contraintes.
Le coût d'énergie, les dégâts, la faiblesse/résistance, le coût de retraite restent aux lots
de résolution — `declarer_attaque` ne porte donc **que** l'effet « termine le tour » (R-5.8),
et n'est volontairement pas encore un coup *listé* par le générateur.

Le serveur tient les contraintes **seul** (risque nommé par la mission) : les gardes sont des
fonctions pures du moteur, pas des règles d'interface.

## Livrables

- **Paquet `pbm_game.tour`** (`apps/game/src/pbm_game/tour/`) :
  - `drapeaux.py` — prédicats bruts (« énergie posée ? », « premier tour ? », « entré en jeu
    ce tour ? ») et marqueurs qui lèvent un drapeau en renvoyant un nouveau `Tour`. **Sans
    dépendance à `pbm_game.actions`** pour que `journal.transitions` l'importe sans cycle.
  - `contraintes.py` — les **six contraintes** en `Verdict` motivés (règle citée).
  - `fenetres.py` — `declencher()` et les fenêtres `début de tour` / `fin de tour`
    (`DECLENCHEURS` **vide au jalon J1**, mais câblé ; fenêtre inconnue → `ValueError`).
  - `__init__.py` — API publique (fenêtres + drapeaux ; `contraintes` s'importe de son
    sous-module, pour éviter le cycle avec le générateur).
- **Transitions journalisées** (`journal/transitions.py`) :
  - `debut_tour` (système) — pioche obligatoire (R-5.2) ; **pioche vide = défaite** (R-14.2) ;
    fenêtre « début de tour » ; passage en phase principale.
  - `declarer_attaque` — **termine le tour même sans dégât** (R-5.7/5.8) → Checkup + fenêtre
    « fin de tour ». Gardes serveur : joueur actif (R-5.7), phase, R-6.1, Actif présent (R-9.1).
  - `avancer_phase` — l'entrée en Checkup ouvre désormais la fenêtre « fin de tour » ; le
    passage de tour remet drapeaux **et** « entrés en jeu ce tour » à zéro (`Tour` neuf).
- **État** : champ `Tour.entres_en_jeu_ce_tour` (R-7.3) + sérialisation (rétrocompatible, pas
  de `schema_version` incrémentée : un ancien JSON se relit avec un ensemble vide).
- **Constantes** : `ACTION_DEBUT_TOUR`, `ACTION_DECLARER_ATTAQUE`, `EVT_ATTAQUE_DECLAREE`,
  `RAISON_PIOCHE_IMPOSSIBLE` (exportées par `pbm_game.journal`).
- **Générateur** : `avancer_phase` n'est plus proposé pendant la pioche (R-5.2) ; `debut_tour`
  refusé à un joueur (R-5.2) ; `declarer_attaque` refusé comme non encore scripté (D9/R-15.12).
- **Tests** : `apps/game/tests/test_machine_tour.py` (26 cas).
- **Docs** : `docs/jeu/MACHINE-TOUR.md` (nouvelle fiche), `docs/jeu/ACTIONS.md` et
  `docs/jeu/ETAT.md` mis à jour.

## Preuves

- **Suite moteur verte** : `uv run pytest -q` (apps/game) → **136 passés** (110 existants + 26
  nouveaux), `uv run ruff check .` → **All checks passed!**. Python 3.12.
- **Les six contraintes, dans les deux sens, motivées** (`test_contrainte_1..6`) : chaque
  refus cite sa règle — R-5.4 (énergie), R-5.5/R-6.2 (Supporter), R-5.6 (retraite), R-7.3
  (entré ce tour), R-6.5 (premier tour), R-6.1 (attaque premier tour) — et
  `test_chaque_refus_de_contrainte_cite_une_regle_du_corpus` vérifie que chaque `R-x.y` cité
  **existe** dans `docs/jeu/REGLES.md`.
- **Drapeaux + « entrés en jeu » survivent à la reprise** :
  `test_drapeaux_survivent_a_une_serialisation_reprise` (round-trip état → JSON texte → état,
  égalité exacte) et `test_entres_en_jeu_ce_tour_defaut_vide_et_retrocompatible`.
- **Attaque sans dégât termine le tour** : `test_declarer_attaque_termine_le_tour_sans_degat_r58`
  (phase → Checkup, `degats == 0`, compteurs de l'adversaire inchangés, invariants sains).
- **Pioche impossible = défaite** : `test_debut_tour_pioche_impossible_est_une_defaite_r142`
  (partie figée, vainqueur = adversaire, raison `pioche_impossible`, phase non avancée).
- **Fenêtres câblées** : vides → aucun événement mais existent ; inconnue → lève ; un
  déclencheur jouet injecté produit bien son effet (preuve que le mécanisme n'est pas mort).
- **Le test mord** : mutation volontaire de `peut_attacher_energie` (ne jamais refuser) →
  `test_contrainte_1` échoue ; correctif restauré → repasse (règle du 2026-08-18).
- **Déroulé complet** : `test_deroule_complet_d_un_tour_de_bout_en_bout` enchaîne début →
  principale → attaque → Checkup → tour suivant (adversaire, drapeaux à zéro).

## Critères d'acceptation

- [x] Les six contraintes de tour testées dans les deux sens (autorisé / refusé motivé).
- [x] Les drapeaux énergie / Supporter / retraite survivent à une sérialisation / reprise.
- [x] Déclarer une attaque termine le tour même si l'attaque n'inflige aucun dégât.

## Écarts au plan

- **Ordre des lots.** `j-actions-legales` était déjà fusionné dans `main` alors que la fiche
  le donne *après* `j-machine-tour`. `suivi.py verifier j-machine-tour` rend **code 0** (ordre
  tenu) : le lot a donc été mené. La seule conséquence est que ce lot **affine** la famille
  `FamilleAvancerPhase` déjà livrée (elle ne propose plus « avancer » pendant la pioche) au
  lieu de la créer — ce que la fiche `ACTIONS.md` annonçait explicitement comme le rôle de
  `j-machine-tour`.
- **`declarer_attaque` non listé par le générateur** (D9) : le coup d'attaque complet (coût,
  dégâts) attend `j-degats-resolution`. La transition « termine le tour » existe et est testée
  en direct ; la vraie `Famille` d'attaque viendra avec le catalogue.

## Reste à faire (lots débloqués)

- `j-checkup` — résolution de la phase entre les tours (point d'ancrage : la fenêtre « fin de
  tour » câblée ici).
- `j-degats-resolution` — coût, dégâts, faiblesse, résistance ; enregistrera le vrai coup
  d'attaque jouable.
- `j-retraite-banc` — banc, retraite, promotion ; consomme `peut_battre_retraite`.
