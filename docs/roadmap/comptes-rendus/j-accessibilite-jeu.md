# `j-accessibilite-jeu` — Confort et accessibilité : jouable par un enfant, lisible par tous

**Statut : livré.** Jalon J3, palier 15, couloir J-UI. Branche `roadmap/j-accessibilite-jeu`.

## Résumé

Le lot demandait quatre choses : passer « l'audit d'accessibilité du projet » sur les écrans de jeu,
rendre chaque animation coupable, vérifier la jouabilité au clavier seul, et brancher un mode « temps
rallongé » sur les horloges (DJ4).

**L'audit n'existait pas.** Le socle était écrit en prose dans `docs/UI-UX.md` (contraste, cibles,
clavier, `prefers-reduced-motion`) et aucun outil ne le vérifiait : ni `axe`, ni `pa11y`, ni test, ni
étape de CI. Le premier livrable du lot est donc l'audit lui-même — et il a trouvé sept défauts
réels, aucun visible à l'œil, dont deux qui rendaient une information **inaudible** pour un lecteur
d'écran (le score de la partie, et la partie entière).

Les trois autres missions sont faites. Et le plateau impose trois compromis d'accessibilité qui sont
**nommés, mesurés et compensés** plutôt que tus — c'est la partie du lot qui mérite une relecture
critique.

## Livrables

### 1. L'audit — trois gardes, et ce que chacune peut prouver

| Garde | Fichier | Couvre | Job CI |
|---|---|---|---|
| `axe-core` en jsdom | `apps/web/src/__tests__/a11y-jeu.test.tsx` | structure : rôles, étiquettes, `aria-*` invalides, boutons sans nom | **web** (~0,2 s) |
| `@axe-core/playwright` | `apps/web/e2e/a11y-jeu.spec.ts` (7 cas) | contraste effectif, taille réelle des cibles, clavier, texte agrandi, animations coupées | **e2e** |
| calcul WCAG direct | `apps/web/src/__tests__/contraste-jeu.test.ts` | le ratio des **onze** types d'énergie, à la source | **web** |

Le partage est contraint, pas arbitraire : `axe` ne calcule pas un contraste sans peinture (jsdom n'a
ni couleur effective ni cascade), et un audit de navigateur ne voit que les pastilles réellement
affichées — jamais les onze types. D'où la troisième garde, qui mesure les couleurs là où elles sont
définies. Les deux audits **nomment** le coupable (sélecteur, dimensions, règle) : un message « trop
petit » obligerait à tout rouvrir à la main.

Dépendances ajoutées : `axe-core` et `@axe-core/playwright` (devDependencies de `apps/web`). Aucune
étape de CI nouvelle n'a été nécessaire — les deux fichiers tombent dans les jobs existants.

### 2. Ce que l'audit a trouvé (et corrigé)

| Défaut | Ce que ça coûtait | Correctif |
|---|---|---|
| `aria-label` sur un `<span>` sans rôle (compteur de récompenses) | **interdit** (WCAG 4.1.2) : ignoré par les lecteurs d'écran, donc le *score* de la partie n'était annoncé à personne | `role="img"` — `game-board.tsx:127` |
| contraste « Psy » **3,99:1**, « Combat » **3,98:1** | sous le minimum AA (4,5) | fonds éclaircis — `indicateurs.ts` |
| bouton d'ouverture du journal : 93 × **20 px** | la cible la plus importante du plateau, sous 24 px | `min-h-6` |
| « Passer » / « Accélérer » : **16 px** de haut | les deux contrôles d'animation | `min-h-6 min-w-6`, texte 11 px |
| pastille de type affichant `grass`, `lightning` | un mot **anglais** montré à un enfant de onze ans | `styleElement(t).label` → « Plante », « Électrique » |
| les quatre surcouches sans aucun clavier | une modale ouverte était un **cul-de-sac** : rien ne la fermait, et le Tab parcourait le plateau derrière elle | `lib/game/use-modale.ts` |
| journal replié ⇒ partie **muette** | la partie avançait sans qu'un mot soit annoncé | région `aria-live="polite"` (`journal-annonce`) |

### 3. Animations coupables — globalement et individuellement

