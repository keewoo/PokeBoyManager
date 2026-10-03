# Autorité du serveur — le client ne voit que ce qu'il a le droit de voir (lot `j-autorite-vues`)

> **Le serveur fait autorité, et il n'a qu'une porte de sortie.** Tout ce qui part vers un
> client — l'état projeté *et* les événements diffusés — passe par **une seule fonction**. Pas de
> filtrage « par route » qu'une route oubliée trahirait : au-delà de cette porte, aucune donnée
> brute de partie ne circule. Code moteur : `pbm_game.sortie` ; adaptateur API : `pbm_api.games.projection`.

Ce lot s'appuie sur la projection d'état déjà posée par `j-modele-etat` (voir `ETAT.md` §
« Information publique vs cachée ») et l'étend en **point de sortie unique**, y ajoute les **jetons
opaques** et la **projection des événements**, puis câble l'API dessus.

## Le point de sortie unique — `pbm_game.sortie.projeter`

`projeter(etat, evenements, *, pour, jetonneur=None)` renvoie, pour le joueur destinataire `pour`,
un `dict` JSON-natif :

```
{"vue": <état projeté>, "evenements": [<événement projeté>, ...]}
```

Il compose trois briques, et **rien** ne sérialise une partie vers un client en dehors de lui :

- `vue(etat, pour)` — l'état réduit à ce que `pour` a le droit de voir (main adverse et pioches en
  **nombre** seulement, récompenses en nombre, zones publiques en clair). Inchangé depuis `ETAT.md`.
- les **jetons de récompenses** — quand un `jetonneur` est fourni, la vue du destinataire gagne
  `recompenses_jetons` : un jeton opaque par emplacement de récompense (voir plus bas).
- la **projection des événements** — chaque événement est redécrit pour son destinataire.

## Jetons opaques des cartes cachées — `pbm_game.sortie.jetons`

Une carte d'une zone cachée que le client doit pouvoir **désigner** sans en connaître l'identité
(ses récompenses face cachée : il choisit laquelle prendre après un K.O.) n'est jamais exposée par
son `instance_id`. On lui donne un **jeton opaque** — un `HMAC-SHA256` tronqué (préfixe `jc_`), clé
par un **secret serveur** et une **époque** :

| Propriété | Comment | Pourquoi |
|---|---|---|
| **Opacité** | HMAC clé par un secret dérivé de la graine (jamais révélée, R-4) | sans le secret, rien à « décoder » côté client |
| **Stable dans une époque** | même carte → même jeton | l'écran garde un repère stable entre deux vues (reconnexion, F5) |
| **Non-corrélable entre deux mélanges** | l'**époque** (= nombre de mélanges du deck) entre dans la clé | un jeton capturé **avant** un mélange ne **résout plus rien après** (`resoudre` → `None`) : on ne suit pas une carte d'un mélange à l'autre |

Le serveur retraduit un jeton en `instance_id` avec `Jetonneur.resoudre(jeton, candidats)` — **parmi
un ensemble légitime de candidats** (p. ex. les propres récompenses du joueur), jamais « dans le
vide » ; `None` est un refus explicite, pas un repli silencieux. Le secret et l'époque sont
**fournis** au moteur (pur) par l'adaptateur API : secret = `secret_jetons(graine)`, époque =
nombre de tirages du flux `flux_melange_deck(joueur)` dans le journal du Rng.

## Projection des événements — `pbm_game.sortie.evenements`

Un même coup n'est pas **décrit pareil** aux deux joueurs quand une information est cachée. Le
filtrage est **structurel** : chaque type d'événement a son projecteur dans le registre
`PROJECTEURS`. Un type **absent du registre est refusé** (`ValueError`), jamais diffusé brut —
c'est la garde qui fait qu'un futur événement ajouté sans projecteur **casse bruyamment** au lieu de
fuir en silence (D9).

Deux événements portent de l'information cachée et ont un **projecteur dédié** :

- `cartes_piochees` (R-5.2) — le **piocheur** voit les `instance_id` tirés (ils entrent dans sa
  main, qu'il voit) ; l'adversaire n'apprend que le **nombre**. Les identités sont **retirées**,
  pas remplacées par un jeton (une carte en main n'a pas à être désignée par l'adversaire).
- `main_revelee` (R-4.4) — la main d'un **mulligan** est **révélée à l'adversaire** (seul moment où
  une main est publique). L'adversaire reçoit les **`ref`** (il constate l'absence de base), jamais
  les **`instance_id`** : ces cartes retournent aussitôt dans la pioche cachée, et leur laisser un
  `instance_id` donnerait un repère de suivi (on choisit le **moins révélateur**). Le propriétaire
  voit sa propre main en entier.

Les autres événements du jeu sont **publics** (projecteur `_public`), inchangés — mais déclarés, car
chacun **doit** figurer au registre. Leur décision de visibilité, citée à `REGLES.md` :

