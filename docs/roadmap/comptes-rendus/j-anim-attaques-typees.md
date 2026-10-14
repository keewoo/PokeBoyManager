# `j-anim-attaques-typees` — Une attaque Feu brûle la carte d'en face : un effet par type

**Statut : livré.** Jalon J3, palier 15, couloir J-GFX. Branche `roadmap/j-anim-attaques-typees`.

## Résumé

Le lot demandait dix effets d'attaque, un par type d'énergie, d'intensité proportionnelle au
résultat réel du combat. Deux choses manquaient avant de pouvoir en écrire un seul.

**La première : le serveur ne disait pas de quel type était l'attaque.** `attaque_declaree` portait
`{joueur, degats}` et rien d'autre. Le type existait côté moteur (`params["type_attaque"]`, celui
qui décide de la faiblesse R-10.2) mais ne sortait jamais. Sans lui, « un effet par type » est
impossible — ou alors il faut le deviner côté client depuis l'Actif courant, ce qui est faux dès que
la vue a bougé entre l'attaque et l'animation.

**La seconde : rien ne disait si la faiblesse avait joué.** L'information était dans l'événement
`degats`, mais noyée dans la phrase française `detail` (« 60 base, ×2 faiblesse = 90 »). La lire
aurait voulu dire chercher un mot dans une chaîne — un repli silencieux, qui cesserait de marcher le
jour où la phrase change, en laissant l'effet s'afficher, simplement faux.

Les deux sont donc **exposées structurellement** par le moteur, sans changer aucun calcul. Le reste
du lot est un système d'effets paramétré, et le point important est ce qu'il n'est **pas** : il n'y a
aucune animation par type. Le risque nommé par le lot (« dix animations écrites séparément :
impossible à maintenir, et l'une d'elles finira par cacher un compteur de dégâts au moment
décisif ») est écarté par construction, et les deux moitiés de cette phrase ont chacune leur garde.

## Livrables

### 1. Côté moteur — deux faits déjà calculés, enfin dits

| Fichier | Changement |
|---|---|
| `apps/game/src/pbm_game/combat/attaque.py` | `attaque_declaree` porte `type` (le type d'énergie de l'attaque, information **publique** : l'Actif est visible des deux joueurs). `""` quand il n'est pas connu — jamais une supposition (D9) |
| `apps/game/src/pbm_game/combat/resolution.py` | `degats` porte `faiblesse` et `resistance`, **booléens**, dérivés des étapes déjà présentes dans `ResultatDegats.etapes` (règles R-10.2 / R-10.3, désormais nommées `REGLE_FAIBLESSE` / `REGLE_RESISTANCE` pour que l'étape qui les pose et l'événement qui les relit ne puissent pas se désaccorder) |

Aucune règle n'est touchée : aucun calcul, aucun ordre d'opérations, aucune valeur. Les projecteurs
n'ont rien à changer (ces deux types sont déjà `_public`, qui passe l'événement tel quel), et les
empreintes de rejeu portent sur l'**état**, pas sur les événements.

### 2. Côté écran — six couches, quatre gestes, une table

| Pièce | Fichier | Quoi |
|---|---|---|
| le module pur | `apps/web/src/lib/game/anim-types.ts` | `SPECS` (onze lignes de **donnée**), `effetAttaque()`, l'intensité, les bornes |
| les couches | `apps/web/src/app/globals.css` | `nappe`, `balayage`, `onde`, `particules`, `flash`, `etreinte` + 4 gestes de carte + la secousse du plateau + la trace — **une** image-clé chacun |
| le composant | `apps/web/src/components/game/effet-type.tsx` | du balisage, aucun calcul |
| le branchement | `animation-layer.tsx`, `board-card.tsx`, `game-board.tsx`, `partie-view.tsx` | l'effet suit l'animation, va sur la carte visée, et dans l'arène quand l'attaque n'a touché personne |
| la galerie | `apps/web/src/app/jeu/effets/` | onze types × six situations, pour la validation de JF et d'Aymeric |

