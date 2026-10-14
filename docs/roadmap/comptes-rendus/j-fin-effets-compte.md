# Compte rendu — `j-fin-effets-compte`

**Ce qu'une partie laisse sur le compte : écriture unique et exacte.** À la clôture d'une partie, le
serveur écrit son résultat, les chiffres de chaque joueur et recalcule leurs totaux — une seule fois
par partie, quelle que soit la façon dont elle s'est terminée. Jalon J4, piste Compte & progression
(couloir J-SRV), palier 13, décision **DJ6**.

## Résumé

Le piège de ce lot est technique et nommé dans sa fiche : une partie peut se terminer **deux fois**
(coup rejoué, reprise, double événement de fin, requêtes concurrentes), et compter les victoires au
fil de l'eau est « la panne muette classique — personne ne remarque un compteur faux avant que
quelqu'un ne compte ». Les deux pièges sont traités à la racine, par la structure et non par de la
vigilance :

- **L'idempotence est une contrainte de base, pas un `if`.** `game_results.game_id` est unique
  (`uq_game_results_game`) ; l'écriture est un `INSERT … ON CONFLICT DO NOTHING … RETURNING id` et
  c'est **la base** qui tranche. Pas de ligne rendue = déjà enregistrée, et rien d'autre n'est
  touché. Un `if` aurait perdu la course entre deux clôtures concurrentes.
- **Il n'existe aucun compteur.** Les chiffres d'une partie viennent du journal, par le module
  **pur** du moteur `pbm_game.journal.recapitulatif` — le **même** que l'écran de fin, pour que les
  deux ne puissent pas se contredire. Les totaux d'un joueur (`player_stats`) sont un **cache**
  reconstruit *intégralement* à chaque clôture depuis `game_result_players` triée par date. Aucune
  fonction du dépôt n'incrémente une victoire.

Ce que ça apporte, concrètement :

