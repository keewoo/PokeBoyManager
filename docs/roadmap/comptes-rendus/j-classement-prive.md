# `j-classement-prive` — Classement privé entre comptes invités

**Statut : livré.** Exécuté le 15/10/2026, piloté depuis **devAI**, travaillé sur **chimera**,
branche `roadmap/j-classement-prive`. Garde-fou d'ordre :
`suivi.py verifier j-classement-prive` → **code 0** (« ordre tenu »).

## Résumé

Le classement privé est livré **sans aucune table de classement** : il est recalculé à la lecture
depuis `game_result_players`, la table que `j-fin-effets-compte` écrit une fois par partie. C'est la
réponse directe au risque que le plan nommait — « un classement incrémental non recalculable : la
première erreur devient définitive ». Un état qu'on ne stocke pas est un état qu'on ne peut pas
corrompre : changer le barème ou corriger une formule rend le tableau suivant déjà juste, sans
migration ni script de rattrapage.

DJ6 est appliquée à la lettre : le classement est **éteint par défaut** (« en option, activable par
JF »), sans saison ni perte de points. Et comme le critère d'acceptation exige que la désactivation
soit « un réglage, pas un déploiement », le lot a dû poser ce qui manquait au dépôt : un mécanisme
de **réglages globaux du jeu** en base, que JF change par une commande sur le serveur — sans build,
sans redémarrage, sans interrompre une partie. `j-profil-jeu` y branchera les badges (l'autre moitié
de DJ6) par une entrée de dictionnaire, **sans migration**.

Les trois critères d'acceptation sont tenus, chacun avec un test qui le mesure. Aucun écran : le lot
est du couloir J-SRV, et « Mes parties » appartient à `j-stats-joueur`, qui consommera la route
telle quelle.

## Les trois critères, un par un

