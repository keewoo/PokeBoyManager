# Compte rendu — `j-coups-joueur`

**Coups du joueur : la partie se joue vraiment, de la mise en place à la victoire.**
Jalon J1, piste Serveur de parties. Exécuté sur **chimera** (couloir J-SRV), livré par devAI.

## Résumé

Avant ce lot, le générateur d'actions légales ne connaissait que « avancer la phase » et
« abandonner » (`FAMILLES_DEFAUT`) : impossible de poser, d'attacher une énergie ou d'attaquer.
Ce lot **branche les coups du joueur** de bout en bout — du moteur pur jusqu'au service de parties —
et **prouve** qu'une partie complète se joue par l'API jusqu'à la victoire par les six récompenses,
puis se rejoue à l'identique depuis son journal.

Le fil conducteur : **une seule source de vérité, la liste**. Chaque famille *liste* les coups
légaux depuis l'état et le catalogue ; la transition déjà livrée les *applique* ; `valider` vérifie
l'*appartenance* à la liste. Côté serveur, un coup soumis sur une partie jouable **doit** appartenir
à cette liste — ce qui vaut anti-triche (un paramètre falsifié ne correspond à aucun coup légal).

## Livrables

### Moteur (`apps/game`, paquet pur `pbm_game`)
- **`actions/familles_jeu.py`** — les familles qui ont besoin du catalogue : `FamillePoser`,
  `FamilleEvoluer`, `FamilleAttacherEnergie`, `FamilleAttaquer`, `FamilleRetraite`,
  `FamillePromouvoir`, `FamillePlacer`, et `familles_jeu(catalogue)`. `FAMILLES_DEFAUT` (sans
  catalogue) **reste inchangé** : le générateur garde son comportement sur des milliers d'états.
- **`cartes/attache.py`** — nouvelle transition `attacher_energie` (R-5.4) + type d'action et
  événement (`EVT_ENERGIE_ATTACHEE`). (Elle n'existait pas : `j-cartes-energies` n'avait livré que
  le modèle `DefinitionEnergie`.)
- **`combat/attaque.py`** + câblage de `_declarer_attaque` — la déclaration d'attaque **résout
  vraiment** coût (R-9.2), dégâts avec faiblesse/résistance (R-10), et K.O./récompenses/victoire
  (R-13/R-14) via la machinerie déjà livrée (`payer_cout`, `resoudre_degats`, `resoudre_kos`), qui
  n'était appelée par personne. Le chemin historique « sans données de carte » (degats:0) est
  conservé (compat `j-machine-tour`).
- **`mise_en_place/transitions.py`** — assoupli pour tolérer les cartes **non-Pokémon** (énergies) :
  les fiches de mise en place ne portent plus qu'un `stade` (une énergie n'a pas de `DefinitionCarte`).

### Serveur (`apps/api`)
- **`jeu/catalogue.py`** — `definition_energie_depuis_card` (énergies de base ; une spéciale, à effet
  non scripté, est refusée — D9). **`games/construction.py`** — `resoudre_deck` accepte désormais les
  cartes Énergie (un deck Pokémon + Énergies se crée).
- **`games/catalogue_jeu.py`** — `construire_catalogue_jeu(db, etat)` : le `CatalogueJeu` d'une partie.
- **`games/service.py`** — `demarrer_partie` (applique `mise_en_place_initiale`), `_piloter`
  (enchaîne les coups système — pioche de début de tour, Pokémon Checkup, passage au tour suivant),
  et dans `appliquer_action` la **validation d'appartenance** (anti-triche) pour une partie *jouable*.
  Une partie *brute* (decks en pioche, avant mise en place) garde la voie mécanique directe — c'est
  elle qu'exercent les tests de plumberie existants.
- **`games/actions.py`, `projection.py`, `routers/games.py`, `temps_reel.py`** — la vue autoritaire
  (`GET /state` et le canal temps réel) porte la **liste complète** des coups légaux pour son
  destinataire. **`games/lancement.py`** — démarre la mise en place après `creer_partie`.

### Front (`apps/web`)
- **Aucun changement nécessaire** : le plateau est générique (il affiche `actions_legales` et soumet
  `type`/`params`, illumine les cibles). Dès que le serveur expose les vrais coups, le plateau les
  joue. (Vérifié par lecture : `game-board.tsx`, `action-bar.tsx`, `interactions.ts`.)

## Preuves (CI GitHub fait foi)
- **Moteur** : `apps/game` — **876 tests** verts, ruff propre. Dont :
  - `tests/test_coups_joueur.py` — chaque famille (poser/évoluer/attacher/attaquer/retraite/
    promouvoir) listée ⇔ validée, chaque test citant son `R-x.y` ;
  - `tests/test_partie_complete.py` — **une partie complète jusqu'à la victoire par les récompenses**,
    puis `rejouer(journal)` redonne l'état final à l'identique (empreinte par empreinte).
- **Serveur** : `apps/api` — suite verte (936 tests de code ; les seuls échecs locaux sont d'ENV —
  bucket S3 et `pg_dump` absents de la WSL de dev, verts en CI). Dont :
  - `tests/test_games_partie_complete.py` — **une partie complète jouée PAR L'API**
    (`appliquer_action`, validation + orchestration) jusqu'à `derniere_recompense`, puis
    `reprendre_partie` reconstruit et **vérifie l'empreinte**.
  - Les ~30 tests de plumberie existants (idempotence, reprise, compaction, abandon, projection,
    temps réel, lancement) restent verts : la voie « partie brute » préserve leur contrat.

## Critères d'acceptation
- [x] `actions_legales` propose poser, évoluer, attacher, attaquer, battre en retraite, passer,
      promouvoir (et placer) quand c'est légal, jamais sinon — `test_coups_joueur`.
- [x] Une partie complète se joue **par l'API** jusqu'à la victoire par récompenses, et le rejeu
      redonne l'état final — `test_games_partie_complete` + `test_partie_complete`.
- [ ] Le plateau joue ces coups dans un navigateur (e2e à deux contextes) — **voir « Reste à faire »**.
- [x] Aucune règle réécrite côté écran ; aucun coup hors liste accepté par le serveur
      (validation d'appartenance = anti-triche).

## Écarts assumés (J1 « laid mais juste »)
- **Placement** : le joueur choisit son Actif ; les autres Pokémon de base de sa main le suivent
  **automatiquement au banc** (le choix fin du banc est une finition d'interface).
- **Retraite** : les énergies défaussées pour payer le coût sont les premières attachées
  (déterministe) ; le choix fin de *quelles* énergies défausser est une finition d'interface.
- **Promotion après K.O.** : exposée dès que l'Actif manque ; appliquée au plus tard au début du tour
  du joueur concerné (résultat identique au jalon J1, sans effet intermédiaire).

## Reste à faire
- **e2e Playwright à deux contextes** (critère 3) : le plateau étant générique et le serveur exposant
  désormais tous les coups (placement, énergie, attaque) via `/state` et le canal temps réel, il ne
  manque que le **test e2e** qui pilote deux navigateurs. Il n'a pas été livré ici parce que
  l'environnement de la flotte **ne peut pas lancer un navigateur Playwright en local**
  (`libnspr4`/`sudo`, cf. `docs/roadmap/comptes-rendus` antérieurs) : un e2e non vérifiable localement
  qui casserait le job `web` bloquerait la PR. C'est une suite focalisée à ajouter, vérifiée en CI.