- **Trois tables** (`apps/api/src/pbm_api/models/fin_compte.py`, migration `e2a7b4c1d6f9`) :
  `game_results` (le fait, une ligne par partie), `game_result_players` (par siège : résultat, deck,
  adversaire, et les six chiffres du récapitulatif), `player_stats` (les totaux : parties, victoires,
  défaites, égalités, série en cours, meilleure série, temps de jeu, et l'entraînement à part).
- **Un service** (`apps/api/src/pbm_api/games/fin_compte.py`) : `enregistrer_fin_de_partie` (la
  transaction unique), `cumuler` (fonction **pure** qui calcule les totaux et les séries, testable
  sans base), `recalculer_stats_joueur` (la seule écriture de `player_stats` du dépôt) et
  `reprendre_fins_non_enregistrees` (le balayage de reprise).
- **Deux points de branchement**, et deux seulement : les deux chemins d'écriture de coup de
  `pbm_api.games.service` (coup de joueur, coup système). Toutes les fins passent donc par le même
  code — victoire par les règles, abandon (R-14.3), désertion (R-14.6), défaite au temps (DJ4),
  expiration pour inactivité.
- **Le balayage dans le cron de maintenance** (`games_maintenance_task`), placé **entre**
  `expirer_parties` et `purger` : après la clôture des fantômes (qui vient d'en produire), avant la
  purge (une partie purgée n'a plus de journal, donc plus de chiffres).

**Aucune route ajoutée** (couloir J-SRV) : l'écran « Mes parties » est `j-stats-joueur`. Donc aucun
changement de schéma d'API, aucun `pnpm gen:api`, aucun impact front. **Le moteur n'a pas été
touché** : il reste pur, et ce lot se contente de l'appeler.

## Critères d'acceptation

- [x] **« Rejouer la clôture d'une partie ne modifie rien la deuxième fois (test explicite). »**
  `test_rejouer_la_cloture_ne_modifie_rien` photographie **champ par champ** la ligne de résultat,
  les deux lignes de joueur et les deux lignes de totaux, rappelle `enregistrer_fin_de_partie`, et
  compare. Puis `test_une_troisieme_cloture_ne_change_rien_non_plus` le rejoue trois fois (un rejeu,
  une reprise et le balayage peuvent se cumuler). Garde qui **mord** : en neutralisant le
  court-circuit sur conflit (`if inseree is None` → `if False`), le test échoue.
- [x] **« Les statistiques recalculées depuis le journal correspondent à la partie jouée. »**
  `test_les_chiffres_du_resultat_viennent_du_journal` recompte les totaux attendus **à la main**,
  dans le test, depuis les lignes de `game_events` (dégâts, K.O., récompenses, énergies, coups par
  joueur, tours) — on ne compare pas le service à lui-même. Garde qui **mord** : en ne lisant que la
  première entrée du journal, le test échoue.
- [x] **« Une partie d'entraînement contre le bot n'affecte ni classement ni série. »**
  `test_partie_entrainement_n_affecte_ni_totaux_ni_serie` : la partie contre le bot entre bien dans
  l'historique (`comptabilisee = False`, `parties_entrainement = 1`, `adversaire_bot = True`) et
  laisse `parties`, `victoires`, `defaites`, `serie_en_cours` et `meilleure_serie` à **zéro**. Le cas
  le plus subtil est couvert par un test pur : deux victoires classées encadrant une *défaite*
  d'entraînement donnent une série de **2**, pas de 1 — l'entraînement ne nourrit ni ne casse une
  série. Garde qui **mord** : deux mutants distincts font rougir ces deux tests.

## Au-delà des critères — ce que la mission demandait aussi

- **« Traiter les fins anormales avec le même chemin d'écriture »** :
  `test_abandon_entre_deux_comptes_laisse_la_trace_du_forfait` (l'adversaire gagne, série à 1) et
  `test_partie_expiree_entre_dans_l_historique_sans_compter`.
- **« Prévoir la reprise après panne »** : `test_le_balayage_reprend_une_cloture_manquante_et_le_dit`
  supprime ce que la clôture avait écrit — l'état exact d'un serveur tué entre le commit du coup et
  celui de la trace, et celui d'une partie close *avant* ce lot — puis vérifie que le balayage
  retrouve **les mêmes chiffres** (le journal n'a pas bougé) et qu'un second passage ne répare rien
  (un balayage qui répare deux fois doublerait tout).
- **« Clôture pendant une reprise »** : `test_une_partie_en_cours_ne_laisse_aucune_trace` — rien
  n'est écrit avant la fin ; sans ce test, une écriture déclenchée à chaque coup passerait inaperçue
  tant que les chiffres finissent par être justes.

## Deux décisions à connaître (elles sont dans `docs/jeu/FIN-COMPTE.md`)

**1. Aucune clé étrangère vers `games` — et c'est volontaire.** `purger` supprime les parties mortes
de plus de 30 jours (`jeu_purge_anciennete_j`). Une clé étrangère en cascade aurait donc effacé
**tout l'historique des joueurs au bout d'un mois, sans un mot** : exactement la panne muette que ce
lot doit empêcher. La trace survit à la partie ; c'est le journal, volumineux et rejouable, que la
purge libère. Un résultat dont la partie est purgée n'a simplement plus de replay à proposer.

**2. Une partie expirée est enregistrée mais ne compte pas.** Personne ne l'a jouée jusqu'au bout,
elle n'a pas de vainqueur mérité (c'est déjà ce que dit `GAME_STATUS_EXPIREE`). La compter en défaite
pour ses deux joueurs serait inventer un résultat (D9). Elle entre dans l'historique en égalité, non
comptabilisée. Même traitement que l'entraînement, pour la même raison.

## Écarts au plan — à lire, ce sont des réductions assumées

La fiche du lot énumère dans ses *fonctionnalités* « l'attribution des badges » et « la mise à jour
du classement privé si activé ». **Ni l'un ni l'autre n'est livré ici**, et ce n'est pas un oubli :

- les **badges** appartiennent au lot `j-profil-jeu`, dont la mission est précisément « définir la
  liste des badges avec JF et Aymeric, en évitant tout badge qui pousse à jouer longtemps plutôt que
  bien ». Poser une liste devinée ici, c'est préempter cet arbitrage pour la jeter ensuite (D9) ;
- le **classement privé** appartient au lot `j-classement-prive`, qui dépend de celui-ci et dont la
  mission exige que « la formule ne soit pas dans le code de clôture » et que JF puisse la désactiver
  par réglage ;
- **DJ6 le confirme** : « historique et statistiques d'office ; classement privé et badges **en
  option, activables par JF** ». Ce sont bien les deux parties optionnelles.

Ce que ce lot leur laisse est le socle exact qu'ils liront : `game_result_players` porte déjà, pour
chaque partie et chaque joueur, le résultat, le deck joué, l'adversaire, la date et les chiffres. Un
`GROUP BY` suffit, sans jointure à une partie peut-être purgée. Les deux *livrables* nommés du lot
(« clôture idempotente », « statistiques recalculées depuis le journal ») sont, eux, livrés.

Second écart, mineur : **aucun test d'accès croisé** n'accompagne ce lot, parce qu'il n'ajoute
**aucune route**. Il viendra avec la route de `j-stats-joueur`.

## Preuves

| Quoi | Preuve |
|---|---|
| `ruff check .` | `All checks passed!` (chimera, `apps/api`) |
| Migration | `alembic heads` → `e2a7b4c1d6f9` (**une seule tête**), `alembic upgrade head` joué sur une base neuve `pbm_jfincompte_test` |
| Tests du lot | **15 passed** — `uv run pytest tests/test_games_fin_compte.py` (5 purs sur `cumuler`, 10 sur des parties réellement jouées) |
| Non-régression du jeu | **328 passed, 0 failed** — `pytest -k "game or partie or jeu or ingame or recap or abandon or solo"` (le branchement tourne sur chaque fin de partie de la suite) |
| Suite API complète | **1330 passed, 2 failed** — les deux échecs sont `pg_dump: command not found` dans `test_catalogue_seed.py` : **les outils clients PostgreSQL ne sont pas installés dans la WSL de chimera**, c'est une limite de la machine, sans rapport avec ce lot (la CI, elle, a `pg_dump`) |
| Les tests mordent | **5 mutants, 5 tests rouges** : l'entraînement qui compte comme une vraie partie · une égalité qui prolonge la série · l'entraînement non exclu de la série · les chiffres lus sur une seule entrée de journal · le court-circuit sur conflit neutralisé. Source restaurée après chaque mutant, suite re-verte |
| CI GitHub Actions | verte sur le dernier commit poussé (c'est elle qui fait foi, pas la suite locale) |

## Reste à faire

- `j-stats-joueur` — l'écran « Mes parties » et les agrégats par deck et par adversaire : tout est
  lisible dans `game_result_players`.
- `j-classement-prive` — la formule retenue en DJ6, désactivable par réglage, et le test « recalcul
  complet depuis l'historique = calcul incrémental » (le cache `player_stats` donne déjà le modèle à
  suivre : il n'y a pas de calcul incrémental, seulement un recalcul).
- `j-profil-jeu` — la liste des badges, à arrêter avec JF et Aymeric avant d'écrire une ligne.
- Rien à livrer en PROD dans ce lot (`docs/jeu/FIN-COMPTE.md` décrit la table à migrer) : la
  migration `e2a7b4c1d6f9` partira avec la prochaine livraison du jeu.
