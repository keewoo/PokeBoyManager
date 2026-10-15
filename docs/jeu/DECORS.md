# Décors d'arène

> Lot `j-arene-decors` (jalon J3). **Six endroits où jouer**, le choix du joueur, un thème
> automatique tiré de son deck, et une variation jour/nuit — sans jamais prendre le pas sur les
> cartes, et sans peser un octet sur le réseau.

## Ce que voit le joueur

Le plateau n'est plus un fond uni : c'est un endroit. Six, exactement, du plus neutre au plus marqué.

| Clé | Nom | Thème automatique pour… |
|---|---|---|
| `arene` | Arène municipale | Plante, Incolore — **c'est aussi le décor par défaut** |
| `caldeira` | Caldeira | Feu, Combat |
| `lagon` | Lagon | Eau |
| `orage` | Plateau d'orage | Électrique, Métal |
| `temple` | Temple oublié | Psy, Fée, Dragon |
| `faille` | Faille obscure | Obscurité |

Les onze types du jeu sont couverts **exactement une fois** ; un test l'impose
(`apps/web/src/lib/game/decors.test.ts`). Un type oublié retomberait sur le défaut sans qu'on sache
que c'est un oubli — le joueur verrait un « automatique » qui ne suit pas son deck.

Le choix se fait sur **`/jeu/confort`**, section « Le décor de l'arène » : sept vignettes, dont
« Automatique » en premier. Les vignettes portent `data-decor` et sont donc peintes par **le même
CSS que l'arène** — elles ne peuvent pas montrer autre chose que ce qui sera joué.

## Qui décide, et dans quel ordre

1. **Le choix du joueur** (`jeu_confort_reglages.decor`). Il l'emporte toujours : un joueur qui a
   choisi « Lagon » le garde même en jouant un deck Feu.
2. **Le thème de son deck**, s'il n'a rien choisi.
3. **`arene`**, s'il n'y a rien pour décider.

`decorEffectif()` (`apps/web/src/lib/game/decors.ts`) est cette règle, et rien d'autre.

### Le thème automatique lit *le camp du joueur*, pas la fiche de son deck

La vue d'une partie ne porte pas la composition du deck — le serveur ne l'y expose pas, et il a
raison : ce serait annoncer sa pioche. Elle porte en revanche le type de **mes** cartes (main,
actif, banc, défausse), et ma main seule, dès le premier tour, c'est sept cartes de mon deck.

Conséquences, toutes voulues :

