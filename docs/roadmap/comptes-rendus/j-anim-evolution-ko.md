# `j-anim-evolution-ko` — Évolution, K.O., récompense : les moments qui comptent

> Lot P1 · piste Graphisme & animations · couloir **J-GFX** · jalon **J3** · palier 15.
> Exécuté le 14/10/2026. Pilotage depuis **devAI**, travail sur **chimera** (worktree
> `~/dev/wt-j-anim-evolution-ko`, branche `roadmap/j-anim-evolution-ko` depuis `github/main` à
> `4cb8cc9`). Garde-fou `suivi.py verifier` : **code 0 — ordre tenu**.

## Résumé

Les **six moments clés** d'une partie sont animés : évolution, mise K.O., prise de récompense, mise
en place initiale, mulligan, pile ou face. Comme le lot précédent (`j-anim-attaques-typees`), il n'y
a **aucune animation écrite par moment** : six couches et quatre gestes partagés, chacun avec une
seule image-clé CSS, composés par une table de six lignes — de la donnée, pas du code.

La décision de conception qui structure tout le reste : **les moments ont leur propre file**, à côté
de celle du socle. Ce n'est pas un doublon, et ce n'est pas un confort — c'est ce qui rend le
critère n°1 atteignable. Trois faits l'imposent :

1. un `ko` du serveur porte **deux** moments (la mise K.O. *et* `recompenses_prises`), alors que le
   socle produit exactement **une** entrée par événement : il ne peut structurellement pas en faire
   deux ;
