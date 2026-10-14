# `j-arene-decors` — Décors d'arène : jouer quelque part, pas sur un fond gris

> Lot P2, piste Graphisme & animations, jalon **J3**, palier 15, taille S.
> Exécuté depuis **devAI** (couloir chimera : worktree et branche sur chimera, suites front et API
> jouées sur devAI — chimera n'a ni Node ni pnpm dans sa WSL).

## Résumé

Le plateau avait un fond : `radial-gradient(#0E2A1E, #06120B)`, écrit en dur dans une classe du
composant. Il a maintenant **six endroits** où jouer, un **choix** qui suit le compte, un **thème
automatique** tiré du deck, et une **variation jour/nuit** — pour **zéro octet transféré** et
**624 mesures de contraste** qui garantissent qu'un décor reste un fond.

Le savoir durable est dans **`docs/jeu/DECORS.md`** (nouvelle fiche, inscrite à la carte de
`CLAUDE.md`). Ce compte rendu ne le répète pas : il dit ce qui s'est passé pendant le lot.

## Les trois décisions qui ont façonné le lot

**1. Des dégradés CSS, pas des images.** Quatre JPG de décor existaient déjà dans
`apps/web/public/arenes/` — **1,24 Mo à eux quatre**. Six décors en images, c'était ~2 Mo pour de la
décoration sur un jeu qu'on ouvre au téléphone, alors que le critère d'acceptation parle justement
du « budget de la partie ». En dégradés : **0 octet réseau**, et surtout la seule forme dont on
puisse *calculer* le contraste au lieu de l'estimer à l'œil. Les JPG restent pour la maquette, avec
un avertissement en tête de leur README.

**2. La nuit est dérivée, jamais recopiée.** Le CSS l'obtient par
`color-mix(in srgb, <teinte> 72%, #000000)` et `teintesNuit()` applique le même calcul : une seule
source de vérité pour douze ambiances. Un premier essai utilisait un bleu nuit (`#02030A`) comme
appoint — le test a montré qu'il rendait la nuit **plus claire** que le jour sur les teintes déjà
très sombres (bord de « Faille obscure », `#020304`). La nuit baisse la lumière, elle ne repeint pas.

**3. `NULL` veut dire « automatique », pas « non renseigné ».** La colonne `decor` est nullable
**sans `server_default`** : c'est le seul moyen de distinguer « je veux le gymnase » de « je n'ai
rien demandé ». Conséquence sur l'API : `PATCH` doit distinguer **trois** états (champ absent, clé,
`null` explicite), ce que porte `decor_fourni`. Sans lui, **revenir à l'automatique serait
impossible** — et le test qui le prouve est le plus utile du lot.

## Livrables

