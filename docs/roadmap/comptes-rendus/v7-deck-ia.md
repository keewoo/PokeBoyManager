# Compte rendu — `v7-deck-ia` — Deck proposé par l'IA du joueur, selon les types voulus

**Statut : livré en recette (chimera), en attente CI GitHub verte puis fusion.**
Piste Jeu — decks et parties · couloir CH5 (chimera) · dépend de `v7-decks-legalite` (intégré) et
`v7-decks-ui` (intégré).

## Résumé

« Fais-moi un deck Feu avec mes cartes » évite la page blanche. Le joueur donne ses vœux (types
privilégiés et leur part, Énergies souhaitées, style, inclusions, taille) ; **un seul appel** à
**son** IA propose un deck **pris dans sa collection**, l'explique carte par carte, puis ce deck
(existant) est réécrit. La proposition brute du modèle n'est **jamais** montrée telle quelle
(risque du lot) : elle est corrigée aux mêmes règles que le contrôle de légalité — possession, 4
exemplaires par nom, au moins un Pokémon de base, taille exacte — chaque correction étant **tracée**,
et la légalité finale est **recalculée côté serveur** (source unique), jamais devinée.

## Livrables

**API** — `POST /me/decks/{deck_id}/propose` (borné au propriétaire, 404 sinon ; CSRF requis) :
- `pbm_api.decks.ai_builder` — le domaine du lot, deux moitiés nettes :
  - **fonctions pures** (testables sans base) : `build_prompt` (liste NUMÉROTÉE des candidats, le
    modèle choisit par `ref`, jamais par UUID ni nom libre → impossible d'inventer une carte hors
    collection) et `reconcile` (applique et **trace** les corrections : `owned_cap`, `copy_cap`,
    `basic_pokemon_added`, `no_basic_pokemon_available`, `energy_fill`, `trimmed_oversize`,
    `must_include_added`, `unknown_ref`) ;
  - **orchestration** (`propose_deck`) : candidats = cartes **possédées ET en format** (+ Énergies
    de base du catalogue, D10), triées par pertinence et coupées à `MAX_CANDIDATES=150` (borne le
    coût jeton, coupe tracée) → **un** appel `provider.extract([], DeckProposal, …)` avec la clé de
    l'utilisateur → réconciliation → réécriture du deck → relecture de la légalité par
    `service.deck_detail`. Usage jeton enregistré (`ai.service.record_usage`).
- Schémas `ProposeDeckRequest` / `DeckProposalResponse` (deck relu + explications + trace des
  corrections + résumé + `provider`/`model`/`input_tokens`/`output_tokens`) dans `decks/schemas.py` ;
  erreurs `NoAiKeyForDeckError` (→ 409) et `EmptyCollectionError` (→ 409) dans `decks/errors.py`.
- Route dans `routers/decks.py`, fournisseur IA **injecté par dépendance** (`get_deck_ai_provider_factory`,
  comme `card_insights`) pour être remplacé par un double déterministe en test.

**Front** — `apps/web/src/app/jeu/decks/[id]/deck-ai-assistant.tsx` (`DeckAiAssistant`), intégré au
constructeur (`deck-builder-view.tsx`) : panneau « Assistant IA » avec chips de types, style, taille ;
sur succès il remonte `response.deck` au parent (`onProposed = setDeck` — **une seule** vérité de
légalité, côté serveur) et affiche le résumé, la trace des ajustements et l'explication par carte.
Client `proposeDeck` + types miroir dans `lib/api/decks.ts`.

**Outil** — `apps/api/scripts/measure_deck_ia_cost.py` : mesure le coût moyen d'une proposition
contre une VRAIE clé (hors chimera : compte de campagne, plafond 5 €) ; refuse d'agir sans
fournisseur par défaut plutôt que d'estimer un coût à zéro.

## Preuves (chimera, worktree `wt-v7-deck-ia`)

- **ruff** : `All checks passed!` sur tout `apps/api`.
- **pytest (base fraîche migrée `alembic upgrade head`, `TZ=Europe/Paris LANG=fr_FR.UTF-8`)** :
  - **16 tests neufs verts** — `test_deck_ai_builder.py` (9, réconciliation pure : complètement en
    Énergies, plafond 4, plafond possession, `ref` inconnu ignoré, ajout d'un Pokémon de base,
    absence signalée, `must_include`, élagage, prompt) + `test_deck_ai_routes.py` (7 : auth 401,
    deck inconnu 404, 409 sans clé, 409 collection vide, **deck légal complet à 60**, correction de
    surquantité remontée, **accès croisé B→404**) ;
  - **suite complète : `818 passed`** (dont tout le domaine decks). Les **5 seuls échecs** sont
    **environnementaux, sans rapport avec ce lot** : `test_catalogue_seed` (2) exige `pg_dump`,
    **absent de l'hôte WSL** (Postgres tourne en conteneur) ; `test_identity` (3) lancent un
    sous-processus `admin create-user` qui vise la base **par défaut** (`pbm_v1_auth`, non migrée
    localement) — ils **passent** dès qu'on pointe `DATABASE_URL` sur la base migrée (vérifié : les
    3 verts). En CI, `pg_dump` est présent et `DATABASE_URL` vise une base fraîchement migrée.
- **Test qui mord** : la route `POST …/propose` renvoyait 404 avant ce lot ;
  `test_propose_builds_a_legal_deck_from_owned_cards` échoue sans l'endpoint et passe avec.
- **web** : `eslint .` 0 problème ; `tsc --noEmit` propre ; `vitest run` → **162 passed** (dont
  `deck-ai-assistant.test.tsx` : types choisis transmis, deck remonté au parent, trace + explications
  affichées, message d'erreur API rendu ; et régression `deck-builder-view`) ; `next build` OK.
- **Isolation** : `test_propose_cross_access_is_forbidden` (l'utilisateur B reçoit 404 sur le deck de
  A) ; candidats et possession toujours calculés pour `user.id`, jamais un id du client.
- **Un seul appel IA** : le double compte `calls == 1` par proposition ; la réponse porte les jetons
  consommés (mesure du coût).
- **La CI GitHub Actions fait foi** : verte attendue sur `roadmap/v7-deck-ia` avant fusion.

## Écarts au plan

- **Maquette** : « sans objet » au prompt (l'assistant s'intègre à l'écran de construction). Le
  panneau réutilise les jetons de style du constructeur ; pas de nouvel écran autonome.
- **Faiblesses/résistances au prompt IA** : le contexte donne le type élémentaire, les PV, le stade
  et le **coût d'attaque le moins cher** de chaque carte, mais pas la table complète des
  faiblesses/résistances (elle gonflerait le prompt et son coût). La réconciliation, elle, garantit
  la légalité quelle que soit la finesse du choix du modèle.
- **Correction « aucun Pokémon de base possédé »** : non corrigeable sans inventer une carte hors
  collection — signalée honnêtement (`no_basic_pokemon_available`), le deck reste incomplet et le dit.

## Reste

- **Essai IA réel** : la campagne (UAT, ≤ 5 €, `measure_deck_ia_cost.py`) reste à passer avec une
  vraie clé pour chiffrer le coût moyen observé — hors chimera (aucune clé), comme prévu.
- **Livraison PROD** : manuelle, sur décision de JF (non déployé par ce lot).
