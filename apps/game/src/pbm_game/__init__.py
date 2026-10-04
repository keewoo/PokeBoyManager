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

Lot `j-retraite-banc` : `pbm_game.banc`, le Pokémon Actif **change de place** (R-8) —
`battre_en_retraite` (volontaire : coût en énergies au choix, une fois par tour, interdit sous
Sommeil/Paralysie), `promouvoir` (obligatoire après un K.O., **banc vide = défaite** R-8.9) et
`echange_force` (provoqué par un effet, sans coût ni retraite consommée, autorisé sous état).
Les trois partagent le **passage au banc** (R-8.6) : le Pokémon qui descend perd ses états mais
garde énergies, Outil, compteurs et pile d'évolutions. Ce sont des transitions journalisées,
enregistrées dans le `REGISTRE` comme les autres.

Lot `j-checkup` : `pbm_game.checkup`, le **Pokémon Checkup** (R-12) — la phase entre les deux
tours, dans un ordre fixé : états de chaque Actif (Empoisonné, Brûlé, Endormi, Paralysé —
R-12.2), expiration journalisée des effets « jusqu'à la fin de ce tour » (R-12.5), puis les
K.O. qui en découlent hors attaque (R-12.4) — récompenses (R-13) et promotion demandée, banc
vide = défaite. `resoudre_checkup` est la phase de bout en bout ; la transition système
`checkup` la journalise. Les K.O. s'appuient sur les primitives partagées de `pbm_game.combat.ko`
(le code de K.O. ne vit pas que dans la résolution d'attaque).

Lot ``j-autorite-vues`` : ``pbm_game.sortie``, le **point de sortie unique** vers un client —
``projeter(etat, evenements, pour, jetonneur)`` compose la projection d'état (``vue``), les
**jetons opaques** des cartes cachées (``Jetonneur`` : non corrélables d'un mélange à l'autre) et
la **projection des événements** par destinataire (un type non projeté est refusé, jamais diffusé
brut). Rien de brut ne part vers un client en dehors de cette porte — ni l'API, ni le temps réel.

Lot ``j-initialisation`` : ``pbm_game.mise_en_place``, la **mise en place** d'une partie (R-4) —
mélange des deux decks et pioche de sept (R-4.1), boucle de **mulligan** (main sans base révélée,
remélangée, repiochée ; double mulligan sans carte bonus, R-4.4/R-4.6), **cartes bonus** dues à
l'adversaire (R-4.5), placement de l'Actif et du banc **face caché** (R-4.2) et **révélation
simultanée** (R-4.3 : six récompenses posées face cachée, puis le premier tour). Deux transitions
journalisées (``mise_en_place_initiale`` système, ``placer_mise_en_place`` par joueur) ; le
placement caché vit dans ``EtatPartie.mise_en_place`` et ne passe dans l'Actif/banc publics qu'à la
révélation — la projection ne laisse rien fuir à l'adversaire avant ce moment.
"""

from __future__ import annotations

# ``banc`` enregistre ses trois transitions de mouvement (retraite, promotion, échange forcé)
# dans le ``REGISTRE`` du journal **à son import**. On l'importe ici pour que ce soit toujours
# fait dès que ``pbm_game`` est chargé — sinon ``appliquer`` ignorerait ces actions. Le noyau des
# transitions ne peut pas le faire lui-même (cycle d'import : voir ``pbm_game.banc.mouvements``).
from . import banc as _banc  # noqa: F401  (import pour effet d'enregistrement)

# ``cartes`` enregistre de même ses transitions « poser » et « evoluer » (R-5.3, R-7) dans le
# ``REGISTRE`` à son import. On l'importe ici, après ``banc`` et ``checkup``, pour que
# ``appliquer`` les reconnaisse dès que ``pbm_game`` est chargé.
from . import cartes as _cartes  # noqa: F401,E402  (import pour effet d'enregistrement)

# ``checkup`` enregistre de même sa transition ``checkup`` (le Pokémon Checkup, R-12) dans le
# ``REGISTRE`` à son import. On l'importe ici, après ``banc``, pour que ``appliquer`` la
# reconnaisse dès que ``pbm_game`` est chargé.
from . import checkup as _checkup  # noqa: F401,E402  (import pour effet d'enregistrement)

# ``demandes`` (lot ``j-effets-choix``) enregistre ses transitions ``repondre_demande`` /
# ``expirer_demande`` dans le ``REGISTRE`` du journal à son import. On l'importe ici pour que
# ``appliquer`` les reconnaisse, et pour poser la garde « demande en cours » dès le chargement.
from . import demandes as _demandes  # noqa: F401,E402  (import pour effet d'enregistrement)

# ``fin_forcee`` (lot ``j-deconnexion-abandon``) enregistre les clôtures forcées ``deserter`` /
# ``expirer_inactivite`` dans le ``REGISTRE`` du journal à son import. Même motif : on l'importe ici
# pour que ``appliquer`` les reconnaisse dès que ``pbm_game`` est chargé.
from . import fin_forcee as _fin_forcee  # noqa: F401,E402  (import pour effet d'enregistrement)

# ``horloges`` (lot ``j-timer``) enregistre ses transitions d'expiration ``fin_tour`` /
# ``defaite_temps`` dans le ``REGISTRE`` du journal à son import. On l'importe ici pour que
# ``appliquer`` les reconnaisse (motif banc/cartes/demandes).
from . import horloges as _horloges  # noqa: F401,E402  (import pour effet d'enregistrement)

# ``mise_en_place`` (lot ``j-initialisation``) enregistre ses transitions ``mise_en_place_initiale``
# et ``placer_mise_en_place`` (R-4) dans le ``REGISTRE`` du journal à son import. On l'importe ici,
# après le noyau des transitions, pour que ``appliquer`` les reconnaisse dès que ``pbm_game`` est
# chargé (même motif que ``banc``, ``cartes`` et ``checkup``).
from . import (
    mise_en_place as _mise_en_place,  # noqa: F401,E402  (import pour effet d'enregistrement)
)

# Le résolveur DSL **sachant se suspendre** se branche dans le registre des résolveurs de décision
# (``demandes.moteur.REGISTRE_EFFETS``). On le fait ici — et pas dans le paquet ``demandes`` — pour
# que ``demandes`` ne dépende pas du DSL (le couplage va du moteur vers ses effets, pas l'inverse).
from .effets.dsl import interprete as _interprete  # noqa: E402

_demandes.enregistrer(_interprete.TYPE_EFFET_DSL, _interprete.resolveur_dsl_demandes)

# ``effets.objets`` enregistre la transition ``jouer_objet`` dans le ``REGISTRE`` du journal à son
# import (lot ``j-cartes-objets``). Même motif que ``banc`` : on l'importe ici, après le DSL, pour
# que ``appliquer`` la reconnaisse (la transition tire le DSL en local à l'usage).
from .effets import objets as _objets  # noqa: E402,F401  (import pour effet d'enregistrement)

__all__: list[str] = []
