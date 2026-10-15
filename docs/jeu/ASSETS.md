# Fabrique d'images du jeu — variantes, cache, pré-chargement, budget de poids

> Lot `j-assets-pipeline` (jalon J3). À lire avant de toucher à la **taille** d'une image de carte,
> au **cache** d'une route d'image, au **pré-chargement** d'une partie, ou avant de relever un
> plafond de poids. Le *choix* entre ma photo et l'image officielle est une autre question : il vit
> dans [`RENDU-CARTES.md`](RENDU-CARTES.md) (décision DJ5).

Le risque que ce lot borne, tel que sa fiche le nomme : **une partie affiche jusqu'à 120 cartes.**
Sans pré-calcul et sans budget, le plateau se charge pendant une minute sur un téléphone en 4G, et
le jeu meurt là.

## Les deux variantes, et pourquoi deux

`j-rendu-carte` avait posé **une** variante de 420 px (45 Ko), servie aussi bien à la carte posée
dans l'arène qu'au zoom. 120 × 45 Ko = **5,2 Mo** par partie : le défaut était là.

| Variante | Taille | Poids réel | Plafond | Qui la charge |
|---|---|---|---|---|
| `plateau` | 192 × 268, WebP 76 | **12,2 Ko** | 18 Kio | `rendu.url` — l'arène, la main, la vignette d'une décision : **jusqu'à 120 fois** |
| `zoom` | 420 × 587, WebP 80 | **45,2 Ko** | 64 Kio | `rendu.url_zoom` — **une carte à la fois**, à la demande du joueur |

Les largeurs ne sont pas choisies au hasard : une carte d'arène fait 60 à 96 px CSS (donc 192 px sur
un écran à densité double), le zoom `min(70vw, 16rem)` soit 256 px CSS (512 px à densité double, et
420 px est le point où le texte d'une carte reste lisible sans payer des pixels invisibles).

Le **dos** d'une carte ne compte pas : il est *dessiné* en CSS (`CardBack`), zéro octet réseau — tout
comme les six décors d'arène ([`DECORS.md`](DECORS.md)).

Poids mesurés le 15/10/2026 sur chimera, sur une carte réelle (`base1/4`, rééchantillonnée en
630×880 JPEG 92 pour simuler la photo stockée) :

| Largeur | photo nette | photo bruitée | bruit pur (incompressible) |
|---|---|---|---|
| 192 (q76) | 12,2 Ko | 12,4 Ko | 15,9 Ko |
| 420 (q80) | 45,2 Ko | 55,7 Ko | 125,9 Ko |

## Le plafond est tenu par construction, pas espéré

`fabriquer_image_jeu` encode à la qualité nominale ; si le résultat dépasse `plafond_octets`, elle
**réessaie** à 70, puis 60, puis 45 ; et si rien n'y suffit, elle **lève** `VarianteTropLourde`. La
photo est alors déclarée inexploitable et se replie sur l'image officielle, **en le disant** (D9).

C'est ce qui rend le budget d'une partie *calculable* : le poids d'un plateau n'est pas une moyenne
constatée mais une **borne**. Sans ce plancher, une photo de capteur bruité pourrait peser 126 Ko —
sept fois son budget, cent vingt fois par partie.

## Le budget d'une partie

`pbm_api.jeu.budget` ne contient aucun chiffre recopié : le total est une **conséquence** des
plafonds ci-dessus. `uv run python -c "from pbm_api.jeu import budget; print(budget.rapport())"` :

```
   120 ×  18.0 Kio  cartes en variante plateau        =  2160.0 Kio
     1 ×  64.0 Kio  zoom ouvert (une carte à la fois) =    64.0 Kio
  total partie        2224.0 Kio (plafond 2304 Kio, 11.1 s en 4G)
  dont mise en place   432.0 Kio (plafond 512 Kio, 2.2 s en 4G)
```

⛔ **Les deux plafonds sont contrôlés en CI** (`tests/test_jeu_assets_pipeline.py`, job `api`).
Si cette garde devient rouge après un changement de variante, **la réponse n'est pas de relever le
plafond** : c'est que le plateau est redevenu trop lourd pour un téléphone en 4G. Le message nomme
lequel des deux a sauté, et de combien.

Les 2,25 Mio du pire cas de partie correspondent à **toutes** les cartes des deux decks qui
défileraient au cours d'une partie entière. Ce qui compte pour la première impression est l'autre
chiffre : **432 Kio de mise en place**, soit 2,2 s en 4G.

## Où les variantes sont produites — et jamais pendant une partie

| Moment | Quoi | Pourquoi là |
|---|---|---|
| **à l'ajout en collection** | job arq `preparer_variantes_jeu_task` | le moment que nomme la fiche ; hors de la requête du joueur (« Tout ajouter » peut porter 143 détections) |
| **au constructeur de deck** | `apercu_deck` | filet pour ce que le worker n'a pas encore traité, borné aux cartes du deck, et c'est là qu'on **dit** au joueur ce qui se repliera |
| **par lots, sur la flotte** | `apps/api/scripts/preparer_rendus_jeu.py` | tout le parc déjà photographié, et tout changement de recette |
| **pendant une partie** | ❌ **rien** | |

⛔ **La dernière ligne est un critère du lot, et elle n'a pas toujours été vraie.** `j-rendu-carte`
rattrapait la variante manquante dans `servir_photo`, au premier accès : une partie à deux joueurs
pouvait donc lancer jusqu'à 120 décodages OpenCV **sur la machine qui sert** — deux cœurs, et des
joueurs à servir. Désormais une variante absente rend **404**, l'écran prend `url_repli` (l'image
officielle), et un test le garde avec un stockage qui *refuse* d'écrire (compter les appels aurait
laissé passer une écriture conditionnelle).

