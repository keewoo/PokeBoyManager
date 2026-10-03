# Mode solo — partie d'entraînement contre un bot (lot `j-mode-solo`, DJ7)

Le jeu est privé entre quelques comptes invités : il y aura des soirs sans adversaire. Plutôt qu'un
écran d'attente vide, on branche le **bot de simulation** (`pbm_sim.bots`, lot `j-simulation-bots`)
comme deuxième joueur d'une partie **ordinaire** du service (`pbm_api.games`). Couloir serveur.

## Ce que fait le serveur

- **Création** — `pbm_api.games.bot.creer_partie_entrainement(user_id, deck_id, niveau)` : recontrôle
  le deck du joueur (propriété, scripts D9, possession, via `lancement.verifier_lancable`), crée une
  partie marquée `entrainement`, le joueur au **siège 0** (il commence), le bot au **siège 1**, lance
  la mise en place (R-4), puis fait **placer le bot** tout de suite. Le bot joue le **même deck** que
  le joueur (match miroir) : partenaire immédiat, sans deck ni collection propres — choix du lot, qu'un
  lot ultérieur pourra enrichir de decks préconstruits.
- **Route** — `POST /matchmaking/entrainement {deck_id, niveau}` → `{game_id, niveau, bot_delai_ms}`
  (201). 404 deck d'autrui, 422 deck injouable (cartes nommées) ou niveau inconnu, 409 déjà en partie.
  C'est l'entrée « S'entraîner » du salon : `GET /matchmaking/presence` propose déjà l'option
  `entrainement_bot` quand personne n'est en ligne.
- **Pilotage du bot** — après **chaque** coup de l'humain, `appliquer_action` appelle
  `bot.boucle_bot_pour_partie` : le bot enchaîne ses coups (et les coups système dus) **jusqu'à ce que
  la main revienne au joueur**, dans la même transaction. Hors coup de l'humain (placement initial),
  `bot.jouer_coups_bot` fait la même chose sous son propre verrou.

## Les trois règles d'or, tenues et testées

1. **Le serveur fait autorité, le bot aussi.** Le bot ne passe **jamais** par HTTP. Il décide sur la
   **seule** `pbm_game.state.vue(etat, bot)` + la liste `actions_legales` — jamais l'`EtatPartie`.
   Vérifié : `test_games_mode_solo.test_bot_ne_voit_que_sa_vue` espionne chaque décision et exige une
   projection qui masque la main adverse (`main_nombre`, jamais `main`).
2. **Rien n'est approximé (D9).** Aucun coup jouable, ou une demande de décision adressée au bot qu'il
   ne sait pas résoudre (à ce jalon, decks à dégâts secs) → il **rend la main** en le journalisant,
   jamais un coup inventé, jamais un repli muet. Le bot **n'abandonne jamais** (vérifié : aucun coup
   d'abandon sous son identité dans le journal d'une partie jouée de bout en bout).
3. **Tout est rejouable.** Les coups du bot sont des entrées de journal ordinaires (auteur = identité
   du compte bot) : la reprise après un F5 (`reprendre_partie`) reconstruit l'état et vérifie
   l'empreinte, bot compris.

## Trois niveaux (DJ7)

| Niveau   | Bot `pbm_sim` | Comportement                                                        |
|----------|---------------|---------------------------------------------------------------------|
| hasard   | `aleatoire`   | un coup légal au hasard (hors abandon)                              |
| correct  | `heuristique` | promeut le plus sain, attaque fort, évolue, pose, charge utile     |
| coriace  | `coriace`     | comme « correct », mais **concentre l'énergie sur l'Actif** (R-9.2) |

`bot_coriace` est **ajouté** à `pbm_sim.bots._PAR_NOM` sans toucher `pbm_sim.decks.BOTS_DISPONIBLES`
(qui pilote le tirage des scénarios de simulation par graine) : la reproductibilité des campagnes et
des anomalies archivées est intacte.

## Persistance & temps de réflexion visible

- `games.entrainement` (bool) : la partie entre dans l'historique (`GET /games`) marquée
  entraînement, mais ne compte pas — il n'existe aujourd'hui **aucun classement de joueur** (le module
  `ranking` classe des cartes) ni séries ; le marqueur est posé pour qu'ils l'excluent dès qu'ils
  existeront.
- `game_players.bot_niveau` (str|null) : renseigné sur le seul siège du bot ; `null` sur le siège
  humain. Le compte bot réservé (`bot.BOT_USER_ID`, migration `f1c0b07a1d02`) est inconnectable.
- **Délai visible** : le serveur **ne temporise pas** (il sert d'autres joueurs) ; il renvoie
  `bot_delai_ms` à la création, et c'est l'écran qui révèle les coups du bot à ce rythme (DJ7
  « rester lisible »).

## Reste côté écran

L'entrée « S'entraîner » du salon (bouton + choix du niveau + appel de la route) est un travail
**front** (`apps/web`, `j-salon-partie`), hors du couloir serveur de ce lot : le contrat serveur est
complet et prouvé, le branchement visuel suit. L'adversaire IA qui raisonne et explique ses coups sur
la clé du joueur est le lot suivant, `j-adversaire-ia`.
