"""`pbm_api.games` — service de parties de jeu (lot `j-partie-service`).

L'enveloppe de persistance et d'orchestration autour du moteur pur `pbm_game` : créer une partie à
partir de deux decks résolus en scripts, appliquer un coup dans une transaction idempotente,
reprendre une partie après un redémarrage, expirer les parties abandonnées et purger les mortes.

* :mod:`~pbm_api.games.construction` — résolution d'un deck en scripts et état initial ;
* :mod:`~pbm_api.games.service` — création, boucle d'application, reprise, expiration, purge ;
* :mod:`~pbm_api.games.errors` — les erreurs du service (chacune dit pourquoi).
"""
