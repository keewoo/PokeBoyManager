# Le profil de joueur : avatar, carte fétiche, badges

> Lot `j-profil-jeu` (jalon J4, décision **DJ6**). On l'ouvre quand on touche aux badges, à la carte
> fétiche, à la vitrine `/jeu/profil` — ou quand quelqu'un dit « je n'ai pas eu mon badge » ou
> « mon adversaire ne voit pas ma carte fétiche ».

## En une phrase

Un badge est une **conséquence déterministe** d'un fait de jeu, écrite **une seule fois** à la
clôture d'une partie ; la carte fétiche est la carte qu'on montre à son adversaire **au lancement**,
avec le rendu que son propriétaire a réglé (DJ5). Rien ne s'achète, rien ne se tire au sort, et
**aucun badge ne récompense le temps passé**.

## La liste des badges — et ce que chacun récompense

Cinq badges, ceux de la fiche du lot. ⚠️ La mission demandait de les arrêter « avec JF et
Aymeric » : la session était autonome, la liste est donc celle du plan, **sans ajout**, et elle
attend un mot de JF (retirer un badge = retirer une entrée de `BADGES`, aucune migration).

| Code | Nom | Comment on l'obtient | Mesure |
|---|---|---|---|
| `premiere-victoire` | Première victoire | gagner une partie qui compte | `issue` |
| `ko-en-un-coup` | K.O. en un coup | mettre K.O. un Pokémon **intact**, d'une seule attaque | `exploit` |
| `victoire-sans-recompense-cedee` | Sans rien céder | gagner sans que l'adversaire prenne **une seule** récompense | `exploit` |
| `dix-parties` | Dix parties | avoir joué dix parties qui comptent | `volume` |
| `deck-monotype-victorieux` | Monotype vainqueur | gagner avec un deck dont tous les Pokémon sont du même type | `construction` |

**Une seule condition commune : la partie doit compter.** `comptabilisee`, la notion posée par
`j-fin-effets-compte` (voir `docs/jeu/FIN-COMPTE.md`) : ni l'entraînement contre le bot (DJ7), ni
une partie expirée faute d'activité. Un badge gagné contre un bot n'en serait pas un.

