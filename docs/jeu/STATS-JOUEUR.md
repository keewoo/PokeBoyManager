# Mes parties : historique, statistiques et honnêteté sur les petits nombres

> Lot `j-stats-joueur` (jalon J4). On l'ouvre quand on touche à l'écran « Mes parties », à un
> agrégat de deck ou d'adversaire, au bloc « Ce deck en partie » de la fiche de deck — ou quand
> quelqu'un dit « mon taux de victoire est faux » ou « je ne retrouve pas une vieille partie ».

## En une phrase

Deux routes en lecture recalculent, à chaque appel, tout ce qu'un joueur peut savoir de ses parties
depuis `game_result_players` : l'historique filtrable avec son lien de replay, et les agrégats par
deck et par adversaire — **chaque taux rendu avec l'information qu'il ne veut peut-être rien dire**.

## Les deux routes

| Route | Ce qu'elle rend | Paginée ? |
|---|---|---|
| `GET /jeu/mes-parties` | une page d'historique (`total`, `limite`, `offset`, `parties[]`) | oui, 20 par défaut, 100 au plus |
| `GET /jeu/mes-statistiques` | totaux, chiffres, `par_deck[]`, `par_adversaire[]`, et `seuil_significativite` | **non** |

Filtres communs : `resultat`, `deck_id`, `adversaire_user_id`, `entrainement`. Les deux sont gardées
par `require_game_access` (D11) : un compte sans accès au jeu reçoit **404**, jamais 403.

Code : `apps/api/src/pbm_api/jeu/stats_joueur.py` (calcul **pur**),
`apps/api/src/pbm_api/jeu/stats_joueur_service.py` (lecture),
`apps/api/src/pbm_api/routers/stats_joueur.py` (HTTP). Écran :
`apps/web/src/app/jeu/parties/` et `apps/web/src/lib/api/stats-joueur.ts`.

## Les cinq règles qui tiennent l'ensemble

**1. Aucun taux n'est affiché nu.** Le risque nommé du lot est « des statistiques flatteuses
calculées sur trois parties : elles trompent le joueur sur son deck et faussent ses choix ». La
parade n'est pas un avertissement en bas de page : la fonction `taux()` est la **seule** porte vers
un pourcentage, et elle rend `significatif` et `parties_manquantes` dans le même objet. Un écran ne
peut donc pas obtenir un taux sans obtenir, du même coup, de quoi dire qu'il ne vaut rien encore.
Le seuil est **cinq** parties (`SEUIL_SIGNIFICATIVITE`) : à quatre, une victoire de plus déplace le
taux de 25 points. Le pourcentage est quand même calculé et affiché — le masquer ressemblerait à un
bug — mais en sourdine, avec la phrase qui chiffre ce qui manque.

**2. Rien n'est stocké.** Tout est recalculé à chaque appel, comme le classement privé. Il n'existe
donc aucun agrégat à réparer : une erreur de calcul se corrige en changeant le code, et le résultat
est juste au prochain affichage. C'est aussi pourquoi il n'y a **aucune route d'écriture** — et pas
de « remise à zéro de mes statistiques » : effacer son historique, c'est supprimer son compte (ses
lignes partent en `ON DELETE CASCADE`).

**3. `player_stats` n'est pas lu, volontairement.** Ce cache dit déjà les totaux, mais il peut être
en retard (son recalcul est reporté quand l'écriture de la trace échoue — voir
[FIN-COMPTE.md](FIN-COMPTE.md)). L'afficher au-dessus de l'historique exposerait à montrer un total
qui contredit la liste juste en dessous, sans que personne sache lequel croire. Les totaux de cet
écran viennent donc des **mêmes lignes** que la liste : les deux ne peuvent pas divergir.

**4. Les agrégats ne sont pas paginés.** Un taux calculé sur la page affichée changerait en cliquant
« suivant » : le joueur verrait son deck s'améliorer en tournant les pages. Les agrégats portent sur
tout l'historique, au filtre près — ce qui permet à la fiche d'un deck de demander `?deck_id=…` et
d'obtenir **exactement** le chiffre que porte la ligne de ce deck dans le tableau général (vérifié
par `test_le_filtre_par_deck_donne_le_meme_chiffre_que_le_tableau`).

**5. Une ligne qui ne compte pas le dit.** `comptabilisee` est rendu avec chaque partie, et l'écran
l'écrit (« entraînement, ne compte pas », « ne compte pour personne »). Sans cela, un joueur qui
recompte ses victoires à la main ne comprend pas l'écart avec le total affiché plus haut — et c'est
le total qu'il soupçonne. La définition de « ça compte » n'est pas dupliquée ici : elle est posée
une fois pour toutes à la clôture par `j-fin-effets-compte`, on ne fait que lire le champ.