- **globalement** : réglage `/jeu/confort`, persisté en base. Il **s'ajoute** à
  `prefers-reduced-motion` (l'un des deux suffit) et ne peut jamais rallumer ce que le système
  demande d'éteindre. Il existe parce que tout le monde ne sait pas où trouver le réglage système —
  un enfant sur le téléphone d'un parent n'y touchera pas.
- **individuellement** : le bouton « Passer » (déjà là, désormais atteignable au doigt).
- CSS : `html[data-anim="reduites"] *` annule durées **et** `animation-iteration-count` — une
  animation en boucle à 0,01 ms tourne toujours, elle boucle juste très vite.

### 4. Clavier

`lib/game/use-modale.ts` : **Échap** ferme, **Tab** reste dedans, le focus **revient** d'où il
venait. Appliqué aux quatre surcouches, avec un réglage par surcouche (la fenêtre de décision est
obligatoire : Tab piégé, pas d'Échap — le moteur attend une réponse et son horloge en donne une par
défaut ; le zoom de carte est non modal : Échap, Tab libre).

### 5. Temps rallongé (DJ4)

Table `jeu_confort_reglages` (migration `c4f1a8b7e2d3`, tête précédente `a1f7c3d9e5b2`), routes
`GET|PATCH /jeu/confort/reglages`, lecture dans `creer_partie` **et nulle part ailleurs** : une
partie fige ses horloges à sa création. Si **l'un** des deux joueurs l'a demandé, la partie entière
l'obtient — dissymétrie assumée (DJ4 fixe un temps *par tour*, pas par joueur ; on tranche en faveur
de qui a demandé de l'aide). Les marges réseau/déconnexion ne sont pas rallongées.

### 6. Écran `/jeu/confort` et son accès

Trois réglages en français d'enfant, chacun disant ce qu'il change vraiment (y compris « ça vaut pour
tes prochaines parties »). Accessible depuis le salon (`salon-lien-confort`) : un réglage qu'on ne
peut pas atteindre n'existe pas.

## Preuves

| Preuve | Résultat |
|---|---|
| `pytest -q` (API, 1333 tests) | **1331 passés**, 2 échecs **préexistants** : `test_catalogue_seed.py` × 2 — `pg_dump: command not found` (outil absent de devAI, présent en CI) |
| `pytest -q tests/test_jeu_confort.py` | **16 passés** (défauts publiés, partiel, 422, CSRF, D11, accès croisé, parité code/base, temps rallongé de bout en bout) |
| `ruff check src tests` | All checks passed |
| `vitest run` (front, 78 fichiers) | **524 passés** |
| `tsc --noEmit` | aucune erreur |
| `eslint .` | 0 erreur (1 avertissement préexistant dans `game-realtime.test.ts`) |
| `next build` | compilé ; `/jeu/confort` présent dans le manifeste des routes |
| `playwright test e2e/a11y-jeu.spec.ts` | **7 passés** |
| `playwright test e2e/partie-deux-navigateurs.spec.ts` | **5 passés** (non-régression du clavier et des surcouches sur une partie entière) |
| `plateau-responsive`, `plateau-rendu`, `decks-*`, `auth`, `card-detail`, `validation`, `parcours-complet` | passés |
| `alembic upgrade head` | `a1f7c3d9e5b2 → c4f1a8b7e2d3` appliquée sur base neuve ; une seule tête |

**Les tests mordent** — vérifié, pas supposé : le test de contraste a échoué en nommant « psychic
3,99 » et « fighting 3,98 » **avant** correction ; l'audit jsdom a échoué sur l'`aria-label` des
récompenses ; l'e2e a échoué en nommant « ▸Journal(0) (93×20) » ; et l'e2e clavier a trouvé une
**régression introduite par ce lot** (voir « Ce qui a failli passer »).

### Deux échecs e2e préexistants, mesurés sur `main`

Pour ne pas les porter au compte de ce lot, les deux ont été rejoués sur un worktree `github/main`
**sans aucun changement du lot** (installation et build dédiés) :

| Test | Sur la branche | Sur `main` | Verdict |
|---|---|---|---|
| `anim-fluidite` « plancher 30 images/s, CPU bridé ×4 » | 9,8 à 14,1 img/s | **10,1 img/s** | préexistant, propre à devAI (machine partagée avec d'autres lots) |
| `responsive` « `/carte/{id}` @ 320 px » | 321 > 320 px | **321 > 320 px** | préexistant, 1 pixel |

Aucun des deux ne touche aux écrans de jeu. Ils ne sont **pas** corrigés ici (hors périmètre, et le
premier est une mesure de machine) — mais ils sont signalés : si la CI les rend rouges, ce sont deux
sujets à ouvrir, pas des régressions de ce lot.

## Écarts au plan — assumés et nommés

Le plateau ne tolère **aucun défilement** (critère de `j-plateau-layout`, gardé par un job e2e) et
met neuf zones par joueur à l'échelle d'un écran de téléphone. Trois exigences s'y heurtent :

1. **Cibles de 24 px dans l'arène** — mesuré : une carte de banc fait **4,7 × 6,5 px** à 844 × 390.
   `target-size` est désactivée **pour le plateau seulement** dans l'audit e2e, au titre de
   l'exception « *Equivalent* » du critère 2.5.8 : tout coup jouable sur une carte est **aussi** un
   bouton de la barre d'actions, et ces boutons-là sont mesurés sans exception, plus le clavier et
   l'agrandissement au focus.
2. **Taille de texte sur la page d'une partie** — mesuré : en « très grande », le document passe à
   **432 px** pour 390 disponibles, donc la page défile. Compenser en rognant l'arène la ramènerait à
   une cinquantaine de pixels. Le réglage est donc neutralisé sur cette page
   (`html[data-ecran="plateau"]`) ; la lisibilité d'une carte passe par son agrandissement, et
   **l'écran de confort le dit au joueur**. Un e2e prouve les deux moitiés (ça grossit hors partie,
   ça ne défile pas sur le plateau).
3. **44 px (AAA, 2.5.5)** — hors d'atteinte dans l'arène, pour la même raison. On tient **AA
   partout**, AAA hors plateau.

Deux autres écarts, de périmètre :

4. **L'audit ne couvre que les écrans de jeu**, comme le demandait la mission. L'outillage est
   générique et réutilisable tel quel pour la collection, la fiche carte, le tableau de bord et le
   profil — reste à ouvrir chaque écran et traiter ce qu'`axe` y trouve. Noté dans `docs/UI-UX.md`.
5. **« Une partie complète au clavier seul »** est prouvée par morceaux : l'e2e vérifie que le Tab
   atteint un coup, qu'Entrée l'envoie réellement (requête interceptée) et qu'Échap sort des
   surcouches ; la partie entière au clavier, de la file à l'écran de fin, n'est pas automatisée —
   ce serait un second pilote complet à écrire dans `partie-deux-navigateurs.spec.ts`. Le risque
   résiduel est faible (les coups sont des `<button>` standard, et le défaut réel qui bloquait la
   navigation a été trouvé par le test partiel), mais il est réel : je ne le présente pas comme
   couvert.

## Ce qui a failli passer

Le crochet `useModale` restituait le focus au démontage **dans tous les cas**. Or le zoom de carte
s'ouvre **au focus** d'une carte et ne contient aucun contrôle : en tabulant, il se démontait,
ramenait le focus sur la carte quittée, et le Tab suivant le rouvrait. La tabulation **tournait en
rond** et n'atteignait jamais la barre d'actions — c'est-à-dire que le lot censé rendre le jeu
jouable au clavier le rendait injouable au clavier. Les cinq tests unitaires de clavier étaient verts
(ils montent une surcouche isolée, pas un plateau). Seul l'e2e « une partie se joue au clavier seul »
l'a vu. Le crochet ne restitue donc le focus que s'il l'a réellement **pris**, et le commentaire
porte la mesure.

Deux autres pièges, consignés pour les lots suivants :

- **`window.localStorage` n'est pas exposé** par l'environnement jsdom de ce dépôt (vérifié :
  `undefined`, alors que `window.location` existe). Tout ce qui garde une préférence côté navigateur
  — thème, guide de première partie, confort — n'était donc testable qu'à travers son `try/catch`,
  c'est-à-dire pas du tout. Un double est posé dans `vitest.setup.ts`, à côté de ceux de
  `matchMedia` et `ResizeObserver`.
- **Un réglage posé dans `localStorage` par un test e2e ne tient pas** : le fournisseur relit le
  serveur dès qu'une session existe et écrase le cache (c'est voulu). Les deux e2e de réglage passent
  donc par `PATCH /jeu/confort/reglages`. Un test qui n'aurait posé que le cache aurait mesuré
  l'inverse de ce qu'il croyait.

