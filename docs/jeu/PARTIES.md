# Parties — la persistance et l'orchestration côté serveur (lot `j-partie-service`)

> L'**enveloppe** qui transforme le moteur de règles pur (`pbm_game`) en parties réelles : deux
> comptes, deux decks, un journal persistant, et une partie qui survit à un redémarrage du serveur.
> Le moteur reste pur (ni HTTP ni base) ; tout ce qui lit la base ou tient une transaction vit dans
> `apps/api/src/pbm_api/games/` (le moteur ne reçoit que des données). Code : `pbm_api.games`.

## Principe : on ne stocke jamais le plateau, on stocke de quoi le rejouer

Une partie **est** un état initial, une graine d'aléatoire et un journal d'actions numéroté
(principe « tout est rejouable » du jalon J1). L'état courant n'est qu'un **cache** reconstructible
par rejeu. Quatre tables (migration `c5f1a9e3b7d0`) :

| Table | Rôle |
|---|---|
| `games` | l'enveloppe : `etat_initial` (JSON), `graine` (hex, **secret serveur**), `engagement` (commit-reveal), `current_numero`/`current_empreinte` (cache), statut, `vainqueur_user_id`/`raison_fin`, `last_action_at`/`expires_at` |
| `game_players` | deux sièges (`seat` 0/1), chacun un `user_id` et le `deck_id` joué |
| `game_events` | le **journal**, *append-only* : `(numero, auteur, action, evenements, horodatage, empreinte)`. Unicité `(game_id, numero)` |
| `game_snapshots` | **instantanés** de compaction : `(numero_entrees, etat, rng_etat, empreinte)`. Unicité `(game_id, numero_entrees)` |

- **L'identifiant de joueur du moteur est `str(user_id)`** — déterministe, donc rejouable. L'état
  initial, le journal et l'empreinte en dépendent : jamais un alias mutable ni un compteur de session.
- **La graine est un secret** : elle n'est **jamais** renvoyée au client en cours de partie (sinon
  la pioche adverse serait prévisible). Seul l'`engagement` (son empreinte) est publiable.
- **Rien ne met à jour une entrée de journal** : une entrée écrite ne bouge plus. C'est ce qui rend
  le rejeu fidèle et l'anti-triche possible.

## La boucle d'application (`appliquer_action`)

Dans **une** transaction, le serveur faisant autorité :

1. charge la partie **sous verrou de ligne** (`SELECT … FOR UPDATE`) et vérifie la participation
   (sinon 404, jamais 403 — pas de fuite) et que la partie est en cours (sinon 409) ;
2. **idempotence par numéro d'action** (risque nommé du lot : double-clic, rejeu réseau) — le numéro
   d'action est la **clé d'idempotence** :
   - `numero_attendu == current_numero` → on applique ;
   - `numero_attendu < current_numero` et **le même** coup est déjà au journal → rejeu idempotent,
     rien n'est réécrit (`rejoue=True`) ;
   - sinon (autre coup au même numéro, ou numéro en avance) → `ConflitNumero` (409) ;
3. reconstruit l'état courant, rejoue l'action par le moteur (`pbm_game.journal.appliquer` ; un refus
   lève `ActionRefusee`, 422), écrit l'entrée de journal, met à jour le cache, et tous les
   `INTERVALLE_INSTANTANE` coups fige un instantané de compaction ;
4. **commit** : journal, cache et instantané passent ensemble ou pas du tout.

Le **verrou de ligne** sérialise les requêtes concurrentes ; la **contrainte d'unicité
`(game_id, numero)`** est le backstop dur (une course perdue échoue au lieu d'écrire deux fois le
même coup). Les deux ensemble garantissent qu'un coup n'est jamais appliqué deux fois.

## Reprise (`reprendre_partie`) — survit à un redémarrage complet

On recharge le **dernier instantané** (≤ `current_numero`) et on **rejoue la queue** des entrées
postérieures (`pbm_game.journal.reprendre`), qui vérifie l'empreinte de l'instantané puis de chaque
coup. On **compare l'empreinte** reconstruite à `current_empreinte` : un écart lève, jamais de
reprise silencieuse sur un état douteux. Rien n'est gardé en mémoire d'un redémarrage à l'autre.

## Création (`creer_partie`) — decks résolus en scripts

Chaque deck est **résolu en scripts** : chaque carte est compilée en `DefinitionCarte` via
l'adaptateur `pbm_api.jeu.catalogue.definition_depuis_card`. Une carte qui ne se compile pas (PV,
stade, marqueur de règle, coût de retraite manquants ou incohérents) fait **refuser la partie**
(`CartesNonJouables`, cartes nommées) — un effet non implémenté n'est jamais approximé (D9).

L'état initial de ce lot est **minimal** : chaque joueur reçoit son deck dans sa **pioche** (ordre
non mélangé), rien d'autre. Le mélange est une action journalisée, joué par la **mise en place**.

## Expiration et purge

- `expirer_parties` fige les parties en cours **inactives** au-delà de `DELAI_INACTIVITE` (chaque
  coup repousse `expires_at`) — une partie ne reste jamais suspendue. Renvoie et **journalise** le
  compte (jamais un balayage muet).
- `purger` supprime les parties **mortes anciennes** (terminées/expirées, > `ANCIENNETE_PURGE`) et
  les **instantanés superflus** (on ne garde que le plus récent par partie), avec une métrique
  `{instantanes_purges, parties_purgees}` journalisée.

## Ce qui est délibérément reporté (D9 — on ne l'approxime pas)

| Reporté à | Ce que ce lot ne fait pas |
|---|---|
| `j-initialisation` | la vraie mise en place : mélange, main de sept, mulligans, actif et banc face cachée, six récompenses |
| `j-lancement-partie` | la **route de création** (choix du deck, adversaire, tirage au sort R-4.7) — ici la création se fait par le service |
| `j-autorite-vues` | la **vue autoritaire** (plateau projeté sans la main adverse ni la graine) et la **restriction aux coups légaux** (`actions_legales`) — ce lot valide mécaniquement via `appliquer` (type inconnu / coup impossible refusés) |
| `j-temps-reel` | la **diffusion** temps réel des événements — ici ils sont **renvoyés** à l'appelant |

## Routes (lecture seule, bornées au participant)

- `GET /games` — les parties du joueur courant ;
- `GET /games/{id}` — le détail (statut, sièges, engagement) ou **404** s'il n'y participe pas.

La graine n'y apparaît jamais ; seul l'engagement est exposé.
