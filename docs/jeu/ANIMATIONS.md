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

---

# Les effets d'attaque par type — `lib/game/anim-types.ts`

> Lot `j-anim-attaques-typees`. Le socle ci-dessus dit *quand* une animation se joue ; cette
> partie dit *à quoi elle ressemble* quand l'animation est une attaque. Une attaque Feu brûle la
> carte d'en face, l'éclair fait trembler le plateau, l'onde Psy déforme l'image.

## Un système, pas dix animations

Le risque était nommé : « dix animations écrites séparément : impossible à maintenir, et l'une
d'elles finira par cacher un compteur de dégâts au moment décisif ». Il n'y a donc **aucune
animation par type**. Il y a :

| Pièce | Où | Quoi |
|---|---|---|
| **six couches** | `globals.css`, images-clés `pbm-anim-fx-*` | `nappe`, `balayage`, `onde`, `particules`, `flash`, `etreinte` — une image-clé chacune, écrite une seule fois |
| **quatre gestes de carte** | idem | `aucun`, `distorsion`, `recul`, `tremblement` — toujours un `transform`, donc aucun défilement provoqué |
| **une table** | `SPECS` dans `anim-types.ts` | onze lignes de **donnée** : quelles couches, combien de particules, quel geste, trace ou non |
| **une fonction** | `effetAttaque()` | module la composition par une **intensité** calculée sur le résultat réel de l'attaque |

Ajouter un type, c'est ajouter une ligne de table. Et comme les onze types partagent les mêmes
couches, une couche qui masquerait un compteur les masquerait **tous les onze** : ça se verrait au
premier essai, au lieu d'attendre la carte Dragon du dixième tour.

**Pourquoi du CSS et pas un canvas** (le lot disait « shaders/canvas légers ») : c'est le plancher
d'images par seconde qui tranche. Le socle tient ses 30 images/s *parce que* rien ne passe par le
fil principal. Un canvas redessinerait à la main, chaque image, sur ce fil — il reprendrait
exactement ce qu'on a économisé. Les images-clés sont nommées `pbm-anim-fx-*` pour tomber sous la
**même** garde statique que le socle (`src/__tests__/anim-css-garde.test.ts`, `transform`/`opacity`
uniquement) : un autre préfixe les en aurait sorties, ce qu'un garde-fou interdit de faire.

## L'intensité vient du serveur, jamais de l'écran

Trois faits décident de la force d'un effet, et **aucun** ne peut être deviné côté client :

| Fait | D'où il vient |
|---|---|
| le **type** de l'attaque | `attaque_declaree.donnees.type` — ajouté par ce lot (`combat/attaque.py`) |
| les **dégâts** réels | `degats.donnees.degats` |
| **faiblesse** / **résistance** | `degats.donnees.faiblesse` / `.resistance`, booléens ajoutés par ce lot (`combat/resolution.py`) |
| l'**échec** | un `dsl_pile_ou_face` sans aucune face, ou une Confusion sur pile (R-11.5) |

⚠️ Les deux booléens existent pour une raison précise : le seul autre moyen de savoir si la
faiblesse a joué serait de **chercher le mot « faiblesse » dans la phrase `detail`**. Ce serait un
repli silencieux — il cesserait de marcher le jour où la phrase change, l'effet continuerait de
s'afficher, simplement faux, et personne ne le verrait.

⚠️ Le type ne se déduit **pas** de l'Actif courant côté client : la vue a pu bouger entre l'attaque
et l'animation. Le serveur fait autorité, y compris là-dessus.

La faiblesse et la résistance pèsent **en plus** du doublement / de la réduction qu'elles ont déjà
produit sur les dégâts. Sans ce supplément, une attaque de 60 doublée par faiblesse serait
visuellement identique à une attaque de 120 sans faiblesse — et le joueur ne verrait pas *pourquoi*
ça a fait mal. Un **échec** court-circuite tout : l'effet part et retombe, sans particule, sans
secousse, sans déformation. Sinon on ne distinguerait pas « ça a raté » de « ça a fait 10 ».

Les événements lus par le planificateur sont ceux du **coup entier**, pas de l'événement isolé :
`degats` arrive **avant** `attaque_declaree` dans la liste du moteur, et c'est ce dernier qui porte
le type.

## Les trois choses que l'effet ne fait jamais

1. **Il ne masque pas le plateau plus d'une seconde** (`TOTAL_MAX_MS`). Tenu par construction :
   `effetAttaque` rabote la **trace** résiduelle pour que `animation + trace` ne dépasse jamais la
   borne, quelle que soit la durée que le socle donne. C'est la trace qui cède, jamais l'animation
   — une animation tronquée se voit, une trace écourtée non.
