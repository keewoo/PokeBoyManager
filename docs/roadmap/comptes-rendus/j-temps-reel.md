# Compte rendu — `j-temps-reel`

**Canal temps réel : diffusion des coups, reconnexion et reprise après F5** (jalon J1, piste Serveur
de parties, couloir J-SRV/chimera). Exécuté sur chimera, piloté depuis devAI.

## Résumé

Le lot pose le **canal temps réel** d'une partie, sur le socle du journal numéroté (`j-partie-service`)
et du point de sortie unique du moteur (`j-autorite-vues`). Trois briques, le moteur restant pur :

1. **Resynchronisation** (`games/temps_reel.py:resynchroniser`) — « donne-moi tout depuis le numéro N » :
   vue autoritaire courante **plus** la file des coups ∈ [N, courant). Le travail est borné (dernier
   instantané ≤ N puis rejeu de la seule queue), chaque coup rejoué est revérifié contre l'empreinte
   du journal. C'est la réponse commune à la reprise après F5 et à la reconnexion après coupure.
2. **Bus de diffusion** (`Hub`) — en mémoire du process : un coup appliqué est diffusé à chaque
   abonné, **projeté pour lui** (jamais l'état brut). Un rejeu idempotent n'est pas diffusé ; une file
   saturée n'est jamais perdue en silence (abonné marqué → rattrapage par resync).
3. **Pilotage de canal** (`piloter_canal`) + transports (`routers/games_ws.py`) : WebSocket
   authentifié `WS /games/{id}/ws?depuis=N` (diffusion numérotée, battement de cœur, resync à la
   demande, rattrapage après saturation) et **repli en interrogation** `GET /games/{id}/sync?depuis=N`.
   Côté front, un client (`lib/game/realtime.ts`) applique **par numéro** (dédoublonnage, détection de
   trou), bascule seul en repli, et un bandeau (`StatutConnexion`) annonce « connexion dégradée ».

Le **numéro de séquence** (le `numero` d'entrée de journal) rend le canal insensible au désordre et
aux doublons, et la garantie de non-perte tient au **journal** (source de vérité), pas au bus live.

## Livrables

- `apps/api/src/pbm_api/games/temps_reel.py` — resync, `Hub`, `piloter_canal` (mécanique sans transport).
- `apps/api/src/pbm_api/routers/games_ws.py` — WebSocket + repli HTTP `/sync` + gardes (origine, session).
- `apps/api/src/pbm_api/routers/games.py` — diffusion du coup appliqué sur le `Hub` (publication).
- `apps/api/src/pbm_api/main.py` — branchement du routeur temps réel.
- `apps/web/src/lib/game/realtime.ts` — client temps réel (WebSocket + repli, séquencement par numéro).
- `apps/web/src/components/game/connection-status.tsx` — bandeau d'état « connexion dégradée ».
- `docs/jeu/TEMPS-REEL.md` — protocole, messages, garanties (référence de réimplémentation).
- Sections ajoutées : `docs/ARCHITECTURE.md` (routes), `docs/SECURITE.md` (anti-CSWSH), `docs/UI-UX.md` (bandeau).

## Preuves (mesurées sur chimera, worktree `wt-j-temps-reel`)

- **Tests du lot** : `tests/test_games_temps_reel.py` + `tests/test_games_ws_routes.py` → **20 passed**.
  Couvrent les trois critères d'acceptation : reprise complète et file depuis N (reprise F5),
  file exhaustive et ordonnée depuis un numéro (aucune perte sur coupure), repli HTTP qui sert la
  même charge et se termine. Plus : diffusion projetée par destinataire, rejeu non diffusé,
  saturation sans perte, battement de cœur, resync à la demande, accès croisé → 404, refus
  d'origine tierce, résolution de session + droit de jeu.
- **Non-régression parties** : `test_games_routes/service/projection/game_access/matchmaking_routes`
  → **31 passed**.
- **Front** : `pnpm --filter @pbm/web lint` ✅, `type-check` (tsc) ✅, `vitest run` → **171 passed**
  (dont `game-realtime.test.ts` 6 et `connection-status.test.tsx` 3 : séquencement par numéro,
  dédoublonnage, trou → resync, battement en avance → resync, repli `/sync`, bandeau dégradé).
- **Lint Python** : `uv run ruff check` → All checks passed.
- Base de test isolée `pbm_j_temps_reel_test` (:55432), `alembic upgrade head` appliqué. La **CI
  GitHub Actions fait foi** (suite complète `uv run pytest -q` + web lint/type-check/test/build).

## Écarts au plan

- **Pas d'écran plateau** : ce lot livre le **transport** (canal + repli) et le **bandeau** dégradé ;
  leur branchement dans un plateau qui se reconnecte après F5 est le lot aval `j-plateau-layout`
  (que ce lot débloque). Il n'y a donc pas d'écran « plateau » à comparer à l'onglet « Maquette du
  jeu » ici ; le bandeau suit la charte (contour teinté, `role=status`). La tâche `maquette` est
  donc **partielle** : composant conforme à la charte, écran complet en aval.
- **Diffusion live mono-process** : le `Hub` vit en mémoire d'un process. Suffisant pour J1 (« laid
  mais juste ») car la non-perte repose sur la resync par numéro, pas sur le bus. La diffusion live
  multi-process (Redis pub/sub) relève de `j-charge-temps-reel` (débloqué par ce lot).
- **Pas de test « transport WebSocket réel »** : le `TestClient` Starlette tourne dans une autre
  boucle asyncio, incompatible avec la session async partagée du conftest. Le pilotage est donc
  exercé **de bout en bout sur un faux canal** dans la boucle du test (resync, diffusion, battement,
  rattrapage), l'auth/anti-CSWSH en unitaire, et le repli HTTP en bout-en-bout via l'API réelle — une
  couverture au moins aussi forte, sans la fragilité d'un socket en thread.

## Reste à faire (aval)

- `j-plateau-layout` — brancher le client temps réel dans le plateau, capture conforme à la maquette.
- `j-charge-temps-reel` — diffusion multi-process (Redis pub/sub) et tenue en charge.
- `j-timer`, `j-echanges-emotes` — s'appuient sur le canal numéroté.

## Décisions attendues de JF

Aucune. Le lot respecte D9 (aucun effet approximé — il ne touche pas aux effets), D11 (droit de jeu),
l'autorité serveur et l'absence de repli silencieux. La PROD se livre à part (aucun déploiement ici).
