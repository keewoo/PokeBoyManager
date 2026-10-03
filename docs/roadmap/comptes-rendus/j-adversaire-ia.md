# Compte rendu — `j-adversaire-ia` (Adversaire IA : un partenaire qui raisonne et explique)

**Statut : livré (recette locale chimera verte ; CI GitHub fait foi).** Couloir **J-SRV** (serveur,
`apps/api`). Jalon J4, décision **DJ7**. L'IA du joueur comme adversaire d'entraînement, sur **sa**
clé (coffre `pbm_api.ai`), qui choisit un coup **légal** et l'**explique** — le bot heuristique
restant le repli quand elle échoue.

## Résumé

On ajoute une **interface unique « joueur automatique »** que la partie d'entraînement appelle : la
boucle `boucle_joueur_auto` ne connaît ni le bot ni l'IA, elle pilote un **décideur**. Le bot et
l'IA l'implémentent tous deux. L'IA reçoit la **seule vue projetée** de son camp et la liste des
coups légaux numérotés, choisit un **index** (donc un coup **légal par construction**, jamais une
action libre — le serveur reste autorité) et l'explique en une phrase simple. Tout échec (réponse
invalide, absente, trop lente, plafond atteint) fait **jouer le bot** et **se voit** au journal.
Budget, délai, coût estimé et la non-fuite de l'information cachée sont gardés et testés. Détail
durable : `docs/jeu/ADVERSAIRE-IA.md`.

## Livrables

- `apps/api/src/pbm_api/games/adversaire_ia.py` — **nouveau** : `DecisionIA` (schéma `{index,
  explication}`), `construire_message` (bâti **uniquement** depuis `vue(etat, acteur)` + étiquettes
  légales), `choisir_coup_ia` (appel borné par `asyncio.wait_for`, validation de l'index, repli bot
  nommé), plafonds `MAX_APPELS_PAR_PARTIE=60` / `DELAI_MAX_COUP_S=20` / `MAX_LONGUEUR_EXPLICATION`.
- `apps/api/src/pbm_api/games/bot.py` — `boucle_bot` généralisée en `boucle_joueur_auto` (pilotée par
  un décideur, renvoie les commentaires) ; décideurs `_decideur_bot` / `_decideur_ia` ; résolution de
  la clé de l'humain (`_humain_du_siege`) et construction/fermeture du fournisseur ;
  `creer_partie_entrainement(adversaire="bot"|"ia")` ; exception `CleIAIndisponible`.
- `apps/api/src/pbm_api/games/service.py` — `ResultatAction.commentaires` ; `_persister_coup(…,
  commentaire=)` ; `creer_partie(…, adversaire_ia=)` ; `appliquer_action` collecte les commentaires
  du joueur automatique.
- `apps/api/src/pbm_api/games/projection.py` — les `commentaires` voyagent jusqu'au client
  (`projeter_resultat`), hors de la vue projetée (ce sont des faits publics).
