# `j-e2e-deux-navigateurs` — partie complète jouée automatiquement, à deux navigateurs

**Statut : livré.** P0 · piste Qualité & exploitation · jalon J5. Branche
`roadmap/j-e2e-deux-navigateurs`, construite sur `github/main` puis **rebasée** sur `0902461`
(`j-rendu-carte` a été intégré pendant le lot et touche `board-card.tsx` et `routers/games.py`, les
deux fichiers que ce lot modifie aussi — correctifs réappliqués sur les versions neuves, suites
rejouées).

## Résumé

Le lot livre le parcours complet et ses quatre parcours dégradés, en Playwright, à **deux contextes
de navigateur** — deux joueurs, deux sessions, de la file d'attente à l'historique du compte, sans
intervention. Les cinq parcours sont verts, et les captures sont désormais publiées par la CI même
quand tout passe.

**Le lot n'a pas seulement écrit un test : il a trouvé cinq défauts, dont deux qui rendaient le jeu
injouable.** C'est exactement ce que le jalon J5 attendait d'un e2e à deux navigateurs, et c'est
l'argument central de ce compte rendu : aucun des cinq ne pouvait être vu autrement.

| # | Défaut | Effet réel | Correctif |
|---|---|---|---|
| 1 | **La file d'attente ne démarrait jamais la partie** | deux joueurs appariés arrivaient sur un plateau resté au coup 0, où le **seul coup légal est « Abandonner »**. La partie existait, s'affichait, et ne pouvait pas être jouée | `games/matchmaking.py` appelle `demarrer_partie` sous le verrou d'appariement |
| 2 | **Le canal annonçait un numéro de coup en retard** | retard **constant de 3 coups** : le coup suivant du joueur était refusé en 409 (« Conflit de numéro ») et il fallait attendre jusqu'à **20 s** que le battement de cœur rattrape. Un coup sur deux refusé | le message porte `courant`, le prochain numéro attendu du serveur ; le client le suit |
| 3 | **Choisir une cible au clic était impossible à la souris** | survol *et* focus ouvraient `CardZoom` (surcouche plein écran qui se referme au clic) : elle apparaissait entre l'appui et le relâchement, et **aucun `click` n'atteignait la carte** | une carte illuminée ne zoome plus (survol, focus, maintien) |
| 4 | **Clés React dupliquées dans la barre d'actions** | 12 boutons `attacher_energie` et 9 `jouer_objet` rigoureusement identiques → même clé → après un coup en vol, une partie des boutons **gardait `disabled` définitivement** | le rang entre dans la clé |
| 5 | **La CSP bloquait le WebSocket** | le canal temps réel échouait 3 fois puis repliait en interrogation périodique : le jeu tournait en **mode dégradé permanent sans que rien n'échoue** | `connect-src` nomme l'origine `ws:`/`wss:` |

⚠️ **Portée du défaut 5 : dev / CI / e2e uniquement, pas la production.** Il ne frappe que les
déploiements où l'API a sa **propre origine** (page sur `:3100`, API sur `:8100`). En UAT/PROD l'API
partage l'origine du site (`https://pokeboy.lol/api`) et `'self'` couvre déjà `wss:` — c'est
précisément pourquoi il est resté invisible en ligne. Les défauts **1 à 4**, eux, touchent la
production.

## Livrables

**Le parcours et ses seeds**

- `apps/web/e2e/partie-deux-navigateurs.spec.ts` — les 5 parcours (nominal + 4 dégradés). Le plan en
  nommait cinq dégradés et le critère en demandait quatre : « déconnexion et reprise » et « repli en
  interrogation périodique » sont le même mécanisme et tiennent dans un parcours, qui prouve les deux.
- `apps/api/scripts/seed_partie_e2e.py` — deux comptes `game_access` (D11) et, pour chacun, un deck
  **compilable par le moteur et entièrement scripté** (D9). Il n'en existait aucun :
  `seed_deck_builder_e2e.py` produit un deck légal pour le constructeur mais **injouable** (ni
  `prize_marker` ni `retreat_cost`), donc `jouabilite` répondait `false` et le bouton « Entrer dans
  la file » restait désactivé.
