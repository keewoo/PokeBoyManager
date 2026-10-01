"""`pbm_game.cas` — format de **cas de règles** exécutables, exécuteur et couverture.

Paquet **pur** (aucune E/S, ni HTTP, ni base, ni React) livré par le lot ``j-tests-regles``. Un
moteur de règles se **prouve** : cette batterie est ce qui permet de modifier le moteur sans tout
casser en silence. Un cas est une **donnée** — un état de départ, une action (ou un appel de
fonction), un résultat attendu, et la règle ``R-x.y`` qu'il vérifie — qu'un humain lit et écrit
**sans toucher au code du moteur**. Les cas vivent dans ``docs/jeu/cas-executables/*.yaml`` ;
leur format est documenté dans ``docs/jeu/CAS-EXECUTABLES.md``.

* :mod:`~pbm_game.cas.constructeur` — ``construire(spec)`` : une description concise d'un état →
  un :class:`~pbm_game.state.EtatPartie` réel + sa table ``fiches`` (PV/récompenses, D9) ;
  ``trouver_graine`` : une graine qui produit des pile ou face voulus (cas déterministes) ;
* :mod:`~pbm_game.cas.executeur` — ``executer(cas)`` : rejoue un cas contre le moteur et
  **vérifie** l'attendu, ou lève :class:`EchecCas` ;
* :mod:`~pbm_game.cas.couverture` — ``rapport(...)`` : quelles règles ont un cas, lesquelles n'en
  ont aucun (la garde CI), et le contrôle des exceptions justifiées.
"""

from __future__ import annotations

from .constructeur import GRAINE_DEFAUT, JOUEURS_DEFAUT, construire, trouver_graine
from .couverture import RapportCouverture, rapport, regles_couvertes, regles_d_un_cas
from .executeur import OPERATIONS, EchecCas, executer

__all__ = [
    "JOUEURS_DEFAUT",
    "GRAINE_DEFAUT",
    "construire",
    "trouver_graine",
    "executer",
    "EchecCas",
    "OPERATIONS",
    "regles_d_un_cas",
    "regles_couvertes",
    "RapportCouverture",
    "rapport",
]