| Événement | Règle | Pourquoi public |
|---|---|---|
| `placement_cache` | R-4.2 | ne porte **que** le joueur — le contenu posé face cachée n'y est jamais |
| `mise_en_place_prete` | R-4.5 | résumé public : mulligans et cartes bonus par joueur |
| `mise_en_place_revelee` | R-4.2/R-4.3 | la révélation **rend** Actif et banc publics (refs, nombres) |
| `mulligan` | R-4.5 | numéro de mulligan et à qui revient la carte bonus — aucune identité |
| `energie_attachee` | R-5.4 | attacher une énergie est un geste public (zone en jeu) |
| `fin_tour` | R-5.8 | joueur et phase quittée |
| `cout_paye` | R-9.2 | coût payé par des énergies **attachées** (donc publiques) |
| `effet_resolu` / `effet_sans_cible` | — | source (carte en jeu) + règle |
| `verrou_pose` / `verrou_leve` | R-12 | nom, portée, source — aucune identité cachée |
| `dsl_pile_ou_face` | — | pile ou face (nombre de pièces et de faces) |
| `dsl_cout_impayable` | — | un coût d'effet n'a pas pu être payé — fait public |

ainsi que phase, tour, attaque, confusion, dégâts, K.O., promotion, retraite, échange, checkup,
expiration d'effet, pose et évolution de Pokémon, mélange, fin de partie.

### Le système d'effets de carte — différé, nommément

Les événements du DSL et des **demandes de décision** (`demande_emise`, `demande_repondue`,
`demande_expiree`, `dsl_choix`, `dsl_primitive`) peuvent porter des **identités cachées** — p. ex.
une primitive `piocher`/`chercher` nomme la carte tirée, secrète à l'adversaire. Leur projection
n'est donc **pas** publique : elle se fera **par destinataire**, et c'est le **lot des effets de
carte** qui la livrera, le jour où une carte au script DSL entrera réellement en jeu (aucune partie
J1 ne les émet). Ils sont tenus **hors** de `PROJECTEURS` et listés **nommément** dans
`DIFFERES_SYSTEME_EFFETS` (test `test_parite_evenements_projecteurs`) — pas ignorés : tant qu'ils
n'ont pas de projecteur par destinataire, `projeter_evenement` les **refuse** (500 bruyant plutôt
que fuite), ce qui est le comportement voulu avant leur livraison.

### La garde de parité (lot `fix-projection-evenements`)

Deux tests ferment la faille qui avait bloqué la livraison des coups du joueur (le registre ne
couvrait pas les événements de la mise en place / du timer, et `POST /actions` répondait 500) :

- `test_parite_evenements_projecteurs` (job `game`) relève **par lecture statique** toutes les
  constantes `EVT_*` de **tout** `pbm_game` — pas seulement `journal.modele`, car le défaut venait
  d'un type défini ailleurs (`cout_paye` dans `combat/`) — et exige que chacune soit **projetée ou
  nommément différée**. Un futur événement sans projecteur casse en CI, plus jamais en PROD ;
- `apps/api/tests/test_games_http_ws_partie_complete.py` (job `api`) **joue une partie entière par
  les routes HTTP et le canal temps réel** — le chemin que les tests de partie ne franchissaient
  pas — et vérifie à chaque coup : 200 (plus de 500), diffusion aux deux joueurs, et aucune fuite
  dans la vue de chacun.

## Câblage API — la vue autoritaire et le coup validé

`pbm_api.games.projection` est l'adaptateur : il dérive secret et époque, mappe `user_id` →
`joueur_id` (`joueur_id_de`), et appelle `projeter`. **Toute** sortie HTTP (et demain le canal temps
réel `j-temps-reel`) passe par lui. Deux routes (`pbm_api.routers.games`) :

| Route | Rôle |
|---|---|
| `GET /games/{id}/state` | la **vue autoritaire** du joueur courant : état reconstruit du journal, projeté par `vue_autoritaire`. Jamais la main adverse, l'ordre d'une pioche ni la graine. 404 si non-participant (pas de fuite d'existence). |
| `POST /games/{id}/actions` | jouer un coup. L'auteur est **imposé** depuis la session (jamais le corps). Coup illégal → **422 motivé, état inchangé** ; conflit de numéro / partie close → 409. Réponse : la vue projetée **après** le coup + ses événements (jamais l'état brut). |

### Traçage des refus et alerte anti-triche

Un coup refusé n'est **jamais** avalé en silence : `appliquer_action` le trace (WARNING) avec sa
cause (partie, joueur, type, motif). Si un même joueur accumule les coups illégaux dans une fenêtre
courte (`FENETRE_REFUS`, `SEUIL_REFUS_RAFALE`), on émet une **alerte** (ERROR) — signe d'un client
modifié qui sonde l'autorité du serveur. On ne **bloque** pas le joueur pour autant : le serveur
fait déjà autorité (l'état n'a pas bougé) ; l'alerte sert la supervision, pas le refus.

## Ce qui garantit la non-fuite

- **Moteur** (`apps/game`, job `game` de la CI — pur, sans E/S, donc rejoué **à chaque lot**) :
  `test_sortie_projection.py` parcourt la sortie de **1 000 états** aléatoires et vérifie qu'aucun
  identifiant d'une zone cachée (pioches, récompenses, main adverse) ne survit, jetons compris ;
  `test_sortie_jetons.py` prouve l'opacité et la non-corrélation entre deux mélanges.
- **API** (`apps/api`, job `api`) : `test_games_projection.py` vérifie le câblage — vue sans graine
  ni main adverse, carte piochée invisible à l'adversaire, accès croisé en 404, coup illégal en 422
  sans effet, traçage et alerte de rafale.

> Ce lot prépare `j-temps-reel` (qui diffusera, par destinataire, via ce même point de sortie) et
> `j-securite-jeu` (la revue de sécurité du jeu avant ouverture).
