# Compte rendu — `j-timer`

**Lot** : Horloges — par tour, par partie, par décision, et ce qui se passe à l'expiration.
**Jalon** J1 · piste Serveur de parties · couloir J-SRV (exécuté sur **chimera**, piloté depuis devAI).
**Branche** `roadmap/j-timer` · base `github/main` (`f39d41e`).

## Résumé

Sans horloge, un joueur parti dîner bloque l'autre indéfiniment ; avec une horloge mal faite, un
enfant perd une partie gagnée parce qu'il réfléchissait. Ce lot pose les **trois horloges de DJ4**
(90 s par tour, 25 min par joueur, 30 s par décision ; 10 s de tolérance réseau, 120 s de pause de
déconnexion) comme une **donnée de la partie calculée depuis des horodatages** — jamais un minuteur
en mémoire. Elle survit donc au F5, au redémarrage de l'API et à la reprise de journal.

- **Moteur pur** `pbm_game.horloges` : le décompte, les bascules, la pause/reprise et la détection
  d'expiration, toutes fonctions pures recevant l'instant par paramètre (aucune horloge système —
  prouvé par un test statique). Deux nouvelles transitions journalisées, `fin_tour` et
  `defaite_temps`, enregistrées à l'import (motif banc/cartes/demandes).
- **Autorité serveur** : les horloges vivent dans la colonne `games.horloges` (JSONB), mises à jour
  dans la **même transaction** que chaque coup, sous verrou. Une expiration produit **toujours** un
  coup journalisé (jamais un blocage) ; le serveur l'applique au gré des synchronisations et des
  battements du canal temps réel.
- **Affichage** : le serveur renvoie le temps restant « vérité serveur » dans chaque charge temps
  réel ; le client en fait une estimation locale **recalée à chaque événement** — l'écran reste à
  moins de deux secondes de la vérité serveur.

Les trois actions par défaut de DJ4 sont incarnées : décision → réponse par défaut de la demande
(`expirer_demande`, déjà dans le moteur) ; tour → fin de tour (`fin_tour`) ; budget épuisé → défaite
au temps (`defaite_temps`, `RAISON_TEMPS_ECOULE`).

## Livrables

| Fichier | Rôle |
|---|---|
| `apps/game/src/pbm_game/horloges/{modele,calcul,transitions_temps,__init__}.py` | moteur pur des horloges + transitions `fin_tour`/`defaite_temps` |
| `apps/game/src/pbm_game/journal/modele.py` | constantes `ACTION_FIN_TOUR`, `ACTION_DEFAITE_TEMPS`, `EVT_FIN_TOUR`, `RAISON_TEMPS_ECOULE` |
| `apps/game/src/pbm_game/journal/transitions.py` | `defaite_temps` permise pendant une demande (comme l'abandon) |
| `apps/game/src/pbm_game/__init__.py` | import de `horloges` pour l'enregistrement des transitions |
| `apps/game/tests/test_horloges_{purete,modele,calcul,transitions}.py` (32) | preuves moteur |
| `apps/api/src/pbm_api/games/horloges.py` | adaptateur : config, init, transition, restant, pause, action par défaut |
| `apps/api/migrations/versions/d4e1f2a3b5c6_game_clocks.py` | colonne `games.horloges` (down `c7e2b1a9f4d3`, tête unique) |
| `apps/api/src/pbm_api/{config,models/games,games/service,games/temps_reel,routers/games,routers/games_ws}.py` | config DJ4, colonne, init+maj+expiration+pause/reprise, charge temps réel |
| `apps/api/tests/test_games_horloges.py` (9) | preuves intégration API |
| `apps/web/src/lib/game/horloges.ts` + `__tests__/game-horloges.test.ts` (7) | estimateur client ≤ 2 s |
| `apps/web/src/lib/game/realtime.ts` | le canal porte les horloges |
| `docs/jeu/HORLOGES.md` | fiche du sous-système |

## Preuves

- **Moteur (`game`)** : `ruff` propre, `828 passed` (dont 32 horloges) — `uv run pytest -q`.
- **API** : `ruff` propre, `alembic upgrade head` atteint `d4e1f2a3b5c6`, `992 passed, 2 failed`.
  Les **2 échecs sont étrangers au lot** : `test_catalogue_seed.py` dépend de `pg_dump`/`psql`
  (postgresql-client), absents du PATH de cette session chimera — sa propre docstring le documente,
  et la CI GitHub (ubuntu-latest) les a nativement. Tous les tests de parties/horloges passent (44).
- **Web** : `type-check` propre, `lint` sans erreur (un *warning* pré-existant, `_url` dans
  `game-realtime.test.ts`, étranger au lot), `vitest` `188 passed`, `build` réussi.
- Base de test API : `pbm_jtimer_test` créée pour la session (le catalogue de référence
  `pbm_catalogue_ref` n'est jamais touché).

### Critères d'acceptation

- [x] **Les durées sont des paramètres de configuration, modifiables sans redéploiement du moteur** —
  `settings.horloge_*` (environnement) → `ConfigHorloges`, figée par partie à la création ; aucune
  durée en dur dans le moteur (`test_games_horloges::test_config_horloges_vient_des_reglages`).
- [x] **Une expiration produit toujours une action journalisée et jamais un blocage** — `fin_tour`,
  `expirer_demande`, `defaite_temps` ; `test_expiration_budget_journalise_une_defaite_au_temps` +
  `test_horloges_transitions`.
- [x] **Le temps affiché ne s'écarte jamais de plus de deux secondes du temps serveur** — l'estimateur
  client se recale sur la vérité serveur à chaque événement (`game-horloges.test.ts`).

### Mission (tests exigés)

- [x] **Expiration pendant une demande adressée à l'adversaire** —
  `test_horloges_transitions::test_expiration_decision_adverse_applique_la_reponse_par_defaut` : c'est
  le tour d'alice, l'horloge de **décision de bob** expire, le moteur applique la réponse par défaut.
- [x] **Reprise après pause** — `test_pause_gele_le_decompte_et_la_reprise_ne_consomme_rien` ;
  intégration `test_pause_puis_reprise_de_deconnexion`.
- [x] **Dérive d'horloge client** — `game-horloges.test.ts` (recalage, pas de dérive accumulée).

## Écarts au plan

- Le **plateau de jeu** n'existe pas encore : le lot livre le moteur de temps, l'autorité serveur et
  l'estimateur client ; le **branchement visuel** (afficher les horloges, avertissements sonores et
  visuels) suivra avec le lot d'écran de partie. La capture « maquette » n'a donc pas d'écran
  d'horloge à comparer à ce stade.
- Il n'existe pas encore d'orchestration de tour côté API (Checkup/début de tour enchaînés
  automatiquement) : les actions par défaut sont donc des **coups autonomes** (`fin_tour` entre en
  Checkup ; l'enchaînement se fera quand l'orchestration arrivera).

## Reste à faire (hors lot)

- Avertissements **sonores et visuels** à l'approche de l'expiration (lot d'écran de partie).
- **Abandon** sur déconnexion prolongée au-delà de la grâce : `j-deconnexion-abandon`.
- Afficher l'horloge sur le plateau et l'estimateur recalé à l'écran.
