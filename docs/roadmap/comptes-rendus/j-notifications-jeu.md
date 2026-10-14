# Compte rendu — `j-notifications-jeu`

**Être prévenu : invitation reçue, c'est ton tour, partie reprise.** P2 · piste Compte &
progression · jalon J4 · palier 12 · taille S. Session autonome pilotée depuis **devAI**, travail
exécuté sur **chimera** (WSL Ubuntu-24.04), worktree `~/dev/wt-j-notifications-jeu`, branche
`roadmap/j-notifications-jeu` depuis `github/main` (`abec21c`).

Garde-fou d'ordre : `suivi.py verifier j-notifications-jeu` → **code 0** (« ordre tenu »).

## Résumé

Le jeu savait déjà tout ce qu'il fallait dire ; il ne le disait à personne. Ce lot pose le canal de
notification dans l'application, ses réglages, et surtout les **freins** — parce que le vrai risque
de ce lot n'est pas de ne pas prévenir, c'est de prévenir trop.

Trois décisions ont structuré le code, et chacune est défendue par un test.

1. **Le silence nocturne enregistre, il ne refuse pas.** Le critère disait « respecté, y compris
   pour les invitations ». La lecture facile aurait été « on ne notifie pas » — et une invitation
   reçue à 23 h aurait disparu. La lecture retenue : la notification est écrite et marquée
   `silencieuse`, seuls les **relais hors application** sont retenus. Rien n'est perdu (elle se lit
   au réveil, et l'invitation reste dans `GET /invitations/recues`), personne n'est réveillé.
   L'écran le dit explicitement sur la ligne concernée — sans cette mention, un joueur prendrait
   son propre réglage pour une panne.

2. **L'e-mail d'invitation a dû quitter `games/invitations.py`.** Il y partait **en dur**, et aucun
   réglage ne pouvait l'arrêter : le critère était contournable par construction, pas par oubli.
   Il vit maintenant derrière la décision du canal (`notifications/relais.py`). Conséquence
   assumée : deux tests existants qui affirmaient « e-mail parti » devenaient **dépendants de
   l'heure de la CI** (silence actif par défaut, 21 h → 7 h). Ils ont été rendus déterministes —
   instant fixé en pleine journée pour le test de service, silence coupé explicitement pour le test
   de route — avec le motif en commentaire. Les laisser tels quels aurait produit une suite qui
   mentait une nuit sur deux.

3. **Trois freins cumulés, et le dernier est une garantie structurelle.** L'anti-doublon (on ne
   redit pas « c'est ton tour » si la précédente n'est pas lue) fait le travail au quotidien ; les
   plafonds par genre épuisent les répétitions ; le plafond global de la partie (**10**) est
   délibérément **inférieur à la somme** des plafonds par genre (11), donc il mord toujours — y
   compris si un genre futur oubliait le sien. Un test tient cet invariant, un autre simule une
   partie bavarde (tous les genres, cent tours, tout lu immédiatement) et exige que le total ne
   dépasse jamais 10.

Un quatrième point, trouvé en route : le destinataire d'une notification de partie ne peut pas être
déduit par `uuid.UUID(etat.tour.joueur_actif)`. Les tests de plumberie du moteur fabriquent des
parties aux joueurs nommés `"A"`/`"B"` : la conversion aurait levé **au milieu du chemin d'un
coup**. La résolution passe par `game_players` (`_user_du_joueur`), avec un test de parité qui tient
la convention `joueur_id_de == str(user_id)` — si elle changeait, les notifications de partie
disparaîtraient en silence.

## Livrables