### Rattrapage du parc, et régénération

Un exemplaire préparé avant le dédoublement n'a que son zoom. La liste des variantes réellement
produites est inscrite dans `collection_items.jeu_qualite["variantes"]` — **pas de colonne neuve**,
donc pas de migration ni de tête Alembic à fusionner : les deux informations sont écrites par le
même appel, dans le même flush, et ne peuvent pas diverger. Son **absence** sur une ligne ancienne
est exactement l'information dont le rattrapage a besoin.

```bash
cd apps/api
uv run python scripts/preparer_rendus_jeu.py --a-blanc              # COMBIEN il y a à faire
uv run python scripts/preparer_rendus_jeu.py                        # tout le parc, par paquets
uv run python scripts/preparer_rendus_jeu.py --utilisateur <uuid>   # un seul compte
uv run python scripts/preparer_rendus_jeu.py --plafond 500 --lot 100
```

⚠️ `--a-blanc` compte ce qui reste à préparer, il ne **pèse** rien : les poids (médiane, p95, max
face au plafond) viennent d'un passage réel, puisqu'ils sont relus depuis le stockage objet. Le
budget, lui, est affiché dans les deux cas — il ne dépend que des plafonds déclarés.

⛔ Ce script tourne **sur la flotte**, jamais sur la machine qui sert ([`JOBS-LOURDS.md`](../infra/JOBS-LOURDS.md)).
Il rend un code de sortie non nul si un plafond de budget est violé — un dépassement doit faire
échouer le passage, pas laisser une ligne dans un journal que personne ne relit.

**Quand une photo est remplacée**, appeler `invalider_variantes` : les variantes sont nommées
d'après l'**exemplaire**, pas d'après la photo — rien dans leur clé ne changerait, et l'ancienne
image serait servie indéfiniment. Au 15/10/2026 aucune route du produit ne remplace la photo d'un
exemplaire existant (une nouvelle détection crée un nouvel exemplaire) : la fonction existe et est
testée pour le jour où un écran « reprendre la photo » apparaîtra.

## Le cache : immuable d'un côté, révocable de l'autre

Un budget tenu à l'octet ne sert à rien s'il est payé à chaque F5. Avant ce lot, `/img/cards/{id}`
ne posait **aucun** en-tête de cache.

| Route | Cache | Pourquoi |
|---|---|---|
| `GET /img/cards/{id}?size=` | `public, max-age=31536000, immutable` + `ETag` | le contenu ne change **jamais** pour un couple (carte, taille) : le navigateur ne redemande rien |
| `GET /jeu/rendu/parties/{g}/photos/{i}?v=` | `private, max-age=86400` + `ETag`, **jamais** `immutable` | la photo change si son propriétaire la reprend ; `immutable` afficherait l'ancienne pendant un an |

