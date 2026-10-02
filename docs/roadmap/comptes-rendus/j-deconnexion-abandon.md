# Compte rendu — `j-deconnexion-abandon`

**Déconnexion, abandon, désertion : une partie ne reste jamais suspendue.**
Jalon J1 · piste Serveur de parties · couloir J-SRV (chimera). Exécuté sur chimera, piloté depuis
devAI.

## Résumé

Le lot distingue les **trois cas** d'un joueur qui part, aux conséquences différentes, et garantit
qu'aucune partie ne reste « en cours » indéfiniment. Toute clôture automatique est un **coup
journalisé** (« tout est rejouable ») dont le motif part dans l'historique — jamais un nettoyage
muet (le risque nommé du lot).

- **Coupure passagère** — déjà posée par `j-timer` (pause de grâce qui gèle les horloges,
  reprise à la reconnexion sans débiter le temps gelé). Couverte par un test dédié.
- **Abandon volontaire** — route dédiée `POST /games/{id}/abandon` (forfait, l'adversaire gagne,
  raison `abandon`, R-14.3), sans numéro d'action à deviner ; la confirmation est à l'écran.
- **Désertion** — une pause qui **dépasse sa grâce** clôt la partie par forfait du joueur qui ne
  revient pas (coup système `deserter`, raison `desertion`). C'est l'**affinement** de `j-timer`,
  qui se contentait de reprendre les horloges : la partie se clôt dès la fin du délai annoncé, sans
  attendre que le budget du déserteur s'épuise.
- **Balayage des parties fantômes** — `expirer_parties` clôt chaque partie sans activité au-delà du
  **plafond configuré** par un coup système `expirer_inactivite` (statut `expiree`, raison
  `inactivite`, **aucun vainqueur**), et `purger` supprime les mortes anciennes. Les deux tournent
  dans un **cron léger** du worker arq (`games_maintenance_task`, toutes les 10 min), posé sur tous
  les nœuds y compris la PROD — ce n'est pas un traitement lourd.

Les clôtures forcées vivent dans le **moteur pur** (`pbm_game.fin_forcee` : `deserter`,
`expirer_inactivite`), au même titre que les expirations d'horloge (`j-timer`) : rejouables,
testables sans base.

## Critères d'acceptation

- [x] **Aucune partie ne reste « en cours » plus longtemps que le plafond configuré.** Plafond
  `JEU_INACTIVITE_PLAFOND_H` (défaut 72 h), appliqué par `expirer_parties` déclenché par le cron
  `games_maintenance_task`. Testé : `test_balayage_clot_les_fantomes_avec_motif_journalise`.
- [x] **Chaque clôture automatique porte son motif dans le journal et dans l'historique.** Désertion
  et inactivité écrivent une entrée de journal (`deserter` / `expirer_inactivite`, auteur `systeme`)
  et posent `raison_fin` (lu par `GameSummaryOut`/`GameDetailOut`). Testé côté moteur
  (`test_fin_forcee`), service (`test_games_horloges`, `test_games_deconnexion_abandon`) et route
  (`/games` renvoie `raison_fin`).
- [x] **La reprise dans le délai ne coûte aucun temps d'horloge au-delà de la pause prévue.** Testé :
  `test_reprise_dans_le_delai_ne_coute_pas_de_temps` (10 s débitées, 100 s de pause non débitées).

## Livrables

- **Moteur** (`apps/game`) :
  - `pbm_game/fin_forcee.py` — transitions système `deserter` (forfait, raison `desertion`) et
    `expirer_inactivite` (clôture sans vainqueur, raison `inactivite`), enregistrées dans le
    `REGISTRE` du journal à l'import (motif banc/cartes/horloges) ;
  - `journal/modele.py` — constantes `ACTION_DESERTER`, `ACTION_EXPIRER_INACTIVITE`,
    `RAISON_DESERTION`, `RAISON_INACTIVITE` ;
  - `journal/transitions.py` — désertion et inactivité ajoutées aux actions permises pendant une
    demande de décision (`_ACTIONS_PENDANT_DEMANDE`) ;
  - `__init__.py` — import pour effet de `fin_forcee`.