| Livrable | Où |
|---|---|
| Six décors (4 teintes chacun) + les dégradés | `apps/web/src/lib/game/decors.ts`, `apps/web/src/app/globals.css` (bloc « Décors d'arène ») |
| Thème automatique par deck + figement | `apps/web/src/lib/game/use-decor.ts` |
| Choix du joueur, persisté | colonne `jeu_confort_reglages.decor`, migration `b8f3c5d7e914`, `GET|PATCH /jeu/confort/reglages` |
| Vocabulaire serveur (refus d'une clé inconnue) | `apps/api/src/pbm_api/jeu/decors.py` |
| Écran de choix (7 vignettes, « Automatique » d'abord) | `apps/web/src/app/jeu/confort/confort-view.tsx` |
| Calcul WCAG partagé, extrait d'un test | `apps/web/src/lib/a11y/contraste.ts` |
| Fiche | `docs/jeu/DECORS.md` (+ renvoi depuis `docs/jeu/ACCESSIBILITE.md`) |

## Les critères d'acceptation, un par un

### ☑ « Chaque décor passe le contrôle de contraste avec tous les indicateurs de plateau »

`apps/web/src/__tests__/contraste-decors.test.ts` : **12 ambiances × 4 teintes × 13 repères =
624 mesures**, au seuil qui convient à chacun (4,5:1 pour ce qui se lit, 3:1 pour ce qui se repère).
Toutes passent.

La mesure est *suffisante* et non approximative : dans les trois couches de dégradés, les seules
couleurs qui **éclaircissent** sont les quatre teintes du décor — les fondus sont transparents et le
vignettage est noir. Mesurer les quatre teintes, c'est mesurer le **pire cas**.

Deux garde-fous : le test **vérifie son propre calcul** sur des extrêmes connus, et la liste des
repères est **ancrée dans le code** (chaque couleur doit exister dans le fichier cité) — sans quoi
elle mesurerait un plateau imaginaire.

### ☑ « Le changement de décor n'affecte ni la disposition ni la lisibilité »

Prouvé aux deux niveaux, et il faut les deux :

- **jsdom** (`game-board-decor.test.tsx`) : le plateau rendu sous les six décors donne **une seule
  empreinte DOM** une fois les attributs de décor retirés — aucun composant ne dépend du décor ;
- **navigateur** (`e2e/plateau-responsive.spec.ts`, 6 cas ajoutés) : pour chacun des six décors, sur
  le téléphone de référence (844×390), `data-decor` est bien arrivé jusqu'à l'arène, les zones
  restent dans la fenêtre et **aucun défilement** n'apparaît. Le décor est injecté par interception
  de `GET /jeu/confort/reglages`, donc le **branchement** est couvert, pas seulement le CSS.

### ☑ « Le poids des décors entre dans le budget de la partie »

**0 octet transféré** : aucun décor ne charge d'image, et une garde l'impose
(`decors-css-garde.test.ts` refuse tout `url(` dans les blocs de décor). À comparer aux 1,24 Mo des
quatre JPG existants.

## Un défaut préexistant trouvé et corrigé

En croisant les repères du plateau avec les décors, le test a montré que **quatre liserés blancs
étaient déjà sous 3:1 sur le fond d'origine** — emplacement vide (0,28), récompense prise et pile
cachée (0,30), filets de la ligne centrale (0,35). Un blanc à 30 % sur `#06120B` donne **2,64:1**.

Le défaut ne vient pas du lot, mais son critère d'acceptation l'exigeait, et la règle du dépôt dit
qu'un bug trouvé se corrige dans la foulée : les quatre sont passés à **0,45**, ce qui les met
au-dessus de 3:1 sur les douze ambiances. Visuellement, un liseré pointillé un peu plus net.

Ce que ça apprend : mesurer la couleur **nominale** d'un repère semi-transparent (du blanc pur,
19:1) aurait caché le défaut au lieu de le trouver. C'est `composer()` — la couleur réellement
affichée après composition sur le fond — qui fait la différence.

## Preuves

| Suite | Résultat |
|---|---|
| `vitest` (front, complet) | **822 tests verts** (92 fichiers), dont 29 nouveaux pour ce lot |
| `tsc --noEmit` | vert |
| `eslint` | **0 erreur** (1 avertissement préexistant dans `game-realtime.test.ts`, non touché) |
| `next build` | vert |
| `pytest` (API, complet) | **1400 verts**, 2 échecs d'outillage local (voir ci-dessous) |
| `ruff` (API) | vert |
| `pytest` + `ruff` (moteur `pbm_game`) | **1147 verts**, ruff vert — non-régression, le moteur n'est pas touché |
| `alembic upgrade head` | vert, **tête unique** `b8f3c5d7e914` |
| `e2e` `plateau-responsive` | **9 verts**, dont les 6 décors |
| `e2e` `a11y-jeu` (audit `axe`) | vert |

**Captures de recette** (non committées — poids) : `/tmp/pbm-captures/` sur devAI, six plateaux +
l'écran de choix. Relues ici : les six décors sont nettement distincts, tous sombres, et les cartes
restent ce qu'on voit en premier. La « galerie » durable n'est pas une image mais l'écran
`/jeu/confort` lui-même, dont les vignettes portent `data-decor` et sont donc peintes par le **même
CSS que l'arène** — elles ne peuvent pas montrer autre chose que ce qui sera joué.

### Les deux échecs API, et pourquoi ils ne sont pas de ce lot

`test_catalogue_seed.py` (2 cas) : `pg_dump: command not found`. Les outils clients PostgreSQL ne
sont pas installés sur devAI ; la CI les a. Aucun rapport avec le lot — aucun fichier de catalogue
n'a été touché.

### Les deux specs de fluidité : vérifié, pas supposé

`anim-fluidite` et `anim-attaques-typees` échouent sur devAI (plancher de 30 images/s non tenu sous
bridage CPU ×4). Comme ce lot **ajoute des dégradés à peindre**, l'hypothèse d'une régression devait
être écartée par la mesure et non par la confiance. `main` (`a2e27c4`) a donc été construit dans un
second atelier et les deux specs rejouées dans les mêmes conditions :

| Spec | Sur `main` (sans le lot) | Sur la branche |
|---|---|---|
| `anim-fluidite` | 15,1 images/s | 9,8 images/s |
| `anim-attaques-typees` | 12,6 images/s | 14,1 images/s |

Les quatre chiffres sont très loin des 30 attendues, et l'écart joue **dans les deux sens** : c'est
devAI qui ne tient pas ce plancher, pas le décor. Même constat que le lot `j-anim-attaques-typees`
(« plancher rouge sur devAI seulement »). La CI, sur runner dédié, fait foi.

## Écarts au plan

1. **Le déblocage des décors par les badges n'est pas fait** (4ᵉ point de la mission, « si DJ6 le
   retient »). DJ6 retient bien les badges, mais ils appartiennent à `j-profil-jeu` — **palier 17**,
   statut `a_faire`, lui-même derrière `j-stats-joueur`. Ce lot est au **palier 15** : il n'y a
   aucun badge auquel se relier. Les six décors sont donc tous disponibles, et **aucun champ
   « verrouillé » n'a été posé en prévision** — on ne fabrique pas un mécanisme de déblocage qui ne
   débloque rien (D9). Ce qui restera à faire au moment de `j-profil-jeu` est écrit dans
   `docs/jeu/DECORS.md` § « Ce qui n'est pas fait ».

2. **Le thème automatique lit le camp du joueur, pas la fiche de son deck.** Le plan dit « selon le
   type dominant du deck » ; la vue d'une partie ne porte pas la composition du deck (le serveur ne
   l'y expose pas, et il a raison). Elle porte le type de **mes** cartes — main comprise, soit sept
   cartes de mon deck dès le premier tour. Même intention, **aucune requête supplémentaire, aucune
   donnée nouvelle exposée**, et le camp adverse n'est jamais regardé (test dédié).

3. **Le décor est rangé dans les réglages de confort**, pas dans un « profil de joueur » — ce
   dernier n'existe pas (`j-profil-jeu`, `a_faire`). `/jeu/confort` était le bon endroit : même
   sorte de réglage, écran déjà là, aucune table ni route nouvelle.

4. **ESLint ne démarre pas dans le dépôt local de devAI** (`eslint-plugin-react-hooks` présent dans
   `.pnpm` mais non lié dans `apps/web/node_modules`). Contourné par un `NODE_PATH` vers les plugins
   du magasin ; la CI, qui fait `pnpm install --frozen-lockfile`, n'a pas ce problème.

## Reste à faire

- **Relier le déblocage aux badges** quand `j-profil-jeu` (palier 17) sera livré — point d'entrée
  décrit dans `docs/jeu/DECORS.md`.
- **Aucune livraison en PROD** : hors périmètre d'un lot (la PROD se livre à part, par devAI). La
  migration `b8f3c5d7e914` ajoute une colonne nullable, sans réécriture de table — anodine, mais
  elle devra figurer dans le prochain dossier de livraison.
- Rien d'autre n'est en suspens : les trois critères d'acceptation sont tenus et prouvés.
