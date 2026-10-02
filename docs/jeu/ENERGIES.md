# ENERGIES.md — Énergies : fourniture générique et paiement expliqué

> Fiche du lot `j-cartes-energies` (jalon J1, palier 8). Elle dit **comment le moteur traite
> l'énergie en jeu** : ce qu'une carte Énergie *fournit*, comment un coût d'attaque est payé et
> expliqué, et comment une énergie spéciale branche ses effets sur la pile. Les règles citées
> vivent dans `docs/jeu/REGLES.md` (R-8, R-9) ; les décisions dans `docs/roadmap/jeu/` (D9, D10).

## La fourniture est une capacité, pas un type figé (R-9.2)

Une énergie n'est pas « de type Feu » : elle **fournit** des unités, décrites par
`{type: unités}`. Ce détour — porté par `pbm_game.cartes.energie.DefinitionEnergie.fournit` —
exprime sans cas particulier :

| Énergie | `fournit` | Ce que ça couvre |
|---|---|---|
| Énergie Feu de base | `{"feu": 1}` | 1 unité, 1 type |
| Double Énergie Incolore | `{"incolore": 2}` | **plusieurs unités** |
| Énergie spéciale bi-type | `{"feu": 1, "eau": 1}` | **plusieurs types** (2 unités) |
| Énergie spéciale mono-type | `{"feu": 1}` | ne compte **que** pour son type |

Une fourniture **vide ou malformée** (type absent, unités négatives) fait échouer la
construction de la `DefinitionEnergie` : une énergie dont on ne sait pas ce qu'elle fournit est
une panne, jamais un zéro silencieux (D9). Le service (`apps/api`) lit le catalogue et fabrique
la `DefinitionEnergie` ; le moteur ne devine aucune fourniture.

## Payer un coût, et l'expliquer (R-9.2)

`pbm_game.combat.cout` répond à deux questions distinctes :

- **« y a-t-il de quoi payer ? »** — `cout_satisfait(cout, fournitures)` : un `Verdict` d'accord
  ou un **refus motivé** citant R-9.2 et nommant ce qui manque ;
- **« avec quoi ? »** — `payer_cout(cout, energies)` : un `PaiementCout` qui porte la
  **combinaison retenue** (quelle énergie paie quel symbole) et son **détail lisible**
  (« feu ← Énergie Feu, ★ ← Double Énergie Incolore »), journalisable via `EVT_COUT_PAYE`.

**Règle de paiement.** Un symbole **coloré** d'un type se paie par une unité de **ce type
exact** ; un symbole **incolore** (★) par **n'importe quelle** unité. On réserve donc d'abord
les unités colorées à leur couleur, puis on paie les incolores avec le reste.

**Pourquoi ce n'est pas un simple compteur** (le piège nommé par la fiche du lot) : comparer
des totaux (« assez d'unités ? ») accepterait de l'incolore pour un symbole coloré **et**
refuserait une attaque parfaitement légale. Dans le modèle additif retenu par le corpus
(R-9.2, « on compte les unités fournies »), chaque unité porte un type **fixe** : une unité de
type `T` ne peut payer qu'un symbole coloré `T` ou un symbole incolore. Réserver les colorées à
leur couleur ne prive donc jamais un autre symbole coloré, et l'algorithme est à la fois
**complet** (il trouve une combinaison dès qu'il en existe une) et **déterministe** (énergies
dans l'ordre donné, types triés) — ce que le rejeu exige.

## Énergies de base vs spéciales : une affaire de deck, pas de moteur (D10)

Qu'une énergie soit **de base** (fournie illimitée, jamais décomptée de la collection, hors de
la règle des 4) ou **spéciale** (possédée, soumise à la règle des 4) relève de la
**construction du deck**. La **seule source de vérité** est
`apps/api/src/pbm_api/decks/energy.py` (classement) et `.../decks/legality.py` (décompte,
règle des 4) — vérifiés par `apps/api/tests/test_deck_legality.py`. On ne le redit pas dans le
moteur : en jeu, une énergie attachée fournit ce qu'elle fournit, point.

## Les effets d'une énergie spéciale se branchent sur la pile (D9)

Une énergie spéciale peut porter un effet (soin, dégâts supplémentaires, coût de retraite
modifié), décrit par un `EffetEnergie`. `DefinitionEnergie.effets_en_attente(instance_id)` le
transforme en `EffetEnAttente` **empilable** sur la pile d'effets (`pbm_game.effets.pile`),
attribué à l'énergie comme **source** (« à cause de l'Énergie X »). Le *script* de chaque effet
(son résolveur dans le `RegistreEffets`) est livré, scripté et testé, par les lots d'effets : une
énergie dont l'effet n'est pas enregistré est **refusée** à la résolution (D9), jamais jouée de
travers. Ce module ne fait que produire les entrées de pile, fidèlement.

## Défausse d'énergie à la retraite (R-8.2)

Le coût de retraite se paie en défaussant **une énergie par symbole, au choix du joueur** :
c'est `pbm_game.banc.battre_en_retraite` (lot `j-retraite-banc`), qui valide le choix et déplace
les énergies vers la défausse. Rien à ajouter ici — on y renvoie.

## Où c'est écrit dans le code

| Quoi | Fichier |
|---|---|
| Capacité d'une carte Énergie (fourniture, effets) | `apps/game/src/pbm_game/cartes/energie.py` |
| Vérification et paiement expliqué d'un coût | `apps/game/src/pbm_game/combat/cout.py` |
| Classement base/spéciale et légalité en deck (D10) | `apps/api/src/pbm_api/decks/energy.py`, `legality.py` |
| Défausse d'énergie à la retraite (R-8.2) | `apps/game/src/pbm_game/banc/mouvements.py` |
| Tests | `apps/game/tests/test_cartes_energies.py`, `apps/api/tests/test_deck_legality.py` |