- l'échantillon est **immédiat** et **privé** — `typesDeMonCamp()` ne regarde jamais le camp adverse,
  et un test le vérifie (une fuite d'information, même minuscule, reste une fuite) ;
- à égalité, le type dominant est tranché par le **code**, jamais par l'ordre d'arrivée : sinon le
  même deck donnerait un décor différent selon la pioche ;
- le décor déduit est **figé** pour la durée de la partie (`useDecorArene`). Sans ce verrou, poser
  une Énergie Feu ferait basculer l'arène du gymnase au volcan en pleine partie. Un décor qui change
  tout seul n'est pas un décor, c'est une distraction.

C'est un **écart assumé** à la formulation du plan (« selon le type dominant du deck ») : même
intention, aucune requête supplémentaire, et aucune donnée nouvelle exposée.

## Comment c'est peint

**En CSS, jamais en images.** Quatre JPG de décor existaient déjà dans `apps/web/public/arenes/`
(produits pour la maquette) : **1,24 Mo à eux quatre**, ~300 Ko pièce. Six décors en images, c'est
près de 2 Mo pour de la décoration, sur un jeu qu'on ouvre au téléphone. En dégradés, c'est **zéro
octet transféré** — et c'est la seule forme dont on puisse *calculer* le contraste au lieu de
l'estimer à l'œil. Les JPG restent sur disque pour la maquette ; **le jeu ne les charge pas**.

Chaque décor n'a que **quatre teintes porteuses** : `tapis` (l'ovale mat du centre), `fond`, `bord`
(le vignettage) et `lueur` (la lumière périphérique, la plus claire). Trois couches de dégradés les
composent (`globals.css`, bloc « Décors d'arène »).

Deux propriétés rendent la mesure de contraste **suffisante**, et il faut les préserver :

- les seules couleurs qui **éclaircissent** sont ces quatre teintes ;
- les fondus sont transparents et le vignettage est noir : ils ne peuvent qu'**assombrir**, donc
  jamais abaisser le contraste d'un repère clair.

Mesurer les quatre teintes, c'est donc mesurer le **pire cas** du décor.

### La nuit est dérivée, jamais recopiée

Le soir (20 h → 7 h, heure locale), l'arène porte `data-decor-moment="nuit"` et le CSS dérive chaque
teinte par `color-mix(in srgb, <teinte> 72%, #000000)`. `teintesNuit()` applique **exactement** ce
calcul côté TypeScript, et une garde vérifie que les deux constantes correspondent.

Une seule source de vérité pour douze ambiances : impossible de corriger une teinte de jour en
oubliant sa nuit.

> **Noir pur, et pas un bleu nuit.** Un appoint teinté éclaircissait la composante bleue des teintes
> déjà très sombres (le bord de « Faille obscure » est à `#020304`) : la nuit devenait *plus claire*
> que le jour sur ces teintes-là, l'inverse de ce qu'on annonce. La nuit baisse la lumière, elle ne
> repeint pas.

## Le contraste, mesuré et non estimé

`apps/web/src/__tests__/contraste-decors.test.ts` croise **les douze ambiances** (six décors ×
jour/nuit) × **quatre teintes** × **treize repères** du plateau = **624 mesures**, au seuil WCAG
qui convient à chacun : 4,5:1 pour ce qui se lit (1.4.3), 3:1 pour ce qui se repère (1.4.11).

Deux garde-fous dans le test lui-même :

- il **vérifie son propre calcul** sur des extrêmes connus — un test de contraste complaisant est
  pire que pas de test, puisqu'il rassure ;
- la liste des repères est **ancrée dans le code** : chaque couleur doit exister dans le fichier
  cité. Sans cet ancrage, la liste se périmerait en silence et mesurerait un plateau imaginaire.

Les repères posés sur leur **propre** fond opaque (compteur de dégâts, PV, pastilles d'énergie) ne
touchent pas le décor : ils sont mesurés là où leur contraste se joue, dans `contraste-jeu.test.ts`.

Un **plafond de luminance** (0,06) borne par le calcul le risque nommé du lot — « des décors trop
présents ». Il ne peut pas être relevé sans casser les 624 mesures.

> ### Ce que la mesure a trouvé au passage
>
> Quatre liserés blancs du plateau étaient à 0,28–0,35 d'opacité, donc **sous 3:1 sur le fond
> d'origine déjà** (2,64:1 pour un blanc à 30 % sur `#06120B`) — emplacement vide, récompense prise,
> pile cachée, filets de la ligne centrale. Le défaut **préexistait au lot** ; le critère
> d'acceptation l'exigeait ; ils sont passés à **0,45**. Mesurer leur couleur nominale (du blanc
> pur, 19:1) l'aurait caché au lieu de le trouver : c'est `composer()` — la couleur réellement
> affichée après composition sur le fond — qui fait la différence.

## Où ça vit

| Quoi | Où |
|---|---|
| La table, la règle de choix, jour/nuit | `apps/web/src/lib/game/decors.ts` (pur) |
| Le branchement sur une partie | `apps/web/src/lib/game/use-decor.ts` |
| Les dégradés | `apps/web/src/app/globals.css`, bloc « Décors d'arène » |
| Le calcul WCAG partagé | `apps/web/src/lib/a11y/contraste.ts` |
| Le vocabulaire côté serveur | `apps/api/src/pbm_api/jeu/decors.py` (pur) |
| Le réglage | colonne `jeu_confort_reglages.decor`, routes `GET|PATCH /jeu/confort/reglages` |
| L'écran de choix | `apps/web/src/app/jeu/confort/confort-view.tsx` |

Le serveur ne sait pas à quoi ressemble un décor — il sait seulement **quelles clés existent**, et
il **refuse** les autres (D9) : sans ça, il enregistrerait `"volcan_bleu"` et le joueur aurait un
fond nu en croyant avoir choisi un décor. Un test de parité compare les six clés Python aux six clés
TypeScript, dans l'ordre.

### `NULL` veut dire « automatique », pas « pas encore renseigné »

La colonne est **nullable sans `server_default`**. C'est le seul moyen de distinguer « je veux le
gymnase » de « je n'ai rien demandé ». Un `DEFAULT 'arene'` aurait donné à tous les comptes existants
un choix explicite qu'ils n'ont jamais fait, et rendu le thème automatique inatteignable, en silence.

Côté API, cela oblige `PATCH` à distinguer **trois** états : champ absent (ne touche à rien),
clé (choisis), `null` explicite (reviens à l'automatique). C'est ce que porte `decor_fourni` dans
`confort_service.enregistrer_reglages` — sans lui, revenir à l'automatique serait impossible.

## « Je n'ai pas le bon décor »

1. **« Le décor ne change pas en cours de partie »** — c'est voulu : le décor déduit est figé au
   lancement. Changer son choix dans `/jeu/confort`, lui, s'applique tout de suite.
2. **« J'ai choisi un décor et le jeu en montre un autre »** — vérifier que le réglage est bien
   enregistré (`GET /jeu/confort/reglages`). Une clé inconnue est **refusée** par l'API (422) ; une
   clé inconnue trouvée dans le cache local du navigateur est ramenée à l'automatique.
3. **« L'arène est noire »** — un décor dont le bloc CSS manque ne pose aucune teinte. La garde
   `decors-css-garde.test.ts` l'interdit ; si elle est verte, regarder plutôt `data-decor` sur
   `.pbm-arena` dans l'inspecteur.
4. **« C'est sombre en plein jour »** — l'ambiance suit l'heure **locale du navigateur**. Après
   20 h, la nuit est normale.

## Le déblocage par les badges : TRANCHÉ, et c'est non (15/10/2026)

**Les six décors sont tous disponibles, et le restent.** Ce lot avait laissé la question ouverte
(4ᵉ point de sa mission, « si DJ6 le retient ») en notant qu'aucun champ « verrouillé » n'avait été
posé en prévision : on ne fabrique pas un mécanisme de déblocage qui ne débloque rien (D9).

`j-profil-jeu` (palier 17) a eu les badges en main et a **choisi de ne rien verrouiller**, pour une
raison plus forte que la symétrie : **verrouiller aujourd'hui retirerait aux joueurs un choix qu'ils
ont déjà**. DJ6 dit « sans saison ni perte de points » — reprendre quatre décors sur six pour les
faire regagner serait exactement une perte. La vitrine du profil (`/jeu/profil`) les montre donc
pour ce qu'ils sont : disponibles, celui du joueur mis en avant. Détail : `docs/jeu/PROFIL.md`.
