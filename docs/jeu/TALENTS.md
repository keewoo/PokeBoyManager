# TALENTS.md — Les talents du jeu (lot `j-cartes-talents`, jalon J2)

> Fiche du **jeu** (`docs/jeu/`). Le corpus de règles qui fait foi reste `docs/jeu/REGLES.md` ;
> l'architecture d'effets sur laquelle les talents se branchent est `docs/jeu/EFFETS.md`. Cette
> fiche ne redit pas ces deux-là : elle dit ce qui est **propre aux talents**, et surtout **la
> décision d'annulation mutuelle**.

Un **talent** est un pouvoir imprimé sur un Pokémon (pas une attaque). Le moteur en porte trois
natures, toutes dérivées de ce qui est en jeu — un talent **existe** exactement tant que sa carte
porteuse est en jeu, sans aucun état à tenir ni à défaire (c'est le critère d'acceptation n°2,
vrai *par construction*). Le code vit dans `apps/game/src/pbm_game/effets/talents.py` (le cadre
pur) et `apps/game/src/pbm_game/effets/talents_actives.py` (la transition du talent activé).

## Les trois natures

| Nature | Quand il agit | Sur quoi il se branche |
|---|---|---|
| **continu** | en permanence, banc compris | un producteur d'effets continus (`pbm_game.effets.continus`), *consulté au calcul*, jamais une mutation |
| **déclenché** | à un moment de jeu (début/fin de tour, dégâts, pose, K.O., **entre les tours**…) | un réacteur abonné au **bus** (`pbm_game.effets.bus`) |
| **activé** | une fois par tour, à son tour | une **action de joueur** journalisée (`activer_talent`), suivie **par Pokémon** |

**Un seul portillon** gouverne les trois : `talent_actif(etat, registre, identite)`. Un talent
n'agit que si son Pokémon est **en jeu**, qu'il n'est **pas neutralisé** par un talent-verrou, et
qu'il n'est **pas désactivé** par un état spécial de son porteur (`desactive_si_etat`, « selon la
carte »). Chaque refus est **nommé** (jamais un silence) : pas en jeu, neutralisé par telle carte,
désactivé par tel état.

Un talent peut aussi n'agir **que depuis l'Actif** (`depuis_banc = False`) : au banc, il se tait,
et le portillon le dit.

### Une fois par tour — **par Pokémon, pas par joueur**

Le drapeau `Tour.talents_actives_ce_tour` porte la clé `« identité|nom »` de chaque talent déjà
activé ce tour. Un second usage du **même** talent du **même** Pokémon est refusé ; un **autre**
Pokémon qui porte le même talent reste libre de l'activer. Le drapeau est porté par l'état — donc
sérialisé, donc le refus **survit à un F5** — et remis à vide à chaque tour neuf, comme l'énergie
du tour.

## ⚖️ La décision — l'annulation mutuelle de talents (critère d'acceptation n°1)

**Le cas.** Un talent qui « éteint les talents » (type *Garbodor* / *Garbotoxine*, R-12.3) :
éteint-il **lui-même** ? éteint-il un **autre** talent-verrou adverse ?

**La règle retenue.** Un talent-verrou porte la clause « **sauf lui-même** » — exactement le texte
officiel (« each Pokémon in play has no Abilities, **except Garbotoxin** »). Donc :

- un talent-verrou **n'éteint pas lui-même** ;
- un talent-verrou **n'éteint pas les autres talents-verrous** : **deux verrous coexistent** sans
  s'annuler l'un l'autre ;
- un talent-verrou **éteint**, des **deux** camps, **tous les autres** talents (continus,
  déclenchés, activés).

**Pourquoi celle-là, et pas une autre.** C'est le comportement officiel, et c'est le seul qui ne se
contredise pas : un verrou qui s'éteindrait lui-même cesserait d'éteindre, donc rallumerait ce
qu'il venait d'éteindre, qui le rééteindrait… La clause « sauf lui-même » **brise la récursion** et
rend l'annulation **décidable** en un seul passage : on cherche s'il existe au moins un verrou
*effectif* (en jeu, à sa place, non désactivé par un état), et si oui, on éteint tous les talents
**non-verrous**.

Un verrou n'est mis en échec que par **lui-même** : son porteur quitte le jeu, part au banc s'il
n'agit pas depuis le banc, ou tombe sous un état spécial qui le désactive (un *Garbodor* Endormi
n'éteint plus rien).

Testée explicitement : `test_deux_verrous_ne_s_annulent_pas`,
`test_verrou_endormi_cesse_d_eteindre_les_talents`,
`test_talent_continu_annule_par_un_talent_adverse` (`apps/game/tests/test_cartes_talents.py`).

## Le garde-fou serveur du talent activé sous un verrou

La neutralisation ci-dessus est **dérivée** de l'état (le portillon la recalcule à chaque fois,
avec le registre des talents) : c'est elle qui fait qu'un talent continu ou déclenché éteint ne
contribue rien, et c'est elle que le service consulte pour **proposer** ou non un talent activé.
Côté transition `activer_talent` — qui, pure, ignore le registre des talents — le garde-fou
serveur est le verrou nommé `talents_sans_effet` (`pbm_game.effets.verrous`) : s'il est posé dans
l'état, le coup est refusé en **nommant** la carte responsable.

## Les cinq talents scriptés de référence

Scriptés et testés dans `apps/game/tests/test_cartes_talents.py` (ce que le service fournirait au
moteur depuis le catalogue) :

| Talent | Nature | Ce qu'il fait |
|---|---|---|
| Bouclier Indéfectible (*Dauntless Shield*) | continu | −30 aux dégâts subis (R-10.1) |
| Garbotoxine (*Garbodor*) | continu | éteint les talents (R-12.3), auto-excepté |
| Incisives Travailleuses (*Bibarel*) | activé | piocher 1, une fois par tour (R-5.2) |
| Soin de Camp | déclenché (entre les tours) | soigne 1 marqueur de l'Actif, **depuis le banc** (R-12.3) |
| Forge Ardente | activé | seulement depuis l'Actif, désactivé si Endormi/Paralysé (R-11) |
