# `j-replay` — Replay d'une partie : la rejouer coup par coup, et la partager

**Statut : livré** (recette locale sur chimera ; la CI GitHub fait foi).
Machine : **chimera** (WSL Ubuntu-24.04), piloté depuis devAI. Branche `roadmap/j-replay`.
Jalon J4, palier 9, couloir J-SRV. Garde-fou d'ordre : `suivi.py verifier j-replay` → **code 0**.

## Résumé

Le journal existait déjà ; ce lot en fait une **fenêtre**. Côté moteur, une seule addition :
`etapes` rend la **suite** des états d'une partie (un rang par coup) au lieu du seul état final,
avec les mêmes contrôles d'empreinte au coup près. Côté serveur, une porte qui ne s'ouvre
**qu'après la fin** de la partie, ne sert que des états **projetés**, et n'est accessible qu'aux
deux joueurs et aux comptes à qui l'un d'eux l'a ouverte. Côté écran, la navigation est **locale** :
les pages sont chargées une fois, puis avancer/reculer ne touche plus le réseau.

Trois décisions ont été prises en session autonome ; elles sont argumentées ci-dessous (§ Écarts et
arbitrages) et dans `docs/jeu/REPLAY.md`.

## Livrables

| Quoi | Où |
|---|---|
| Moteur : `Etape`, `etapes`, `etapes_partie` (purs, paresseux) | `apps/game/src/pbm_game/journal/rejeu.py` |
| Service de replay : accès, pagination, projection par destinataire, partages | `apps/api/src/pbm_api/games/replay.py` |
| Table du droit de regarder | `apps/api/src/pbm_api/models/games.py` (`GameReplayShare`) + migration `a1f6c2d9e4b7` |
| 4 routes HTTP (replay + 3 de partage) | `apps/api/src/pbm_api/routers/games.py` |
| Navigation pure (bornes, fil du journal, complétude, vitesses) | `apps/web/src/lib/game/replay.ts` |
| Écran `/jeu/parties/{id}/replay` + panneau de partage | `apps/web/src/app/jeu/parties/[id]/replay/` |
| Client API typé | `apps/web/src/lib/api/games.ts` |
| Fiche durable | `docs/jeu/REPLAY.md` (+ renvoi depuis `docs/jeu/JOURNAL.md`) |

## Preuves

### Critère 1 — « Le replay reproduit exactement les états successifs (empreintes comparées) »

| Preuve | Résultat |
|---|---|
| Moteur, 200 parties simulées : empreinte de **chaque rang** comparée à celle observée en avant de jeu, + état final octet pour octet (`vers_json`) | ✅ `apps/game/tests/test_replay_etapes.py` |
| API, **partie réellement jouée** par le service jusqu'à la victoire, puis replay demandé **en HTTP** : empreintes rang par rang comparées au journal **en base** (`game_events.empreinte`) | ✅ `test_replay_reproduit_les_empreintes_de_la_partie_jouee` |
| Repartir d'un instantané rend les mêmes rangs que le replay complet (ce sur quoi repose la pagination) | ✅ `test_repartir_d_un_instantane_donne_les_memes_rangs` (coupes 0, 1, 4, 8) |

**Le test mord** — vérifié par mutation, pas supposé : en neutralisant le contrôle d'empreinte de
`_pas` (`if False:`), `test_replay_mord_sur_une_empreinte_truquee_au_coup_pres` **échoue**
(« DID NOT RAISE RejeuDivergent »), puis repasse au vert après restauration du fichier.

### Critère 2 — « Aucune information cachée n'est servie avant la fin de la partie »

| Preuve | Résultat |
|---|---|
| Replay d'une partie **en cours** (journal non vide — sinon le test ne prouverait rien) : **409**, et la réponse ne porte **aucun** rang. Vérifié pour `vue=moi` **et** `vue=complete` | ✅ `test_replay_d_une_partie_en_cours_est_refuse_sans_rien_servir` |
| Sur une partie **finie**, la vue d'un joueur ne porte jamais `main` de l'adversaire (seulement `main_nombre`), ni `pioche` (seulement `pioche_nombre`) — à **tous** les rangs | ✅ `test_le_replay_ne_montre_pas_la_main_adverse` |
| `vue=complete` ne sert que des vues **projetées** : chacune porte son propre `pour` | ✅ `test_replay_vue_complete_donne_les_deux_vues_de_joueur` |
| Une vue hors vocabulaire (`""`, `"tout"`, `"spectateur"`) est **refusée** (422), pas repliée | ✅ `test_vue_inconnue_est_refusee_jamais_repliee` |
| Côté écran, un 409 n'affiche **aucun** plateau et dit pourquoi | ✅ `replay-view.test.tsx` |

### Critère 3 — « Le lien de replay n'est pas accessible à un compte non autorisé »

`test_acces_croise_puis_partage_ouvert_puis_ferme` : le compte C **connaît l'URL exacte du début à
la fin du test** ; seul son *droit* change.

