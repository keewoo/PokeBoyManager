# `j-anim-socle` — Socle d'animation : les effets suivent les événements, jamais l'inverse

> Jalon **J3**, palier 14, piste Graphisme & animations, couloir **J-GFX**.
> Exécuté le **14/10/2026**, piloté depuis devAI, travaillé sur **chimera** (WSL Ubuntu-24.04),
> worktree `~/dev/wt-j-anim-socle`, branche `roadmap/j-anim-socle`, PR **#83**.
> Garde-fou d'ordre : `suivi.py verifier j-anim-socle` → **code 0** (« ordre tenu »).

## Résumé

Le plateau a désormais une **file d'animations** alimentée par les événements que le serveur a
déjà décidés — et par rien d'autre. Elle est **pure** (`apps/web/src/lib/game/animations.ts` :
aucune E/S, aucun React, état sérialisable), branchée à l'écran par un crochet et une couche
visuelle (`apps/web/src/components/game/animation-layer.tsx`).

Le point dur du lot n'était pas graphique, il était architectural : **ne jamais faire dépendre
l'état affiché de la fin d'une animation**. C'est tenu de bout en bout. La vue reste celle du
serveur ; la file ne retient rien ; jouer un coup la **jette** avant même de soumettre ; un onglet
passé en arrière-plan la **vide**. Rien ne peut donc figer le plateau dans un état qui n'existe pas.

Deux décisions de conception méritent d'être nommées, parce qu'elles sont ce qui fait tenir le
critère de fluidité :

1. **le temps passe par minuterie, pas par boucle de cadre.** Une animation se termine par un
   `setTimeout` de sa durée, et le mouvement est fait par le CSS, donc par le compositeur. React ne
   rend qu'**une fois par animation** (deux ou trois rendus par seconde). Une boucle
   `requestAnimationFrame` qui aurait dispatché à chaque cadre aurait fait rendre tout le plateau
   soixante fois par seconde : le socle lui-même aurait mangé les images qu'il prétend compter ;
2. **seules `transform` et `opacity` sont animées**, et c'est **gardé par un test statique** plutôt
   que par une consigne. Animer `width`, `top`, `box-shadow` ou `filter` remet le fil principal au
   travail à chaque image — et ça ne se voit pas sur la machine de qui écrit le CSS, seulement sur
   l'appareil de référence.

## Livrables