2. **Il ne couvre pas les compteurs de dégâts.** La parade n'est pas une consigne mais un **ordre
   de DOM** : dans `board-card.tsx`, l'effet est rendu **avant** les indicateurs, donc dessous.
   Inverser les deux lignes fait tomber un test (`board-card.test.tsx`).
3. **Il n'invente pas un type.** Un type absent de `SPECS` ne donne **aucun** effet typé : le socle
   garde son effet neutre (D9). Pareil pour une attaque sans dégât et sans échec — elle se lit dans
   le journal, pas en fanfare.

## La version réduite

En « animations réduites » (réglage système `prefers-reduced-motion` **ou** réglage du jeu,
`/jeu/confort`), l'effet prend une forme **immobile** : aucune couche, aucun geste, aucune secousse,
et à la place un **badge** qui dit en texte ce que l'animation aurait montré — « Feu — attaque
violente, 120 dégâts : c'est une faiblesse, ça fait double mal ». Le badge porte l'**abréviation**
du type (jamais la couleur seule : daltonisme), et il est **annoncé** aux lecteurs d'écran
(`role="img"` + `aria-label`), contrairement à la couche animée qui est `aria-hidden` — en réduit,
c'est le seul canal visuel qui reste.

⚠️ Il **vit sa propre durée**, hors de la file. En mode réduit la file avance en zéro milliseconde :
un badge accroché à l'animation courante clignoterait sans jamais être lisible. Comme l'état affiché
ne dépend jamais d'une animation, le faire vivre plus longtemps ne retient rien.

## La galerie — `/jeu/effets`

Le lot demandait de « faire valider le rendu par JF et par Aymeric ». Le faire en partie
demanderait de réunir un Pokémon de chacun des onze types, avec la bonne faiblesse, la bonne
résistance et un pile ou face perdu : autant dire jamais. `/jeu/effets` montre les onze types × six
situations, d'un clic, avec le **même** code que le plateau (`effetAttaque` et `EffetTypeAttaque`,
rien de reproduit) — une galerie qui redessinerait les effets à sa façon ne vaudrait aucune
validation. Elle respecte le réglage « animations réduites » comme le plateau, et elle est
atteignable depuis le salon.

## Ajouter un type — ce qu'il faut faire

1. ajouter la ligne dans `SPECS` (couches, particules, geste, trace) ;
2. ajouter sa **teinte** dans `globals.css` (`.pbm-fx[data-fx="<cle>"]`) — sans elle l'effet serait
   transparent, donc invisible, donc mensonger. `anim-types-css-garde.test.ts` nomme la manquante ;
3. s'assurer que le code existe dans `ELEMENTS` (`lib/game/indicateurs.ts`) : c'est de là que vient
   l'abréviation du badge réduit, et le contraste y est déjà mesuré pour les onze types ;
4. rien d'autre — les couches, les gestes, l'intensité et les bornes sont déjà là.

Ce qu'il ne faut **pas** faire : écrire une image-clé propre à un type (c'est le retour aux dix
animations séparées), ou nommer une image-clé autrement que `pbm-anim-fx-*` (elle échapperait à la
garde `transform`/`opacity`).

## Le plancher, avec l'effet le plus lourd

`e2e/anim-attaques-typees.spec.ts` mesure le plancher sur le type **le plus lourd de la table** —
calculé (`TYPE_LE_PLUS_LOURD`), pas choisi : le jour où un type plus chargé est ajouté, c'est lui
qui est mesuré, sans que personne n'ait à y penser. La fenêtre de mesure est **exactement** celle de
`anim-fluidite.spec.ts` (la rafale entière, pas le premier effet) : c'est ce qui rend les deux
chiffres comparables, et c'est de leur écart qu'on apprend ce que l'effet typé coûte vraiment.

# Les six moments clés — `lib/game/anim-moments.ts`

> Lot `j-anim-evolution-ko`. Évoluer, tomber K.O., prendre une récompense, se mettre en place,
> repiocher, lancer la pièce. Ce sont les instants qu'un joueur raconte après la partie.

## Deux files, et pourquoi ce n'est pas un doublon

Le socle garde la sienne : une pastille à la fois, au rythme de son registre `EFFETS`. Les moments
ont la **leur** (`reduireMoments`), pour trois raisons qui sont des faits, pas des préférences :

| | |
|---|---|
| Un moment dure plus que la case que le socle lui donne | le socle borne tout à `DUREE_MAX` = 900 ms ; un K.O. qui bascule, s'éteint **puis** rejoint la défausse a besoin de ses trois temps |
| Deux moments peuvent naître du **même** événement | un `ko` porte la mise K.O. *et* `recompenses_prises` — le serveur ne les sépare pas, et le socle produit **une** entrée par événement |
| Le socle peut avaler un événement sans l'exposer | son `avancer` enchaîne plusieurs entrées de durée nulle en un seul appel : un moment accroché à `courante` aurait disparu sans un mot (`main_revelee` et `mise_en_place_revelee` ne sont même pas à son registre) |

