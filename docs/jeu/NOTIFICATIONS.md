# Notifications du jeu — prévenir sans harceler

> Lot `j-notifications-jeu` (jalon J4). **À ouvrir quand** : un joueur dit qu'il n'a rien reçu, on
> ajoute un genre de notification, on branche la PWA, ou on se demande pourquoi un e-mail
> d'invitation n'est pas parti.

Un jeu à deux où personne ne sait que l'autre attend ne se joue pas. Mais le défaut inverse coûte
plus cher : un jeu qui sonne à chaque coup se fait couper **au niveau du système** — et on perd
alors *aussi* les invitations, les seules notifications qui comptaient vraiment. Tout ce qui suit
découle de cette asymétrie.

## Le vocabulaire : six genres, et un seul relais e-mail

| Genre | Quand | Plafond par partie | E-mail |
|---|---|---|---|
| `invitation_recue` | quelqu'un vous invite (`j-invitations`) | — (pas de partie) | **oui** |
| `adversaire_trouve` | la file vous a apparié (`j-file-attente`) | 1 | non |
| `ton_tour` | le tour change de main | 4 | non |
| `temps_bientot_ecoule` | votre budget passe sous 60 s (`j-timer`) | 3 | non |
| `adversaire_revenu` | le joueur déconnecté est de retour | 2 | non |
| `partie_forfait` | abandon (R-14.3) ou désertion (R-14.6) | 1 | non |

Le vocabulaire est figé dans `pbm_api.models.notifications` (`NOTIF_GENRES`) ; un genre hors de cet
ensemble n'est **jamais écrit** — les règles lèvent `GenreInconnu` plutôt que d'enregistrer une
ligne dont l'écran ne saurait pas fabriquer la phrase.

**Seule l'invitation part par e-mail**, et c'est un choix : elle peut attendre des heures, donc elle
mérite un canal asynchrone. « C'est ton tour » par e-mail serait du harcèlement par un autre moyen.

## Les trois freins, du plus doux au plus dur

Ils se cumulent, et c'est volontaire — le premier fait le travail au quotidien, le dernier tient la
garantie.

1. **L'anti-doublon.** On ne redit pas « c'est ton tour » tant que la précédente n'a pas été lue.
   En pratique c'est lui qui évite la sonnerie : un joueur devant son écran reçoit une notification
   par absence, pas une par coup.
2. **Le plafond par genre et par partie** (tableau ci-dessus). Même lues, les répétitions
   s'épuisent.
3. **Le plafond global de la partie** : `PLAFOND_PAR_PARTIE = 10`, tous genres confondus, par
   destinataire. Il est **inférieur à la somme** des plafonds par genre (11) : c'est lui qui mord en
   dernier, et il mord toujours — y compris si un genre futur oubliait son propre plafond. Un test
   tient cet invariant (`test_somme_des_plafonds_par_genre_depasse_le_plafond_global`).

Les plafonds sont **par partie** : une partie saturée n'empêche pas la suivante de notifier.

## Le silence nocturne : enregistrer sans réveiller

Actif **par défaut**, 21 h → 7 h, à l'heure locale du joueur (`fuseau`, défaut `Europe/Paris`). Le
jeu est celui d'un enfant de onze ans : mieux vaut avoir à demander « réveille-moi » que d'avoir
été réveillé.

Pendant la fenêtre, la notification est **enregistrée** (marquée `silencieuse`) mais **aucun relais
hors application ne part** et l'écran ne la sonne pas. C'est la lecture retenue du critère « le
silence nocturne est respecté, y compris pour les invitations » : rien n'est perdu — l'invitation
reste dans `GET /invitations/recues`, et sa notification se lit au réveil ; ce qui n'arrive pas,
c'est le réveil.

Deux détails de bord, chacun gardé par un test :