1. sans droit → **404** (jamais 403 : pas de fuite d'existence), et 404 aussi sur les partages ;
2. A ouvre le partage par pseudo → 201, idempotent (deux POST, une seule ligne) ;
3. C voit le replay en `vue=complete` — et reçoit **422** sur `vue=moi` (il n'a pas de siège) ;
   il reste à **404** sur les routes de partage (regarder n'est pas administrer) ;
4. B (l'autre joueur) ferme le partage → 204 ; le fermer deux fois → 404 ;
5. C, même URL → **404**.

Compléments : un compte **sans droit au jeu** (D11) ne voit aucun replay, même participant
(`test_replay_sans_droit_au_jeu_est_introuvable`) ; un compte **ordinaire** (sans D11) est
introuvable comme cible de partage, et l'autre joueur est refusé en 422
(`test_partage_refuse_un_compte_non_invite_et_un_joueur_de_la_partie`).

### Cas du lot — partie interrompue par abandon

✅ Moteur (`test_replay_d_une_partie_interrompue_par_abandon`) **et** API (même nom) : le dernier
rang porte `type: "abandonner"`, l'état terminé et le bon vainqueur ; les rangs d'avant ne sont
**pas** marqués terminés (un replay ne réécrit pas l'histoire en fonction de sa fin) ; et
l'empreinte du dernier rang est retrouvée en recalculant depuis la base (`reprendre_partie`).

### Suites exécutées (chimera, `TZ=Europe/Paris`)

| Suite | Résultat |
|---|---|
| `apps/game` — ruff + pytest | ✅ **1113 passed**, ruff clean |
| `apps/web` — type-check, lint, vitest, `next build` | ✅ **328 passed / 58 fichiers** (dont **16** `replay.test.ts` + **9** `replay-view.test.tsx`), build OK |
| `apps/api` — ruff + pytest complet | **1150 passed, 2 failed** — voir ci-dessous |
| `alembic upgrade head` puis `alembic heads` | ✅ une seule tête : `a1f6c2d9e4b7` |

⚠️ **Les 2 échecs de `apps/api` sont un manque d'outillage local, pas une régression** :
`tests/test_catalogue_seed.py` appelle `scripts/catalogue_seed.sh`, qui échoue sur
`pg_dump: command not found` (code 127) — le client PostgreSQL n'est pas installé dans cette WSL.
Aucun rapport avec le replay (catalogue/seed), et la CI dispose de `pg_dump`. **Je ne présente donc
pas la suite API comme verte en local** : c'est la CI GitHub qui tranche.

## Écarts et arbitrages (décidés en session autonome)

1. **« Vue complète » = les deux vues de joueur, pas une sortie non projetée.** Le moteur n'a aucune
   sortie « tout voir » (`projeter` exige un destinataire, `vue` refuse un inconnu). En ajouter une
   pour le replay rouvrirait le chemin brut que `j-autorite-vues` a précisément supprimé. On sert
   donc les deux vues de joueur, une fois la partie finie. **Conséquence assumée** : l'ordre du
   reste de la pioche et l'identité des récompenses non prises ne sont **pas** révélés — ni l'un ni
   l'autre joueur ne les a jamais sus, et un replay n'en a pas besoin.
2. **Le partage est un droit en base, pas un jeton d'URL.** Un lien porteur est une autorisation qui
   voyage (copie, journal d'un intermédiaire, historique) : il ne peut pas satisfaire « pas
   accessible à un compte non autorisé ». D'où `game_replay_shares` + une migration, et un lien
   partagé qui est l'URL ordinaire. Coût : une table et trois routes de plus que si on avait posé un
   jeton ; bénéfice : le critère est réellement tenu, et le droit se **retire**.
3. **Les parties closes pour inactivité (`expiree`) ont aussi un replay.** La porte est
   `status != en_cours` : une partie expirée n'accepte plus aucune action, son journal est figé. En
   revanche sa **graine n'est pas révélée** (seules les parties `terminee` la révèlent, comme le
   fait déjà `j-lancement-partie`) : elle n'a pas été jouée jusqu'au bout.

Deux retraits volontaires par rapport à la vue du plateau en direct, documentés dans la fiche :
pas de **jetons opaques** de récompenses (rien à désigner dans un replay) et pas d'**actions
légales** (un rang de replay n'est pas un tour de jeu).

## Reste à faire

- **Export du journal pour le support** : la réponse porte déjà tout (coups, empreintes, graine
  révélée), mais aucun bouton ni format de fichier n'est posé. Mentionné dans les fonctionnalités du
  lot ; traitable en quelques lignes quand le support en aura l'usage réel.
- **Commentaire d'affichage d'un coup** (explication de l'IA adverse, `game_events.commentaire`) :
  non servi dans le replay — il n'est pas porté par l'`Entree` du moteur, et le fil du journal se
  reconstruit sans lui.
- **Capture d'écran de l'onglet « Maquette du jeu »** : non jointe. L'écran réutilise les composants
  déjà conformes (`GameBoard`, `JournalPanel`) ; la barre de navigation est un ajout **hors flux**
  (`fixed` en haut, le journal occupant déjà le bas) dans les jetons de style existants, sans
  nouvelle couleur en dur. Un e2e navigateur n'est pas exécutable en local sur chimera
  (`libnspr4`, sudo requis) — la CI fait foi.
- **Pas d'e2e dédié** au replay : la navigation est couverte en vitesse par vitest (pur + composant)
  et l'accès par les tests API. Un e2e « ouvrir un replay partagé » serait le complément naturel.
- **Aucun déploiement** : la PROD se livre à part, par devAI.