Les deux files sont alimentées par les **mêmes** coups, chacune de son côté. Aucune ne dépend de
l'autre, et comme le socle, **aucune ne retient l'état du plateau** : on les jette à tout instant.

## Un système, pas six animations

Même parade que les effets typés : **six couches**, **quatre gestes**, chacun avec *une* image-clé
écrite une seule fois (`globals.css`, bloc « Les six moments clés »), et une **table** de six lignes
qui dit seulement quoi composer, dans quel ordre et pendant combien de temps.

| Couche | Ce qu'elle fait |
|---|---|
| `halo` | une auréole lumineuse qui gonfle puis retombe — l'évolution, la récompense révélée |
| `fondu` | un fondu enchaîné de l'entrant sur le sortant — l'évolution, la révélation |
| `voile` | un voile sombre qui éteint l'objet — le K.O. qui se désature |
| `traine` | une traînée le long du trajet — vers la défausse, vers la main |
| `eclat` | un éclat bref — la révélation simultanée, la pièce qui s'arrête |
| `rotation` | la pièce qui tourne, et **elle seule** (un test le garde) |

Gestes de l'objet : `pose`, `bascule`, `envol`, `retournement`. Toujours un `transform` — aucune
boîte de disposition ne change, donc rien ne peut provoquer de défilement (`j-plateau-layout`).

Un moment se découpe en **temps pondérés** plutôt qu'en durées fixes. C'est ce qui permet de
**comprimer** une rafale sans toucher au CSS : les parts restent les mêmes, le total change.

## Les six lignes

| Genre | Événement du serveur | Les temps | Durée |
|---|---|---|---|
| `evolution` | `evolution` | montée (halo, pose) → fondu (fondu, éclat) | 620 ms |
| `ko` | `ko` | bascule → extinction (voile) → défausse (traînée, envol) | 760 ms |
| `recompense` | `ko` avec `recompenses_prises > 0` | vol (traînée, envol) → révélation (halo, éclat, retournement) | 680 ms |
| `mise-en-place` | `mise_en_place_revelee` | distribution → alignement → **révélation simultanée** | 1200 ms |
| `mulligan` | `main_revelee` | révélation (retournement) → remélange (envol) | 900 ms |
| `piece` | `dsl_pile_ou_face`, `confusion_resolue` | rotation → arrêt | 820 ms |

La mise en place a la durée la plus longue des six : c'est **le premier effet qu'un joueur voit**.

## Les trois choses que ces animations ne font jamais

