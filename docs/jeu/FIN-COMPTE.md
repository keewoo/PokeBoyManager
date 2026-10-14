# Ce qu'une partie laisse sur le compte

> Lot `j-fin-effets-compte` (jalon J4, décision **DJ6**). On l'ouvre quand on touche à la fin de
> partie, aux statistiques d'un joueur, au classement privé ou aux badges — ou quand quelqu'un dit
> « mon compteur de victoires est faux ».

## En une phrase

À la clôture d'une partie, le serveur écrit **une** ligne de résultat, **une** ligne par joueur, et
**recalcule** les totaux des deux comptes. Une seule fois par partie, quelle que soit la façon dont
elle s'est terminée.

## Les trois tables

| Table | Ce qu'elle porte | Nature |
|---|---|---|
| `game_results` | le résultat d'une partie : statut, raison, vainqueur, coups, tours, durée | **fait**, une ligne par partie |
| `game_result_players` | par joueur : résultat, deck joué, adversaire, et ses six chiffres de la partie | **fait**, une ligne par siège |
| `player_stats` | les totaux d'un compte : parties, victoires, défaites, égalités, série en cours, meilleure série, temps de jeu | **cache recalculé** |

Code : `apps/api/src/pbm_api/models/fin_compte.py` (tables) et
`apps/api/src/pbm_api/games/fin_compte.py` (écriture, recalcul, balayage).

## Les quatre règles qui tiennent l'ensemble

**1. L'idempotence est une contrainte de base, pas un `if`.** `game_results.game_id` est *unique*
(`uq_game_results_game`). L'écriture est un `INSERT … ON CONFLICT DO NOTHING … RETURNING id` : pas
de ligne rendue = déjà enregistrée, et **rien d'autre** n'est touché. C'est ce qui rend inoffensifs
les quatre cas où une partie se termine « deux fois » : un coup rejoué (même numéro renvoyé par le
client), une reprise qui repasse par la fin, le balayage qui croise le coup final, deux requêtes
concurrentes. Un `if` aurait perdu la course sur le dernier.

**2. Les chiffres se recalculent, ils ne s'accumulent pas.** Les chiffres d'une partie viennent du
journal, par le module **pur** du moteur `pbm_game.journal.recapitulatif` — le même que l'écran de
fin, pour que les deux ne puissent pas se contredire. Les totaux d'un joueur sont reconstruits
*intégralement* depuis `game_result_players` (triée par `finie_a`) à chaque clôture : il n'existe
aucun chemin qui incrémente un compteur dans ce dépôt. Deux conséquences qu'on veut :

- une erreur n'est jamais définitive — `recalculer_stats_joueur` répare tout ;
- la **série de victoires** reste juste même quand le balayage enregistre une partie ancienne après
  une récente (un calcul par incréments l'aurait cassée, sans bruit).

**3. La trace ne fait jamais échouer la partie.** Elle s'écrit **après** le commit du coup, dans sa
propre transaction (`enregistrer_fin_si_due`). Le coup gagnant ne peut donc pas être perdu à cause
d'une écriture de statistiques — ce serait le pire moment pour rendre une erreur. En échange, cette
écriture peut manquer : l'échec part dans le journal du serveur en `error`, et le **balayage**
`reprendre_fins_non_enregistrees` la reprend au passage suivant *en le disant*.

**4. Toutes les fins passent par le même chemin.** Victoire par les règles, abandon (R-14.3),
désertion (R-14.6), défaite au temps (DJ4), expiration pour inactivité : toutes arrivent par les
deux fonctions d'écriture de coup de `pbm_api.games.service`, donc toutes laissent la même trace.

## Ce qui « compte », et ce qui ne compte pas

`comptabilisee` est faux dans deux cas, et dans ces deux-là seulement :

- **partie d'entraînement** contre le bot (DJ7) : elle entre dans l'historique (`parties_entrainement`,
  `temps_jeu_entrainement_s`) mais n'affecte **ni les totaux ni la série** — ni pour les nourrir, ni
  pour les casser ;
- **partie expirée** faute d'activité : personne ne l'a jouée jusqu'au bout, elle n'a pas de
  vainqueur mérité. La compter en défaite pour les deux joueurs serait inventer un résultat (D9).

Une **égalité** compte comme une partie jouée et **interrompt** la série : prolonger une série sur
une égalité serait flatteur, donc faux.

## Deux pièges déjà payés

**La purge efface les parties, pas l'historique.** `purger` supprime les parties mortes de plus de
30 jours (`jeu_purge_anciennete_j`). Si `game_results.game_id` portait une clé étrangère en cascade,
**tout l'historique des joueurs disparaîtrait au bout d'un mois**, sans un mot — la panne muette
exacte que ce lot doit empêcher. Il n'y a donc **volontairement aucune clé étrangère** vers `games` :
la trace survit à la partie. Un résultat dont la partie est purgée n'a simplement plus de replay à
proposer.

**L'ordre du cycle de maintenance n'est pas cosmétique.** Dans `games_maintenance_task` :
`expirer_parties` → `reprendre_fins_non_enregistrees` → `purger`. Le balayage **après** la clôture
des fantômes (qui vient d'en produire) et **avant** la purge (une partie purgée n'a plus de journal,
donc plus de chiffres à recalculer).

## Ce que ce lot ne décide pas

- Les **badges** appartiennent à `j-profil-jeu`, dont la mission est d'en arrêter la liste avec JF
  et Aymeric. Aucune table de badge n'est posée ici : on ne devine pas une liste pour la jeter
  ensuite (D9).
- Le **classement privé** appartient à `j-classement-prive`, qui implémente la formule retenue en
  DJ6 et doit rester désactivable par réglage.
- L'**écran** « Mes parties » appartient à `j-stats-joueur`.

Les trois liront `game_result_players`, qui porte déjà le résultat, le deck, l'adversaire et la
date de chaque partie — un `GROUP BY` suffit, sans jointure à une partie peut-être purgée.

## Diagnostiquer

```sql
-- Une partie close dont la trace manque ? (ce que le balayage cherche)
SELECT g.id, g.status, g.updated_at FROM games g
 LEFT JOIN game_results r ON r.game_id = g.id
 WHERE g.status <> 'en_cours' AND r.id IS NULL;

-- Les totaux d'un joueur contredisent-ils ses parties ?
SELECT resultat, count(*) FROM game_result_players
 WHERE user_id = :uid AND comptabilisee GROUP BY resultat;
```

Si les deux ne concordent pas, le cache est en retard : `recalculer_stats_joueur` le reconstruit, et
c'est sans risque — il ne fait que relire les faits.

Tests : `apps/api/tests/test_games_fin_compte.py`.
