# Horloges d'une partie — `j-timer`

Trois horloges, décision **DJ4** : **par tour** (90 s), **par joueur** sur toute la partie (25 min,
plafond dur), **par décision** (30 s, y compris quand c'est l'adversaire qui doit trancher). Plus
deux marges : **tolérance réseau** (10 s — la latence ne fait pas perdre un tour) et **pause de
déconnexion** (120 s de grâce pendant lesquelles les horloges sont gelées).

## Principe : une donnée, pas un minuteur

Une horloge codée en *minuteur vivant* meurt au redéploiement et fait perdre des parties. Ici,
l'horloge est un **état sérialisable** calculé **à partir d'horodatages** : on relit l'état, on
redonne l'instant courant, on obtient le temps restant. Elle survit donc au F5, au redémarrage de
l'API et à la reprise de journal.

- **Moteur pur** — `pbm_game.horloges` (`modele` : `ConfigHorloges`, `EtatHorloges`, `CompteurActif` ;
  `calcul` : `demarrer`, `restant`, `basculer`, `poser_decision`/`lever_decision`, `pause`/`reprendre`,
  `premiere_echeance`). Aucune E/S, aucune horloge système : le temps entre **par paramètre**
  (`maintenant`, secondes depuis l'époque). Un test statique interdit `import time`/`datetime`.
- **Où elle vit** — colonne **`games.horloges`** (JSONB), pas dans `EtatPartie` : le contrat
  empreinte/rejeu du journal reste intact, et la config de chaque partie est **figée à sa création**
  (changer les durées côté serveur — `settings.horloge_*`, variables d'environnement — ne touche pas
  une partie en vol, et aucune durée n'est codée en dur dans le moteur).
- **Un seul compteur tourne à la fois** : le tour du joueur actif, **ou** une décision en attente.
  Toute bascule débite le temps écoulé du **budget total** du joueur qui comptait (plafond dur).

## Expiration = toujours un coup journalisé, jamais un blocage

`premiere_echeance` donne la première échéance atteinte (`tour` / `decision` / `budget`, le budget
primant). L'adaptateur `pbm_api.games.horloges.action_par_defaut` la traduit en l'une des trois
actions par défaut de DJ4, toutes **système**, journalisées comme les autres coups :

| Cause | Action par défaut | Effet |
|---|---|---|
| décision | `expirer_demande` (moteur `demandes`) | **réponse par défaut** de la demande (premier choix valide / abandon) |
| tour | `fin_tour` *(nouveau)* | **termine le tour** (entrée en Checkup), sans déclarer d'attaque |
| budget | `defaite_temps` *(nouveau)* | **défaite au temps** (`RAISON_TEMPS_ECOULE`), l'adversaire gagne |

`fin_tour` et `defaite_temps` sont des transitions journal qui s'enregistrent à l'import de
`pbm_game.horloges` (motif banc/cartes/demandes). `defaite_temps` est permise même pendant une
demande (comme l'abandon) : un budget peut s'épuiser pendant que l'adversaire décide.

Le service applique l'expiration sous verrou (`expirer_horloge`), appelée au gré des
synchronisations (`GET /games/{id}/sync`) et des battements de cœur du canal temps réel — un jeu en
direct n'a donc pas besoin d'un ordonnanceur pour avancer.

## Pause de déconnexion

À la fermeture du WebSocket, `marquer_deconnexion` **gèle** les horloges (le temps ne court plus) ;
à la reconnexion, `marquer_reconnexion` reprend **là où elles s'étaient gelées** (la pause ne
consomme rien). Au-delà de la grâce (120 s), le balayage d'expiration reprend les horloges
(l'abandon pour déconnexion prolongée est le lot `j-deconnexion-abandon`). L'affichage est honnête
des deux côtés (« l'adversaire s'est déconnecté, 1 min 47 ») via `pause_restant_s`.

## Affichage à moins de deux secondes

Le serveur renvoie, dans chaque charge temps réel (`resync`, événement, `GET /games/{id}/state`), le
temps restant **vérité serveur** et l'instant serveur du calcul (`restant`). Le client
(`apps/web/src/lib/game/horloges.ts`, `estimerHorloges`) n'en fait qu'une **estimation** locale
entre deux messages, **recalée** sur la valeur serveur à chaque événement : aucun compteur ne court
librement en accumulant de la dérive, ce qui garde l'écran à moins de deux secondes de la vérité
serveur. L'horloge courte peut descendre légèrement sous zéro dans la tolérance réseau (affichage
honnête du dépassement) ; le budget reste ≥ 0.

> Le plateau de jeu (où ces horloges s'affichent réellement) n'existe pas encore : ce lot livre le
> **moteur de temps**, son autorité serveur et l'estimateur client. Le branchement visuel suit avec
> le lot d'écran de partie.
