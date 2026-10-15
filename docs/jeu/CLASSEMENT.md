# Le classement privé entre comptes invités

> Lot `j-classement-prive` (jalon J4, décision **DJ6**). On l'ouvre quand on touche au classement,
> au barème, aux réglages globaux du jeu — ou quand quelqu'un dit « je ne vois pas le classement »
> ou « mon total est faux ».

## En une phrase

Le classement est **calculé à la lecture** depuis l'historique des parties, **éteint par défaut**,
et JF l'allume ou l'éteint par une commande sur le serveur — sans redéployer, sans redémarrer, sans
interrompre une partie en cours.

## Ce qu'il n'y a pas, et c'est l'essentiel

**Il n'existe aucune table de classement.** Ni points stockés, ni rang conservé, ni compteur
incrémenté à la fin d'une partie. La clôture d'une partie (`j-fin-effets-compte`) n'appelle
**rien** de ce lot.

C'est la réponse au risque que le plan nommait : « un classement incrémental non recalculable : la
première erreur devient définitive ». Un état qu'on ne stocke pas est un état qu'on ne peut pas
corrompre. Changer le barème, corriger une formule, réparer un historique : le tableau suivant est
déjà juste, sans migration ni script de rattrapage.

Le prix est un calcul à chaque requête. Il est négligeable à l'échelle du produit (quelques comptes
invités, quelques centaines de parties — une requête sur une table indexée par `user_id`), et le
jour où il cesserait de l'être, :func:`appliquer` est déjà là.

## Les trois morceaux

| Fichier | Ce qu'il porte | Nature |
|---|---|---|
| `apps/api/src/pbm_api/jeu/classement.py` | les barèmes, le rangement, les **deux** chemins de calcul | **pur** (aucune base, aucune horloge) |
| `apps/api/src/pbm_api/jeu/classement_service.py` | ce qu'on lit en base et pour qui | accès base |
| `apps/api/src/pbm_api/routers/classement.py` | `GET /jeu/classement` | une route, en lecture seule |

Les réglages globaux ont leurs propres modules, réutilisables par les lots suivants :
`pbm_api/jeu/reglages.py` (le registre des clés, pur), `pbm_api/jeu/reglages_service.py` (la base),
`pbm_api/models/jeu_reglages.py` (la table `jeu_reglages`).

## Les deux chemins de calcul, et pourquoi les deux existent

- **`calculer`** — le recalcul complet : on *compte* les issues de chaque joueur, puis on
  *multiplie* par le barème. C'est ce que le serveur appelle, à chaque requête.
- **`appliquer`** — le pas incrémental : ce qu'une partie de plus ajoute à un cumul existant.
  Personne ne l'appelle en production.

