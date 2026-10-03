# Compte rendu — `j-coach-ia` (Coach IA : un conseil sur demande, et un bilan de fin de partie)

**Statut : livré (recette locale chimera verte ; CI GitHub fait foi).** Couloir **J-SRV** (serveur,
`apps/api`). Jalon J4, décision **DJ7**. Deuxième visage de l'IA du joueur (après `j-adversaire-ia`) :
au lieu de jouer contre l'enfant, elle l'**aide** — un conseil pendant son tour, un bilan après la
partie, sur **sa** clé (coffre `pbm_api.ai`). Détail durable : `docs/jeu/COACH-IA.md`.

## Résumé

Deux usages, réutilisant l'interface et les garde-fous de `j-adversaire-ia` (vue projetée seule,
coups légaux numérotés, plafonds, clé jamais exposée) :

- **Conseil** (`POST /games/{id}/conseil`) : l'IA reçoit **sa** vue et ses coups légaux, choisit un
  **index** (donc un coup légal par construction, jamais une action libre) et l'explique. Le serveur
  **n'applique rien** — le conseil est une suggestion, le geste reste celui du joueur. Réservé aux
  parties d'**entraînement** (refusé entre deux humains), borné par un plafond de conseils par partie
  **réglable** (`settings.coach_max_conseils`, défaut 3) compté sur la partie (`games.conseils_utilises`),
  refusé sans clé IA ou si le coach est désactivé. Aucun repli sur le bot : un conseil absent se **dit**.