`private` sur la seconde : la photo d'un joueur n'a rien à faire dans un cache partagé. L'empreinte
est un SHA-256 tronqué à 128 bits, calculé sur les octets **déjà lus** pour répondre — aucune
lecture supplémentaire, et juste par construction (un contenu différent donne une empreinte
différente, sans dépendre d'une date de modification que le stockage local ne garantit pas).
Un `If-None-Match` connu rend **304 sans corps**, y compris quand le navigateur envoie plusieurs
empreintes ou un validateur faible (`W/"…"`).

## Le pré-chargement

Le navigateur ne demande une image qu'au moment où il la peint (`loading="lazy"` sur chaque carte) :
un joueur qui pose son premier Pokémon verrait les cartes apparaître une par une. On les charge donc
**pendant la mise en place**.

- La logique est **pure** et testable sans navigateur : `apps/web/src/lib/game/prechargement.ts`
  (quoi charger, dans quel ordre, et le compte) ; le chargeur est injecté.
- **L'ordre est celui de l'utilité** : les Pokémon en jeu des deux camps, puis ma main, puis le
  Stade et les options d'une décision, puis les défausses et zones perdues.
- **Jamais `url_zoom`** : charger les deux variantes triplerait le poids d'une partie.
- **Six images de front** (`PARALLELISME`) : la limite de connexions par origine en HTTP/1.1, et
  au-delà on retarderait la requête d'état de la partie, qui est sur le chemin critique.
- La barre (`BandeauPrechargement`) est **honnête** — comptée sur les images réellement arrivées, et
  un **échec compte comme traité** : une barre bloquée à 93 % est pire qu'une absence de barre.
  Elle s'efface dès qu'elle n'a plus rien à dire, et n'apparaît pas du tout quand tout est en cache.

⚠️ **Le bandeau est hors flux (`fixed`), et ce n'est pas un détail de style** : la page
`/jeu/parties/{id}` n'admet **aucun défilement** (e2e `plateau-responsive`, voir
[`ANIMATIONS.md`](ANIMATIONS.md)). Un élément ajouté en flux normal décale le plateau et fait
échouer le job e2e, sans qu'aucun test unitaire ne bronche. Un test unitaire garde explicitement la
classe `fixed` pour cette raison.

Le critère « le pré-chargement se termine avant la fin de la mise en place » est mesuré en 4G
simulée par `apps/web/e2e/prechargement-4g.spec.ts`. La 4G y est **modélisée explicitement** (un
tuyau partagé à 200 Ko/s, 150 ms de latence) et non bridée par CDP : `Network.emulateNetworkConditions`
ne s'applique pas aux réponses fabriquées par `route.fulfill`, un bridage CDP donnerait un test qui
ne mesure rien. Le modèle est sérialisé, donc **pessimiste** — une vraie 4G fait mieux.

## « Je ne vois pas ma photo en jeu »

Dans l'ordre, et chaque étape a sa réponse ailleurs :

1. **le rendu décidé est l'officielle** → c'est DJ5 : préférence du compte, du deck, ou veto.
   Le constructeur de deck le **dit**, avec la raison ([`RENDU-CARTES.md`](RENDU-CARTES.md)) ;
2. **la variante n'est pas préparée** → la vue sert l'officielle avec `RAISON_PAS_PRETE`, et la
   route rend 404. Passer par le constructeur de deck, ou lancer le script par lots sur la flotte ;
3. **la photo est inexploitable** (trop sombre, coupée, ou trop lourde pour son plafond) → la raison
   est écrite dans `jeu_qualite` à la préparation ;
4. **l'image ne se charge pas** → l'écran passe à `url_repli` après deux essais (`EtapeImage`).

## Repères d'implémentation

| Quoi | Où |
|---|---|
| Les variantes, leurs plafonds, la fabrication | `apps/api/src/pbm_api/jeu/rendu_image.py` |
| Le budget d'une partie et son rapport | `apps/api/src/pbm_api/jeu/budget.py` |
| Préparation, rattrapage, invalidation | `apps/api/src/pbm_api/jeu/rendu_service.py` |
| Cache et empreinte des images | `apps/api/src/pbm_api/http_images.py` |
| Fabrication par lots | `apps/api/scripts/preparer_rendus_jeu.py` |
| Job d'ajout en collection | `preparer_variantes_jeu_task` dans `apps/api/src/pbm_api/worker.py` |
| Pré-chargement (logique pure) | `apps/web/src/lib/game/prechargement.ts` |
| La barre de progression | `apps/web/src/components/game/bandeau-prechargement.tsx` |
| Garde de budget (CI) | `apps/api/tests/test_jeu_assets_pipeline.py` |
| Preuve en 4G | `apps/web/e2e/prechargement-4g.spec.ts` |
