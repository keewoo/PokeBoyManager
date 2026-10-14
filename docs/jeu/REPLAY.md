# Replay d'une partie — revoir, et partager

> Livré par le lot `j-replay` (jalon J4 — « la partie laisse une trace »). Le code vit dans
> `apps/game/src/pbm_game/journal/rejeu.py` (les états successifs, purs),
> `apps/api/src/pbm_api/games/replay.py` (la porte HTTP et le droit de regarder) et
> `apps/web/src/app/jeu/parties/[id]/replay/` (l'écran). La navigation pure est dans
> `apps/web/src/lib/game/replay.ts`.

## Pourquoi c'est presque gratuit

Le journal existe déjà (`docs/jeu/JOURNAL.md`) : une partie **est** un état initial, une graine et
une suite de coups numérotés. Le rejeu existe aussi — mais il ne répondait qu'à « où en est la
partie ». Le replay pose l'autre question : **« par où est-elle passée »**. D'où une seule addition
au moteur, et trois usages d'un coup : revoir sa partie, comprendre un désaccord de règle,
diagnostiquer une panne sans interroger le joueur.

## Côté moteur : `etapes` — la suite des états

`Etape` est un **rang** du replay : `rang` (combien d'entrées ont été appliquées), `entree` (le coup
qui y mène, `None` au rang 0), `etat`, `evenements` **recalculés**, et `empreinte`.

| Fonction | Ce qu'elle rend |
|---|---|
| `etapes(instantane, queue)` | les rangs depuis un instantané + la queue des entrées — **paresseux** |
| `etapes_partie(partie)` | les rangs 0..*n* depuis le début, sans emprunter d'instantané persisté |

Une partie de *n* coups a ***n+1* rangs** (0..*n*) : le rang 0 est l'état d'avant le premier coup.

Deux propriétés, et ce sont elles qui font qu'on peut croire un replay :

- **mêmes contrôles que le rejeu, au coup près.** Chaque rang recalcule l'empreinte de son état et
  la compare au journal ; un écart lève `RejeuDivergent` **sur le coup fautif**. Un replay ne
  s'aligne pas sur le journal, il le **contrôle** — c'est la différence entre « montrer une
  partie » et « montrer ce que le journal prétend ».
- **repartir d'un instantané donne les mêmes rangs** que le replay complet. C'est ce qui autorise
  la pagination côté serveur (page *k* repart du dernier instantané qui la précède) sans que la
  deuxième page montre une autre partie que la première.

Le paquet reste **pur** : `etapes` ne lit ni base, ni réseau. Ce qui lit le catalogue vit côté API.

## Côté serveur : trois décisions, trois risques fermés

### 1. Une partie en cours n'a pas de replay — 409

Pas « un replay tronqué », pas « un replay sans les zones cachées » : *pas de replay*. Le risque
nommé du lot est « servir le journal complet d'une partie en cours sous prétexte de replay », et une
porte qui ne s'ouvre qu'après la fin ne peut pas fuiter pendant. Le test le mesure avec un journal
**non vide**, sinon il ne prouverait rien.

### 2. « Vue complète » = les deux vues de joueur, pas une sortie brute

Le moteur n'a **aucune** sortie « tout voir » : `pbm_game.sortie.projeter` exige un joueur
destinataire. On n'en ajoute pas une — ce serait rouvrir, pour le replay, le chemin brut que
`j-autorite-vues` a supprimé, en espérant qu'aucune route ne s'y trompe. Donc :

| `vue` | Ce qui est servi | Qui peut la demander |
|---|---|---|
| `moi` | la vue du joueur de la session | les deux joueurs seulement |
| `complete` | **les deux** vues de joueur, côte à côte | les joueurs et les spectateurs autorisés |

Ce que les deux joueurs ont su, on peut le rendre ; ce que **ni l'un ni l'autre** n'a jamais su
(l'ordre du reste de la pioche, l'identité des récompenses non prises) n'a pas à l'être, et ne l'est
pas. Un spectateur qui demande `moi` reçoit **422** — jamais un repli silencieux sur `complete`,
qui lui donnerait *plus* que ce qu'il a demandé sans que personne le sache.

Deux retraits volontaires par rapport à la vue du plateau en direct :

- **aucun jeton opaque** (`recompenses_jetons`) : les jetons servent à *désigner* une carte cachée ;
  dans un replay il n'y a rien à désigner, donc rien à exposer ;
- **aucune action légale** : un rang de replay n'est pas un tour de jeu. Les servir donnerait à
  l'écran des coups cliquables sur une partie finie.

La **graine** accompagne la réponse d'une partie terminée **par les règles** (volet « reveal » du
commit-reveal, comme `j-lancement-partie` la révèle déjà) : c'est ce qui rend le replay vérifiable
de bout en bout. Une partie close pour **inactivité** ne la révèle pas.