**Durer plus qu'une seconde et demie.** `MOMENT_MAX_MS = 1500`, la borne que le lot nomme mot pour
mot (« au-delà d'une seconde et demie, elle agace au lieu de marquer »). Tenue par construction, et
vérifiée **pour les six genres** — pas laissée à la vigilance de qui ajoutera la septième ligne.

**Ajouter une occlusion au plateau.** Un moment **remplace** la pastille du socle dans la même case
centrale de l'arène ; il ne s'y ajoute pas. Un tableau plein écran aurait été plus spectaculaire et
aurait masqué les compteurs de dégâts pendant une seconde et demie — exactement ce que le lot
précédent s'était fait interdire. Un moment remplace un mot, il n'ajoute rien.

**Perdre un moment.** La file ne résume jamais et ne jette jamais ce qui attend : elle **accélère**,
bornée par `COMPRESSION_MIN` (45 %). C'est la différence de nature avec le rattrapage du socle, qui
a vingt pastilles à condenser là où la file de moments en a quatre à faire voir.

## Le double K.O., et pourquoi la clé porte le rang

Un double K.O. (R-13.5) produit **quatre** moments : K.O., récompense, K.O., récompense. Ils sont
joués un par un, et aucun ne manque. Ce qui le garantit tient dans la forme de la clé —
`numero:rang:genre` : les deux `ko` viennent du **même coup**, donc sans le rang de l'événement le
second écraserait le premier à l'empilage, et un K.O. disparaîtrait de l'écran sans un bruit.

C'est testé dans les deux sens : la version pure prouve l'ordre et l'unicité, la version composant
prouve que les quatre sont bien **rendus** l'un après l'autre.

Le tempo d'un moment est **figé à sa prise** (`FileMoments.retard`). Lire l'attente courante aurait
fait recalculer la durée en cours de route — l'écran aurait redémarré l'animation à chaque coup reçu.

## Le pile ou face honnête — ce qui est garanti, et ce qui ne l'est pas

Le critère du lot est : « le pile ou face ne donne jamais une impression de résultat prédéterminé
côté client ». Trois faits le tiennent, tous testés :

1. **Aucun tirage n'a lieu côté client.** Pas un `Math.random`, pas une graine. Le résultat vient du
   serveur, qui fait autorité. Une garde statique relit la source du module pour s'en assurer.
2. **La rotation ne sait rien du résultat.** Durée, nombre de tours, nombre d'objets, retards,
   phases : tout est calculé *sans jamais lire* `faces`. Deux lancers opposés produisent un effet
   identique au seul champ `ObjetMoment.face` près — et ça reste vrai **comprimé**, qui est le
   chemin par lequel une dépendance aurait pu se glisser sans qu'on y pense.
3. **Le résultat n'arrive qu'à la fin.** `revelationA` vaut la fin du temps `rotation`, donc
   strictement plus que zéro et strictement moins que la durée totale. Le CSS ne pose la face finale
   qu'à partir de là : avant, les deux faces ont une opacité nulle — rien ne les distingue.

**Ce qui n'est pas prétendu**, et qu'il vaut mieux écrire que laisser croire : le résultat est déjà
dans la charge utile reçue du serveur, puisque c'est le serveur qui a tranché. Un joueur qui
ouvrirait l'inspecteur le verrait. Ce qu'une animation peut garantir, c'est qu'elle ne le laisse pas
fuir — pas qu'elle l'ignore.

> ⚠️ Le serveur n'envoie que des **comptes** (`pieces`, `faces`), pas quelle pièce est tombée sur
> face : le moteur n'a pas d'ordre à leur donner. L'écran en fabrique un (les `faces` premières).
> C'est de la **présentation**, pas de l'information inventée — le compte affiché est exactement
> celui du serveur, et c'est le seul fait qui existe.

## La version réduite

Pour les six genres, et vérifiée genre par genre. Elle n'est pas « la même chose en plus court » :
aucune phase, aucun objet, rien qui bouge. Toute la charge d'information passe dans `phrase` (badge
annoncé en `role="img"` + `aria-label`) et `badge`. Elle reste une seconde à l'écran — le temps
d'être lue, là où une animation se comprend en la voyant passer.

Et elle porte **les comptes** : « 2 cartes récompenses », « 1 face sur 2 », « main de 7 cartes ».
C'est précisément ce qui disparaîtrait si on coupait les animations sans y penser.

## La galerie — `/jeu/effets`

La page des effets typés porte désormais une seconde section, « Les six moments clés ». Chaque
vignette part d'un **vrai événement du moteur**, passé par `momentsEvenement` : si la lecture d'un
`recompenses_prises` se cassait, la galerie se casserait avec le plateau au lieu de continuer à
montrer un joli film.

Les **trois lancers de pièce** (0, 1 et 2 faces sur 2) sont côte à côte exprès : c'est comme ça
qu'on vérifie à l'œil ce que le test affirme — les trois tournent exactement pareil.

## Ajouter un moment — ce qu'il faut faire

1. une ligne dans `MOMENTS` (genre, libellé, temps, durée ≤ `MOMENT_MAX_MS`) ;
2. le `case` correspondant dans `momentsEvenement`, qui lit l'événement **réel** du serveur ;
3. si la ligne introduit une couche ou un geste neuf : son sélecteur et son image-clé
   `pbm-anim-fx-m-*` dans `globals.css` — `anim-moments-css-garde.test.ts` nomme la manquante ;
4. sa phrase et son badge (`phraseMoment`, `badgeMoment`) : la version réduite est **obligatoire**.

Ce qu'il ne faut **pas** faire : écrire une animation à part pour un genre. La table est ce qui fait
qu'une couche masquant un chiffre les masquerait pour les six — donc que ça se verrait au premier
essai, au lieu d'attendre le double K.O. du dixième tour.

## Voir aussi

- `docs/jeu/JOURNAL.md` — les événements et leur format : c'est la matière première.
- `docs/jeu/DEGATS.md` — l'ordre strict du calcul, d'où viennent dégâts, faiblesse et résistance.
- `docs/jeu/TEMPS-REEL.md` — le canal, la resynchronisation, le repli en interrogation.
- `docs/jeu/ACCESSIBILITE.md` — les trois réglages de confort, dont « animations réduites ».
- `docs/jeu/REGLES.md` — R-4.1 à R-4.5 (mise en place, mulligan), R-13.1 et R-13.5 (K.O. et
  simultanéité), R-11.5 (Confusion) : ce que les six moments mettent en images.
- `docs/UI-UX.md` — les écrans et les jetons de style du plateau.
