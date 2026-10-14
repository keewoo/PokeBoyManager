"""Observabilité du jeu (lot ``j-observabilite-jeu``) — voir ce qui se passe, sans SSH.

Quatre pièces, séparées pour que la partie qui *décide* reste testable sans base :

* :mod:`pbm_api.observabilite.motifs` — normalise le motif d'un incident (**pur**) ;
* :mod:`pbm_api.observabilite.consignation` — écrit l'incident en base, hors de la transaction
  de l'appelant (un refus ne doit pas disparaître avec le rollback du coup refusé) ;
* :mod:`pbm_api.observabilite.releve` et :mod:`pbm_api.observabilite.metriques` — la forme du
  relevé (**pure**) et sa lecture en base ;
* :mod:`pbm_api.observabilite.regles` et :mod:`pbm_api.observabilite.rapport` — les seuils
  d'alerte et la mise en forme des messages (**purs** tous les deux).

La sonde ``apps/api/scripts/sonde_jeu.py`` assemble les quatre ; la route ``GET /jeu/metriques``
en expose le relevé et le verdict.
"""
