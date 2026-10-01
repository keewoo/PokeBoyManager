# apps/game — moteur de jeu `pbm_game`

Le moteur du jeu PokeBoyManager. **Fonctions pures, état sérialisable, aucune entrée/sortie** :
il ne connaît ni HTTP, ni base de données, ni React. C'est ce qui permet de le tester par
milliers de cas et de le faire jouer par des bots.

La référence des règles vit **hors du paquet**, dans le dépôt : [`docs/jeu/REGLES.md`](../../docs/jeu/REGLES.md)
(règles numérotées `R-x.y`) et [`docs/jeu/cas-de-regles.yaml`](../../docs/jeu/cas-de-regles.yaml)
(table de cas qui nomme, pour chacun, la règle qu'il vérifie). Tout test de règle cite son `R-x.y`.

## Commandes

```bash
cd apps/game
uv sync --locked          # installe pytest, ruff, pyyaml (Python 3.12)
uv run ruff check .
uv run pytest -q
```

La CI (`.github/workflows/ci.yml`, job `game`) exécute exactement ces trois commandes.
Le moteur n'a besoin **ni de base, ni de Docker**.

## État

| Lot | Apport |
|---|---|
| `j-regles-reference` | `pbm_game.regles` : corpus de règles + table de cas, et leur vérification de cohérence. |

Lots suivants (voir `docs/roadmap/jeu/BACKLOG-JEU.md`) : `j-modele-etat` (état de partie),
`j-aleatoire-determinisme`, `j-journal-actions`, `j-actions-legales`, `j-machine-tour`,
`j-degats-resolution`, `j-ko-recompenses`, `j-retraite-banc`, `j-etats-speciaux`, `j-checkup`.