### 3. Le droit de regarder vit en base, pas dans l'URL

`game_replay_shares` (`game_id`, `user_id`, `created_by_user_id`, unique sur les deux premiers).

Un **lien porteur** (`?jeton=…`) serait une autorisation qui voyage : collée dans une conversation,
journalisée par un intermédiaire, gardée dans un historique, elle ouvre la partie à qui la détient —
exactement ce que le critère du lot interdit (« le lien de replay n'est pas accessible à un compte
non autorisé »). Le lien partagé est donc **l'URL ordinaire** du replay ; ce qui se partage est le
**droit**, et il se retire aussi vite qu'il s'accorde.

Qui voit un replay :

1. les **deux joueurs**, de droit (leurs sièges le disent) ;
2. un **compte invité** (D11) à qui un joueur l'a ouvert nommément, par son **pseudo**.

Tout le reste → **404**, jamais 403 : pour un compte non autorisé, ce replay n'existe pas. Et
**regarder n'est pas administrer** : un spectateur autorisé reçoit 404 sur les routes de partage.

## Les routes

| Route | Qui | Quoi |
|---|---|---|
| `GET /games/{id}/replay?vue=&depuis=&limite=` | joueurs + spectateurs autorisés | une page de rangs |
| `GET /games/{id}/replay/partages` | les deux joueurs | à qui c'est ouvert |
| `POST /games/{id}/replay/partages` | les deux joueurs | ouvrir à un pseudo (idempotent) |
| `DELETE /games/{id}/replay/partages/{user_id}` | les deux joueurs | retirer le droit |

Codes : **404** pas le droit / pseudo inconnu / rien à retirer · **409** partie en cours ·
**422** vue impossible, pagination hors bornes, cible déjà joueuse de la partie.

### La pagination dit toujours ce qu'elle n'a pas servi

Une partie de quatre cents coups, c'est quatre cents états projetés (deux fois en vue complète) : on
ne les met pas dans une réponse. Chaque page porte `total`, `depuis`, `limite` et `complet`
(défaut 100 rangs, plafond **250**). Une `limite` au-delà du plafond est **refusée**, pas rognée : un
client qui croit avoir demandé mille rangs et n'en reçoit que deux cent cinquante en déduirait que la
partie finit là. Même raison pour le `depuis` hors bornes → 422 plutôt qu'une page vide.

## Côté écran

`/jeu/parties/{id}/replay`. Le plateau est le **même composant** qu'en jeu, sans `onJouer` : il
passe en lecture seule tout seul (aucune barre d'actions, aucune cible saisissable).

L'écran charge les pages jusqu'à `complet`, puis **navigue localement** — avancer, reculer, se
placer au curseur, lire en continu à ×0,5 / ×1 / ×2 / ×4. Aucun aller-retour par coup : c'est ce
qui rend le va-et-vient immédiat, et c'est la raison d'être de la pagination côté serveur.

Deux choses qu'il refuse de taire :

- **il ne se place jamais hors de ce qui est chargé** (`borner`) — sinon le curseur montrerait du
  vide en prétendant que la partie s'arrête là ;
- **une page manquante s'affiche** (« *n* coup(s) non chargé(s) ») ; un spectateur basculé en vue
  complète le lit à l'écran.

Le **fil du journal** est reconstruit **jusqu'au rang regardé** (`coupsJusqua`), avec les événements
du destinataire choisi : c'est la même suite que celle que ce joueur a reçue en direct, donc le fil
est identique à celui qu'il avait sous les yeux. En vue complète, on choisit **par quels yeux**
regarder (l'ordre vient des sièges, pour que « joueur 1 / joueur 2 » ne s'inverse pas d'un
chargement à l'autre).

## Ce que le lot ne fait pas

- Il n'**exporte pas** le journal en fichier pour le support : la réponse de la route porte déjà
  tout (coups, empreintes, graine révélée), mais aucun bouton d'export n'est posé.
- Il ne sert pas le **commentaire d'affichage** d'un coup (l'explication de l'IA adverse,
  `game_events.commentaire`) : il n'est pas porté par l'`Entree` du moteur, et le fil du journal se
  reconstruit sans lui.
- Il n'**anime** pas les coups (lot `j-anim-socle`) : le replay avance d'un état à l'autre.
- Il ne **pré-calcule** rien : chaque page rejoue depuis un instantané. Si une partie très longue
  rendait cela coûteux, la parade est un instantané plus fréquent, pas un cache de replay.
