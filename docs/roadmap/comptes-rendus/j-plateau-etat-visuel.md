# Compte rendu — `j-plateau-etat-visuel`

**Lire le plateau d'un coup d'œil : dégâts, énergies, états, récompenses.**
Piste Interface de jeu · jalon J1 · couloir J-UI (chimera) · taille M.

## Résumé

Le plateau montre désormais l'état complet de chaque Pokémon **sans clic** : PV restants **et**
maximum (en plus des compteurs de dégâts), énergies **typées** empilées, Outil, états spéciaux (icône
+ orientation de la carte), récompenses restantes, cartes en main et en pioche, et un **halo** sur le
Pokémon qui vient d'agir. Tout se lit sur la **vue projetée par le serveur** : aucun recalcul côté
écran. Le point clé — et le risque nommé par la fiche — est traité à la racine : les **PV restants
sont calculés par le serveur** comme `seuil_de_KO − dégâts` (donc exacts même avec un Outil qui ajoute
des PV), jamais « imprimés − dégâts » déguisé côté client.

## Livrables

- **Moteur (pur)** : `pbm_game.sortie.enrichir_indicateurs` + `refs_en_jeu`
  (`apps/game/src/pbm_game/sortie/indicateurs.py`) — calcule `pv_max` (via `seuil_ko`, R-13.1),
  `pv_restants` (R-10.4) et pose le `type` des énergies/Outil/Pokémon. Reçoit des **données**, ne lit
  pas le catalogue (D9).
- **API (adaptateur)** : `pbm_api.games.indicateurs` (`CatalogueAffichage`, `catalogue_affichage`,
  `catalogue_pour_etat`/`_resultat`) — lit `Card` (tolérant), et enrichissement branché au **point de
  sortie unique** (`projection.vue_autoritaire`/`projeter_resultat`), donc actif sur la route d'état,
  la diffusion temps réel et la resynchronisation.
- **Front** : `lib/game/indicateurs.ts` (styles de types + icônes d'états + `agisseurDepuisEvenements`,
  purs), `components/game/board-card.tsx` (indicateurs posés sur la carte + halo), `game-board.tsx`
  (halo de l'agisseur), `partie-view.tsx` (agisseur dérivé des événements), `globals.css`
  (orientation physique de la carte). Types enrichis dans `lib/game/plateau.ts`.
- **Doc** : `docs/UI-UX.md` § « Indicateurs d'état du plateau », `docs/ARCHITECTURE.md` § « Indicateurs
  d'affichage de la vue ».

## Preuves

- `apps/game` : ruff clean, **865 tests** (dont `test_sortie_indicateurs.py` : 8 — PV avec/sans Outil,
  plancher à 0, type non deviné ; `test_effets_purete` garde la pureté).
- `apps/api` : ruff clean ; suite **jeu** verte (`test_games_projection`, `test_games_temps_reel`,
  `test_games_ws_routes`, `test_game_access`, `test_games_horloges`, `test_state_service`,
  `test_games_indicateurs`). Le reste de la suite : 993 passés, 7 échecs **hors périmètre**
  (auth rate-limit : flake d'ordre, verte en isolation ; identité/seed : dérive de schéma de la base
  de test locale de chimera, `users.first_name` absent — aucun lien avec les modules touchés ; la CI
  migre à neuf).
- `apps/web` : lint 0 erreur, type-check clean, **228 tests** (dont `indicateurs.test.ts` et
  `board-indicators.test.tsx`), `build` OK.

### Critères d'acceptation

- [x] L'état complet d'un Pokémon (dégâts, énergies, Outil, états) se lit sans clic — `BoardCard`.
- [x] Aucun indicateur ne dépend uniquement de la couleur — abréviation par type, icône par état,
  étiquette ARIA ; testé dans `board-indicators.test.tsx` et `indicateurs.test.ts`.
- [x] Les PV restants sont exacts, y compris avec un Outil qui ajoute des PV — `seuil_ko` ;
  `test_pv_max_suit_un_outil_qui_ajoute_des_pv`.

## Écarts au plan

- **Halo de l'agisseur** : dérivé des événements qui désignent un Pokémon (pose, évolution, attache
  d'énergie, K.O., promotion — `donnees.pokemon`/`base`). L'événement `attaque_declaree` ne porte pas
  encore l'identité de l'attaquant (il n'a que `joueur`) : une attaque seule ne déclenche donc pas le
  halo tant que `j-anim-socle`/les lots de combat n'enrichissent pas cet événement. Mécanique prête et
  testée côté plateau ; aucune invention (on ne met pas un halo au hasard).
- **Type des énergies** : résolu depuis `Card.element_type`. Correct pour les énergies de base ; une
  énergie spéciale sans `element_type` retombe sur un repère neutre nommé plutôt qu'une couleur
  inventée (D9).

## Reste à faire

- Enrichir `attaque_declaree` de l'identité de l'attaquant (lot de combat / `j-anim-socle`) pour que
  le halo suive aussi une attaque.
- Animations des coups (dégâts, déplacements) : lot aval `j-anim-socle`.