- [x] **« Le classement se recalcule intégralement depuis l'historique et retrouve le même état. »**
  Le module pur porte **deux** chemins de calcul arithmétiquement distincts : `calculer` compte les
  issues puis multiplie une fois par le barème (c'est ce que le serveur appelle), `appliquer` ajoute
  les points partie par partie (le pas incrémental qu'un cache utiliserait). Le test
  `test_recalcul_complet_identique_au_calcul_incremental` les confronte, **pour chaque barème**, sur
  un historique volontairement tordu : trois joueurs, les trois issues, de l'entraînement intercalé,
  un joueur qui ne s'est *qu'*entraîné, et une partie ancienne enregistrée après une récente (le cas
  que le balayage de `j-fin-effets-compte` produit réellement). La comparaison porte sur chaque
  champ et chaque joueur. Elle est informative parce que les deux implémentations ne partagent
  aucune ligne d'arithmétique — un recalcul qui replierait `appliquer` ne se comparerait qu'à
  lui-même, et c'est la raison pour laquelle `appliquer` reste dans le code alors que la production
  ne l'appelle pas.
- [x] **« La désactivation est un réglage, pas un déploiement. »**
  `test_eteindre_le_classement_sans_redemarrer_le_serveur` allume puis éteint le classement **dans
  la vie du même processus**, sur le même client HTTP, sans rien recharger. Si l'activation vivait
  dans une variable d'environnement, ce test serait inécrivable — et c'est précisément pourquoi la
  variable d'environnement a été écartée : elle demande d'éditer le fichier d'environnement du
  serveur *et* de redémarrer les conteneurs.
- [x] **« Les parties d'entraînement n'y figurent jamais. »** Vérifié aux deux bouts :
  `test_entrainement_jamais_au_classement` sur les deux chemins de calcul purs (c'est le genre de
  condition qu'on oublie dans celui qu'on n'appelle pas), et `test_la_route_ignore_l_entrainement`
  de bout en bout par la route. La condition est unique — `comptabilisee`, **la même** notion que
  celle des statistiques du joueur : dupliquer le raisonnement aurait fait exister deux définitions
  de « ça compte » qui finissent toujours par se contredire.

## Les décisions que le lot a prises, et pourquoi

| Décision | Raison |
|---|---|
| **Rien n'est stocké** : pas de table de classement, pas de points, et la clôture d'une partie n'appelle **rien** de ce lot | la mission demandait que « la formule ne soit pas dans le code de clôture » ; elle n'y est pas, parce qu'il n'y a pas de code de clôture à toucher. Et le risque du lot disparaît avec l'état |
| **L'abandon et la désertion COMPTENT** (la mission laissait le choix ouvert) | 1. ne pas rendre la fuite gratuite : si déserter effaçait la défaite, le coup optimal d'une partie perdue serait de fermer l'onglet — c'est fabriquer la dispute que le plan redoute ; 2. ne pas se contredire : les statistiques du compte comptent déjà ces défaites, un classement qui les ignorerait afficherait « 4 victoires / 1 défaite » à côté de 6 parties sans qu'on sache lequel a tort. Conséquence : **aucun** filtre sur la raison de fin dans le code |
| **Barème par défaut : `points` (3/1/0)** | l'autre option du plan (`victoires`, simple décompte) est aveugle à l'égalité : deux joueurs à une victoire sont à égalité même si l'un a joué dix parties. Les deux sont livrés, JF bascule en une commande |
| **Défaut « éteint »** | DJ6 dit « en option, activable par JF » : un lot ne s'auto-active pas sur une décision qui dit « en option » |
| **Figurent au tableau les comptes invités (`game_access`) ayant ≥ 1 partie comptée, plus le demandeur à zéro** | filtrer sur `game_access` exclut le compte du bot **sans avoir à le nommer** (une condition de moins quand un autre compte technique apparaîtra) ; et un joueur absent de son propre classement croirait à une panne |
| **Les ex æquo partagent leur rang** (1, 1, 3) | départager un ex æquo serait inventer une hiérarchie que le barème n'a pas produite — le détail exact qui transforme un tableau amical en dispute |
| **Aucune route n'écrit un réglage global** | « activable par JF » veut dire par JF sur le serveur, pas par un compte muni du bon cookie. Ce produit n'a aucune notion d'administrateur côté web, et ce lot n'allait pas en inventer une pour un réglage que deux personnes changeront trois fois |
| **`actif: false` se rend en 200**, pas en 404 | l'écran doit pouvoir distinguer « JF n'a pas activé le classement » d'une route cassée. Éteint, l'historique **n'est pas lu** : le réglage n'est pas un filtre d'affichage |

## Livrables

| Fichier | Quoi |
|---|---|
| `apps/api/src/pbm_api/jeu/classement.py` | **pur** : les barèmes, le rangement, les deux chemins de calcul |
| `apps/api/src/pbm_api/jeu/classement_service.py` | la lecture en base, et qui figure au tableau |
| `apps/api/src/pbm_api/routers/classement.py` | `GET /jeu/classement` (lecture seule, `require_game_access`) |
| `apps/api/src/pbm_api/jeu/reglages.py` | **pur** : le registre des réglages globaux, leurs valeurs et leurs défauts |
| `apps/api/src/pbm_api/jeu/reglages_service.py` | lire/écrire un réglage global |
| `apps/api/src/pbm_api/models/jeu_reglages.py` + migration `c2d9b4e7f315` | la table `jeu_reglages` (clé/valeur, aucune ligne semée) |
| `apps/api/src/pbm_api/admin.py` | `set-reglage-jeu` et `lire-reglages-jeu` |
| `apps/api/tests/test_jeu_classement.py` | 26 tests |
| `docs/jeu/CLASSEMENT.md` | la fiche, plus une entrée dans la carte des fiches de `CLAUDE.md` |

Les deux commandes que JF utilisera :

```bash
python -m pbm_api.admin lire-reglages-jeu                       # l'état : posé et effectif
python -m pbm_api.admin set-reglage-jeu classement_actif oui    # allumer (défaut : non)
python -m pbm_api.admin set-reglage-jeu classement_bareme victoires
```

## Preuves

| Mesure | Résultat |
|---|---|
| Suite du lot (chimera, Python 3.12) | **26 passed** en 3,0 s |
| Suite API **complète** (chimera) | **1439 passed, 2 failed** en 4 min 35 — les deux échecs sont `test_catalogue_seed.py`, tombés sur `pg_dump: command not found` : **la WSL de chimera n'a pas `postgresql-client`**, aucun rapport avec ce lot (ils ne touchent ni le classement ni les réglages) |
| `ruff check .` | **All checks passed** |
| `alembic upgrade head` | passe ; **une seule tête** après la migration (`c2d9b4e7f315`) |
| CI GitHub Actions | verte sur la branche (voir le SHA en fin de compte rendu) |

**Les tests mordent — vérifié par mutation**, pas supposé. Deux défauts introduits exprès dans le
recalcul complet, puis retirés :

| Mutation | Ce qui a rougi |
|---|---|
| l'égalité payée comme une victoire (`egalites * bareme.victoire`) | **5 tests**, dont le test de parité sur les deux barèmes |
| l'entraînement plus exclu du recalcul (`if not partie.comptabilisee: continue` retiré) | **3 tests**, dont la parité et le critère d'entraînement |

Après restauration : 26 verts. Un test de parité qui ne distinguerait pas ces deux cas ne vaudrait
rien, et c'est exactement ce qu'un recalcul replié sur `appliquer` aurait donné.

## Ce que le tableau révèle — nommé, pas tu

Le classement **nomme les comptes invités qui ont joué**. C'est sa raison d'être, mais cela va plus
loin que le reste du jeu : les invitations refusent déjà de dire si un pseudo donné appartient à un
compte invité (« révéler qu'un pseudo donné fait partie des comptes invités serait une fuite sur un
jeu délibérément privé », `pbm_api/games/invitations.py`). Les deux tiennent ensemble parce que le
classement est **éteint par défaut** : montrer la table de famille est une décision de JF, pas un
effet de bord d'un lot. Trois précautions l'accompagnent, chacune testée :

- éteint, l'historique **n'est pas lu** ;
- la route ne publie **aucun identifiant de compte** (le pseudo nomme, `moi` surligne, rien de plus
  ne traverse) — `test_le_tableau_classe_les_comptes_invites` l'affirme ;
- un compte sans accès au jeu reçoit **404** (pas 403) et un compte non invité n'apparaît pas au
  tableau, même avec un historique flatteur.

## Écarts au plan

- **Aucun écran livré**, et c'est conforme : couloir J-SRV, `j-stats-joueur` porte « Mes parties ».
  La tâche `maquette` de la grille est donc **sans objet** pour ce lot — rien à comparer à la
  maquette du jeu. La route rend tout ce qu'un tableau demande (rang, pseudo, points, les quatre
  compteurs pour recompter, l'évolution récente).
- **Le client TypeScript n'a pas été régénéré** (`pnpm gen:api`) : il n'est pas versionné et aucune
  garde de CI ne le contrôle — vérifié avant de conclure. Il se régénérera avec l'écran.
- **`release_prod` non fait** : aucun déploiement, conformément au cadre du lot (la PROD se livre à
  part, par devAI). Le lot ajoute **une migration** (`c2d9b4e7f315`, création de table, sans
  donnée) : elle doit être inscrite dans la livraison suivante.
- **L'« évolution dans le temps »** du plan est livrée comme `points_recents` (points gagnés dans
  une fenêtre, 30 jours par défaut, bornée 1–365) et non comme un historique de rangs : montrer
  *ce qui a été gagné récemment* est plus honnête qu'une variation de rang, qui bouge parce qu'un
  tiers a joué. Un historique de rangs aurait par ailleurs demandé la table stockée que ce lot
  refuse.

## Reste à faire

- **Décision d'exploitation pour JF** : allumer ou non le classement, et sur quel barème. Rien ne
  l'exige — éteint, le jeu se comporte exactement comme avant ce lot.
- **Inscrire la migration `c2d9b4e7f315`** dans le prochain déploiement PROD.
- `j-stats-joueur` consommera `GET /jeu/classement` pour l'écran ; `j-profil-jeu` ajoutera
  `badges_actifs` au registre de réglages (une entrée de dictionnaire, pas de migration).
- `postgresql-client` manque dans la WSL de chimera : les deux tests de `catalogue_seed` ne peuvent
  pas y passer. À installer sur chimera (ou à accepter comme trou connu de cette machine, la CI les
  couvrant).
