# Compte rendu — `j-mode-solo` (Partie d'entraînement contre un bot)

**Statut : livré (recette locale chimera verte, CI à confirmer).** Couloir J-SRV (serveur,
`apps/api` + `apps/game/pbm_sim`). Décision **DJ7** appliquée : bot d'abord (gratuit, instantané,
sans clé), en mode « entraînement », non compté au classement ; l'IA adversaire viendra avec
`j-adversaire-ia`.

## Résumé

On branche le bot de simulation (`pbm_sim.bots`) comme **deuxième joueur** d'une partie ordinaire du
service de parties. Trois niveaux (hasard/correct/coriace), partie marquée « entraînement »
(historique oui, classement non), bot piloté **côté serveur** qui ne voit **que** sa vue projetée, et
une route « S'entraîner » qui crée la partie en un appel. Tout reste rejouable (reprise après F5
vérifiée à l'empreinte). Détail durable : `docs/jeu/MODE-SOLO.md`.

## Livrables

- `apps/game/src/pbm_sim/bots.py` — troisième bot `bot_coriace` (heuristique + concentration de
  l'énergie sur l'Actif, R-9.2), ajouté à `_PAR_NOM` **sans** toucher `BOTS_DISPONIBLES` (déterminisme
  des simulations préservé). Test : `apps/game/tests/test_bots_coriace.py`.
- `apps/api/src/pbm_api/games/bot.py` — nouveau module : compte bot réservé, trois niveaux, création
  d'une partie d'entraînement, pilotage du bot (`boucle_bot`, `boucle_bot_pour_partie`,
  `jouer_coups_bot`) sur la seule `vue(etat, bot)` + `actions_legales`.
- `apps/api/src/pbm_api/games/service.py` — `creer_partie(entrainement=, bot_niveau=)` ; après chaque
  coup de l'humain, `appliquer_action` fait jouer le bot (import local, pas de cycle).
- `apps/api/src/pbm_api/routers/matchmaking.py` — `POST /matchmaking/entrainement`.
- `apps/api/src/pbm_api/models/games.py` + migration `f1c0b07a1d02` — `games.entrainement`,
  `game_players.bot_niveau`, compte bot réservé (idempotent, inconnectable).
- `apps/api/src/pbm_api/games/schemas.py`, `routers/games.py` — `entrainement` à l'historique/détail,
  `bot_niveau` au siège.
- Tests : `apps/api/tests/test_games_mode_solo.py`.

## Preuves (recette locale sur chimera, base de test fraîche + migrations)

- **Critère 1** (de bout en bout + F5) : `test_partie_entrainement_de_bout_en_bout_et_reprise` — une
  partie humain vs bot se joue jusqu'à une fin **méritée** (jamais abandon du bot : vérifié dans le
  journal), et `reprendre_partie` reconstruit l'état à l'empreinte près à chaque tour.
- **Critère 2** (vue seule) : `test_bot_ne_voit_que_sa_vue` — chaque décision du bot reçoit une
  projection (`pour == bot`, `main_nombre` de l'adversaire, jamais `main`), jamais l'`EtatPartie`.
- **Critère 3** (historique « entraînement » + isolation) :
  `test_historique_entrainement_et_acces_croise` — `GET /games` liste la partie `entrainement=true`,
  le détail nomme le niveau du bot au siège 1, et un autre compte reçoit **404** (pas de fuite).
- Route : `test_route_entrainement_cree_la_partie` (201, bot déjà placé), `…_niveau_inconnu_422`,
  et garde côté service `test_niveau_inconnu_leve_cote_service`.
- Comptes : **6** tests mode-solo ✓, **3** tests `bot_coriace` ✓, **103** tests de non-régression
  (games/lancement/matchmaking/accès) ✓, **912** tests `apps/game` ✓. `ruff check .` propre sur
  `apps/api` et `apps/game`. (Base de test locale fraîche `pbm_js_solo_test` : la base par défaut de
  chimera était en retard ; sans rapport avec le lot — la CI part d'une base vierge.)

## Écarts au plan

- **Couloir serveur, par décision du 03/10** : le contrat serveur de l'entrée « S'entraîner » est
  complet (route + option `entrainement_bot` déjà renvoyée par `presence`). Le **bouton** du salon
  (`apps/web`, choix du niveau, appel de la route, animation du délai) reste à câbler côté front —
  tâche `maquette`/front hors de ce couloir. Signalé plutôt que simulé.
- **Deck du bot = miroir du deck du joueur** : choix assumé (partenaire immédiat, sans collection
  bot). Des decks préconstruits par niveau seraient un enrichissement ultérieur.
- **Demandes de décision adressées au bot** : non pilotées à ce jalon (les decks jouables sont à
  dégâts secs, D9 — aucune demande n'y survient) ; le bot rend la main en le journalisant plutôt que
  d'inventer une réponse. À couvrir quand des effets à choix seront scriptés.
- **Délai de réflexion** : exposé en `bot_delai_ms` (le serveur ne dort pas) — l'animation est à la
  charge de l'écran.

## Reste à faire

- Front `j-salon-partie` : bouton « S'entraîner », choix du niveau, animation du délai du bot.
- `j-adversaire-ia` (débloqué par ce lot) : adversaire qui raisonne et explique, sur la clé du joueur.
- Exclure explicitement les parties `entrainement` du classement/des séries **quand** ils existeront.
