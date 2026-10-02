# Compte rendu — `j-autorite-vues`

**Lot** : Autorité du serveur — le client ne voit que ce qu'il a le droit de voir.
**Piste** : Serveur de parties (couloir J-SRV, chimera) · **Jalon** J1 · P0 · palier 9.
**Branche** : `roadmap/j-autorite-vues` · **Machine** : chimera (worktree `~/dev/wt-j-autorite-vues`),
pilotée depuis devAI.

## Résumé

Le serveur fait désormais autorité par **une seule porte de sortie**. Tout ce qui part vers un
client — l'état projeté *et* les événements diffusés — passe par `pbm_game.sortie.projeter`, câblé à
l'API par `pbm_api.games.projection`. Pas de filtrage « par route » qu'une route oubliée trahirait :
au-delà de cette porte, aucune donnée brute de partie ne circule. Trois pièces :

- **Point de sortie unique** (`pbm_game.sortie.projeter`) : compose `vue(etat, joueur)` (déjà posée
  par `j-modele-etat`), les jetons de récompenses et la projection des événements.
- **Jetons opaques** (`pbm_game.sortie.jetons.Jetonneur`) : une carte cachée qu'il faut pouvoir
  *désigner* sans la révéler (les récompenses face cachée) est exposée par un HMAC-SHA256 tronqué,
  clé par un secret serveur (dérivé de la graine) et une **époque** (nombre de mélanges du deck).
  Stable dans une époque (repère d'écran après F5), **non-corrélable d'un mélange à l'autre** : un
  jeton capturé avant un mélange ne résout plus rien après.
- **Projection des événements** (`pbm_game.sortie.evenements`) : filtrage **structurel** par un
  registre `PROJECTEURS` ; un type d'événement sans projecteur est **refusé**, jamais diffusé brut
  (D9). La pioche n'est pas décrite pareil aux deux joueurs : le piocheur voit les identités (elles
  entrent dans sa main), l'adversaire n'a que le nombre.

Côté API, deux routes passent par l'adaptateur unique : `GET /games/{id}/state` (vue autoritaire) et
`POST /games/{id}/actions` (coup validé — auteur imposé par la session). Un coup illégal est refusé
(422 motivé) **sans altérer l'état**, tracé, et une **rafale** de coups illégaux lève une alerte
anti-triche.

## Livrables

- **Paquet moteur `pbm_game.sortie`** (`apps/game/src/pbm_game/sortie/`, pur, aucune E/S) :
  - `jetons.py` — `Jetonneur` (`jeton`, `resoudre`) + `secret_jetons(graine)`.
  - `evenements.py` — `projeter_evenement()` + registre `PROJECTEURS` (tout `EVT_*` déclaré ;
    inconnu → refus).
  - `__init__.py` — `projeter(etat, evenements, *, pour, jetonneur)`, le point de sortie unique.
- **Adaptateur API `pbm_api.games.projection`** : `vue_autoritaire(etat, rng, …)` et
  `projeter_resultat(resultat, …)` — dérivent secret/époque, mappent `user_id → joueur_id`, et
  délèguent au moteur. Aucune route ne refiltre à la main.
- **Routes** (`pbm_api.routers.games`) : `GET /games/{id}/state`, `POST /games/{id}/actions`
  (+ schéma `ActionIn`, mapping des erreurs du service → 404/409/422).
- **Traçage + alerte** dans `appliquer_action` : `_journaliser_refus()` (WARNING par refus, ERROR en
  rafale), `rng_compteurs` ajouté à `ResultatAction` (l'API en dérive l'époque des jetons).
- **Docs** : fiche `docs/jeu/AUTORITE-VUES.md` ; renvoi ajouté dans `docs/jeu/ETAT.md`.

## Preuves

- **Moteur** (`apps/game`, job `game` — pur, rejoué à chaque lot) : `uv run pytest` →
  **646 tests verts** (632 + 14 nouveaux : `test_sortie_jetons.py` 8, `test_sortie_projection.py`
  6 ; `test_state_projection.py` porté de 300 à **1 000 états**, même nombre de tests). `ruff` vert.
- **API** (`apps/api`, job `api`) : `test_games_projection.py` (6 tests) + suites de parties
  existantes → **22 verts** contre une base Postgres isolée (conteneur éphémère + base dédiée
  `pbm_jav_test`, redis db 15 — aucune base partagée touchée). `ruff` vert.
- **Critères d'acceptation** :
  1. *Test de non-fuite vert, à chaque modif du moteur/scripts* → `test_sortie_projection.py`
     (1 000 états) dans le job `game`, qui tourne sur chaque lot moteur. ✅
  2. *Coup illégal → refus motivé, état jamais altéré* → `test_action_illegale_refusee_et_etat_inchange`
     (422 motivé, `current_numero` inchangé, coup légal 0 toujours jouable ensuite). ✅
  3. *Jetons non traçables d'un mélange à l'autre* → `test_jeton_d_une_autre_epoque_ne_resout_plus_rien`
     + `test_ordre_des_jetons_ne_suit_pas_l_ordre_des_cartes_entre_epoques`. ✅

## Écarts au plan

- **Réponses de route typées + `pnpm gen:api`** : `GET /state` et `POST /actions` renvoient un
  `dict` JSON (la vue est une structure dynamique). Le client TypeScript n'est **pas** régénéré : le
  front ne consomme pas encore ces routes (ce sera `j-temps-reel`). La CI web reste verte (aucun
  import côté front). Un schéma de réponse typé accompagnera le canal temps réel, quand l'écran de
  jeu le consommera.
- **Jetons de récompenses** : au jalon J1, l'état initial (`j-partie-service`) ne pose **pas** de
  récompenses (mise en place réelle = `j-initialisation`) ; `recompenses_jetons` est donc une liste
  vide en partie réelle aujourd'hui. Le mécanisme est pleinement exercé et prouvé côté moteur
  (`fabrique_etat` pose 0–6 récompenses), prêt pour l'initialisation.

## Reste à faire (hors périmètre, aux lots suivants)

- `j-temps-reel` : diffuser chaque coup **par destinataire** via ce même point de sortie, et typer
  la charge utile.
- `j-securite-jeu` : revue de sécurité du jeu avant ouverture (l'alerte de rafale y trouvera son
  exploitation/supervision).
- L'alerte de rafale est **en mémoire du process** (sonde, pas limite de débit dure) : une
  supervision persistante relève de `j-securite-jeu`.