- `apps/api/src/pbm_api/ai/service.py` — `record_usage(…, commit=False)` : l'usage IA se compte
  **dans la transaction du coup** (jamais un commit à mi-chemin d'une partie).
- `apps/api/src/pbm_api/routers/matchmaking.py` — `POST /matchmaking/entrainement` prend
  `adversaire` ; 422 `CleIAIndisponible` explicite ; `GET /matchmaking/presence` expose
  `ia_disponible`.
- `apps/api/src/pbm_api/routers/games.py` + `games/schemas.py` — `GET /games/{id}` expose `ia_cout`
  (`{appels, jetons, plafond_appels}`) ; `adversaire_ia` au siège.
- `apps/api/src/pbm_api/models/games.py` + migration `a1b2c3d4e5f6` — `game_players.adversaire_ia`,
  `games.ia_appels`, `games.ia_tokens`, `game_events.commentaire`.
- Tests : `apps/api/tests/test_adversaire_ia.py` (11 tests, fournisseur factice).
- Doc durable : `docs/jeu/ADVERSAIRE-IA.md`.

## Preuves (recette locale sur chimera, base de test fraîche `pbm_jia_test` + migrations)

- **Migration** : `alembic upgrade head` applique la chaîne jusqu'à `a1b2c3d4e5f6` sans erreur ;
  `alembic heads` → **une seule tête**.
- **Critère 1** (partie complète, coups légaux et expliqués) :
  `test_partie_contre_mon_ia_jusqua_la_fin_chaque_coup_explique` — une partie humain vs « mon IA »
  (factice) se joue jusqu'à une fin **méritée** (`raison_fin ∉ {None, abandon}`) ; l'IA est consultée
  (`ia_appels > 0`), des explications remontent au client **et** sont persistées au journal
  (`game_events.commentaire`, auteur = siège bot) ; `ia_tokens` = 15 × appels.
- **Critère 2** (aucune information cachée) : `test_message_ne_fuite_aucune_information_cachee` —
  photographie **cohérente dans le temps** : à un état de milieu de partie, aucun `instance_id` de
  la main ni de la pioche de l'humain **à cet instant** n'apparaît dans le message réellement bâti
  (`construire_message(vue(etat, BOT), legales)`). Complété par
  `test_construire_message_ne_reprend_que_la_vue` (l'ordre de la pioche n'est exposé pour personne :
  seulement `pioche_nombre`).
- **Critère 3** (échec → bot, et ça se dit) : `test_repli_sur_exception_du_fournisseur`,
  `test_repli_sur_index_hors_bornes` (usage réel compté), `test_repli_sur_delai_depasse`,
  `test_coup_valide_est_joue_et_explique`, et `test_plafond_appels_arrete_lia_et_le_dit` (plafond
  ramené à 1 : `ia_appels ≤ 1`, et le journal **annonce** le plafond). Dans tous les cas le bot joue
  et le commentaire le dit — jamais un repli silencieux, jamais un coup inventé.
- **Critère 4** (sans clé) : `test_sans_cle_ia_refuse_en_expliquant` (422 nommant la clé **et** le
  bot) et `test_sans_cle_le_bot_reste_jouable` (la partie contre le bot se crée).
- **Isolation** : `test_lia_utilise_la_cle_de_lhumain_de_la_partie` — l'IA d'une partie résout la clé
  de **l'humain de cette partie**, jamais celle d'un autre joueur.
- **Comptes** : **11** tests `test_adversaire_ia` ✓ ; **non-régression** ✓ : mode-solo, matchmaking,
  routes, projection, service, partie complète, HTTP/WS, interactions, déconnexion/abandon, horloges
  (**63**), + IA/clés/providers/detail carte (**57**). `ruff check .` propre sur `apps/api`.

## Écarts au plan

- **Couloir serveur (J-SRV)** : comme `j-mode-solo` l'a fait pour son bouton de salon, le **front**
  reste à câbler dans un lot front : choix « mon IA / bot » au salon (en lisant `ia_disponible`),
  rendu des `commentaires` dans le panneau de journal, affichage de `ia_cout`, et régénération du
  client TypeScript (`pnpm gen:api` — le schéma d'API a gagné `adversaire`, `ia_disponible`,
  `ia_cout`, `adversaire_ia`). Signalé, pas simulé. Aucun check `gen:api`/OpenAPI en CI, et le front
  n'utilise aucun nouveau champ → la CI web reste verte.
- **Coût en euros** : non calculé — aucune table de tarification par modèle n'existe dans ce dépôt
  (limite déjà documentée de `record_usage`). `ia_cout` expose honnêtement appels et jetons ; le prix
  en euros reste à faire.
- **Placement initial toujours par le bot**, même en partie IA : il survient à la création (route
  synchrone), où un appel réseau n'a pas sa place. L'IA joue les tours de jeu. Choix documenté.
- **Fournisseur simulé** (`AI_SIMULATED_PROVIDER`) non étendu à `DecisionIA` : l'e2e d'une partie
  contre l'IA viendra avec un lot ultérieur. Les tests unitaires couvrent la logique via un
  fournisseur factice injecté.
- **Demandes de décision adressées au joueur automatique** : non pilotées à ce jalon (decks à dégâts
  secs, D9) — l'adversaire rend la main en le journalisant, comme le bot.

## Reste à faire

- Lot **front** : salon (option « mon IA » + explication sans clé), journal (rendu des
  `commentaires`), coût affiché, `pnpm gen:api`.
- `j-coach-ia` (débloqué par ce lot) : un conseil sur demande, et ce qu'on retient d'une partie.
- Étendre le fournisseur simulé pour un e2e Playwright d'une partie contre l'IA.
