"""Notifications du jeu (lot `j-notifications-jeu`) : les règles, le canal, les relais.

Trois modules, une seule responsabilité chacune — c'est ce qui rend les critères du lot
vérifiables sans base de données :

* :mod:`pbm_api.notifications.regles` — **pur** : faut-il notifier, en silence, par quels canaux ;
* :mod:`pbm_api.notifications.service` — la persistance, les compteurs de plafond, la lecture ;
* :mod:`pbm_api.notifications.relais` — ce qui sort du processus (e-mail branché, PWA nommée
  absente tant que `v6-pwa` n'est pas livré).
"""