- `apps/api/scripts/forcer_horloge_e2e.py` — épuise le budget du joueur actif sur **une** partie
  nommée, pour le parcours « expiration d'horloge ».

**Les correctifs** — `apps/api/src/pbm_api/games/matchmaking.py`,
`apps/api/src/pbm_api/games/temps_reel.py`, `apps/api/src/pbm_api/routers/games.py`,
`apps/web/src/lib/game/realtime.ts`, `apps/web/src/components/game/board-card.tsx`,
`apps/web/src/components/game/action-bar.tsx`, `apps/web/src/middleware.ts`.

**Les tests de non-régression** — chacun **vérifié en cassant le correctif** :

| Test | Sans le correctif |
|---|---|
| `apps/api/tests/test_matchmaking_service.py::test_partie_appariee_est_jouable_mise_en_place_lancee` | `AssertionError: la partie appariée n'a pas été démarrée : son journal est vide, le plateau sera muet` |
| `apps/web/src/__tests__/game-realtime.test.ts` (2 cas, dont le repli de compatibilité) | `le client doit retenir 3, pas 1: expected 1 to be 3` |
| `apps/web/src/__tests__/board-card-ciblage.test.tsx` (2 cas) | `une cible illuminée ne doit pas zoomer au survol : la surcouche avalerait le clic` |
| `apps/web/src/__tests__/action-bar-cles.test.tsx` (2 cas) | `React signale des clés dupliquées : Encountered two children with the same key…` |
| `apps/web/src/__tests__/middleware.test.ts` (3 cas ajoutés) | l'origine `ws://`/`wss://` absente de `connect-src` |

**La CI** — `.github/workflows/ci.yml` : l'envoi du rapport Playwright passe de `failure()` à
`always()`. Les captures sont la preuve demandée par le lot, et une preuve publiée seulement en cas
d'échec n'existe pas quand tout va bien.

**La doc** — `docs/jeu/E2E-PARTIE.md` (nouvelle fiche : ce que chaque parcours prouve, comment le
pilote décide, les pièges, les cinq défauts, ce qui reste ouvert) et son entrée dans la carte des
fiches de `CLAUDE.md`.

## Preuves

**Les cinq parcours, verts, sur la base rebasée (`0902461` + ce lot), devAI :**

```
Running 12 tests using 1 worker
  ✓ partie-deux-navigateurs.spec.ts › parcours nominal : de la file d'attente à l'historique du compte (15.7s)
  ✓ partie-deux-navigateurs.spec.ts › dégradé — F5 au milieu : le plateau se redessine et la partie continue (9.6s)
  ✓ partie-deux-navigateurs.spec.ts › dégradé — abandon : les deux écrans l'annoncent, l'historique le retient (7.5s)
  ✓ partie-deux-navigateurs.spec.ts › dégradé — expiration d'horloge : défaite au temps, sans que personne ne clique (27.1s)
  ✓ partie-deux-navigateurs.spec.ts › dégradé — déconnexion puis reprise : repli en interrogation périodique (18.2s)
  ✓ plateau-rendu.spec.ts (4 tests)          ← lot `j-rendu-carte`, non régressé par mes correctifs
  ✓ plateau-responsive.spec.ts (3 tests)     ← idem
  12 passed (1.7m)
```

**Captures jointes au rapport** (onglet de chaque test, publiées en artefact `playwright-report`) :
`01-plateau-ouverture-joueur-A`, `02-fin-de-partie-gagnant`, `03-fin-de-partie-perdant`,
`04-historique-du-compte-gagnant`, `05-apres-F5`, `06-abandon-celui-qui-abandonne`,
`07-abandon-l-adversaire`, `08-expiration-horloge`, `09-connexion-degradee`,
`10-fin-de-partie-en-mode-degrade`, `11-connexion-retablie`.

**La partie du parcours nominal, mesurée** : 32 coups, fin par `plus_de_pokemon` (R-14.1 adossé à
R-8.9), vainqueur = joueur A, avec `declarer_attaque` ×2, un Objet et un Supporter joués. Avant le
correctif n° 2, le même parcours accumulait les refus : `demandé 9, la partie en est à 12`,
`demandé 14 / 17`, `demandé 20 / 23` — retard constant de 3.