## Ce que le lien de replay dit vraiment

La purge supprime les parties mortes de plus de `jeu_purge_anciennete_j` jours (trente par défaut),
**pas leur trace** — `game_result_players` n'a volontairement aucune clé étrangère vers `games`. Une
ligne d'historique peut donc n'avoir plus de replay. `replay_disponible` le dit, calculé depuis
l'existence réelle de la partie (jointure externe sur `games`), et l'écran affiche alors
« Replay effacé » au lieu d'un lien qui répondrait 404 — ce qu'un joueur lirait comme une panne.

Même logique pour un **deck supprimé** : ses parties restent comptées et se regroupent sous une
ligne nommée « Deck supprimé », pas fondues dans un autre deck (ce qui fausserait le taux de
celui-là). Elle n'est pas proposée au filtre : on ne filtre pas sur un deck qui n'existe plus.

## Ce que ce lot ne sait pas encore dire

Le plan annonçait deux palmarès que ce lot **ne livre pas**, et c'est un choix, pas un oubli.

- **« Cartes les plus jouées » et « attaques les plus décisives »** demandent le détail du journal
  (`game_events`), que la purge supprime au bout de trente jours. Un palmarès calculé sur les
  journaux survivants **rétrécirait tout seul** : un joueur verrait sa carte préférée disparaître
  de son palmarès sans que rien ne l'explique — exactement la statistique trompeuse que ce lot doit
  empêcher. Les rendre justes demande de **cumuler ces compteurs à la clôture**, dans
  `game_result_players` (une colonne par palmarès, écrite une fois, qui survit à la purge comme le
  reste de la trace). C'est une colonne à ajouter, pas un calcul à deviner (D9).
- **« Ce deck gagne surtout contre les decks Eau »** : le type du deck **adverse** n'est pas
  conservé (`game_result_players` porte le deck du joueur, pas celui d'en face), et le déduire de la
  collection de l'adversaire serait deviner. Le croisement livré nomme donc l'**adversaire**, pas
  une couleur qu'on n'a pas. Afficher un type de deck demanderait d'écrire, à la clôture, le profil
  élémentaire du deck d'en face — même nature de travail que ci-dessus.

Ces deux manques sont nommés dans le compte rendu du lot
(`docs/roadmap/comptes-rendus/j-stats-joueur.md`) : ils appartiennent à `j-fin-effets-compte` (la
colonne) avant d'appartenir à un écran.

## Le budget d'une page

| Mesure | Valeur |
|---|---|
| Critère du lot | page chargée en moins d'**une seconde** avec cent parties |
| Mesuré (chimera, 15/10/2026) | **0,183 s** pour les **deux** appels que la page fait (historique de 100 lignes + agrégats non paginés) |
| Requêtes | 3 — la page, son total, et les agrégats. Jamais une requête par ligne |

Le test chronomètre les deux appels, pas seulement la liste : ne mesurer que l'historique aurait
laissé passer un agrégat quadratique. Il vit dans
`apps/api/tests/test_jeu_stats_joueur.py::test_cent_parties_tiennent_la_seconde`.

## Diagnostiquer

```sql
-- « Mon taux de victoire est faux » : ce que la route compte, en SQL.
SELECT resultat, count(*) FROM game_result_players
 WHERE user_id = :uid AND comptabilisee GROUP BY resultat;

-- « Je ne retrouve pas une partie » : sa trace existe-t-elle, et sa partie ?
SELECT p.finie_a, p.resultat, (g.id IS NOT NULL) AS replay_encore_la
  FROM game_result_players p LEFT JOIN games g ON g.id = p.game_id
 WHERE p.user_id = :uid ORDER BY p.finie_a DESC LIMIT 20;
```

Un total qui ne colle pas à la liste **ne peut pas** venir d'un cache : il n'y en a pas. Il vient
soit d'une partie non comptabilisée (entraînement, partie expirée — la liste le dit sur la ligne),
soit d'une trace manquante, et c'est alors le balayage de `j-fin-effets-compte` qu'il faut regarder
(`reprendre_fins_non_enregistrees`).

Tests : `apps/api/tests/test_jeu_stats_joueur.py` (26 cas) et
`apps/web/src/app/jeu/parties/mes-parties-view.test.tsx` (12 cas).