Les deux empruntent des chemins arithmétiquement **différents**, et le test d'acceptation les
confronte sur un historique volontairement tordu (trois joueurs, les trois issues, de
l'entraînement intercalé, une partie ancienne enregistrée après une récente). C'est ce qui rend la
comparaison informative : un recalcul qui replierait `appliquer` ne se comparerait qu'à lui-même.

`appliquer` reste donc dans le code comme **oracle du test**, et comme base d'un cache si le volume
l'exigeait un jour — avec son test de parité déjà écrit.

## Le barème : la formule, nommée et remplaçable

| Nom | Victoire | Égalité | Défaite | Note |
|---|---|---|---|---|
| `points` *(défaut)* | 3 | 1 | 0 | le barème du football, que tout le monde connaît sans l'avoir appris |
| `victoires` | 1 | 0 | 0 | le simple décompte ; aveugle à l'égalité, donc pas le défaut |

Deux propriétés tiennent, et la seconde est vérifiée par un test **structurel** sur tous les barèmes
déclarés — pas sur ceux du jour :

- **aucun barème ne peut retirer de points** (DJ6 : « sans saison ni perte de points ») ;
- une victoire vaut toujours au moins une égalité, qui vaut au moins une défaite.

Un barème ajouté plus tard avec une défaite à `-1` fait donc rougir la suite sans que personne n'ait
eu à y penser. Ajouter un barème le rend immédiatement choisissable par JF : les valeurs acceptées
du réglage sont **dérivées** de `BAREMES`, jamais recopiées.

Les totaux sont volontairement recomptables de tête, et la route rend les quatre compteurs
(parties, victoires, défaites, égalités) **à côté** du barème : un classement qu'on ne peut pas
recompter est un classement qu'on soupçonne.

## Ce qui compte, et ce qui ne compte pas

Une seule condition : `comptabilisee`, **la même** notion que celle des statistiques du joueur, posée
une fois pour toutes par `j-fin-effets-compte` (voir `docs/jeu/FIN-COMPTE.md`). Donc :

- une partie d'**entraînement** contre le bot (DJ7) n'y figure jamais — c'est un critère
  d'acceptation du lot, vérifié deux fois : sur le calcul pur et par la route ;
- une partie **expirée** faute d'activité n'y figure pas non plus : personne ne l'a jouée jusqu'au
  bout, et inventer un résultat serait contraire à D9.

**L'abandon (R-14.3) et la désertion (R-14.6) comptent**, en revanche — la mission laissait le choix
ouvert, et c'est le choix retenu, pour deux raisons dans cet ordre :

1. **Ne pas rendre la fuite gratuite.** Si déserter effaçait la défaite, le coup optimal d'une
   partie perdue serait de fermer l'onglet. Un classement qui récompense l'abandon fabrique
   exactement la dispute entre frères que le plan redoute.
2. **Ne pas se contredire.** Les statistiques du compte comptent déjà ces défaites. Un classement
   qui les ignorerait afficherait « 4 victoires / 1 défaite » à côté d'un total de 6 parties, sans
   que personne ne sache lequel des deux a tort.

Conséquence : il n'y a **aucun** filtre sur la raison de fin dans le code du classement. Le jour où
JF voudrait l'inverse, c'est un barème qu'on ajoute, pas une condition qu'on glisse dans le service.

## Qui figure au tableau

Les **comptes invités** (`users.game_access`, D11) ayant au moins une partie comptabilisée, **plus le
demandeur** — à zéro s'il n'a encore rien joué, pour qu'il ne soit jamais absent de son propre
classement et ne croie pas à une panne.

Filtrer sur `game_access` exclut du même coup le compte du bot d'entraînement **sans avoir à le
nommer** : une condition de moins à maintenir quand un autre compte technique apparaîtra. Un compte
à qui l'accès au jeu est retiré disparaît du tableau — son historique est conservé, il n'est plus
classé.

Les **ex æquo partagent leur rang**, et le suivant saute (1, 1, 3 — la convention du sport).
Départager un ex æquo serait inventer une hiérarchie que le barème n'a pas produite : précisément le
détail qui transforme un tableau amical en dispute. L'ordre d'*affichage*, lui, est total et stable
(points, puis victoires, puis moins de parties d'abord, puis l'identifiant) : deux appels ne rendent
jamais deux ordres différents.

## ⚠️ Ce que le tableau révèle — et pourquoi c'est un réglage

Le classement **nomme les comptes invités qui ont joué**. C'est sa raison d'être, mais cela va plus
loin que le reste du jeu : les invitations refusent déjà de dire si un pseudo donné appartient à un
compte invité (« révéler qu'un pseudo donné fait partie des comptes invités serait une fuite sur un
jeu délibérément privé », `pbm_api/games/invitations.py`).

Les deux tiennent ensemble parce que le classement est **éteint par défaut** : montrer la table de
famille est une décision de JF, pas un effet de bord d'un lot. Trois précautions l'accompagnent :

- éteint, **l'historique n'est pas lu** — le réglage n'est pas un filtre d'affichage ;
- la route ne publie **aucun identifiant de compte** : le pseudo nomme, `moi` surligne, et rien de
  plus ne traverse ;
- aucun compte sans accès au jeu ne voit la route (404, pas 403 : on ne confirme pas ce qu'il n'a
  pas le droit de voir).

## Les réglages — une commande, pas un déploiement

C'est un critère d'acceptation du lot : « la désactivation est un réglage, pas un déploiement ».
Une variable d'environnement n'aurait pas suffi — il faut éditer le fichier d'environnement du
serveur **et redémarrer les conteneurs**. Les réglages globaux vivent donc dans la table
`jeu_reglages`, lus à chaque requête :

```bash
# sur le serveur, dans le conteneur de l'API
python -m pbm_api.admin lire-reglages-jeu                       # l'état : posé et effectif
python -m pbm_api.admin set-reglage-jeu classement_actif oui    # allumer
python -m pbm_api.admin set-reglage-jeu classement_actif non    # éteindre
python -m pbm_api.admin set-reglage-jeu classement_bareme victoires
```

| Clé | Valeurs | Défaut | Ce qu'elle décide |
|---|---|---|---|
| `classement_actif` | `oui` / `non` | **`non`** | le classement est-il calculé et montré ? |
| `classement_bareme` | `points` / `victoires` | `points` | quelle formule compte les points |

Trois propriétés de ce mécanisme, chacune voulue :

- **le défaut est « éteint »** : DJ6 dit « en option, activable par JF ». Un lot ne s'auto-active pas
  sur une décision qui dit « en option » ;
- **rien n'est semé en base** : un réglage jamais touché n'a pas de ligne et rend son défaut
  déclaré. Installer un serveur n'a donc rien à initialiser ;
- **une clé inconnue est refusée**, pas écrite. `set-reglage-jeu classement_active oui` (un « e » de
  trop) échoue en nommant les clés existantes — sinon la commande rendrait un succès et JF croirait
  avoir allumé le classement. C'est la panne muette que ce dépôt refuse par principe.

**Aucune route HTTP n'écrit un réglage global**, et c'est délibéré : « activable par JF » veut dire
par JF sur le serveur, pas par un compte muni du bon cookie. Ce produit n'a pas de notion
d'administrateur côté web, et ce lot n'allait pas en inventer une pour un réglage que deux personnes
changeront trois fois.

`j-profil-jeu` ajoutera `badges_actifs` au même registre — une entrée dans un dictionnaire, **sans
migration** : c'est l'autre moitié de DJ6.

## La route

```
GET /jeu/classement?fenetre_jours=30
```

Réponse : `actif`, `bareme` (nom, libellé, les trois valeurs de points), `fenetre_jours`, et
`lignes` — chacune avec `rang`, `pseudo`, `moi`, `points`, `parties`, `victoires`, `defaites`,
`egalites`, `points_recents`, `derniere_partie_a`.

- **`actif: false` se rend en 200**, avec zéro ligne — pas en 404 : l'écran doit pouvoir distinguer
  « JF n'a pas activé le classement » d'une route cassée.
- **`points_recents`** est l'« évolution dans le temps » que demandait le plan : les points gagnés
  dans la fenêtre (30 jours par défaut, bornée à 1–365, hors bornes = 422). On montre *ce qui a été
  gagné récemment* plutôt qu'une variation de rang : un rang qui bouge parce qu'un tiers a joué ne
  dit rien de mon mois.

## « Je ne vois pas le classement »

Dans cet ordre, c'est presque toujours le premier :

1. **`actif` est faux** → `lire-reglages-jeu` sur le serveur. C'est le défaut du produit, pas une
   panne.
2. **404 sur la route** → le compte n'a pas l'accès au jeu (D11) :
   `python -m pbm_api.admin set-game-access <email> on`.
3. **Je suis seul au tableau** → les autres comptes invités n'ont aucune partie *comptabilisée* : de
   l'entraînement contre le bot ne compte pas, et c'est voulu.
4. **Mon total me paraît faux** → recomptez-le avec le barème rendu à côté
   (`victoires × points_victoire + egalites × points_egalite`). S'il ne tombe pas juste, c'est un
   bug de calcul, pas un cache en retard : il n'y a pas de cache.

```sql
-- Ce que le classement lit, et rien d'autre
SELECT u.pseudo, grp.resultat, count(*)
  FROM game_result_players grp JOIN users u ON u.id = grp.user_id
 WHERE grp.comptabilisee AND u.game_access
 GROUP BY u.pseudo, grp.resultat ORDER BY u.pseudo;
```

## Ce que ce lot ne décide pas

- **L'écran** : le lot est du couloir J-SRV, il n'ajoute aucune page. `j-stats-joueur` (« Mes
  parties ») est le lot d'interface du jalon, et il consommera cette route telle quelle.
- **Les badges** : `j-profil-jeu`, qui arrêtera la liste avec JF et Aymeric (D9 : on ne devine pas
  une liste pour la jeter ensuite). Le registre de réglages l'attend.
- **Les saisons et la perte de points** : DJ6 les exclut. Si JF changeait d'avis, c'est un barème et
  une borne de date — pas une table de plus.

Tests : `apps/api/tests/test_jeu_classement.py`.
