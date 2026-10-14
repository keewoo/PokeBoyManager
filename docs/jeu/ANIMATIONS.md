# Socle d'animation du plateau — `lib/game/animations.ts`

> Livré par le lot `j-anim-socle` (jalon J3). Le code vit dans
> `apps/web/src/lib/game/animations.ts` (pur) et
> `apps/web/src/components/game/animation-layer.tsx` (crochet React + couche visuelle).
> Cette fiche documente **la mécanique et ses règles**, pour que les lots d'animation qui
> viennent (`j-anim-attaques-typees`, `j-anim-evolution-ko`, `j-anim-pokemon-apparition`,
> `j-son`, `j-arene-decors`) s'y branchent sans la réinventer ni la contourner.

## Pourquoi, en une phrase

**Les effets suivent les événements, jamais l'inverse.** Le serveur a déjà décidé ; une
animation ne fait que le raconter. Elle n'est pas une source de vérité, et **rien de ce
qu'elle fait ne conditionne l'état affiché ni le droit de jouer**.

Le piège que ce socle évite, et c'est celui que le lot nommait : faire dépendre l'état
affiché de la fin d'une animation. Au moindre onglet passé en arrière-plan, le plateau se
figerait dans un état faux — l'animation n'ayant jamais fini, l'écran n'aurait jamais
rattrapé le serveur. Ici la file ne retient rien : elle se jette, et l'écran reste juste.

## La mécanique, en quatre pièces

| Pièce | Où | Rôle |
|---|---|---|
| Le **plan** | `planifier(coups, pour)` | une entrée par événement, dans l'ordre, **sans exception** |
| Le **registre** | `EFFETS` | quel type d'événement moteur donne quel effet, et pendant combien de temps |
| La **file** | `reduireFile(file, action)` | au plus **une** animation en cours, le reste en attente |
| Le **temps** | `useFileAnimations` | une minuterie par animation — jamais une boucle par cadre |

La file est un **réducteur pur** : état sérialisable, aucune E/S, aucune référence au DOM.
Elle se teste par milliers de cas sans navigateur, exactement comme le moteur de jeu.
Les cinq actions sont `empiler`, `avancer`, `sauter`, `vider`, `mode` (plus
`reinitialiser` au changement de partie).

### Le temps passe par minuterie, pas par cadre

C'est le choix qui tient la fluidité, et il mérite d'être dit : une animation se termine
par un `setTimeout` de sa durée, et le mouvement lui-même est fait par le **CSS**, donc
par le compositeur. React ne rend donc qu'**une fois par animation** — deux ou trois
rendus par seconde. Une boucle `requestAnimationFrame` qui aurait dispatché à chaque
cadre aurait fait rendre tout le plateau soixante fois par seconde : c'est le socle
lui-même qui aurait mangé les images qu'il prétend compter.

Corollaire utile : un onglet en arrière-plan ne gèle pas la file. `setTimeout` continue
de s'y déclencher (ralenti), et de toute façon `visibilitychange` la **vide** aussitôt.

## Les règles qui ne se discutent pas

1. **Aucune animation ne peut empêcher une action légale d'être jouée.** La couche
   visuelle est en `pointer-events-none` et en `absolute` dans l'arène ; jouer un coup
   **vide** la file avant même de soumettre (`PartieView.onJouer`). Un bouton « passer »
   est offert tant qu'une animation tourne.
2. **Aucun événement ne disparaît.** Un type absent du registre `EFFETS` produit tout de
   même son entrée (`effet: null`, `duree: 0`) : il traverse la file en un instant, et le
   journal de partie en porte la phrase. On n'approxime jamais un effet qu'on ne connaît
   pas (D9), et on ne le masque jamais non plus.
3. **Les durées sont bornées** (`DUREE_MAX`, 900 ms) et le registre est contrôlé par un
   test : une durée nulle ou hors borne fait échouer la CI.
4. **`prefers-reduced-motion` passe la file en mode `reduit`** : durées nulles, et
   **aucun** effet rendu (le crochet renvoie `null`). La file se vide quand même, un coup
   après l'autre — rien ne bloque, rien ne disparaît.
5. **Le mode accéléré** divise les durées par `FACTEUR_ACCELERE` (4), pour le joueur
   pressé. Il est masqué quand le système demande des animations réduites : une demande
   d'accessibilité n'est pas une préférence de confort.