- la fenêtre est `[debut, fin[` et **peut franchir minuit** (c'est le cas par défaut) ;
- `debut == fin` vaut **fenêtre vide**, jamais silence de 24 h : désactiver les notifications se
  fait par `genres_desactives`, pas par un réglage d'horaire détourné.

## Où vit quoi

| Fichier | Rôle |
|---|---|
| `apps/api/src/pbm_api/notifications/regles.py` | **pur** : faut-il notifier, en silence, par quels canaux. Aucune base, aucune horloge implicite |
| `apps/api/src/pbm_api/notifications/service.py` | la persistance, les compteurs de plafond, la lecture, les réglages |
| `apps/api/src/pbm_api/notifications/relais.py` | ce qui sort du processus : e-mail (branché), notification web (nommée absente) |
| `apps/api/src/pbm_api/routers/notifications.py` | `/jeu/notifications` — lire, marquer lu, régler |
| `apps/api/src/pbm_api/models/notifications.py` | `game_notifications`, `notification_reglages`, le vocabulaire des genres |
| `apps/web/src/lib/api/notifications.ts` | le client, et **les phrases** (le serveur ne stocke pas de texte) |
| `apps/web/src/app/jeu/notifications/` | l'écran : les reçues, et les réglages |

Les règles sont séparées du service pour une raison pratique : on peut se placer à 23 h un mardi
sans attendre 23 h, et vérifier un plafond sans Postgres. C'est ce qui rend les trois critères du
lot testables (`apps/api/tests/test_jeu_notifications_regles.py`).

## Les points d'accroche dans le jeu

| Genre | Émis depuis |
|---|---|
| `invitation_recue` | `pbm_api.games.invitations.inviter_par_pseudo` |
| `adversaire_trouve` | `pbm_api.games.matchmaking.apparier` (hors du verrou d'appariement) |
| `ton_tour`, `temps_bientot_ecoule`, `partie_forfait` | `pbm_api.games.service._notifier_apres_coup` |
| `adversaire_revenu` | `pbm_api.games.service.marquer_reconnexion` |

Trois règles tenues à ces accroches :

- **avant le commit du coup** : la notification partage le sort de ce qui l'a provoquée — on ne
  prévient pas « c'est ton tour » pour un coup que la transaction finira par annuler ;
- **jamais au prix d'un coup** : les accroches passent par `notifier_sans_casser`, qui journalise
  l'échec avec sa pile (`logger.exception`) et laisse le coup s'appliquer. Ce n'est pas un
  `except: pass` — la trace est nominative et complète, et aucun chemin ne rend la perte normale ;
- **rien en mode solo** (`game.entrainement`) : l'adversaire est un bot, il n'y a personne à
  prévenir.

Le destinataire est résolu via `game_players` (`_user_du_joueur`), pas par `uuid.UUID(joueur)` :
les tests de plumberie du moteur fabriquent des parties aux joueurs nommés `"A"`/`"B"`, et une
conversion à l'aveugle lèverait au milieu du chemin d'un coup.

## Ce qui n'est pas branché, et ce qui ne le sera pas

**La notification web (PWA) n'a pas de transport** : le lot `v6-pwa` n'est pas livré. La décision
d'envoyer est pourtant bien prise (réglage `relais_push`, silence nocturne, plafonds) ;
`relais.relayer_par_push` **le dit** à chaque tentative (un INFO qui nomme le lot manquant) plutôt
que de l'ignorer. Le jour où `v6-pwa` arrive, brancher le transport dans ce module est la seule
chose à faire.

**Aucune route n'émet de notification**, et c'est une garde de conception, pas un oubli — un test la
tient (`test_aucune_route_nemet_de_notification`). Si une telle route existait, n'importe quel
client pourrait se fabriquer une sonnerie, ou en fabriquer une à l'autre en contournant ses
réglages et les plafonds. Les notifications naissent d'un événement du jeu, point.

## Diagnostiquer « je n'ai rien reçu »

Un refus n'est **jamais muet** : `notifier` journalise le motif rendu par les règles. Dans l'ordre
des causes possibles :

1. le genre est **coupé** par le joueur (`notification_reglages.genres_desactives`) ;
2. une notification du même genre sur la même partie **attend d'être lue** (anti-doublon) ;
3. le **plafond du genre** ou celui de la partie est atteint ;
4. c'était le **silence nocturne** : la notification existe (`silencieuse = true`), seul le relais
   n'est pas parti ;
5. pour un e-mail : `SMTP_HOST` vide → `DisabledEmailSender` journalise l'envoi non fait
   (configuration tracée, pas un repli muet — voir `docs/PLUGINS.md`).

Le motif exact est dans le journal du serveur, à la ligne
`notification « <genre> » non émise (destinataire …) : <motif>`.

## Ajouter un genre

1. la constante et son entrée dans `NOTIF_GENRES` (`models/notifications.py`) ;
2. son plafond dans `PLAFOND_PAR_GENRE` (`notifications/regles.py`) — sans quoi seul le plafond
   global le borne, ce qui reste sûr mais imprécis ;
3. sa phrase dans `phraseNotification` et son libellé dans `LIBELLES_GENRE`
   (`apps/web/src/lib/api/notifications.ts`) ;
4. son point d'accroche dans le jeu.

Aucune migration n'est nécessaire : les genres sont des chaînes, et `genres_desactives` est une
liste JSON — c'est précisément pourquoi ce n'est pas une colonne par genre.