- **API** (`apps/api`) :
  - `games/service.py` — `abandonner_partie` (abandon volontaire), `expirer_horloge` affiné
    (désertion à l'expiration de la pause), `expirer_parties` réécrit (clôture journalisée par
    coup système, une partie à la fois sous verrou), helper mutualisé `_appliquer_coup`, plafond
    d'inactivité lu de la configuration (`_delai_inactivite`) ;
  - `games/horloges.py` — adaptateur `joueur_en_pause` (nomme le déserteur) ;
  - `routers/games.py` — route `POST /games/{id}/abandon` (bornée au participant, diffusée) ;
  - `worker.py` — `games_maintenance_task` + cron léger `_light_cron_jobs()` (10 min, tous nœuds) ;
  - `config.py` — réglages `jeu_inactivite_plafond_h`, `jeu_purge_anciennete_j`.
- **Docs** : `docs/ARCHITECTURE.md` (§ Déconnexion, abandon, désertion, inactivité),
  `docs/LIVRAISON.md` (variables d'environnement + cron de maintenance).

## Preuves

Lancé sur chimera (WSL Ubuntu-24.04), Python 3.12 — la CI GitHub fait foi.

- **Moteur** : `uv run ruff check .` → *All checks passed* ; `uv run pytest -q` → **836 passed**
  (dont `test_fin_forcee.py` : désertion, inactivité, refus auteur/joueur, R-14.6, abandon et
  désertion pendant une demande).
- **API** : `uv run ruff check .` → *All checks passed* ; tests ciblés (base de test migrée à head,
  Redis) → **58 passed** : `test_games_service.py`, `test_games_horloges.py`,
  `test_games_deconnexion_abandon.py`, `test_games_routes.py`, `test_games_ws_routes.py`,
  `test_games_temps_reel.py`, `test_games_projection.py`, `test_game_access.py`.
- Import du worker vérifié : `games_maintenance_task` dans `WorkerSettings.functions`, `deserter` et
  `expirer_inactivite` dans le `REGISTRE` du moteur.

### Test d'accès croisé (exigé)

`test_route_abandon_forfait_acces_croise_et_historique` : l'intrus C (non participant) reçoit **404**
sur `POST /games/{id}/abandon` (pas de fuite d'existence) et la partie reste en cours ; B abandonne →
forfait, A gagne, `raison_fin = abandon` ; un second abandon → **409** ; l'historique de A porte le
motif.

### Maquette

Lot **serveur** (couloir J-SRV) : aucun écran livré. L'affichage honnête des deux côtés (« adversaire
déconnecté, N restant ») s'appuie sur les champs `en_pause`/`pause_joueur`/`pause_restant_s` déjà
renvoyés par les charges temps réel (`j-timer`) ; l'écran qui les consomme relève des lots d'interface.

## Écarts au plan

- **Comportement de `j-timer` affiné.** `expirer_horloge` ne *reprend* plus les horloges à
  l'expiration de la pause ; il déclare la **désertion**. Le test `j-timer`
  `test_pause_dont_la_grace_est_depassee_est_reprise_par_l_expiration` a été renommé et réécrit en
  `…_declenche_la_desertion`. C'est un choix assumé de ce lot (qui *possède* la désertion), pas une
  régression : il sert directement le but « une partie ne reste jamais suspendue ».
- Écriture du résultat **sur les comptes** : hors périmètre ici — c'est le lot `j-fin-effets-compte`
  (que ce lot débloque). Les clôtures posent `vainqueur_user_id`/`raison_fin` ; l'effet sur le compte
  viendra ensuite.

## Reste à faire / limites connues

- **Flottement du socket adverse et désertion.** `marquer_reconnexion` (hérité de `j-timer`) lève la
  pause à **toute** reconnexion sur la partie : si le socket du joueur *présent* se reconnecte pendant
  que l'autre est absent, la pause du déserteur est levée et son compte à rebours de désertion
  repart. La désertion reste correcte dans le cas courant (le présent reste connecté, l'absent ne
  revient pas) ; raffiner la pause par joueur relève d'un lot `j-timer` ultérieur.
- Le balayage des fantômes clôt **sans vainqueur** (abandon mutuel) ; la désertion *avec* vainqueur
  passe par le temps réel (socket du présent ouvert), pas par le balayage — c'est le partage voulu.
