"""`pbm_sim` — bots de simulation et campagnes de masse pour débusquer les blocages du moteur.

**Outillage**, pas moteur : ce paquet vit à côté du moteur pur ``pbm_game`` (dans le même ``src``
pour que les tests l'importent), mais il n'en fait **pas** partie — il a le droit de lire des
fichiers, d'ouvrir des processus et de tirer de l'aléatoire (``random``) — interdit au moteur.
Le moteur ne l'importe jamais ; c'est l'inverse. Il n'est pas empaqueté dans le *wheel* du moteur.

Ce qu'il apporte (lot ``j-simulation-bots``) :

* :mod:`pbm_sim.bots` — deux bots qui décident sur la **seule vue joueur** : un aléatoire, un
  heuristique ;
* :mod:`pbm_sim.decks` — un roster de decks synthétiques **entièrement jouables** (D9) et le
  :class:`~pbm_sim.decks.Scenario` qu'une graine détermine de bout en bout ;
* :mod:`pbm_sim.orchestrateur` — :func:`~pbm_sim.orchestrateur.jouer_partie`, qui joue une partie
  et range toute défaillance dans une :class:`~pbm_sim.orchestrateur.Anomalie` nommée ;
* :mod:`pbm_sim.campagne` — :func:`~pbm_sim.campagne.campagne`, des milliers de parties en
  parallèle, et la distribution des durées ;
* :mod:`pbm_sim.rapport` — la mise en forme lisible d'une campagne ;
* ``python -m pbm_sim`` — la ligne de commande : lancer une campagne, reproduire une anomalie.
"""

from __future__ import annotations

from .orchestrateur import Anomalie, ResultatPartie, jouer_partie

__all__ = ["Anomalie", "ResultatPartie", "jouer_partie"]