## Reste à faire

- Étendre l'audit aux écrans **hors jeu** (collection, fiche carte, tableau de bord, profil) —
  l'outillage est posé.
- Automatiser une partie **entière** au clavier (écart 5).
- Les deux échecs e2e préexistants (`anim-fluidite` sur devAI, `responsive` à 320 px) : à trancher
  sur la foi de la CI.
- Rien à livrer en PROD par ce lot (la livraison se fait à part, par devAI).

## Où travailler ensuite

Documentation durable : **`docs/jeu/ACCESSIBILITE.md`** (la fiche), plus les renvois dans
`CLAUDE.md`, `docs/UI-UX.md`, `docs/ARCHITECTURE.md` et `docs/jeu/HORLOGES.md`.

## Note d'exécution

Le lot est annoncé en couloir **chimera**, mais chimera n'a **ni Node ni pnpm** dans sa WSL (vérifié
ce jour : `which node pnpm` ne rend rien) et ne peut pas lancer de navigateur Playwright. Un lot
entièrement front, dont les deux preuves centrales sont un audit `axe` dans un navigateur et une
suite vitest, n'y est donc pas exécutable. Il a été mené **sur devAI**, dans une copie de travail
jetable (`/tmp/wt-j-accessibilite-jeu`, clonée sur `github/main`), avec sa propre base Postgres
(`pbm_jaccess_test`, `pbm_a11y_e2e`) — aucune base partagée touchée. `/Volumes/Data` reste refusé en
écriture depuis une session agent (`Operation not permitted`, TCC), d'où le transit par `/tmp` ; il
est signalé plutôt que contourné en silence.
