# Compte rendu — `j-file-attente`

**Recherche d'un adversaire : file d'attente privée et appariement** · jalon J1 · couloir J-SRV (chimera).

## Résumé

Posé la **file d'attente privée**, l'**appariement** et la **présence** du jeu, par-dessus le service
de parties (`j-partie-service`). Entrer avec un deck vérifié, être apparié par ordre d'arrivée ou
attendre, annuler, voir qui est en ligne, et — si personne n'est disponible — se voir proposer
l'invitation ou l'entraînement contre le bot. Introduit le **droit d'accès au jeu** (D11,
`users.game_access`) : l'inscription est libre, mais le jeu est réservé — un compte sans ce droit
reçoit **404** sur **toutes** les routes du jeu. Le risque nommé du lot (deux joueurs appariés chacun
avec un troisième) est fermé par un **verrou Redis atomique**, prouvé par un test de concurrence réel.

Travaillé sur chimera (WSL), base de test dédiée `pbm_j_file_attente_test` + Redis `:56379`.

## Livrables

- **Moteur de file / appariement / présence** : `apps/api/src/pbm_api/games/matchmaking.py`
  (file ZSET FIFO, verrou `SET NX EX` + libération Lua compare-and-delete, présence par battement de
  cœur, garde « jamais deux parties » revérifiée en base).
- **Vérification du deck à l'entrée** : `apps/api/src/pbm_api/games/entry.py` — propriété (404) +
  scripts disponibles (D9, cartes nommées → 422).
- **Routes** : `apps/api/src/pbm_api/routers/matchmaking.py` (`POST/GET/DELETE /matchmaking/queue`,
  `GET /matchmaking/presence`), enregistrées dans `main.py`, toutes gardées par `require_game_access`.
- **Droit d'accès au jeu (D11)** : colonne `users.game_access` (migration additive `d2b7f1a4c9e0`),
  dépendance `pbm_api.auth.dependencies.require_game_access`, commande d'administration
  `pbm_api.admin set-game-access <email> on|off`. Les routes `/games` (parties) sont **aussi** gardées.
- **Doc** : `docs/jeu/FILE-ATTENTE.md` (le savoir durable du lot).
- **Tests** : `test_matchmaking_service.py`, `test_matchmaking_routes.py`, `test_game_access.py` ;
  `test_games_routes.py` / `test_games_projection.py` adaptés (les routes `/games` exigent désormais
  le droit d'accès).

## Preuves

- **Ruff** vert (`uv run ruff check .` → « All checks passed! »).
- **Migration** appliquée sur la base de test (`alembic upgrade head` → `… -> d2b7f1a4c9e0`).
- **Tests du service** : `tests/test_matchmaking_service.py` → **8 passés** (deux joueurs appariés,
  FIFO, trois joueurs dont un annule, deck refusé/propriété, déjà-en-partie, verrou, concurrence).
- **Sous-ensemble large** (auth, profil, decks, isolation croisée, games, matchmaking, game_access,
  deadlock concurrent) : **100 passés** en 32 s. (Une première exécution avait 2 échecs sur les tests
  de rate-limit de `test_auth` — **flakiness de timing** sur la fenêtre Redis, indépendante du lot :
  `test_auth` tournait en tête et passe seul 21/21 ; la relance a donné 100/100.)
- **Collecte** de la suite API entière sans erreur d'import : **923 tests collectés**.
- Critères d'acceptation :
  - *Jamais deux parties (concurrence)* → `test_concurrence_jamais_deux_parties` (deux `apparier`
    concurrents, sessions distinctes, sur trois joueurs → une seule partie, aucun joueur en double).
  - *Refus d'un deck nomme les cartes et la raison* → `test_entree_refuse_deck_non_jouable_cartes_nommees`
    (service) et `test_deck_refuse_nomme_les_cartes` (route, 422 avec `refus:[{carte,raison}]`).
  - *Attente affiche l'état réel* → `position`, `joueurs_en_file`, `attente_secondes` (routes + service).
  - *404 sans droit d'accès sur chaque route* → `test_sans_acces_404_partout` (`/matchmaking/*`),
    `test_games_404_sans_acces` (`/games/*`) ; la commande pose/retire le droit et c'est testé
    (`test_set_game_access_pose_et_retire`).

## Écarts au plan

- **Légalité de format non imposée à l'entrée.** Le plan liste « légalité, possession, scripts ». La
  vérification bloque sur la **propriété** (sécurité) et les **scripts** (D9, le vrai « jouable »,
  même gate que `creer_partie`). La légalité TCG (60 cartes, max 4, possession en collection) vit déjà
  dans le module de decks (`v7-decks-legalite`) côté *construction* ; l'imposer ici rendrait les decks
  minimaux du jalon J1 injouables et contredirait le service de parties livré, qui ne l'impose pas. La
  porte « deck légal » s'ajoutera quand `j-initialisation` fera du deck complet l'unité de jeu — report
  **explicite** (voir `docs/jeu/FILE-ATTENTE.md`), pas un abandon silencieux.
- **Appariement FIFO strict** (pas de proximité de niveau) : aucun classement de **joueur** n'existe
  encore (le module `ranking` classe des cartes). Documenté, s'activera avec un classement de joueur.
- **Présence « personne en ligne » = données, pas features** : la réponse propose
  `["invitation","entrainement_bot"]` ; l'invitation (`j-invitations`) et le bot ne sont pas de ce lot.

## Reste à faire (hors périmètre)

- `j-invitations` (inviter par pseudo/lien) et le bot d'entraînement, ciblés par les options de repli.
- Imposer la légalité de deck complète à l'entrée une fois `j-initialisation` livré.
- Écran de file d'attente (interface) : lot d'interface du jeu (`j-salon-partie`).

## Sécurité

- Isolation : toute route du jeu filtre par le `user_id` de la session ; deck/partie d'autrui → **404**
  (jamais 403, pas de fuite). Tests d'accès croisé pour `/matchmaking` et `/games`.
- Aucun secret en clair ; la graine de partie reste le secret du service de parties (non touché).
- Le droit d'accès au jeu ne s'accorde **que** hors ligne (CLI admin), jamais par HTTP.