| Livrable attendu | Où |
|---|---|
| file d'animations | `apps/web/src/lib/game/animations.ts` (plan, registre `EFFETS`, réducteur, rattrapage) |
| mode accéléré et réduit | même fichier (`dureeEffective`, `FACTEUR_ACCELERE`) + `useFileAnimations` (`prefers-reduced-motion`) et son bouton « Accélérer » |
| mesure de fluidité | `apps/web/e2e/anim-fluidite.spec.ts` (mesure), `apps/web/src/__tests__/anim-css-garde.test.ts` (garde la cause) |
| couche visuelle | `apps/web/src/components/game/animation-layer.tsx` + images-clés `pbm-anim-*` dans `src/app/globals.css` |
| câblage | `components/game/game-board.tsx` (couche dans l'arène) et `app/jeu/parties/[id]/partie-view.tsx` (file nourrie par les coups diffusés) |
| documentation | **`docs/jeu/ANIMATIONS.md`** (la fiche), renvoi de trois lignes depuis `docs/UI-UX.md` |

`CLAUDE.md` n'a **pas** été touché, volontairement : sa carte des fiches ne liste pas les fiches
individuelles de `docs/jeu/` (ni `JOURNAL.md`, ni `TEMPS-REEL.md` n'y figurent), et le lot n'apporte
aucune règle qui s'applique en dehors du jeu. La règle « où écrire quoi » est respectée : le savoir
durable est dans **une** fiche.

## Critères d'acceptation — preuves

### 1. « Aucune animation ne peut empêcher une action légale d'être jouée (l'animation se saute) » ✅

- **Prouvé au niveau écran** par `components/game/game-board-animations.test.tsx` : le plateau est
  rendu avec une animation **en cours**, le coup légal part quand même et `onJouer` reçoit l'action
  exacte du moteur. Le même fichier vérifie que la couche est `pointer-events-none`, qu'elle vit
  **dans** `.pbm-arena` en `absolute` (donc n'allonge pas la page), et que le plateau se rend à
  l'identique avec et sans animation.
- **Prouvé au niveau file** par `animations.test.ts` : `sauter` enchaîne immédiatement, `vider` ne
  laisse rien en vol, et ce qui a été jeté ne se rejoue pas à la resynchronisation suivante.
- **Prouvé au navigateur** par `e2e/anim-fluidite.spec.ts` (second test) : les clics sur « Passer »
  terminent la rafale, et la main du joueur reste dans la fenêtre.
- **Et le geste décisif** : `PartieView.onJouer`/`onRepondre` appellent `viderAnimations()` **avant**
  de soumettre. L'écran ne se met jamais en travers.

**Vérifié en cassant volontairement**, sur chimera : retirer `pointer-events-none` de la couche fait
**échouer 2 tests** (`game-board-animations` + `animation-layer`). La garde mord.

### 2. « Un événement sans animation définie ne bloque ni ne disparaît » ✅

Le registre `EFFETS` est **délibérément partiel** (23 types animés sur les 42 que le serveur
diffuse) : un mélange de pioche ou un verrou d'effet se lit dans le journal, pas en fanfare. Un type
absent produit tout de même son entrée dans le plan, avec `effet: null` et `duree: 0`.

Trois tests le tiennent :

- un type inventé (`un_type_que_le_front_ne_connait_pas`) produit son entrée, sans effet ni durée ;
- une rafale de **30 entrées muettes** suivie d'un K.O. se vide en **un seul** pas de temps — la
  suivante devient courante, rien n'est retenu ;
- les **42 types** de `TYPES_EVENEMENT_CONNUS` (le registre du journal) donnent 42 entrées, dans
  l'ordre, et la file les consomme toutes sans en abandonner une.

### 3. « Le plancher d'images par seconde est tenu sur l'appareil de référence » ✅

**L'appareil de référence est nommé, pas sous-entendu** : fenêtre **844×390** (le téléphone d'un
enfant tenu en paysage, comme le critère de `j-plateau-layout`) et **bridage processeur ×4**
(`Emulation.setCPUThrottlingRate`, la façon dont Chromium simule un appareil lent). Plancher
annoncé : **`PLANCHER_FPS = 30`**.

**Mesure réelle, lue dans le journal de la CI** (job `e2e`, run `38552982711`) :

```
[j-anim-socle] fluidité mesurée : 59.9 images/s (150 cadres en 2503 ms, 844×390, CPU ×4)
```

**59,9 images/s pour un plancher de 30** — le double de la marge demandée, sur 150 cadres
échantillonnés pendant 2,5 s d'animation continue. Le test publie son chiffre à chaque passage :
c'est une mesure, pas une intention.

Deux garde-fous contre une mesure qui mentirait, et ils sont dans le test : il **exige** d'avoir vu
la couche d'animation apparaître (une fenêtre vide échoue au lieu de passer), et il **exige** un
échantillon minimum de 20 cadres.

La **cause** du plancher est gardée séparément, parce qu'une mesure ne dit jamais *pourquoi* elle
tombe : `anim-css-garde.test.ts` lit `globals.css` et refuse toute propriété non composable dans une
image-clé `pbm-anim-*`. **Vérifié en cassant volontairement** : ajouter `filter: blur(2px)` dans
`@keyframes pbm-anim-pulse` fait échouer la garde avec le message exact
(« anime filter : hors du compositeur, le plancher d'images par seconde tombe »).

## Le rattrapage (mission 3 du lot)

Au-delà de `SEUIL_RATTRAPAGE` (6 animations) **ou** `BUDGET_RATTRAPAGE` (2,4 s), la file garde les
**2 dernières** animations et remplace tout ce qui précède par **une** animation de résumé qui dit
combien (« 18 coups rejoués »). Mesuré : vingt coups livrés d'un bloc donnent **3** animations, et la
rafale rattrapée tient dans le budget annoncé (alors que les vingt dépasseraient largement).

Les entrées **muettes** sont toutes conservées par un rattrapage (vérifié : 20 sur 20) — elles ne
coûtent rien, et les perdre reviendrait à masquer des événements.

Un détail payé d'avance : le résumé **somme les `nombre`** des animations qu'il remplace au lieu de
les compter. Deux coupures de suite, et le second résumé continue de dire combien d'événements réels
il représente — et non « 1 ».

## `prefers-reduced-motion`

Le réglage système passe la file en mode `reduit` : durées nulles et **aucun** effet rendu (le
crochet renvoie `null`). La file se vide quand même, un coup après l'autre — rien ne bloque, rien ne
disparaît. Le bouton « Accélérer » est alors **masqué** : une demande d'accessibilité n'est pas une
préférence de confort, on ne lui propose pas un réglage concurrent.

## Tests

| Fichier | Tests | Quoi |
|---|---|---|
| `src/lib/game/animations.test.ts` | 18 | plan, registre, bornes, modes, rattrapage, invariant « une à la fois », coût du réducteur |
| `src/components/game/animation-layer.test.tsx` | 11 | minuterie, accéléré, sauter/vider, onglet caché, reduced-motion, couche |
| `src/components/game/game-board-animations.test.tsx` | 4 | **critère 1** : jouer pendant une animation |
| `src/__tests__/anim-css-garde.test.ts` | 3 | garde statique des images-clés |
| `e2e/anim-fluidite.spec.ts` | 2 | **critère 3** : mesure de fluidité, et « passer » termine la rafale |

**38 tests nouveaux.** Mesures sur chimera : suite web **339/339 verte** (60 fichiers),
`type-check` sans erreur, `lint` sans erreur (une seule alerte, préexistante, dans
`game-realtime.test.ts`), `next build` réussi (`/jeu/parties/[id]` 20 kB / 131 kB).

**CI GitHub Actions verte** sur `2aa225b` — les **4 jobs** (`web`, `api`, `game`, `e2e`) en
`success`, run `38552982711`, et **20 tests e2e passés** dont les deux nouveaux. C'est elle qui fait
foi, pas la suite locale.

Deux tests dont l'échec a été **constaté volontairement** avant d'être réparé (« un test qui échoue
sans le changement et passe avec ») : la couche sans `pointer-events-none`, et une image-clé qui
anime `filter`. Détail des deux ci-dessus.

## Sécurité

Rien de nouveau à défendre : le lot est **entièrement côté écran**, n'ouvre aucune route, ne touche
ni à la base ni au moteur. Il ne **lit** même pas la vue — la file ne reçoit que les coups déjà
projetés par le serveur pour ce joueur (`pbm_game.sortie`), donc rien qu'il n'ait déjà le droit de
voir : pas de main adverse, pas d'ordre de pioche, pas d'identité de récompense. Aucun secret, aucun
journal, aucune sortie sensible. Le test d'accès croisé du plateau (`partie-view`) est inchangé et
reste vert.

## Écarts au plan, et ce qui reste

- **L'e2e n'a pas pu être exécuté en local sur chimera** : `libnspr4.so` est absent et son
  installation exige `sudo` (vérifié ce jour, Chromium refuse de démarrer — c'est le piège déjà noté
  pour les e2e de ce dépôt). Les services nécessaires étaient tous là (Postgres 55432, Redis 56379,
  Mailpit 51025, S3 59000) ; seul le navigateur manquait. **La CI a donc été le seul verdict possible
  sur ces deux tests — et elle est verte**, avec la mesure publiée. Ce n'est pas un contournement :
  c'est la règle du dépôt (« la CI fait foi »), appliquée en le disant.
- **Aucun effet graphique fin n'est livré**, et c'est conforme : ce lot est le *socle*. La couche
  dessine une pastille sobre par type d'effet. L'attaque Feu qui brûle la carte d'en face
  (`j-anim-attaques-typees`), l'évolution et le K.O. (`j-anim-evolution-ko`), le Pokémon au-dessus
  de sa carte (`j-anim-pokemon-apparition`), les sons (`j-son`) et les décors (`j-arene-decors`)
  enrichiront le **registre**, pas la mécanique. `docs/jeu/ANIMATIONS.md` donne la recette en quatre
  points, et la liste de ce qu'il ne faut pas faire.
- **Pas de livraison en PROD** : hors périmètre d'un lot (la PROD se livre à part, par devAI, sur
  décision de JF). `release_prod` reste donc à faire, comme pour les autres lots du jalon J3.
- **Pas de capture de maquette jointe** : le jalon J3 n'a pas d'onglet « Maquette du jeu » pour la
  couche d'animation (elle n'y figure pas), et le lot ne modifie aucune zone du plateau — vérifié par
  le test qui compare le rendu avec et sans animation. La conformité à la maquette du plateau reste
  celle de `j-plateau-layout`, inchangée.

## Grille de tâches

| Tâche | État | Preuve |
|---|---|---|
| `dev` | fait | commit `2aa225b` — file pure, crochet, couche, câblage |
| `tests` | fait | 38 tests nouveaux ; suite web 339/339 ; 20 e2e en CI ; 2 gardes vérifiées en cassant |
| `securite` | fait | aucune route, aucune donnée nouvelle, aucun secret ; la file ne reçoit que du déjà-projeté |
| `maquette` | sans objet | la couche n'existe pas dans la maquette ; le plateau est rendu à l'identique (test) |
| `doc_tech` | fait | `docs/jeu/ANIMATIONS.md` + renvoi dans `docs/UI-UX.md` |
| `release_uat` | fait | recette locale sur chimera : type-check, lint, 339 tests, `next build` |
| `release_prod` | **à faire** | hors périmètre du lot |
| `backlog` | tenu par la file | l'état du lot est tenu par la file de lots, pas par ce lot |
| `compte_rendu` | fait | ce fichier |
