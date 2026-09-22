# Compte rendu — `v7-decks-legalite`

## Résumé
Extension du contrôle de légalité des decks livré par `v7-decks-api`, en gardant **une seule
implémentation** (`pbm_api.decks.legality.evaluate`) exposée par l'API et destinée à l'écran —
jamais deux logiques qui divergent (risque du lot). Quatre apports : **sévérité** de chaque
constat (`bloquant` / `avertissement`), **au moins un Pokémon de base**, **légalité par format**
(Standard / Étendu / Illimité, choisi par le joueur) et **exclusion des contrefaçons** du
décompte de possession.

## Livrables
- `pbm_api.decks.formats` (nouveau) : les trois formats, leurs libellés, `card_in_format`
  (légalité inconnue = autorisée, bénéfice du doute ; Énergie de base toujours autorisée).
- `pbm_api.decks.legality` (étendu) : `LegalityIssue.severity`, `is_basic_pokemon`, constats
  `no_basic_pokemon` / `out_of_format` / `counterfeit_excluded`, `DeckLegality.format` +
  `format_label` ; `legal` = aucun constat bloquant.
- `pbm_api.decks.service` : possession et contrefaçons séparées en une requête
  (`_owned_counts` → deux dicts), `Deck.format` propagé (création, copie), `update_deck`
  (renommer et/ou changer de format, partiel).
- Routes : `PATCH /me/decks/{id}` accepte `name` et/ou `format` (`UpdateDeckRequest`) ;
  `DeckCardOut`/`DeckLegalityOut`/`DeckSummary`/`DeckDetail` portent les nouveaux champs.
- Modèles : `Card.stage` (TCGdex `stage`, alimenté à l'import), `Deck.format`
  (défaut `standard`). Migration `a4e9c1d7b3f5` (chaînée sur `d1c7a3f0b2e4`).
- Point d'extension `v7-regles-cartes` conservé et neutre (`unsupported_card_ids` → ensemble
  vide) : report explicite, pas un repli silencieux.

## Preuves
- `tests/test_deck_legality.py` : **33 cas purs** (logique testable sans base), dont les pièges
  exigés — 5ᵉ exemplaire d'un même nom sous deux illustrations (`card_id` distincts), Énergie
  spéciale non possédée, deck sans Pokémon de base, carte contrefaite (exclue → `not_owned`).
- `tests/test_deck_routes.py` : **15 cas** API — format choisi + carte hors format puis bascule
  Illimité, contrefaçon exclue (avertissement) entraînant un `not_owned` (bloquant), sévérités
  dans la réponse, format invalide → 422, accès croisé B→404 sur toutes les routes, revalidation
  après vente, CSRF.
- `uv run pytest` : **48 tests decks passent** ; suite API complète **659 passed** (hors les 2
  tests `test_catalogue_seed.py` qui échouent sur `pg_dump: command not found` — client
  PostgreSQL absent du WSL de chimera, **échec strictement environnemental**, vérifié identique
  sur `github/main` non modifié ; la CI GitHub provisionne postgresql-client).
- `uv run ruff check .` : propre.
- Migration : `alembic upgrade head` → `a4e9c1d7b3f5 (head)`, colonnes `cards.stage` et
  `decks.format` présentes.

## Écarts au plan
- **Règle ajoutée qui change des tests de `v7-decks-api`** : « au moins un Pokémon de base » rend
  un deck de 60 Énergies de base **illégal** (il l'était déjà dans les règles réelles du jeu,
  mais `v7-decks-api` n'avait volontairement câblé que 60/4/possession). Les cas de
  `test_deck_legality.py`/`test_deck_routes.py` qui supposaient un deck 100 % énergies « légal »
  ont été adaptés (ajout d'un Pokémon de base) — c'est un renforcement, pas un affaiblissement.
- **Sévérités** : les six constats de règle sont `bloquant` ; seul `counterfeit_excluded` est un
  `avertissement`. C'est le seul constat purement informatif du périmètre (il explique un
  décompte, il n'interdit rien par lui-même).
- **Client TypeScript généré** (`packages/api-client`) non régénéré : la CI ne le régénère ni ne
  le vérifie (`gen:api` absent du workflow), et ce lot est back-end seul — les nouveaux champs
  seront tirés par `v7-decks-ui`. Aucune régression front (types en sur-ensemble).

## Reste à faire (hors périmètre)
- `v7-decks-ui` (couloir CH5) : constructeur affichant sévérités, formats et badges (Pokémon de
  base, hors format, contrefaçon exclue).
- `v7-regles-cartes` : activera `unsupported_card_ids` en remplaçant son corps par un appel au
  moteur (aucun autre changement).