**Suites complètes (devAI)**

- API : **1259 passés**, 2 échecs — `test_catalogue_seed.py`, qui exige `pg_dump`/`psql`
  (postgresql-client) absents de cette machine, présents en CI ; sa propre docstring le dit.
  Reproduits sur une base vierge en 0,32 s, donc ni pollution ni lien avec le lot.
- Web (vitest) : **440 passés**, 15 échecs — les 3 fichiers `app-shell*` préexistants sur cette
  machine (`window.localStorage` indéfini dans `theme-provider`, Node 26 local contre Node 24 en
  CI). Fichiers non touchés par le lot.
- `tsc --noEmit` : propre.

**La CI GitHub Actions fait foi** — voir le passage déclenché par le push de la branche.

## Écarts au plan

- **Cinq correctifs applicatifs n'étaient pas au périmètre d'un lot de test.** Ils ont été faits
  dans la foulée, chacun avec son test qui mord, conformément à la règle « un bug trouvé pendant une
  opération longue se corrige dans la foulée ». Sans eux, le critère « le parcours nominal est vert »
  était inatteignable : les défauts 1, 3 et 4 bloquent la partie, le 2 la rend inutilisable.
- **Aucun déploiement.** Le lot ne livre pas en PROD (la PROD se livre à part, par devAI). Les
  correctifs 1 à 4 **concernent la production** et méritent une livraison ; c'est une décision de JF.
- **Le navigateur e2e ne tourne pas sur chimera** (`libnspr4`, `sudo` requis) : le lot a été piloté
  depuis devAI, qui héberge Node/pnpm et les conteneurs Postgres/Redis — conformément à ce que la
  mémoire du projet enregistrait déjà. Le travail versionné reste dans le worktree chimera.
- **Transit sur le disque système de devAI.** `/Volumes/Data` est monté et libre, mais refusé en
  écriture depuis une session agent (`Operation not permitted`, TCC) — vérifié au début du lot. La
  copie de travail jetable a donc vécu dans `/tmp/pbm-e2e`, supprimée à la clôture. Le réglage
  *Confidentialité et sécurité* reste à faire par JF.
- **Un test de performance échoue localement et n'est pas de ce lot** :
  `anim-fluidite.spec.ts` « 30 images/s avec un processeur bridé ×4 » mesure 14,1 img/s sur devAI,
  seul et sans contention. Il n'est pas touché par le lot (les correctifs portent sur des
  gestionnaires d'événements et une clé React, pas sur la boucle d'animation) ; `j-rendu-carte`
  vient d'ajouter le rendu d'images sur les cartes. La CI, sur runner dédié, fait foi — à surveiller
  sur le passage de ce lot.

## Reste à faire

- **Livrer les correctifs 1 à 4 en PROD** (décision de JF). Le défaut n° 1 en particulier : la file
  d'attente est le chemin principal de deux humains vers une partie.
- **Diffuser les coups système un par un** (ou donner au client de quoi compléter son journal
  immédiatement) : depuis le correctif n° 2 son **numéro** est juste, mais son **journal** peut être
  momentanément incomplet jusqu'à la resynchronisation suivante.
- **Éviter le conflit de numéro à la mise en place** : les deux joueurs ont « placer » légal au même
  numéro (R-4), le second reçoit un 409 et doit re-cliquer. Une file côté client, ou un numéro par
  joueur pendant la mise en place, le supprimerait.
- **Taire la pile `WebSocketDisconnect` (1006)** de `games_ws.py` quand un onglet se ferme pendant
  un envoi : sans conséquence, mais c'est du bruit qui gênera la supervision
  (`docs/jeu/OBSERVABILITE.md`).
- **Fenêtres de décision non couvertes** : le deck de test s'en tient volontairement à des effets
  sans décision, parce que `j-plateau-decisions` vient **après** ce lot. À ajouter au parcours quand
  il sera livré.