2. un moment dure plus que la case que le socle lui donne (le socle borne tout à 900 ms ; un K.O.
   qui bascule, s'éteint puis rejoint la défausse a besoin de ses trois temps) ;
3. le `avancer` du socle enchaîne plusieurs entrées de durée nulle **en un seul appel** : un moment
   accroché à son `courante` aurait disparu sans un mot. Et c'est le cas réel de deux des six —
   `main_revelee` et `mise_en_place_revelee` ne sont même pas à son registre.

Le point 3 est le piège qu'il fallait voir avant d'écrire la première ligne : la voie « évidente »
(accrocher les moments à l'animation courante, comme le lot précédent accroche son effet typé)
aurait livré un lot qui perd des moments en silence — exactement ce que le critère interdit, et sans
qu'aucun test écrit à la va-vite ne le montre.

## Livrables

| Fichier | Quoi |
|---|---|
| `apps/web/src/lib/game/anim-moments.ts` (**neuf**, 883 l.) | le module **pur** : la table des six genres, `momentsEvenement` (lecture des événements réels), `effetMoment` (composition, compression, honnêteté de la pièce), `reduireMoments` (la file FIFO) |
| `apps/web/src/components/game/effet-moment.tsx` (**neuf**) | le rendu : autant de couches que de temps, autant d'objets que de cartes ou de pièces, les gestes enchaînés en une liste d'animations CSS. Aucun calcul |
| `apps/web/src/app/globals.css` (+317 l.) | le bloc « Les six moments clés » : 6 couches, 4 gestes, 11 images-clés `pbm-anim-fx-m-*` |
| `apps/web/src/components/game/animation-layer.tsx` | `useFileMoments` (le crochet), et le moment rendu dans `CoucheAnimation` — où il **remplace** la pastille |
| `apps/web/src/app/jeu/parties/[id]/partie-view.tsx` | branchement : les deux files sur les mêmes coups, « Passer » et la vidange agissent sur les deux |
| `apps/web/src/components/game/game-board.tsx` | passage du moment, et la **secousse** du K.O. par le chemin déjà existant (`data-fx-secousse`) |
| `apps/web/src/app/jeu/effets/effets-view.tsx` | la galerie `/jeu/effets` gagne la section « Les six moments clés », pour la validation de JF et d'Aymeric |
| `apps/web/src/lib/game/anim-moments.test.ts` (**neuf**) | 65 tests, dont un bloc nommé par critère d'acceptation |
| `apps/web/src/components/game/effet-moment.test.tsx` (**neuf**) | 30 tests de rendu et de branchement |
| `apps/web/src/__tests__/anim-moments-css-garde.test.ts` (**neuf**) | 13 tests : la table et le CSS ne peuvent plus divergir |
| `docs/jeu/ANIMATIONS.md` (+140 l.) | le savoir durable : les deux files et pourquoi, les six lignes, le double K.O., la pièce honnête, la version réduite, comment ajouter un moment |
| `CLAUDE.md` | la carte des fiches, une ligne |

## Les trois critères d'acceptation, et leur preuve

### 1. « Un double K.O. affiche deux animations sans se chevaucher ni se perdre »

Un double K.O. (R-13.5) avec récompenses produit **quatre** moments. Ce qui garantit qu'aucun ne
disparaît tient dans la forme de la clé — `numero:rang:genre` : les deux `ko` viennent du **même
coup**, donc sans le rang de l'événement le second écraserait le premier à l'empilage.

Prouvé des deux côtés :

- côté pur, l'ordre et l'unicité : `["12:0:ko", "12:0:recompense", "12:2:ko", "12:2:recompense"]`,
  joués un par un, `simultanes` plafonné à 1 ;
- côté écran, qu'ils sont bien **rendus** : le témoin fait défiler les quatre clés dans l'ordre, et
  finit à `aucun` / `attente 0` — le quatrième n'est pas perdu en route.

La rafale est **comprimée** (facteur borné à 45 %), jamais résumée ni tronquée : un moment réduit à
zéro serait un moment perdu. Un test vérifie que les six genres restent de durée strictement
positive même à `enAttente = 10 000`.

### 2. « La prise de deux récompenses se voit comme deux cartes »

Le serveur n'émet pas d'événement de prise de récompense : `recompenses_prises` voyage sur le `ko`.
Le moment `recompense` en est donc séparé, lit ce compte, et produit **N objets échelonnés**. Des
retards égaux auraient donné un vol groupé — deux cartes qui partent ensemble ne se comptent pas à
l'œil, et c'est précisément ce que le critère interdit.

Prouvé : deux objets, deux retards distincts, dans le module **et** dans le DOM (deux `.pbm-m-objet`
avec deux `--pbm-m-retard`). Jusqu'à six récompenses restent six cartes distinctes. Le retard se
rabote pour que le dernier objet parti ait encore son premier temps entier à l'écran, même comprimé.

### 3. « Le pile ou face ne donne jamais une impression de résultat prédéterminé côté client »

Trois faits, tous testés :

| | Preuve |
|---|---|
| **Aucun tirage côté client** | garde **statique** qui relit la source du module : ni `Math.random`, ni `Date.now`, ni `crypto` (les commentaires qui *nomment* l'interdit sont retirés avant le contrôle) |
| **La rotation ne sait rien du résultat** | trois lancers (0, 1, 2 faces sur 2) comparés champ par champ : phases, durée, `revelationA`, nombre d'objets, retards, index — **identiques**. Et ça reste vrai à `enAttente` 0, 3 et 12, qui est le chemin par lequel une dépendance aurait pu se glisser |
| **Le résultat n'arrive qu'à la fin** | `revelationA` = fin du temps `rotation`, donc `0 < revelationA < duree`. Côté CSS, la pose finale est à `opacity: 0` jusqu'à `var(--pbm-m-revelation)` : avant, rien ne distingue un pile d'un face |

Preuve supplémentaire côté DOM : le balisage de deux lancers opposés est **identique** à l'attribut
`data-face` près (comparaison de `outerHTML` après neutralisation de cet attribut).

**Ce qui n'est pas prétendu**, et qui est écrit noir sur blanc dans le code et dans la fiche : le
résultat est déjà dans la charge utile reçue du serveur, puisque c'est le serveur qui tranche. Un
joueur qui ouvrirait l'inspecteur le verrait. Ce qu'une animation peut garantir, c'est qu'elle ne le
laisse pas fuir — pas qu'elle l'ignore. Le dire valait mieux que laisser croire l'inverse.

## Le risque nommé par le lot

> « Faire durer l'animation de K.O. plus que le plaisir : au-delà d'une seconde et demie, elle agace
> au lieu de marquer. »

`MOMENT_MAX_MS = 1500`, appliqué par construction et vérifié **pour les six genres** — pas seulement
pour le K.O., et pas laissé à la vigilance de qui ajoutera la septième ligne. Le K.O. lui-même dure
760 ms ; le plus long des six est la mise en place (1200 ms), et c'est délibéré : c'est le premier
effet qu'un joueur voit.

## Les mesures et les vérifications

| | Résultat |
|---|---|
| Suite web complète (`vitest run`) | **784 tests verts, 87 fichiers** — dont 108 dans les trois fichiers neufs |
| Garde du compositeur (`anim-css-garde`) | **verte** : ses images-clés contrôlées passent de **12 à 23**, les 11 nouvelles n'animent que `transform` et `opacity` |
| `tsc --noEmit` | vert (y compris `noUncheckedIndexedAccess`) |
| `eslint` sur les 9 fichiers touchés | **aucune sortie** (le seul avertissement du dépôt, dans `game-realtime.test.ts`, préexiste) |
| `next build` | vert — `/jeu/parties/[id]` 9,6 ko, `/jeu/effets` 5,06 ko |

### Les tests mordent — vérifié par mutation

La consigne de la machine (« blinder, et vérifier qu'il mord en cassant volontairement le correctif
une fois ») appliquée aux trois critères, chacun cassé à son tour :

| Mutation | Ce qui est tombé |
|---|---|
| le retard d'un objet dépend du résultat du lancer | **2 tests du critère n°3** (dont la version comprimée) |
| tous les objets partent au même instant (`retard: 0`) | **2 tests du critère n°2** |
| la clé oublie le rang de l'événement (`numero:genre`) | **4 tests**, dont les trois du critère n°1 |

Restauré : 65/65 verts. Aucune mutation n'est passée inaperçue.

## Écarts au plan, et choix assumés

- **Pas de nouvelle spec e2e.** Le lot précédent en avait ajouté une pour *mesurer* le plancher
  d'images par seconde sur l'effet le plus lourd ; ici les trois critères portent sur de la logique
  (ordre, comptes, indépendance au résultat), entièrement couverte par 108 tests dont deux gardes
  statiques. Une spec de plus aurait mesuré ce qui l'est déjà. Les specs e2e existantes du plateau
  restent la preuve de non-régression, et **c'est la CI qui en fait foi** : l'e2e navigateur est
  connu pour rendre deux faux rouges sur devAI (`anim-fluidite`, `responsive @320`).
- **Le moment remplace la pastille du socle**, il ne s'y ajoute pas. Écart visuel assumé, et c'est
  une contrainte, pas une économie : une scène ajoutée aurait masqué des compteurs de dégâts une
  seconde et demie durant — exactement le reproche que le lot précédent s'était fait interdire. Un
  moment remplace donc un mot (« K.O. ! » → l'animation de K.O.) et n'ajoute aucune occlusion.
- **La scène est petite et centrée**, pas un tableau plein cadre. Même raison. Conséquence : les
  moments sont plus sobres que ce que « la carte d'évolution se pose en fondu lumineux sur la
  précédente » peut laisser imaginer sur une maquette — ils se jouent dans une case de 7 × 5 em.
  C'est le compromis entre « ça se voit » et « ça ne cache rien », et il est à valider sur
  `/jeu/effets`.
- **La désaturation du K.O. n'est pas un `filter: saturate()`.** La garde du compositeur l'interdit
  (hors du compositeur, le plancher d'images par seconde tombe sur un téléphone d'entrée de gamme) :
  c'est l'**opacité** d'un voile sombre statique qui porte l'extinction. Le résultat se lit pareil.
- **La pile d'évolution montre deux cartes**, pas l'étage réel : l'événement `evolution` porte
  `base`, `vers` et `nom`, mais pas le nombre de cartes empilées. Deux est tout ce qu'on peut
  affirmer — en inventer un troisième aurait été une approximation (D9).
- **L'ordre des pièces est de la présentation.** Le serveur n'envoie que `pieces` et `faces` : il ne
  dit pas *laquelle* est tombée sur face, parce que le moteur n'a pas d'ordre à leur donner. L'écran
  en fabrique un (les `faces` premières). Le compte affiché est exactement celui du serveur.
- **`/Volumes/Data` refusé en écriture depuis cette session** (`Operation not permitted`, TCC) —
  déjà connu. L'atelier d'édition a donc été posé sur `/tmp` de devAI, avec les `node_modules`
  **liés** (zéro octet écrit) : il ne contient que des sources. ⚠️ `rm -rf /tmp/wt-anim-evo` est
  refusé par le garde-fou de session (répertoire de travail) — **à supprimer à la main**, c'est
  léger (sources seules).

## Reste à faire

- **Validation de rendu par JF et Aymeric sur `/jeu/effets`**, section « Les six moments clés ».
  Deux questions précises : (a) les moments sont-ils assez visibles dans une case de 7 × 5 em, ou
  faut-il arbitrer en faveur d'une scène plus grande *en acceptant* l'occlusion ? (b) la mise en
  place à 1200 ms est-elle le bon tempo pour le premier effet d'une partie ?
- Les **trois lancers de pièce** sont côte à côte dans la galerie exprès : c'est là qu'on vérifie à
  l'œil ce que le test affirme.
- Aucun lot aval ne dépend de celui-ci (`débloque : aucun`).
- Rien à livrer en PROD par ce lot : la mise en ligne se fait à part, par devAI.
