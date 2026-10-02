# Canal temps réel d'une partie

> Lot `j-temps-reel` (jalon J1). Référence du protocole de diffusion des coups, de la reprise après
> F5 et du repli en interrogation. Le code vit dans `apps/api/src/pbm_api/games/temps_reel.py`
> (mécanique, sans transport), `apps/api/src/pbm_api/routers/games_ws.py` (WebSocket + repli HTTP) et
> `apps/web/src/lib/game/realtime.ts` (client). Pour une réimplémentation indépendante, ce fichier
> suffit ; il s'appuie sur le journal numéroté décrit dans `docs/jeu/JOURNAL.md`.

## Le numéro de séquence fait tout tenir

L'unité de diffusion est l'**entrée de journal**, numérotée 0, 1, 2… `current_numero` est le
**prochain** numéro attendu ; les entrées existantes portent `0..current_numero-1`.

Le client **applique par numéro, jamais par ordre d'arrivée**. C'est ce qui rend le canal insensible
au désordre et aux doublons (risque nommé du lot), et ce qui rend la reprise possible :

- un coup de numéro **≤ dernier appliqué** est un **doublon** → ignoré ;
- le coup **attendu** est `dernier appliqué + 1` → appliqué ;
- un numéro **plus grand** est un **trou** → le client ne devine pas, il **redemande tout depuis
  `dernier appliqué + 1`**.

Le serveur fait autorité : toute resynchronisation porte la **vue complète** de l'état courant, qui
prime. La vue vient du point de sortie unique du moteur (`pbm_game.sortie.projeter`) — jamais la main
adverse, ni l'ordre d'une pioche, ni l'identité d'une récompense.

## Resynchronisation — « donne-moi tout depuis N »

`resynchroniser(db, game, user_id, depuis)` (et la route HTTP `GET /games/{id}/sync?depuis=N`)
renvoient :

```jsonc
{
  "type": "resync",
  "numero": 12,          // current_numero : prochain numéro attendu
  "depuis": 7,           // borné à [0, numero]
  "vue": { … },          // état projeté courant — suffit à la reprise exacte (F5)
  "evenements": [        // la file des coups de numéro ∈ [depuis, numero), dans l'ordre
    { "numero": 7, "evenements": [ … ] },
    …
  ],
  "statut": "en_cours",
  "termine": false,
  "vainqueur_user_id": null,
  "raison_fin": null
}
```

Le travail est **borné** : on repart du dernier instantané ≤ `depuis`, on positionne l'état à
`depuis`, puis on ne rejoue que `[depuis, courant)`. Chaque coup rejoué est **revérifié** contre
l'empreinte du journal (« tout est rejouable ») — une divergence lève, jamais tue en silence. Les
jetons des cartes cachées sont projetés avec l'époque de ce point (cohérents avec la vue).

C'est la **seule** garantie de livraison : une coupure, un message perdu, un process distinct — tout
se rattrape par une resync, car le client détecte le trou par le numéro. Le WebSocket n'est qu'un
raccourci de latence.

## Messages du canal WebSocket

`WS /games/{id}/ws?depuis=N`. Après acceptation, le serveur envoie d'abord une resync depuis `N`.

**Serveur → client :**

| type | charge | sens |
|---|---|---|
| `resync` | voir ci-dessus | reprise / rattrapage |
| `evenement` | `numero`, `vue`, `evenements`, `termine`, `vainqueur_user_id`, `raison_fin` | un coup diffusé, projeté pour ce joueur |
| `battement` | `numero` | preuve de vie (toutes les 20 s de silence) **et** numéro courant du serveur : si le client est en retard, il redemande |
| `pong` | — | réponse à `ping` |
| `erreur` | `code`, `message` | message client invalide (jamais avalé en silence) |

**Client → serveur :**

| type | charge | effet |
|---|---|---|
| `souscrire` / `resync` | `depuis` | (re)synchronisation depuis un numéro |
| `ack` | `numero` | accusé de réception (supervision ; sans effet d'état) |
| `ping` | — | → `pong` |

Le serveur suit `transmis`, le plus grand numéro réellement émis. Une file d'abonné saturée (client
lent) ne perd **rien** : l'abonné est marqué, et le pilote lui renvoie une resync depuis `transmis+1`.

## Repli en interrogation périodique

Quand le WebSocket est impossible (réseau d'école, proxy), le client interroge `GET
/games/{id}/sync?depuis=N` en boucle et avance `depuis` au fil des réponses. **Plus lent, mais la
partie se termine** — et le client l'**annonce** (« connexion dégradée », `StatutConnexion`). Même
charge que la resync WebSocket : une seule mécanique, deux transports.

## Garanties (critères d'acceptation du lot)

- **F5 au milieu d'une partie, même au milieu d'une décision** : la resync porte la vue complète →
  le joueur revient exactement où il était.
- **Coupure de 60 s** : à la reconnexion, `depuis = dernier appliqué + 1` ramène tous les coups
  manqués, dans l'ordre, sans doublon.
- **Repli dégradé** : l'interrogation permet de finir la partie, et l'écran dit qu'on est dégradé.