Code : `apps/api/src/pbm_api/jeu/badges.py` (pur — la liste et les conditions),
`badges_service.py` (les faits lus en base, l'écriture), `models/player_badges.py` (la table),
`profil_service.py` (la vitrine, la carte fétiche), `routers/profil_jeu.py` (deux routes).

## « Aucun badge ne récompense le temps passé » — une parade, pas une consigne

Le risque que le plan nomme est précis : *« des badges de temps de jeu transforment un jeu en
obligation quotidienne, ce qui n'est pas ce qu'on veut pour un enfant de onze ans »*. Une consigne
ne tient pas : le lot suivant ajoutera un badge sans l'avoir lue.

La parade est **structurelle** : `FaitsBadges` — la seule chose que voit la fonction d'attribution —
ne porte **aucun champ de temps**. Ni durée de partie, ni date, ni série, ni jour de connexion. Une
condition de badge ne *peut pas* récompenser le temps, puisqu'elle n'en sait rien. `champs_de_temps()`
relit les noms de champs et doit rester vide ; un test l'exige.

Deux gardes l'accompagnent, du même genre :

- le vocabulaire des mesures est **fermé** et comparé à l'identique par un test : ajouter
  « assiduité » oblige à modifier le test en connaissance de cause ;
- il n'existe qu'**un seul** badge de volume. Dix parties, pas 10/50/100/500 — une échelle est un
  tapis roulant ; un palier unique se franchit puis s'oublie. C'est pourquoi « dix parties » est
  accepté alors qu'il mesure une quantité : il n'y a ni récurrence, ni remise à zéro, ni série.

## Pourquoi une table, alors que le classement ne stocke rien

`j-classement-prive` recalcule tout **à la lecture** et c'est le bon choix pour lui : un état qu'on
ne stocke pas ne peut pas se corrompre (voir `docs/jeu/CLASSEMENT.md`). Les badges ne peuvent pas
suivre ce chemin, pour une raison unique et décisive :

> **« K.O. en un coup » est un fait du journal, et le journal est purgé à trente jours.**

Un badge recalculé à la lecture disparaîtrait donc un mois après avoir été mérité, sans un mot. On
capte le fait **pendant que la preuve existe**, à la clôture.

L'idempotence est alors une **contrainte de base** (`uq_player_badges_user_code`), pas un `if` — un
`if` perdrait la course entre deux clôtures concurrentes, exactement comme pour `game_results`.
L'écriture est un `INSERT … ON CONFLICT DO NOTHING … RETURNING code` : ce qui revient est ce qui est
**nouveau**, et rejouer une clôture ne rend rien.

## Le réglage de JF gouverne la VITRINE, pas l'attribution

DJ6 veut les badges « en option, activables par JF ». Donc `badges_actifs` (défaut **non**,
`pbm_api.jeu.reglages`) :

```bash
python -m pbm_api.admin set-reglage-jeu badges_actifs oui   # allumer la vitrine
python -m pbm_api.admin lire-reglages-jeu                   # voir posé / effectif
```

⚠️ **L'attribution tourne même quand le réglage est à `non`.** Ce qui est optionnel, c'est l'écran.
Si l'attribution s'arrêtait aussi, allumer les badges après six mois de parties donnerait une
vitrine vide — et « K.O. en un coup », qui dépend d'un journal purgé, serait perdu à jamais. Un
badge gagné n'est pas une fonctionnalité visible : c'est une ligne dérivée d'un historique déjà
stocké. Quand le réglage est à `non`, la route ne lit même pas la table : `badges` est vide, et
l'écran **le dit** au lieu d'afficher une grille grise qu'on prendrait pour une panne.

## Les badges d'avant ce lot ne sont pas reconstruits

Aucun rattrapage, et c'est dit plutôt que compensé : quatre badges sur cinq se rattrapent **tout
seuls** à la prochaine partie (leurs conditions relisent l'historique complet : « dix parties »,
« première victoire »…). Le cinquième — « K.O. en un coup » — dépend du journal de la partie où il a
eu lieu : s'il est passé avant ce lot, il ne reviendra pas. Écrire un script qui invente des dates
aurait été pire.

## La carte fétiche

**Ce que c'est** : une carte **du catalogue** (« Dracaufeu »), pas un exemplaire précis
(`users.carte_fetiche_card_id`). On la choisit parmi les cartes qu'on possède — un exemplaire
signalé contrefaçon ne compte pas, même notion de possession que la légalité des decks.

**La possession est contrôlée au choix, pas à la lecture.** Vendre la carte ne fait pas disparaître
ce qu'on a déclaré aimer ; le rendu retombe simplement sur l'image officielle, sans cas particulier
(il n'y a plus de photo).

**Où elle s'affiche** : dans la vue du **lancement** (`GET /jeu/lancements/{id}`), des deux côtés,
sur chaque camp — `inviter.carte_fetiche` et `invitee.carte_fetiche`.

### Le rendu, et le cadre d'autorisation qu'il a fallu créer

La carte fétiche passe par le juge DJ5 habituel (`decider_origine`) — le veto « ne jamais montrer
mes photos » n'est pas réécrit, il est **appelé**. Mais une URL de photo n'existe pas sans cadre, et
au moment du lancement **la partie n'existe pas encore** : elle naît du pile ou face. D'où une route
jumelle de celle des parties, bornée au lancement :

```
GET /jeu/rendu/lancements/{launch_id}/photos/{item_id}?v=zoom
```

Mêmes règles, à la lettre : la décision est **rejouée** côté serveur (participation au lancement,
propriété de l'exemplaire, préférence du compte, veto), tous les refus rendent le **même** 404, et
le cache est `private`. Aucun droit ne vient de l'URL elle-même.

Trois détails qui comptent :

- **le regard est toujours celui de l'adversaire.** La vue d'un lancement est symétrique par
  construction (c'est ce qui rend le pile ou face vérifiable par les deux joueurs). Je vois donc ma
  carte fétiche *comme mon adversaire la voit* — l'information utile, et la garantie qu'aucun chemin
  asymétrique ne puisse émettre une URL de photo sous veto ;
- **la préférence lue est celle du compte**, pas celle d'un deck : une carte fétiche n'appartient à
  aucun deck ;
- **hors d'un lancement** (la vitrine du profil), il n'existe aucun cadre : l'image officielle est
  servie, et la raison le dit (`RAISON_HORS_CADRE`). On montre moins, jamais plus.

### La variante de jeu est préparée au CHOIX de la carte

`j-assets-pipeline` interdit de fabriquer une image pendant une partie, et nomme les trois moments
où on la produit (`docs/jeu/ASSETS.md`). Le choix d'une carte fétiche en est un quatrième, et il en
a toutes les propriétés : un geste **délibéré** du joueur, borné à **une** image, hors de toute
partie. Sans cela, la carte fétiche se replierait presque toujours sur l'officielle alors que le
joueur a demandé ses photos — le critère d'acceptation serait « vrai » et le produit faux.

## Les décors ne se débloquent pas

`j-arene-decors` a laissé les six décors **tous disponibles** en écrivant pourquoi : « on ne fabrique
pas un mécanisme de déblocage qui ne débloque rien ». Ce lot avait la possibilité d'en verrouiller
derrière des badges (4ᵉ point de la mission de ce lot-là, « si DJ6 le retient »). **Il ne le fait
pas**, pour une raison plus forte que la symétrie : verrouiller aujourd'hui **retirerait** aux
joueurs un choix qu'ils ont déjà, et DJ6 dit « sans saison ni perte de points ». La vitrine les
montre donc pour ce qu'ils sont — disponibles, celui du joueur mis en avant.

## La vitrine

`/jeu/profil` (atteignable depuis le salon). Elle montre :

- **l'identité reprise du compte** : pseudo et avatar de `v1-profil`. Il n'existe **pas** de pseudo
  de jeu distinct — un joueur n'a qu'un nom, celui que l'adversaire voit déjà dans le salon ;
- **la carte fétiche**, avec ce que l'adversaire en verra, et de quoi la changer ou la retirer ;
- **les badges** (quand ils sont allumés), obtenus **et** à obtenir, chacun avec sa description :
  un objectif lisible, pas une collection mystérieuse. Rien n'est caché, rien n'est surprise ;
- **les décors**, tous.

Le serveur publie son vocabulaire (`mesures_possibles`, `palier_parties`) : l'écran l'affiche, il ne
le code pas en dur. Et il ne décide **aucun** rendu d'image : si l'écran choisissait, le veto DJ5
serait contournable depuis le navigateur.

## Diagnostiquer

```sql
-- Les badges d'un joueur, et dans quelle partie il les a eus
SELECT code, obtenu_a, game_id FROM player_badges
 WHERE user_id = '<uuid>' ORDER BY obtenu_a;

-- Une partie close dont les badges manqueraient (la clôture a-t-elle bien eu lieu ?)
SELECT r.game_id, r.comptabilisee FROM game_results r
 WHERE r.finie_a > now() - interval '1 day';
```

| « Je n'ai pas eu mon badge » | Ce qu'il faut regarder |
|---|---|
| la vitrine est vide | `lire-reglages-jeu` : `badges_actifs` est-il à `oui` ? |
| la partie était un entraînement | aucun badge : c'est la règle (`comptabilisee` faux) |
| « K.O. en un coup » manque | la forme stricte n'était pas réunie (un seul K.O., une seule attaque, cible intacte) — voir l'en-tête de `pbm_game/journal/recapitulatif.py` |
| « sans rien céder » manque | l'adversaire a pris au moins une récompense (sa ligne `game_result_players`) |
| le badge d'une vieille partie manque | aucun rattrapage rétroactif (voir plus haut) |

| « Mon adversaire ne voit pas ma carte fétiche » | Ce qu'il faut regarder |
|---|---|
| il voit l'image officielle | `rendu.raison` le dit : préférence du compte, veto, pas de photo, variante pas prête |
| rien ne s'affiche du tout | aucune carte choisie (`users.carte_fetiche_card_id` nul) |
| 404 sur la photo | le regardant ne participe pas à ce lancement, ou le veto s'applique — le même 404 dans les deux cas, délibérément |
