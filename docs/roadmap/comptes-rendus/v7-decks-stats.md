# Compte rendu — `v7-decks-stats` — Fiche d'un deck : composition, courbe d'énergie et valeur

**Statut : livré en recette (chimera), en attente CI GitHub verte puis fusion.**
Piste Jeu — decks · couloir CH5 (chimera) · dépend de `v7-decks-ui` (livré).

## Résumé

Une fiche chiffrée d'un deck, calculée **côté serveur** et rendue par un panneau sobre sous le
constructeur. Elle répond à trois questions : ce que le deck **coûte à jouer** (courbe des coûts
d'attaque, PV moyens), ce qu'il **contient** (répartition par type de carte, par type élémentaire,
par rôle, structure d'évolution, cartes spéciales), et ce qu'il **vaut** (valeur marchande, part
de doublons). Tous les chiffres viennent du **catalogue** et de la **valorisation existante** —
jamais d'une estimation du modèle (risque du lot).

## Livrables

**API** — `GET /me/decks/{deck_id}/stats` (borné au propriétaire, 404 sinon, jamais 403) :
- `pbm_api.decks.stats` : logique **pure** (sans base), agrégats pondérés par quantité —
  `by_role` (partition `attaquant`/`mur`/`soutien`/`energie`, somme = `card_count`), `by_supertype`,
  `type_distribution` (+ `untyped_pokemon`), `attack_cost_curve` (nombre d'énergies par attaque,
  `Card.attacks.cost` TCGdex), `average_hp`, `stage_distribution` (+ `has_basic_pokemon` /
  `evolution_copies_without_base`), `special_cards`, `duplicate_copies`/`duplicate_ratio`, `value` ;
- `pbm_api.decks.service.deck_stats` : charge le deck (isolation `user_id`), enrichit `_load_cards`
  (PV, type élémentaire, attaques, marqueur de règle) et calcule la **valeur marchande** via
  `pbm_api.pricing.valuation.bulk_reference_prices_eur` (variante `normal`), **Énergies de base
  exclues** (fournies, D10) ; un prix manquant n'est jamais compté 0 (`value.missing_price_cards`) ;
- `DeckStatsOut` / `DeckValueOut` / `DeckStatBucketOut` dans `decks/schemas.py`.

**Front** — `apps/web/src/app/jeu/decks/[id]/deck-stats-panel.tsx` (`DeckStatsPanel`), rendu sous le
constructeur : tuiles chiffrées (cartes, PV moyens, cartes spéciales, valeur, doublons), barres de
répartition (rôle, type de carte), et deux graphiques `recharts` sobres (courbe des coûts d'attaque,
répartition par type élémentaire — couleurs alignées sur les fonds de carte). Recharge quand le deck
change (`refreshKey = deck.updated_at`). Client API `fetchDeckStats` (miroir du schéma serveur),
types générés régénérés (`pnpm gen:api` → `packages/api-client/src/schema.d.ts`).

## Preuves

- **ruff** : `All checks passed!` (E/F/I/UP/B, ligne 100).
- **pytest (base fraîche migrée, `alembic upgrade head`, TZ=Europe/Paris)** : `40 passed` —
  `test_deck_stats.py` (6 : logique pure sur decks connus, forme+valeurs de la route, accès croisé
  404, auth 401) + régression `test_deck_routes.py`, `test_deck_collection_sync.py`,
  `test_deck_card_search_routes.py`.
- **Test qui mord** : la route de stats renvoyait 404 avant ce lot ;
  `test_deck_stats_route_shape_and_values` échoue sans l'endpoint et passe avec.
- **web** : `tsc --noEmit` propre ; `vitest run` → **160 passed** (dont `deck-builder-view` avec le
  panneau intégré et `deck-stats-panel.test.tsx` : tuiles, alerte « évolutions sans base », erreur
  API sans plantage) ; `eslint .` 0 problème ; `next build` OK ; garde « aucune URL localhost dans
  `.next/static` » : `GUARD_OK`.
- **Isolation** : `test_deck_stats_cross_access_returns_404` (l'utilisateur B reçoit 404 sur le deck
  de A), route entièrement bornée à `get_current_user`.
- **La CI GitHub Actions fait foi** : verte attendue sur la branche `roadmap/v7-decks-stats` avant
  fusion.

## Écarts au plan

- **Lignes d'évolution « complètes ou non »** : le catalogue ne porte **pas** de champ `evolveFrom`
  (seulement `stage`). Reconstruire les chaînes d'évolution par le nom serait une devinette — exclu
  par le risque du lot (« les chiffres viennent du catalogue, jamais d'une estimation »). La fiche
  livre donc la **répartition par stade** (`stage_distribution`) et le signal honnête « des
  évolutions sans aucun Pokémon de base » (`evolution_copies_without_base`, aligné sur la règle de
  légalité). Une vraie complétude des lignes demanderait d'ajouter `evolveFrom` à l'import catalogue
  (lot ultérieur).
- **Rôles** : partition heuristique **de catalogue** documentée (`mur` = Pokémon à PV ≥ 200 ;
  attaquant = Pokémon qui attaque ; sinon soutien ; Dresseur = soutien). Assumé, pas un jugement du
  modèle.
- **Maquette** : `ROADMAP.html` ne porte pas d'écran dédié à la fiche de statistiques de deck (les
  maquettes couvrent V1–V4). Le panneau suit la **charte PokéBoy** (jetons de style, graphiques
  `recharts` sobres cohérents avec la courbe de valeur existante) et s'intègre sous le constructeur.
  Capture non jointe : session autonome sans navigateur ; le rendu est couvert par les tests
  `vitest` (tuiles, libellés, états). Écart assumé.

## Reste à faire

- **Fusion dans `main`** sous `flock` après CI verte (mécanique du couloir chimera).
- **Déploiement** : ce lot ajoute une route et un écran ; la mise en PROD reste **manuelle, sur
  décision de JF** (règle de flotte). Rien de lourd ne tourne côté serveur (agrégats calculés à la
  lecture, requêtes bornées au deck).

## Grille

- `dev` — fait (module stats, service, route, schémas, panneau front, client API).
- `tests` — fait (6 pytest ciblés + régression 40 passed ; 160 vitest).
- `securite` — fait (isolation `user_id`, accès croisé 404, aucun secret, aucune clé exposée).
- `maquette` — écart assumé (pas de maquette dédiée ; charte respectée, couvert par tests).
- `doc_tech` — fait (`docs/ARCHITECTURE.md`, `docs/UI-UX.md`).
- `release_uat` — fait (recette locale chimera : ruff, pytest base fraîche, vitest, build, garde).
- `release_prod` — en attente (décision JF).
- `backlog` / `compte_rendu` — tenus par l'ordonnanceur + ce fichier.
