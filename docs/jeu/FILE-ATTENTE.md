# File d'attente et appariement — trouver un adversaire (lot `j-file-attente`)

> « Je veux jouer » doit aboutir à une partie en quelques secondes, ou à une réponse claire
> (« personne en ligne »). Ce lot pose la **file d'attente privée**, l'**appariement** et la
> **présence** — par-dessus le service de parties ([PARTIES.md](PARTIES.md)). Comme lui, tout ce qui
> lit la base ou parle à Redis vit dans `apps/api/src/pbm_api/games/` ; le moteur `pbm_game` reste
> pur. Code : `pbm_api.games.matchmaking`, `pbm_api.games.entry`, routeur `pbm_api.routers.matchmaking`.

## Le droit d'accès au jeu — « compte invité » (D11)

L'inscription est libre (D8), mais le jeu est **réservé**. Une colonne booléenne porte ce droit :

| Colonne | Rôle |
|---|---|
| `users.game_access` | droit d'accès au jeu, `false` par défaut (migration `d2b7f1a4c9e0`, additive) |

- Un compte sans ce droit ne voit **rien** du jeu : **toutes** les routes du jeu (`/matchmaking/*`
  **et** `/games/*`) répondent **404**, jamais 403 — pour un compte non invité, le jeu n'existe pas,
  exactement comme un objet d'un autre utilisateur. La garde est la dépendance FastAPI
  `pbm_api.auth.dependencies.require_game_access` (elle renvoie l'utilisateur, donc remplace
  `get_current_user` sur une route).
- Le droit se pose et se retire **hors ligne**, par l'administration — il n'existe **aucune** route
  HTTP pour l'accorder :

  ```bash
  uv run python -m pbm_api.admin set-game-access joueur@example.com on
  uv run python -m pbm_api.admin set-game-access joueur@example.com off
  ```

## La file, la présence, le verrou (Redis)

Tout l'état de la file vit dans Redis (non transactionnel, éphémère), préfixé par
`settings.redis_prefix` + `mm:` :

| Clé | Structure | Rôle |
|---|---|---|
| `mm:queue` | ZSET `score = horodatage d'arrivée`, membre = `user_id` hex | la file, ordonnée **par ordre d'arrivée** (FIFO) |
| `mm:deck:<user>` | STRING `deck_id`, TTL 1 h | le deck choisi à l'entrée (une entrée oubliée expire) |
| `mm:online` | ZSET `score = expiration du battement de cœur`, membre = `user_id` hex | présence des comptes invités en ligne |
| `mm:lock` | STRING jeton, `SET NX EX` | le **verrou d'appariement** (un seul détenteur à la fois) |

- **L'appariement est FIFO.** La proximité de niveau (évoquée par le plan) viendra **quand un
  classement de joueur existera** — il n'en existe aucun aujourd'hui (le module `ranking` classe des
  *cartes*, pas des joueurs). On ne l'approxime pas (D9) : FIFO strict, documenté comme tel.

## Jamais deux parties : le verrou, pas une relecture

Le risque du lot est une condition de course — **deux joueurs appariés chacun avec un troisième**.
La parade est un **verrou atomique** (`pbm_api.games.matchmaking.apparier`) :

1. `apparier` acquiert `mm:lock` (`SET NX EX`). S'il est déjà pris, un autre appariement tourne : on
   renonce **sans forcer** (notre entrée reste dans la file, elle sera prise au tour suivant).
2. Sous le verrou, tant qu'il reste ≥ 2 joueurs : on prend les **deux plus anciens**, on **écarte**
   (sans apparier) tout candidat déjà dans une partie en cours (garde « jamais deux parties »,
   revérifiée **en base**) ou dont le deck a expiré, on crée la partie
   ([`creer_partie`](PARTIES.md)), puis on retire les deux appariés de la file.
3. Le verrou est libéré par un **compare-and-delete** Lua (on ne supprime que *notre* jeton, jamais
   celui d'un appariement voisin).

Une seconde garde à l'entrée (`rejoindre`) refuse d'enfiler un joueur déjà en partie. Test de
concurrence réel (deux `apparier` concurrents sur trois joueurs, sessions distinctes) :
`test_concurrence_jamais_deux_parties`.

## Vérifier le deck à l'entrée (`pbm_api.games.entry.verifier_deck`)

Avant d'enfiler un joueur, son deck est vérifié — sinon l'appariement fabriquerait une partie
refusée à la création, et le joueur attendrait pour rien. Deux contrôles :

1. **Propriété** — le deck est bien celui du joueur, sinon **404** (`DeckIntrouvable`, pas de fuite).
2. **Scripts disponibles (D9)** — chaque carte se compile pour le moteur (même contrôle que
   `creer_partie`). Une carte non jouable est **nommée** avec sa raison → **422** (`DeckInjouable`).

> **Pourquoi pas la légalité de format ici** (60 cartes, max 4, possession en collection) : ces
> règles de *construction* vivent dans `pbm_api.decks.legality` (mission `v7-decks-legalite`) et
> s'appliquent quand on **bâtit** un deck. Le service de parties livré ne les impose pas : au jalon
> J1, la mise en place réelle (main de sept, bancs, six récompenses, deck de 60) est le lot
> `j-initialisation`. La porte « deck légal » s'ajoutera ici quand ce lot fera du deck complet
> l'unité de jeu — report explicite, pas un abandon silencieux.

## Présence et « personne en ligne »

`GET /matchmaking/presence` photographie les comptes invités : `en_ligne`, `en_partie`, `en_file`,
et `autres_disponibles` (en ligne, hors partie, **autres que soi**). Consulter la présence **bat le
cœur** du demandeur (le voir, c'est être en ligne). Quand `autres_disponibles` est nul, la réponse
propose les options de repli — `["invitation", "entrainement_bot"]` — chemins des lots
`j-invitations` et du bot : on **nomme** l'option, on ne l'implémente pas ici (D9).

## Les routes (`/matchmaking`, toutes gardées par `require_game_access`)

| Route | Rôle |
|---|---|
| `POST /matchmaking/queue` `{deck_id}` | entrer dans la file ; → `apparie` (partie créée) ou `en_attente` ; 404 deck d'autrui, 422 deck non jouable (cartes nommées), 409 déjà en partie |
| `GET /matchmaking/queue` | l'état réel : `apparie` / `en_attente` (rang, taille, temps) / `absent` |
| `DELETE /matchmaking/queue` | annuler la recherche (idempotent) |
| `GET /matchmaking/presence` | présence et options de repli |

Les écritures exigent le jeton CSRF, comme toute mutation utilisateur.