- **Modèles** `apps/api/src/pbm_api/models/notifications.py` : `game_notifications` (CASCADE sur la
  partie — « c'est ton tour » sur une partie purgée serait un mensonge, pas une archive) et
  `notification_reglages` (une ligne par compte, **créée à la première modification** ; son absence
  vaut les défauts du code). Migration `d8e5a3c6b2f1` ; **tête alembic unique** après fusion dans la
  branche.
- **Règles pures** `notifications/regles.py` : `Reglages`, `Compteurs`, `Decision`, `decider`,
  `dans_silence_nocturne`. Aucune base, aucun réseau, aucune horloge implicite. Chaque décision —
  refus **comme** acceptation — porte son `motif`.
- **Canal** `notifications/service.py` : compteurs de plafond en SQL, émission, lecture, réglages
  partiels. `notifier_sans_casser` pour les accroches dans le chemin d'un coup.
- **Relais** `notifications/relais.py` : e-mail branché (invitation seule), notification web **nommée
  absente** tant que `v6-pwa` n'est pas livré — un INFO par tentative, jamais un silence.
- **Routes** `/jeu/notifications` : lister (filtre `non_lues`), marquer une lue, tout marquer lu,
  lire et modifier les réglages. Toutes gardées par `require_game_access` (D11), écritures sous CSRF.
- **Câblage** : invitation par pseudo, appariement (hors du verrou), changement de tour + alerte de
  temps + fin par forfait, retour d'un adversaire.
- **Front** : client `lib/api/notifications.ts` (et **les phrases** — le serveur ne stocke pas de
  texte), écran `/jeu/notifications` (reçues + réglages + plafonds affichés), lien depuis le salon,
  badge des non lues sur l'entrée « Jouer ».
- **Doc** : `docs/jeu/NOTIFICATIONS.md` (fiche complète, dont « diagnostiquer *je n'ai rien reçu* »
  et « ajouter un genre ») ; une ligne dans la carte des fiches de `CLAUDE.md`.

## Preuves

| Vérification | Résultat |
|---|---|
| `uv run ruff check .` (apps/api) | **All checks passed** |
| `uv run alembic upgrade head` | joue jusqu'à `d8e5a3c6b2f1` ; `alembic heads` → **une seule tête** |
| Tests du lot (3 fichiers) | **53 passés** — `test_jeu_notifications_regles.py` (31, purs), `_routes.py` (12), `_cablage.py` (10) |
| Non-régressions ciblées | **82 passés** — invitations (service + routes), matchmaking, parties (service, routes, déconnexion/abandon, horloges, mode solo, fin d'UI), isolation croisée, accès au jeu |
| `pnpm --filter @pbm/web lint` | 0 erreur (1 *warning* préexistant, `game-realtime.test.ts`) |
| `pnpm --filter @pbm/web type-check` | **tsc --noEmit** sans erreur |
| Tests front du lot | **16 passés** (`notifications-view.test.tsx`) ; `salon-view.test.tsx` (fichier modifié) **8 passés** |
| CI GitHub Actions | verte sur le commit poussé — **c'est elle qui fait foi** |

Les trois critères d'acceptation, et où ils se prouvent :

- *chaque type désactivable séparément* → `test_genre_desactive_seul` (paramétré sur **tous** les
  genres), `test_desactiver_un_genre_nen_desactive_pas_un_autre`,
  `test_invitation_genre_coupe_nenregistre_rien_et_nenvoie_rien`, et côté écran
  « offre un interrupteur par type, et ne coupe que celui-là » ;
- *silence nocturne respecté, y compris pour les invitations* →
  `test_silence_nocturne_sapplique_a_linvitation`, `test_aucun_genre_nechappe_au_silence`,
  `test_invitation_de_nuit_enregistree_mais_sans_email` (en base, chemin réel d'invitation), plus
  les cas de bord : franchit minuit, bornes `[debut, fin[`, fenêtre vide, **fuseau du joueur** ;
- *aucune partie au-delà du plafond* → `test_plafond_global_borne_la_partie_quoi_quil_arrive`
  (simulation pure), `test_plafond_dune_partie_tient_en_base` (compté en SQL),
  `test_somme_des_plafonds_par_genre_depasse_le_plafond_global` (l'invariant de conception).

## Écarts au plan

- **La notification web (PWA) n'a pas de transport.** C'est conforme à la mission (« quand elle
  existe, sans en dépendre ») : le réglage `relais_push` est respecté dès maintenant et la décision
  est prise, mais `v6-pwa` n'est pas livré — `relayer_par_push` journalise l'absence à chaque
  tentative au lieu de la taire. Un seul endroit à brancher le jour venu.
- **« Il te reste une minute » est évalué au changement de tour, pas par un minuteur.** Il n'existe
  aucun ordonnanceur côté serveur pour le jeu ; la mesure se fait sur le budget restant à l'instant
  où le tour change de main. Un joueur qui laisse filer son horloge sans jouer n'est donc pas
  prévenu une seconde fois — c'est `j-timer` qui tranche alors (défaite au temps, DJ4). Inventer un
  minuteur aurait dépassé le lot.
- **Tâche `release_prod` non faite, volontairement** : aucun déploiement dans un lot (la PROD se
  livre à part, par devAI). La migration `d8e5a3c6b2f1` est à jouer à la prochaine livraison.
- **Suites front exécutées sur devAI**, pas sur chimera : la WSL de chimera n'a **ni node ni pnpm**
  (seul un *store* pnpm résiduel), donc aucune suite web n'y est exécutable. Copie de travail
  jetable sous `/tmp` sur devAI (55 Mo + dépendances, supprimée en fin de lot) — `/Volumes/Data` est
  monté mais refuse l'écriture depuis une session agent (`Operation not permitted`, TCC), ce qui
  reste à régler par JF. Sur cette copie, **15 tests `app-shell` échouent** (`window.localStorage`
  indéfini dans `theme-provider`) : vérifié, **ils échouent à l'identique sur `main` pristine** dans
  le même environnement — Node 26.5 local contre Node 24 en CI. Ce n'est pas une régression du lot,
  et c'est la CI qui tranche.

## Reste à faire

- Brancher le transport des notifications web dans `relais.relayer_par_push` quand `v6-pwa` sera
  livré (le réglage, la décision et le journal d'absence sont déjà en place).
- Jouer la migration `d8e5a3c6b2f1` à la prochaine livraison PROD.
- Un rafraîchissement du badge pendant une partie (il se réévalue au changement de page) viendra
  naturellement avec le canal temps réel si le besoin se fait sentir — pas d'anticipation ici.