6. **Seules `transform` et `opacity` sont animées** en CSS. C'est gardé par
   `src/__tests__/anim-css-garde.test.ts`, qui lit `globals.css` et refuse toute autre
   propriété dans une image-clé `pbm-anim-*`. Animer `width`, `top`, `box-shadow` ou
   `filter` remet le fil principal au travail à chaque image — et le plancher tombe sur
   l'appareil de référence, pas sur la machine de qui écrit le CSS.

## Le rattrapage — la reprise après coupure

À la reconnexion, le canal temps réel resynchronise depuis le dernier coup appliqué et
livre **d'un bloc** tout ce qui a été manqué. Les rejouer un par un ferait regarder dix
secondes d'un film que personne n'a demandé.

Au-delà de `SEUIL_RATTRAPAGE` (6 animations) **ou** de `BUDGET_RATTRAPAGE` (2,4 s), la
file garde les `GARDEES_RATTRAPAGE` (2) dernières animations — celles qui expliquent la
situation présente — et remplace tout ce qui précède par **une** animation de résumé qui
dit combien (« 18 coups rejoués »). Les entrées muettes, elles, sont toutes conservées :
elles ne coûtent rien, et les perdre reviendrait à masquer des événements.

Mesuré par le test : vingt coups d'un bloc donnent **trois** animations, et la rafale
rattrapée tient dans le budget annoncé.

## Le plancher d'images par seconde

`PLANCHER_FPS = 30`, sur un **appareil de référence** nommé : une fenêtre de 844×390 (le
téléphone d'un enfant tenu en paysage, comme le critère de `j-plateau-layout`) et un
**bridage processeur ×4** (`Emulation.setCPUThrottlingRate`), qui est la façon dont
Chromium simule un appareil lent.

Il est tenu par trois choses, et vérifié de trois façons — c'est voulu, parce qu'une
mesure seule ne dit jamais *pourquoi* elle vient de tomber :

| Ce qui le tient | Ce qui le vérifie |
|---|---|
| une seule animation à la fois, un coût de file négligeable | `src/lib/game/animations.test.ts` (pur, déterministe) |
| seules `transform` et `opacity` sont animées | `src/__tests__/anim-css-garde.test.ts` (garde statique) |
| le résultat, au navigateur | `e2e/anim-fluidite.spec.ts` (mesure, chiffre publié dans le journal de la CI) |

L'e2e compte les cadres réellement rendus pendant la rafale et **échoue** si la couche
d'animation n'est jamais apparue, ou si l'échantillon de cadres est trop faible pour
conclure : une fenêtre vide ne doit pas pouvoir passer pour un succès.

## Ajouter un effet — ce qu'il faut faire, et ce qu'il ne faut pas

Les lots aval enrichissent le **registre**, pas la mécanique :

1. ajouter l'entrée dans `EFFETS` (`{ effet, duree }`), durée bornée ;
2. ajouter son mot dans `LIBELLES` (`animation-layer.tsx`) ;
3. ajouter ses images-clés dans `globals.css`, **`transform`/`opacity` uniquement** ;
4. ajouter le test qui le montre — et la durée du registre est déjà contrôlée.

Ce qu'il ne faut pas faire, et qui annulerait tout le lot :

- **attendre la fin d'une animation** pour appliquer un changement d'état (c'est le
  risque que ce socle existe pour écarter) ;
- **rendre plusieurs animations simultanées** : l'invariant « une à la fois » est ce qui
  borne le travail par cadre sur un téléphone d'entrée de gamme ;
- **poser un élément en flux normal** sur la page de partie : elle ne tolère **aucun**
  défilement (`e2e/plateau-responsive.spec.ts`) — tout ce qui s'ajoute est `absolute`
  dans l'arène, ou `fixed` comme le tiroir du journal ;
- **capturer les clics** : la couche reste `pointer-events-none`, seuls ses boutons sont
  cliquables.

## Voir aussi

- `docs/jeu/JOURNAL.md` — les événements et leur format : c'est la matière première.
- `docs/jeu/TEMPS-REEL.md` — le canal, la resynchronisation, le repli en interrogation.
- `docs/UI-UX.md` — les écrans et les jetons de style du plateau.