- **Bilan** (`GET /games/{id}/bilan`) : à partir du **journal** (pas de l'état complet), l'IA dégage
  deux ou trois moments décisifs. Chaque moment cité est **vérifié** contre les numéros réels du
  journal : un numéro inventé est écarté (anti-hallucination). Désactivable ; 502 si l'IA ne rend rien
  d'exploitable (jamais un bilan vide passé pour un succès).

Le moteur du coach (`pbm_api.games.coach_ia`) est **pur** (ni base, ni HTTP, ni réseau) : il reçoit un
fournisseur et des données pures et renvoie une suggestion ou un bilan. Le service
(`pbm_api.games.coach`) porte les garde-fous, la clé et la base. Le moteur de jeu `pbm_game` n'est pas
touché (il reste pur).

## Livrables

- `apps/api/src/pbm_api/games/coach_ia.py` — **nouveau** : `ConseilIA`/`BilanIA`/`MomentBilan`
  (schémas), `proposer_conseil` (index validé, pas de coup inventé, pas de repli bot),
  `resumer_partie` (filtre les moments sur les numéros réels), `construire_lignes_journal`
  (journal lisible, coups système écartés), `decrire_action`, plafonds/délais. Réutilise les outils de
  l'adversaire IA (`etiqueter_coups`, nettoyage d'explication, raison d'échec).
- `apps/api/src/pbm_api/games/coach.py` — **nouveau** : `conseil_pour_joueur`, `bilan_de_partie`,
  refus nommés (`CoachDesactive`, `ConseilHorsEntrainement`, `PlafondConseils`, `CleCoachIndisponible`,
  `PartieNonTerminee`, `BilanIndisponible`). Appel IA **hors verrou** ; incrément du compteur **sous
  verrou** ; usage IA compté (`record_usage`).
- `apps/api/src/pbm_api/routers/games.py` — routes `POST /games/{id}/conseil`, `GET /games/{id}/bilan`
  (404/422/409/502 nommés).
- `apps/api/src/pbm_api/games/schemas.py` — `ConseilOut`, `CoupConseille`, `BilanOut`, `MomentBilanOut`.
- `apps/api/src/pbm_api/models/games.py` + `models/users.py` + migration `b2c3d4e5f6a7` —
  `games.conseils_utilises`, `users.coach_actif`.
- `apps/api/src/pbm_api/config.py` — `coach_max_conseils` (réglable par l'environnement).
- `apps/api/src/pbm_api/ai/{schemas,service}.py` + `routers/ai_keys.py` — `coach_actif` dans
  `GET`/`PATCH /me/ai-settings` (désactivation du coach par le joueur).
- Tests : `apps/api/tests/test_coach_ia.py` (17 tests, fournisseur factice) ; `tests/test_ai_keys.py`
  mis à jour (coach_actif dans les réglages).
- Doc durable : `docs/jeu/COACH-IA.md`.

## Preuves (recette locale sur chimera, base de test fraîche `pbm_jcoach_test` + migrations)

- **Migration** : `alembic upgrade head` applique la chaîne jusqu'à `b2c3d4e5f6a7` sans erreur ;
  `alembic heads` → **une seule tête**.
- **Critère 1** (coup légal ou rien, jamais inventé) : `test_conseil_coup_valide` (index conforme →
  coup légal + explication), `test_conseil_index_hors_bornes` (index hors bornes → `coup=None` +
  raison, usage compté, **jamais inventé**), `test_conseil_echec_fournisseur` (injoignable → dit),
  `test_conseil_aucun_coup_ne_consomme_rien`, et le bout-en-bout `test_conseil_propose_un_coup_legal`
  (conseil dans une vraie partie d'entraînement, `conseils_utilises` persisté sur la partie).
- **Critère 2** (pas entre deux humains) : `test_conseil_refuse_entre_deux_humains` — une partie
  humain vs humain lève `ConseilHorsEntrainement`, **avant tout appel IA** (`faux.appels == 0`).
- **Critère 3** (bilan cite des coups réels) : `test_bilan_ecarte_les_numeros_inventes` (unitaire) et
  `test_bilan_cite_des_coups_reellement_joues` (bout en bout : partie jouée jusqu'à une fin méritée,
  un numéro réel cité est **gardé**, un numéro inventé est **écarté**, tout numéro retenu existe au
  journal) ; `test_lignes_journal_ecarte_les_coups_systeme`.
- **Garde-fous** : `test_conseil_plafond`, `test_conseil_sans_cle`, `test_conseil_coach_desactive`,
  `test_bilan_partie_non_terminee`.
- **Accès croisé** : `test_conseil_acces_croise_404` et `test_bilan_acces_croise_404` (service →
  `PartieIntrouvable`) ; **routes HTTP** `test_route_conseil_happy_et_acces_croise` (A reçoit 200 avec
  un coup ; B non-participant → **404**) et `test_route_bilan_acces_croise` (B → 404).
- **Comptes** : **17** tests `test_coach_ia` ✓ ; **18** tests `test_ai_keys` ✓ ; **non-régression** :
  **1037 passed** sur la suite `apps/api` (hors les 2 tests `test_catalogue_seed` qui échouent
  localement faute de `pg_dump` dans la WSL de chimera — environnement, pas le code ; la CI GitHub a le
  client postgres). `ruff check .` propre sur `apps/api`.

## Écarts au plan

- **Couloir serveur (J-SRV)** : le **front** reste à câbler dans un lot front (bouton « Un conseil ? »,
  rendu du coup suggéré **sans l'appliquer**, panneau de bilan, réglage « coach activé », `pnpm
  gen:api` — le schéma d'API a gagné `/games/{id}/conseil`, `/games/{id}/bilan`, `coach_actif`). Comme
  `j-adversaire-ia`, signalé, pas simulé. Pas de capture de maquette : ce lot n'ajoute aucun écran.
- **Coût en euros** : non calculé (aucune table de tarification par modèle, limite déjà documentée de
  `record_usage`). L'usage IA est compté ; le prix reste à faire.
- **Bilan non persisté** : généré à la demande à chaque appel (re-dépense la clé). Un lot ultérieur
  pourrait le mettre en cache sur la partie.
- **Placement initial** : au tout début (mise en place), le conseil porte sur le placement — légitime.
  L'enfant demande conseil à son propre tour ; hors de son tour, la route répond `coup=null` + raison.

## Reste à faire

- Lot **front** : écran du conseil et du bilan, réglage de désactivation, `pnpm gen:api`.
- Coût en euros (table de tarification par modèle, transverse).
- Cache du bilan sur la partie (éviter de re-dépenser la clé à chaque consultation).
