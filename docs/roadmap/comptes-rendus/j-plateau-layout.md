# Compte rendu — `j-plateau-layout`

**Plateau : la table de jeu, du grand écran au téléphone.** Jalon J1, piste Interface de jeu.

## Résumé

Livraison du **plateau de jeu** à `/jeu/parties/{id}` — la route vers laquelle pointaient déjà
« Reprendre » / « Rejoindre » du salon (`j-salon-partie`), jusqu'ici inexistante. Le plateau dispose
les neuf zones de chaque camp, se met à l'échelle du grand écran au téléphone en paysage, offre le
zoom d'une carte et la consultation des zones publiques. Il branche le canal temps réel
(`j-temps-reel`) et gate l'accès (droit au jeu D11 + participation à la partie).

Le moteur `pbm_game` reste **pur** : rien n'a été ajouté côté moteur. Le plateau ne consomme que la
**vue projetée** par le serveur (`pbm_game.sortie.projeter`) — il ne rejoue aucune règle, n'apprend
jamais la main adverse ni l'ordre d'une pioche (zones cachées réduites à un compteur à la source).

## Livrables

- Route `apps/web/src/app/jeu/parties/[id]/` : `page.tsx` (serveur, attend `params`) + `partie-view.tsx`
  (client : gating d'accès, chargement de la vue autoritaire, canal temps réel + bandeau d'état).
- `apps/web/src/components/game/game-board.tsx` — l'arène : deux camps, neuf zones, actifs dominants,
  Stade partagé, main en éventail. Responsive par conteneur (`.pbm-arena`, `em` sur la plus petite
  dimension), hauteur bornée à l'écran.
- `apps/web/src/components/game/board-card.tsx` — la carte (deux tailles), déclencheur de zoom au
  survol / focus / maintien long ; point d'extension unique pour `j-rendu-carte`.
- `apps/web/src/components/game/card-zoom.tsx` — l'agrandissement lisible, sans quitter la partie.
- `apps/web/src/components/game/zone-consultation.tsx` — `ZonePublique` (consultable) et `ZoneCachee`
  (compteur seulement).
- `apps/web/src/lib/game/plateau.ts` — types (miroir du contrat serveur) et aides **pures**.
- `apps/web/src/lib/api/games.ts` — `getGameState(id)`.
- CSS d'arène responsive dans `apps/web/src/app/globals.css`.
- `apps/api/scripts/seed_game_access_e2e.py` — droit d'accès au jeu pour l'e2e.
- Doc : section « Plateau de jeu » dans `docs/UI-UX.md`.

## Preuves

- Tests unitaires (vitest, jsdom) : `plateau.test.ts`, `board-card.test.tsx`,
  `zone-consultation.test.tsx`, `game-board.test.tsx`, `partie-view.test.tsx`. Chacun échoue sans le
  code livré (les composants n'existaient pas). Lancés sur chimera.
- E2E (Playwright, exécuté par la CI) : `apps/web/e2e/plateau-responsive.spec.ts` — mesure l'absence de
  défilement (horizontal **et** vertical, `scrollWidth/scrollHeight` vs fenêtre, même méthode que
  `responsive.spec.ts`) à **844×390 en paysage**, vérifie que les zones clés sont dans la fenêtre
  (`toBeInViewport`), et que le plateau se redessine sans perdre l'état après une rotation
  portrait → paysage.
- Isolation : le gating lit `game_access` et la participation côté serveur ; un refus → `notFound()`.
  Test `partie-view.test.tsx` : compte sans droit → page inexistante, `getGameState` jamais appelé ;
  partie d'autrui (404) → page inexistante.
- CI GitHub Actions verte sur la PR (jobs web / game / e2e) — voir le dernier message du lot.

## Écarts au plan

- **Pas de build/déploiement** : hors périmètre du lot (la PROD se livre à part, par devAI).
- Les cartes sont des **repères de disposition** (référence + pastilles minimales), pas encore l'image
  officielle ni les attaques/coûts : c'est délibérément le lot aval `j-rendu-carte`, et le rendu fin des
  dégâts/énergies/états est `j-plateau-etat-visuel`. On ne fabrique aucun contenu absent (D9) ;
  `BoardCard` est le point d'extension unique.
- L'AC « texte d'une carte zoomée lisible sans pincer » est satisfaite par la **taille** du zoom (grande
  police indépendante du conteneur) ; le contenu riche (attaques, coûts) suivra avec `j-rendu-carte`.

## Reste à faire (lots aval, déjà débloqués)

- `j-plateau-etat-visuel` — lecture d'un coup d'œil : dégâts, énergies, états, récompenses.
- `j-plateau-interactions` — jouer un coup : cibles valides, annulation, confirmation.
- `j-rendu-carte` — ma photo ou l'image officielle : la carte telle qu'elle est jouée.