Les onze types (les dix du lot, plus **Incolore** — un Pokémon `colorless` attaque comme les autres,
et le laisser muet aurait fabriqué un onzième cas que personne n'aurait cherché) :

| Type | Composition | Particules | Geste de carte | Plateau | Trace |
|---|---|---|---|---|---|
| Feu | nappe + particules | 8 | — | — | oui |
| Eau | balayage + nappe | 6 | — | — | oui |
| Plante | etreinte + particules | 6 | — | — | — |
| Électrique | flash + balayage + particules | 4 | tremblement | **tremble** | — |
| Psy | onde + nappe | — | distorsion | — | — |
| Combat | onde + nappe | — | recul | **tremble** | oui |
| Obscurité | nappe + etreinte | — | — | — | oui |
| Métal | balayage + flash + particules | 7 | — | — | — |
| Dragon | balayage + nappe + particules | 5 | — | **tremble** | — |
| Fée | particules + onde | 9 | — | — | — |
| Incolore | onde | — | — | — | — |

**Pourquoi du CSS et pas un canvas**, alors que le lot disait « shaders/canvas légers » : c'est le
plancher d'images par seconde qui tranche. Le socle (`j-anim-socle`) tient ses 30 images/s *parce
que* rien ne passe par le fil principal — `transform`/`opacity` seulement, composés sur le processeur
graphique, et un rendu React par animation. Un canvas redessinerait à la main, chaque image, sur ce
fil : il reprendrait exactement ce qu'on a économisé. Les images-clés sont donc nommées
`pbm-anim-fx-*` pour tomber sous la **même** garde statique que le socle — et non sous un préfixe
qui les en aurait sorties, ce qu'un garde-fou interdit de faire. C'est un écart assumé au mot du
plan, pas un oubli.

### 3. L'intensité vient du résultat, pas d'une intention

`intensiteDe()` part des dégâts réels (plafonnés à `DEGATS_REFERENCE` = 200 : sans plafond, une
attaque à 600 écraserait toutes les autres et l'intensité ne dirait plus rien), puis **renforce** en
cas de faiblesse et **atténue** en cas de résistance. Ce supplément s'ajoute au doublement que la
faiblesse a déjà produit sur les dégâts, et c'est voulu : sans lui, une attaque de 60 doublée serait
visuellement identique à une attaque de 120 sans faiblesse, et le joueur ne verrait pas *pourquoi* ça
a fait mal.

Un **échec** (pile ou face sans aucune face, ou Confusion sur pile, R-11.5) a son palier à lui : pas
une particule, pas de secousse, pas de déformation. Sinon on ne distingue pas « ça a raté » de « ça a
fait 10 ».

## Preuves

### Les quatre critères d'acceptation

| Critère | Comment c'est tenu | Preuve |
|---|---|---|
| **1.** Les dix types ont leur effet, l'intensité reflète le calcul | table `SPECS` + `effetAttaque()` | `anim-types.test.ts` — un cas **par type**, plus la parité `SPECS` ↔ `ELEMENTS` (les deux tables doivent parler du même vocabulaire) |
| **2.** L'effet ne masque jamais le plateau plus d'une seconde | `effetAttaque` rabote la trace sous `TOTAL_MAX_MS` | `anim-types.test.ts` — vérifié pour les **onze types × toutes les durées du registre `EFFETS`** × les quatre modificateurs, pas sur un cas choisi |
| **2 bis.** L'effet ne couvre jamais les compteurs de dégâts | **ordre de DOM** : l'effet est rendu avant les indicateurs, donc dessous | `board-card.test.tsx` — **vérifié qu'il mord** : inverser les deux lignes le fait tomber avec le message « il recouvrirait le compteur de dégâts » (`expected 3 to be less than 1`) |
| **3.** La version réduite existe pour chaque effet et reste compréhensible | badge immobile + phrase complète | `anim-types.test.ts` — un cas **par type** : aucune couche, aucun geste, aucune secousse, et la phrase contient le type et le chiffre. `effet-type.test.tsx` : le badge est **annoncé** (`role="img"`), contrairement à la couche animée |
| **4.** Le plancher d'images par seconde est tenu avec l'effet le plus lourd | mesuré au navigateur | `e2e/anim-attaques-typees.spec.ts` — voir ci-dessous |

### Le plancher — ce qui a été mesuré, et ce que ça dit

Le type mesuré est **calculé**, pas choisi (`TYPE_LE_PLUS_LOURD`, aujourd'hui Fée : 2 couches +
9 particules) : le jour où un type plus chargé est ajouté, c'est lui qui est mesuré, sans que
personne n'ait à y penser. Un test vérifie que cette constante est bien le maximum de la table.

Mesuré sur **devAI**, appareil de référence (844×390, processeur bridé ×4), fenêtre de mesure
identique à celle de `anim-fluidite.spec.ts` (la rafale entière) :

| Passage | Effet typé (Fée, palier fort, faiblesse) | Socle seul (`anim-fluidite`, référence) |
|---|---|---|
| 1 | 14,5 images/s | 11,2 images/s |
| 2 | 14,3 images/s | 9,4 images/s |
| 3 | 10,8 images/s | — |

**Les deux sont rouges sur devAI, et le socle l'était déjà sans ce lot** — c'est l'échec local connu
de `anim-fluidite.spec.ts` (mémoire du projet : « 2 specs rouges sur devAI sans régression »).
Vérifié en rejouant la spec de référence **avant** de conclure quoi que ce soit : 14,1 images/s sur
`main`, sans une ligne de ce lot. La machine ne tient pas 30 images/s sous bridage ×4 ; ce n'est pas
l'effet.

Ce que la comparaison dit, et c'est l'information utile : à fenêtre égale, **l'effet typé mesure
aussi bien ou mieux que le socle seul**. Son coût est dans le bruit de mesure. Le verdict reste
**la CI** (runner dédié, où `anim-fluidite` passe) — c'est elle qui fait foi, pas une mesure sur une
machine chargée.

⚠️ Une faiblesse de mesure a été trouvée et corrigée pendant le lot : la première version attendait
la fin du **premier** effet typé (420 ms) au lieu de la rafale entière. La fenêtre était alors
dominée par le chargement de la page, et le test passait ou échouait au hasard — il a fait les deux.
Un test qui conclut au hasard est pire qu'absent.

### Les suites

| Suite | Résultat |
|---|---|
| `apps/game` — `uv run pytest -q` | **1147 passés** (dont 9 nouveaux : `test_evenements_attaques_typees.py`) |
| `apps/game` — `uv run ruff check .` | propre |
| `apps/web` — `pnpm exec vitest run` | **648 passés / 82 fichiers** (505 avant le lot sur le même périmètre filtré ; +4 fichiers de test, +95 cas) |
| `apps/web` — `pnpm type-check` | propre |
| `apps/web` — `pnpm lint` | propre (1 avertissement préexistant, `game-realtime.test.ts`) |
| `apps/web` — `pnpm build` | propre |
| `e2e` — `anim-attaques-typees.spec.ts` | 2 cas verts (compteurs visibles pendant l'effet, galerie complète + captures) ; le cas du plancher rouge **localement seulement**, voir ci-dessus |

Captures jointes au rapport Playwright (`info.attach`, et non un fichier écrit dans
`playwright-report/` — le rapporteur HTML nettoie ce dossier) : `fx-typee-plateau`,
`fx-galerie-grosse-attaque`, `fx-galerie-attaque-ratee`.

### Les tests qui mordent sans le changement

- `test_evenements_attaques_typees.py` — `KeyError` sur `donnees["type"]` et `donnees["faiblesse"]` :
  les champs n'existaient pas.
- `anim-types.test.ts`, `effet-type.test.tsx`, `anim-types-css-garde.test.ts`, `effets-view.test.tsx`
  — le module, le composant et l'écran n'existaient pas.
- le bloc « typage des animations » de `animations.test.ts` — `Animation.typage` n'existait pas, et
  le planificateur ne regardait chaque événement qu'isolément. Or ni le type ni l'échec ne sont sur
  l'événement qui s'anime : ils sont sur ses **voisins du même coup** (`degats` arrive **avant**
  `attaque_declaree`, qui porte le type). Un planificateur événement par événement n'aurait jamais
  joué le moindre effet typé.
- `board-card.test.tsx` — l'ordre de DOM, vérifié en l'inversant pour de vrai.

### La garde que personne n'aurait pensé à écrire

`anim-types-css-garde.test.ts` vérifie la parité **table ↔ CSS** : chaque couche, chaque geste et
chaque teinte citée par `SPECS` existe dans `globals.css`, et le fautif est nommé. Le mode de panne
qu'elle ferme est le pire qui soit : un `<i>` sans dégradé et sans image-clé est un **carré
transparent**. L'effet s'afficherait, simplement il ne montrerait rien ; l'écran aurait l'air de
marcher, et aucun test de rendu ne tomberait.

## Écarts au plan

1. **« Shaders/canvas légers » → couches DOM animées en CSS.** Assumé, et pour une raison mesurable :
   un canvas rend sur le fil principal et reprendrait ce que le socle a économisé pour tenir son
   plancher. Le reste de la phrase du plan — « réutilisables, paramétrés par intensité, pas dix
   animations sans rapport entre elles » — est tenu à la lettre.
2. **« La trace reste noircie une seconde » → la seconde est un plafond total, pas la durée de la
   trace.** Le critère d'acceptation dit « l'effet ne masque jamais l'état du plateau plus d'une
   seconde » : les deux phrases ne peuvent pas être vraies ensemble si l'animation dure déjà 420 ms.
   Arbitré en faveur du critère — `animation + trace ≤ 1000 ms`, et c'est la trace qui cède. Elle
   dure donc jusqu'à 420 ms, pas une seconde. Et elle ne masque rien, puisqu'elle passe sous les
   indicateurs.
3. **Onze types livrés, pas dix** (Incolore en plus). Le critère ne demandait que les dix.
4. **Un écran non prévu au plan : `/jeu/effets`.** Le lot demandait de « faire valider le rendu par
   JF et par Aymeric » ; sans cette page, la validation aurait demandé de réunir en partie un
   Pokémon de chacun des onze types avec la bonne faiblesse et un pile ou face perdu. La galerie
   utilise le **même** code que le plateau : une galerie qui redessinerait les effets à sa façon ne
   vaudrait aucune validation.

## Reste à faire

- ⚠️ **La validation de JF et d'Aymeric n'a pas eu lieu** — c'est le seul livrable du lot qui ne
  pouvait pas l'être : la session est autonome, personne ne répond. Le lot livre donc le **moyen** de
  la faire (`/jeu/effets`, atteignable depuis le salon) et les captures de recette. Rien n'a été
  « industrialisé » dans le dos de cette validation : si le rendu d'un type ne plaît pas, il se
  change en une ligne de `SPECS` et une teinte, sans toucher à la mécanique.
- **Le plancher d'images par seconde n'est pas mesurable sur devAI** (ni sur chimera, qui n'a pas de
  navigateur). Le verdict est celui de la CI. Si la CI le rendait rouge, la réponse serait de réduire
  le nombre de particules du type le plus lourd — **pas** d'abaisser `PLANCHER_FPS`.
- Les types qui font trembler le plateau (Électrique, Combat, Dragon) sont les plus susceptibles de
  gêner : c'est le premier point à soumettre à JF, et le réglage « animations réduites » le coupe
  déjà entièrement.

## Notes d'exécution

- Travail mené **sur devAI** et non sur chimera, malgré le couloir J-GFX : la WSL de chimera n'a ni
  Node ni pnpm (mémoire du projet), et ce lot est presque entièrement front. Copie jetable obtenue
  par `git archive` dans `/tmp`, `node_modules` partagé par lien symbolique. Le dépôt de travail,
  les commits, la CI et la fusion restent sur chimera, sous le verrou.
- `/Volumes/Data` est de nouveau **refusé en écriture** depuis une session d'agent (`Operation not
  permitted`, TCC) : le volume est monté et a 125 Go libres. Transit fait dans `/tmp` (572 Mo de
  `node_modules` non copiés mais liés), et c'est dit ici plutôt que tu.
- L'e2e a été joué localement sur une base **à moi** (`pbm_fx_e2e`, créée puis supprimée) : la base
  e2e partagée du port 55432 était à une tête Alembic d'un autre lot. Aucune base d'autrui n'a été
  touchée.
