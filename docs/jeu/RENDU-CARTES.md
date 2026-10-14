# Rendu des cartes en jeu — ma photo, l'image officielle, le dos

> Lot `j-rendu-carte` (jalon J3). Décision **DJ5**. À lire avant de toucher à l'image d'une carte
> sur le plateau, aux réglages de confidentialité des photos, ou à la variante de jeu d'une photo.

C'est la promesse du produit : on joue avec **ses** cartes, celles qu'on a photographiées, cornées,
avec leur reflet — pas avec un catalogue anonyme.

## Les trois rendus

| Rendu | D'où il vient | Qui le décide |
|---|---|---|
| **photo** | la photo personnelle du propriétaire de la carte, en variante de jeu | le serveur |
| **officielle** | l'image du catalogue, via `GET /img/cards/{id}` (proxy public) | le serveur |
| **dos** | **dessiné** par l'écran (`CardBack`), aucune image chargée | l'écran |

Le dos n'est pas une préférence : c'est l'état d'une carte qu'on ne voit pas. Il n'apparaît donc
jamais dans une vue de partie — une carte face cachée n'a pas d'identité à révéler, la projection du
moteur n'en laisse que le **nombre**. Son premier consommateur est la fenêtre de décision sur un
**ensemble caché** (« choisis une carte dans la main de ton adversaire ») : l'écran y montre N dos,
sans qu'aucune identité ne circule. La désignation à l'aveugle, elle, n'est pas implémentée — et
n'est pas approximée (D9).

## DJ5 — qui voit quoi

> *« Oui par défaut côté joueur, et réglage par deck : "mes cartes telles que je les ai
> photographiées" ou "images officielles". L'adversaire voit ce que le joueur a choisi de montrer ;
> un réglage "ne jamais montrer mes photos" existe. »* — JF, 14/10/2026

Trois niveaux, du plus large au plus fort :

1. le **défaut du compte** — `jeu_rendu_reglages.rendu_defaut`, `"photo"` par défaut ;
2. la préférence **du deck** — `decks.rendu_cartes`, qui l'emporte quand elle est posée. **Nulle =
   suit le compte**, et jamais `"photo"` : un défaut posé sur la colonne figerait les decks
   existants et rendrait le réglage global sans effet sur eux ;
3. le **veto** `jamais_montrer_mes_photos`, qui l'emporte sur les deux — mais **seulement pour le
   regard de l'adversaire**. Son propriétaire continue de voir ses propres photos : le réglage
   protège qui s'en sert, il ne le prive de rien.

**L'ordre des verdicts vit à un seul endroit** : `pbm_api.jeu.rendu.decider_origine`. Le
constructeur de deck et la vue de partie passent tous deux par lui — sinon l'avertissement montré au
joueur (« ta photo est trop sombre ») et ce qu'il voit réellement en jeu pourraient diverger, sans
qu'aucun test de l'un ou de l'autre ne l'attrape.

### Deux propriétés qui font que le veto est réel

- **Le veto est évalué avant toute consultation de la photo.** Aucune URL de photo ne peut sortir
  par une erreur d'ordre, et l'identifiant d'exemplaire n'apparaît **nulle part** dans la charge
  utile de l'adversaire.
- **La raison rendue est la même qu'une photo existe ou non** (« le propriétaire ne montre pas ses
  photos »). Sinon le refus lui-même révélerait que le joueur a photographié cette carte.

Et le serveur fait autorité : l'écran ne choisit pas entre « ma photo » et « l'officielle », il
affiche l'URL qu'on lui donne. S'il choisissait, le réglage ne serait qu'une politesse — l'URL
serait déjà partie.

## Ce que porte la vue de partie

