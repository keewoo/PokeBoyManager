# Compte rendu — `j-partie-service`

**Service de parties : créer, persister, reprendre, expirer.** Couloir **J-SRV** (chimera), jalon
**J1**. Exécuté en session autonome sur chimera, piloté depuis devAI.

## Résumé

L'enveloppe de persistance et d'orchestration autour du moteur pur `pbm_game` est livrée. Une partie
se crée à partir de deux decks résolus en scripts (carte non jouable → partie refusée, D9), ses coups
s'appliquent dans une transaction idempotente sous verrou de ligne, elle se reprend à l'identique
après un redémarrage (empreinte comprise), et les parties abandonnées expirent puis se purgent avec
métrique. Le moteur reste pur : tout ce qui lit la base vit dans le nouveau paquet `pbm_api.games`.

## Livrables

- **Modèle + migration** — `apps/api/src/pbm_api/models/games.py` (`Game`, `GamePlayer`, `GameEvent`,
  `GameSnapshot`) et migration Alembic `c5f1a9e3b7d0` (down_revision `a3f9c2e5b1d4`, tête unique). Le
  journal (`game_events`) est *append-only* ; unicité `(game_id, numero)` = socle de l'idempotence.
- **Boucle d'application transactionnelle** — `pbm_api.games.service.appliquer_action` : verrou de
  ligne (`FOR UPDATE`), idempotence par numéro d'action (rejeu / conflit), validation par le moteur,
  journalisation, cache, compaction périodique, le tout en une transaction.
- **Résolution des decks en scripts** — `pbm_api.games.construction` : chaque carte compilée via
  `pbm_api.jeu.catalogue.definition_depuis_card` ; toute carte non jouable fait lever
  `CartesNonJouables` (cartes nommées) avant toute écriture.
- **Reprise et purge** — `reprendre_partie` (instantané + queue, empreinte vérifiée),
  `expirer_parties`, `purger` (métrique journalisée).
- **Routes de lecture** bornées au participant — `GET /games`, `GET /games/{id}` (404, pas 403).
- **Doc durable** — `docs/jeu/PARTIES.md`.

## Preuves

- **Ruff** : `uv run ruff check .` → *All checks passed!* (apps/api).
- **Migration** : `alembic heads` → `c5f1a9e3b7d0` (tête unique) ; `alembic upgrade head` applique
  toute la chaîne + les quatre tables sur une base neuve, EXIT=0.
- **Tests du lot** : `tests/test_games_service.py` (14 cas) + `tests/test_games_routes.py` (2 cas) →
  **16 passed**. Couvrent les trois critères d'acceptation :
  - *reprise après redémarrage* — `test_reprise_apres_redemarrage_rend_etat_exact`,
    `test_compaction_instantane_et_reprise_identique` (instantanés aux coups 0/3/6, Rng reconstruit
    via un mélange rejoué, empreinte vérifiée) ;
  - *pas de double application* — `test_idempotence_meme_numero_meme_action_ne_rejoue_pas` (une seule
    entrée au numéro 0), `test_conflit_numero_*`, `test_unicite_game_numero_backstop` (la contrainte
    DB rejette la seconde écriture au même numéro) ;
  - *carte non scriptée refusée* — `test_creer_partie_refuse_une_carte_non_scriptee` (cartes nommées,
    aucune partie persistée).
- **Non-régression** : suite `api` complète lancée sur chimera (voir dernière exécution) ; CI
  GitHub Actions verte sur la branche (fait foi).
- **Accès croisé** : `test_acces_croise_et_liste_bornee_au_participant` — un non-participant reçoit
  404 et une liste vide ; le participant voit la partie ; la graine n'apparaît jamais, l'engagement
  oui.

## Écarts au plan

- **Validation des coups mécanique seulement.** Ce lot valide via `pbm_game.journal.appliquer` (type
  inconnu / coup impossible refusés, D9) ; la restriction à la **liste des coups légaux**
  (`actions_legales`) et la **vue autoritaire** sont le lot `j-autorite-vues`. Documenté dans
  `docs/jeu/PARTIES.md`.
- **Diffusion** des événements : ils sont **renvoyés** à l'appelant ; le canal temps réel est
  `j-temps-reel`.
- **État initial minimal** : decks chargés en pioche, sans mise en place (mélange/main/récompenses) —
  c'est le lot `j-initialisation`. Pas de route de création (c'est `j-lancement-partie`).

Aucun de ces écarts n'est une approximation de règle : chacun est une frontière de lot explicite,
nommée dans la doc et le code. Aucun repli silencieux.

## Reste à faire (lots aval)

`j-autorite-vues` (vue projetée + coups légaux), `j-lancement-partie` (route de création + tirage au
sort), `j-initialisation` (mise en place), `j-temps-reel` (diffusion), `j-timer`,
`j-deconnexion-abandon`, `j-replay` — tous débloqués par cette enveloppe.

## Grille

| Tâche | État | Preuve |
|---|---|---|
| dev | fait | `pbm_api.games` (models, construction, service, errors, schemas, router) + migration `c5f1a9e3b7d0` |
| tests | fait | 16 tests du lot verts ; suite api complète ; chaque critère d'acceptation couvert |
| securite | fait | routes bornées `user_id` (404 cross-access testé) ; graine jamais exposée ; aucun secret au dépôt |
| maquette | s/o | lot serveur, aucun écran |
| doc_tech | fait | `docs/jeu/PARTIES.md` ; docstrings françaises sur tout le code ajouté |
| release_uat | fait | recette locale sur chimera (ruff, alembic, pytest) |
| release_prod | s/o | la PROD se livre à part, par devAI (aucun déploiement dans ce lot) |
| backlog | s/o | tenu par la file (etat.json non touché) |
| compte_rendu | fait | ce fichier |
