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
vérificateur a posteriori (`python -m pbm_game.rng verifier`).

Lot `j-journal-actions` : `pbm_game.journal`, le **journal d'actions** — une partie est un
état initial, une graine et un journal numéroté ; `appliquer(etat, action, rng)` produit
un nouvel état et des événements, `rejouer(partie)` reconstruit l'état en contrôlant une
empreinte à chaque coup, et la compaction (instantané + queue) évite de tout rejouer. Les
lots suivants y ajoutent les actions légales et la résolution.

Lot `j-actions-legales` : `pbm_game.actions`, le **générateur d'actions légales** —
`actions_legales(etat, joueur)` rend la liste exhaustive des coups jouables (étiquette +
cibles valides) et `valider(etat, action)` rend l'accord ou un refus motivé par une règle
citée. Une seule source de vérité : la liste ; la validation en vérifie l'appartenance. Les
familles dépendantes du catalogue (poser, évoluer, attacher, attaquer) ne sont pas
approximées (D9) — chaque lot de résolution enregistre la sienne dans `FAMILLES_DEFAUT`.

Lot `j-degats-resolution` : `pbm_game.combat`, la **résolution d'attaque** — vérification du
coût (`cout_satisfait` : colorés, incolores, énergies multi-unités, R-9.2) et calcul des
dégâts dans l'ordre strict du corpus (`resoudre_degats` : base, modificateurs, faiblesse ×2,
résistance −30, plancher, R-10.1). Les dégâts se posent en **compteurs** (`poser_degats` /
`poser_compteurs`), jamais en PV soustraits (R-10.4), et le **détail de calcul** lisible
(« 60 base, ×2 faiblesse, −30 résistance = 90 ») est produit et porté par le journal (R-10.9).
"""

__all__: list[str] = []