Chaque carte **visible** (Pokémon en jeu et sa pile, énergies, Outil, défausse, zone perdue, sa
propre main, Stade, options d'une décision) reçoit un champ `rendu` :

```json
{"origine": "photo", "url": "…", "url_zoom": "…", "credit": "photo de Aymeric",
 "raison": null, "url_repli": "/img/cards/…?size=low"}
```

- `url` est la taille **plateau**, `url_zoom` la taille **zoom** : deux tailles données plutôt
  qu'une règle de taille à redériver côté écran ;
- `credit` est l'indicateur discret « photo de Aymeric », posé **seulement** sur la photo d'un autre
  joueur. Il est **écrit dans le zoom** et **annoncé par l'`aria-label`** sur le plateau : sur une
  carte de 60 px de large, un bandeau de texte serait illisible et recouvrirait les énergies ;
- `raison` dit pourquoi l'officielle a remplacé la photo. Montrée dans le **constructeur de deck**,
  pas sur le plateau — en pleine partie, c'est du bruit ;
- `url_repli` n'accompagne qu'une photo : l'image officielle de la même carte, pour que l'écran ait
  de quoi afficher si la photo ne se charge pas. Elle ne révèle rien (l'officielle est publique).

Le champ est **absent** quand la carte est inconnue du catalogue : il n'y a alors pas même d'image
officielle, et on n'en invente pas (D9) — l'écran retombe sur le nom de la carte.

## La note de qualité, et le repli

Une photo prise au flash par un enfant de onze ans n'est pas toujours jouable. Sur un plateau de
téléphone, une carte floue ou brûlée n'est pas « moins belle » : elle est **illisible**, et le
joueur ne sait plus ce qu'il joue. `pbm_api.jeu.rendu_qualite` note donc chaque photo et conclut.

| Mesure | Seuil | Raison affichée |
|---|---|---|
| cadrage (part hors cadre) | > 0,12 | « carte coupée sur la photo » |
| luminance moyenne | < 55 | « photo trop sombre » |
| part de pixels brûlés (≥ 250) | > 0,22 | « reflet du flash sur la carte » |
| luminance moyenne | > 225 | « photo trop claire » |
| variance du Laplacien | < 60 | « photo trop floue » |

L'ordre compte : on nomme d'abord le défaut qu'on **peut corriger en reprenant la photo** (cadrage,
lumière), puis le flou. Le joueur reçoit une consigne utile, pas un diagnostic complet.

Deux points qui ont guidé la mesure :

- **la part de pixels brûlés est mesurée à part**, parce qu'un flash peut brûler un quart de
  l'image en laissant une luminance moyenne tout à fait normale. Sur la seule moyenne, cette photo
  passerait pour correcte et arriverait illisible sur le plateau ;
- **le cadrage n'est pas mesuré sur l'image** : une fois la carte redressée en 630×880
  (`warp_card`, lot `v3-detection`), l'image remplit le cadre par construction — ce qui a été coupé
  l'a été avant. Il est donc **reçu en donnée**, depuis `detections.bbox["crop_quality"]`. Un
  exemplaire sans détection (import, saisie manuelle) n'a pas de cadrage mesuré : il vaut `None` et
  n'empêche rien — on ne suppose pas qu'il est parfait, ce serait faire passer une carte coupée.

Calibrage : une image de carte réelle (Dracaufeu base1-4, redressée) note **netteté 677**,
**luminosité 130**, **0 % brûlé** — très loin des seuils. Ils ont été posés sur des images
synthétiques puis vérifiés contre cette carte réelle.

## La variante de jeu, et où elle est produite

Servir la photo d'origine serait le piège du lot. Mesuré sur une carte réelle :

| | Taille | Poids | Un plateau (20 cartes) | Un deck (60) |
|---|---|---|---|---|
| photo stockée (`photo_s3_key`) | 630×880 JPEG 92 | 178 Ko | 3,5 Mo | 10,5 Mo |
| **variante de jeu** (`jeu_image_key`) | 420×587 WebP 80 | **44 Ko** | **0,86 Mo** | 2,6 Mo |

420 px de large, parce que le pire cas d'affichage n'est pas le plateau (≈ 60 px) mais le **zoom**
(`min(70vw, 16rem)` = 256 px, soit 512 px à densité double). Au-delà, on paierait des pixels que
personne ne voit.

**Où elle est produite**, et pourquoi là :

- au **constructeur de deck** (`GET /jeu/rendu/decks/{deck_id}`) : c'est le moment « à l'avance » —
  le joueur regarde son deck avant de jouer, la fabrication est bornée à ses cartes, et c'est là
  qu'on lui **dit** ce qui se repliera ;
- à la **première demande** d'une photo (`GET /jeu/rendu/parties/{game_id}/photos/{item_id}`) : une
  seule image, pour l'exemplaire demandé ;
- par le script `apps/api/scripts/preparer_rendus_jeu.py`, **sur la flotte**, pour rattraper le
  corpus existant (reprenable, `--a-blanc` pour voir ce qu'il ferait) ;
- **jamais dans la projection d'une partie.** Un plateau se lit plusieurs fois par seconde : on n'y
  fabrique pas d'image. Une photo pas encore préparée s'y replie sur l'officielle **en le disant**
  (`RAISON_PAS_PRETE`) — le critère est « sans trou ni attente », pas « coûte que coûte ».

Un exemplaire possédé en plusieurs copies : c'est la **plus lisible** qui représente la carte (prête
et exploitable d'abord, puis la plus nette), pas la plus récente. Sur un plateau de téléphone, la
lisibilité est la seule qualité qui compte.

## « Je ne vois pas ma photo en jeu »

Dans cet ordre, c'est toujours l'une des six :

1. **le deck joue en images officielles** → l'aperçu du deck l'affiche (`rendu_effectif`) ;
2. **le compte joue en images officielles** → `/jeu/rendu` ;
3. **aucune photo de cette carte** dans la collection → la carte est au deck, pas l'exemplaire ;
4. **la photo est jugée inexploitable** → l'aperçu du deck nomme la carte et la raison ;
5. **la variante n'est pas encore produite** → ouvrir le deck une fois, ou lancer le script ;
6. **c'est la photo de l'adversaire et il a posé son veto** → rien à corriger, c'est son droit.

Et si c'est l'inverse (« l'adversaire voit mes photos alors que je ne veux pas ») :
`jamais_montrer_mes_photos` sur `/jeu/rendu`. Le veto est revérifié **par la route** à chaque
requête d'image, pas seulement au moment où la vue est construite : une URL devinée ou gardée d'une
partie précédente ne sert rien.

## Routes et fichiers

| Quoi | Où |
|---|---|
| Décision DJ5 (pure) | `apps/api/src/pbm_api/jeu/rendu.py` |
| Note de qualité (pure) | `apps/api/src/pbm_api/jeu/rendu_qualite.py` |
| Variante d'image | `apps/api/src/pbm_api/jeu/rendu_image.py` |
| Lectures base + stockage | `apps/api/src/pbm_api/jeu/rendu_service.py` |
| Pose du `rendu` sur la vue | `apps/api/src/pbm_api/games/rendu_vue.py` |
| Routes `/jeu/rendu/**` | `apps/api/src/pbm_api/routers/jeu_rendu.py` |
| Carte et dos à l'écran | `apps/web/src/components/game/board-card.tsx` |
| Écran « Mes cartes en jeu » | `apps/web/src/app/jeu/rendu/` |
| Panneau du constructeur de deck | `apps/web/src/app/jeu/decks/[id]/deck-rendu-panel.tsx` |

Réglages : `GET|PATCH /jeu/rendu/reglages` · aperçu d'un deck : `GET /jeu/rendu/decks/{deck_id}` ·
photo d'une partie : `GET /jeu/rendu/parties/{game_id}/photos/{item_id}`. Toutes gardées par
`require_game_access` (D11), et **tout refus est un 404** — sur une photo personnelle, l'existence
est déjà une information.
