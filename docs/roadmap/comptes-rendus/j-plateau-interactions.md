# Compte rendu — `j-plateau-interactions`

**Jouer un coup : cibles valides, annulation, confirmation.** Jalon J1, piste Interface de jeu,
couloir J-UI (chimera). Exécuté en session autonome sur chimera, piloté depuis devAI.

## Résumé

Le plateau devient **jouable** : il consomme les actions légales du moteur, illumine leurs cibles,
et soumet les coups — **sans réécrire aucune règle côté client**. Deux modes d'entrée interchangeables
(tap-tap et glisser-déposer) reposent sur une **seule machine à états pure**. Un coup refusé affiche
la **raison du moteur** (règle `R-x.y`), un coup irréversible demande confirmation, et un double clic
ne joue jamais deux fois (verrou d'écran + idempotence serveur).

Le câblage manquant a d'abord été posé côté serveur : l'API n'exposait ni les actions légales ni le
numéro d'action au client. Un adaptateur pur les sérialise dans la vue autoritaire.

## Livrables

**Serveur (apps/api)**
- `pbm_api/games/actions.py` (nouveau) — `actions_pour(etat, joueur)` sérialise `actions_legales`
  (coups + cibles + `irreversible`) et `actions_refusees` (commandes de palette non jouables, avec la
  règle et le message de `pbm_game.actions.valider`). Aucune règle réécrite : tout vient du moteur.
- `pbm_api/games/projection.py` — la vue autoritaire porte désormais `actions_legales` et
  `actions_refusees` (dans `vue_autoritaire` **et** `projeter_resultat`, donc aussi par le canal
  temps réel).
- `routers/games.py` — l'enveloppe de `/state` et des réponses de coup/abandon porte `numero` (le
  prochain numéro d'action attendu, clé d'idempotence côté client).

**Client (apps/web)**
- `lib/game/interactions.ts` (nouveau) — machine à états **pure** (sans React, sans E/S) : choisir un
  coup, cibler, confirmer un irréversible, annuler ; aides `ciblesIlluminees`, `cibleParReference`.
- `lib/game/plateau.ts` — types `VueCible`, `VueActionLegale`, `VueActionRefusee` ; `VuePartie` gagne
  `actions_legales` / `actions_refusees` ; l'enveloppe gagne `numero`.
- `lib/api/games.ts` — `playAction(gameId, {type, params, numero_attendu})`.
- `components/game/action-bar.tsx` (nouveau) — coups jouables (certains glissables), coups refusés
  grisés avec leur raison, panneau de confirmation, bouton annuler.
- `components/game/board-card.tsx` — une carte peut être **illuminée** (cible) : cliquable, focusable
  clavier, zone de dépôt (glisser-déposer).
- `components/game/game-board.tsx` — intègre la machine à états, illumine les cibles sur le plateau,
  gère le verrou anti-double-envoi et l'affichage du refus.
- `app/jeu/parties/[id]/partie-view.tsx` — tient le `numero` courant, fournit `onJouer`.

**Docs** : `docs/UI-UX.md` (§ « Jouer un coup »), `docs/jeu/ACTIONS.md` (§ « Servir les actions au
client »).

## Preuves

- **Moteur pur préservé** : aucune modification de `pbm_game`. L'`irreversible` et la palette vivent
  dans l'adaptateur `apps/api` ; la machine à états côté client ne lit que des données.
- **Tests serveur** (`apps/api/tests/test_games_interactions.py`) : 4 tests purs de `actions_pour`
  (joueur actif → coups sans refus ; joueur passif → `avancer_phase` grisé avec `R-5.1` ; checkup →
  « Terminer le tour » irréversible ; partie terminée → aucun coup, refus `R-14.6`) **passent** sur
  chimera. 1 test HTTP (`/state` porte `actions_legales`/`actions_refusees`/`numero`, et un coup
  renvoie le `numero` suivant) — vérifié par la CI (base requise).
- **Tests client** : `lib/game/interactions.test.ts` (10) + `components/game/game-board-interactions.test.tsx`
  (6) **passent**. Ils couvrent les trois critères d'acceptation :
  - *aucune règle côté client* : l'écran soumet le coup exact fourni par le serveur ;
  - *un coup refusé affiche la raison du moteur* : refus 422 → message du moteur affiché ; commande
    grisée → `regle` + `message` au survol ;
  - *un double clic ne joue jamais deux fois* : `onJouer` appelé **une** fois sur double clic.
  Plus : confirmation d'un irréversible (abandon), ciblage (illumination + tap qui soumet avec la
  cible), lecture seule sans `onJouer`.
- **Suite web complète verte** sur chimera : 51 fichiers, 260 tests. `lint` (0 erreur),
  `type-check` (0 erreur), `build` (OK). `ruff check .` vert sur `apps/api`.

## Critères d'acceptation

- [x] Aucune règle du jeu n'est implémentée côté client — l'écran consomme `actions_legales` /
  `actions_refusees` et soumet le coup exact du moteur ; même l'`irreversible` vient du serveur.
- [x] Un coup refusé affiche la raison du moteur (422 → message affiché ; palette grisée → `regle` +
  `message`), jamais un message générique.
- [x] Un double clic ne joue jamais deux fois (verrou d'écran synchrone + idempotence `numero_attendu`).

## Écarts au plan

- **Périmètre palier 4 (D9, assumé)** : le moteur ne déclare aujourd'hui que `avancer_phase` et
  `abandonner`, **sans cible**. La mécanique de ciblage (illumination, tap-tap, glisser-déposer,
  cibles valides) est donc livrée et **testée avec des données synthétiques** ; elle sera exercée en
  conditions réelles quand les familles de coups à cibles (attacher, attaquer, retraite…) seront
  enregistrées par les lots de cartes. On n'a **rien approximé** : l'UI affiche fidèlement ce que le
  moteur déclare, pas un bouton « piocher » que le moteur traite encore comme action système (R-5.2).
- **Glisser-déposer** : fonctionnel (le chip d'un coup ciblé est glissable, la cible illuminée est
  zone de dépôt). Le mode **tap-tap** reste le chemin primaire, pleinement robuste ; le glisser passe
  par la même machine à états.

## Reste à faire (lots aval)

- `j-plateau-decisions` (débloqué) : fenêtres de décision (choisir/ordonner/répondre pendant le tour
  adverse) — réutilise cette machine à états et le canal `demande` déjà présent dans la vue.
- Les familles de coups à cibles (lots de cartes) peupleront `actions_legales` avec de vraies cibles ;
  aucune modification d'écran attendue.
- Retour **sonore et tactile** (vibration) : esquissé par le verrou/animation, à enrichir avec
  `j-anim-socle` / le lot audio.

## Tests exigés — couverture

- Test qui échoue sans le changement : `interactions.test.ts` et `test_games_interactions.py`
  n'existent pas avant ce lot ; ils portent sur les modules créés ici.
- Moteur pur : intact (aucune modification), son test d'import reste la garantie.
- Accès croisé : déjà couvert par `test_games_projection` (404), non redoublé.
