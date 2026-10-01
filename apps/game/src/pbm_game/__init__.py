"""`pbm_game` — moteur de jeu PokeBoyManager.

Fonctions pures, état sérialisable, **aucune** entrée/sortie : le moteur ne connaît
ni HTTP, ni base de données, ni React. C'est ce qui permet de le tester par milliers
de cas et de le faire jouer par des bots.

Premier module livré par le lot `j-regles-reference` : `pbm_game.regles`, qui vérifie
la cohérence du corpus de règles de référence (`docs/jeu/REGLES.md`) avec sa table de
cas (`docs/jeu/cas-de-regles.yaml`).

Lot `j-modele-etat` : `pbm_game.state`, l'état d'une partie — zones, attachements,
compteurs, projection par joueur (`vue`), sérialisation JSON bidirectionnelle et
invariants vérifiables.

Lot `j-aleatoire-determinisme` : `pbm_game.rng`, l'aléatoire **reproductible, vérifiable
et journalisé** — flux nommés indépendants, engagement-révélation (commit-reveal) et un
vérificateur a posteriori (`python -m pbm_game.rng verifier`). Les lots suivants y
ajoutent le journal d'actions et la résolution.
"""

__all__: list[str] = []
