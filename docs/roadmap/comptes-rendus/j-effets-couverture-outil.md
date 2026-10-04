# Compte rendu — `j-effets-couverture-outil`

**Lot** : Tableau de couverture — ce qui est jouable, ce qui manque, et pour qui.
**Jalon** : J2 (toutes les cartes du deck vraiment jouées). **Piste** : Effets & cartes. **Taille** : S.
**Machine** : travail sur **chimera** (WSL Ubuntu-24.04), pilotage depuis **devAI**.
**Statut** : livré (recette locale chimera verte ; la CI GitHub fait foi sur la PR).

## Résumé

Sur le registre `card_scripts` posé par `j-effets-catalogue-compilation`, ce lot livre l'**outil qui
dirige l'effort de scriptage** : une mesure de couverture qui ne regarde que les **collections
réelles** des joueurs du jeu (jamais le catalogue entier, qui flatterait), le branchement de la
légalité du deck sur le registre (une carte à effet non scripté est désormais refusée en le disant,
avec la catégorie du blocage), et une **file de demandes** « je voudrais jouer cette carte » qui
alimente la priorisation. Le moteur `pbm_game` reste pur : tout ce qui lit la base vit dans
`pbm_api.jeu.scripts`, et `legality.evaluate` reste pur (il reçoit la carte→raison déjà résolue).

## Livrables

- **Couverture** (`jeu/scripts/couverture.py`) : cœur **pur** (couverture par effet, par carte, par
  extension, par famille d'effet, **par collection de joueur**, classement des cartes qui bloquent le
  plus) + adaptateur base `charger_couverture` (univers = cartes possédées par un joueur `game_access`
  ou dans l'un de ses decks) + **CLI** `python -m pbm_api.jeu.scripts.couverture [--json]` (la « page
  d'administration »). Univers vide → le rapport le **dit**, jamais un `0 %` trompeur.
- **File de demandes** : table `card_play_requests` (`models/card_play_requests.py`, migration
  `b7d3f1a2c9e4`, une seule tête alembic, `down_revision = c3a7f1e9d2b4`) ; service
  `jeu/scripts/demandes.py` (upsert idempotent par (joueur, carte), progression = statut + jouabilité
  recalculée) ; routes `/me/demandes-cartes` (POST/GET/DELETE, bornées `user_id`, CSRF sur les écritures).
- **Légalité branchée** : `chargeur.refus_scripts_par_carte` (card_id → première raison bloquante) ;
  `legality.evaluate(unsupported=…)` émet un constat `unsupported_effect` bloquant pour les cartes du
  deck jugé ; chaque constat porte une **catégorie** `possession`/`legalite`/`script` (schéma API +
  `decks/service.py` qui calcule la carte→raison une fois et la réutilise).
- **Écran** : `lib/game/legality.ts` (libellés de catégorie, cartes bloquées par script) ;
  constructeur de deck — badge « Effet non géré » + bouton « Je voudrais jouer cette carte » par
  carte, et catégorie nommée dans la liste des constats ; client `lib/api/play-requests.ts`.
- **Doc** : `docs/jeu/COUVERTURE.md`.

## Preuves (recette locale chimera, CI faisant foi)

- **API** : `ruff check .` vert ; `alembic upgrade head` → tête unique `b7d3f1a2c9e4` ; import de
  l'app + des modules OK. Tests nouveaux :
  - `tests/test_script_coverage.py` (21 cas purs, avec `test_deck_legality_scripts.py`) — jouabilité
    D9, couverture par effet/carte/famille/extension/collection, classement des manquantes ;
  - `tests/test_card_play_requests.py` (6 cas HTTP) — création idempotente, carte sans effet « déjà
    jouable », carte inconnue 404, suppression, **accès croisé** (B ne voit pas les demandes de A) ;
  - `tests/test_script_coverage_db.py` (4 cas base) — l'univers exclut un compte sans `game_access`,
    le **chiffre par collection** (aymeric 2 effets/1 jouable, zoe 0 jouable), le classement (1 deck,
    2 joueurs), la file dans le rapport, et la légalité d'un deck qui porte le constat `script`.
  - Régression : `test_deck_legality.py`, `test_card_scripts_chargeur.py`, `test_deck_collection_sync.py`,
    `test_deck_ai_routes.py` → 58 cas verts.
- **Web** : `lint` (0 erreur), `type-check` (0 erreur), `test` **264/264** (dont la nouvelle vignette
  de deck « Effet non géré » + bouton de demande, et `legality-categories.test.ts`), `build` OK et
  **garde localhost** OK.
- **CLI** : `python -m pbm_api.jeu.scripts.couverture` s'exécute et rend le rapport (sur une base de
  test vide : message « univers vide » honnête). Le rendu **par collection** est prouvé par
  `test_script_coverage_db` (le texte cite `aymeric`/`zoe`).

## Critères d'acceptation

- [x] Le constructeur affiche, pour chaque carte refusée, si c'est la **possession** (« Non possédée »),
  la **légalité** (« Hors format » + constats globaux nommés) ou le **script** (« Effet non géré ») qui
  bloque — catégorie portée par l'API et rendue à l'écran.
- [x] La page de couverture donne le chiffre **par collection de joueur**, pas seulement global (section
  `par_collection` du rapport / CLI).
- [x] La file de demandes est **visible dans le rapport de couverture** que lit chaque lot de scripts
  (`file_agregee` → `RapportCouverture.file_demandes`).

## Écarts au plan

- **La « page d'administration » est une CLI, pas une page web.** Le détail par collection expose, par
  joueur, ce qu'il possède : c'est une donnée d'exploitation qu'un joueur ne doit pas voir d'un autre.
  L'exposer en HTTP exigerait un rôle d'administration qui n'existe pas dans le dépôt (l'admin y est
  déjà, par convention, une CLI « jamais exposée en HTTP » — `pbm_api/admin.py`). La CLI sur le serveur
  est la surface correcte et sûre ; une page web admin reste possible plus tard, une fois un rôle admin
  introduit. Signalé, pas silencieux.
- **`pnpm gen:api` non commité.** La régénération du client produit un diff de ~6800 lignes (reformat dû
  à une version d'`openapi-typescript` plus récente que celle ayant généré le `schema.d.ts` commité) et
  **casse** le type-check sur des références écrites à la main (`auth.ts`, `profile.ts`) — une dérive
  d'outillage **préexistante**, hors périmètre de ce lot. Mon écran consomme des **types écrits à la
  main** (`lib/api/decks.ts`, `lib/api/play-requests.ts`), jamais le schéma généré : rien ne « ment ».
  Le `schema.d.ts` commité est donc laissé tel quel ; réaligner l'outillage est une tâche à part.

## Reste à faire (hors périmètre)

- Écrire de vrais scripts de cartes (lots de scripts + `j-effets-assistance-ia`) : cet outil les dirige.
- Éventuelle page web d'administration de la couverture, si un rôle admin est introduit.
- Marquer automatiquement une demande `scriptee` quand son effet passe `scripte` (aujourd'hui la
  jouabilité est recalculée à la lecture ; le statut stocké est posé par l'exploitation).
