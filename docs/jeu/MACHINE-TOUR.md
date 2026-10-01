# Machine à tour — `pbm_game.tour`

> Livré par le lot `j-machine-tour` (jalon J1). Le code vit dans
> `apps/game/src/pbm_game/tour/`, plus deux transitions dans
> `apps/game/src/pbm_game/journal/transitions.py` (`debut_tour`, `declarer_attaque`). Cette
> fiche documente **le déroulé d'un tour**, les six contraintes, et les fenêtres de
> déclenchement — tout est porté par l'état, donc sérialisé, donc repris après un F5.

## Pourquoi

Les actions existent (lot `j-actions-legales`) mais rien ne disait **quand** chacune a le
droit de survenir. La machine à tour est ce squelette : elle enchaîne les phases, tient les
drapeaux « une fois par tour », traite la pioche impossible comme une défaite, et ouvre les
fenêtres où les effets (talents, Dresseurs, états au Checkup) se brancheront plus tard.

**Le serveur tient les contraintes seul.** L'interface ne fait que griser ce que ces
fonctions refusent ; elle ne réécrit aucune règle (risque nommé dans la fiche du lot).

## Le déroulé d'un tour (R-5.1)

```
          debut_tour (système)                  declarer_attaque  OU  avancer_phase
pioche ─────────────────────────▶ principale ───────────────▶ attaque ──────────────▶ checkup
   │         pioche 1 (R-5.2)        avancer_phase                                         │
   │         fenêtre DÉBUT                                                       fenêtre FIN│
   │                                                                     avancer_phase ◀────┘
   └◀──────────────────────── tour suivant : numéro+1, joueur adverse, drapeaux à zéro
```

- **Début de tour** — l'action **système** `debut_tour` (pas un coup libre du joueur, R-5.2)
  pioche 1 carte obligatoirement, ouvre la fenêtre « début de tour », puis passe en phase
  principale. **Si la pioche est vide, c'est une défaite** (R-14.2, voir plus bas), pas une
  exception : la partie se fige et l'adversaire gagne.
- **Phase principale** — actions libres (R-5.3) : les coups que proposera le générateur
  d'actions une fois le catalogue là (poser, évoluer, attacher, Dresseurs, talents, retraite).
- **Déclarer une attaque termine le tour** (R-5.7) — **même sans aucun dégât** (R-5.8) : la
  transition `declarer_attaque` fait passer directement au Checkup. Au jalon J1 elle ne
  mécanise **que** la fin de tour ; coût, dégâts, faiblesse et résistance arrivent avec
  `j-degats-resolution` (D9 — on n'approxime rien, donc le coup d'attaque complet n'est pas
  encore *listé* par le générateur).
- **Passage de tour** — depuis le Checkup, `avancer_phase` ouvre le tour suivant : numéro + 1,
  joueur actif adverse, et un `Tour` neuf — donc **tous les drapeaux et l'ensemble « entrés en
  jeu ce tour » remis à zéro**.

> ⚠️ `avancer_phase` reste une transition **mécanique** permissive (le simulateur du journal
> s'en sert pour parcourir les phases) : elle n'effectue **pas** la pioche de début de tour.
> Seul `debut_tour` quitte proprement la phase de pioche. Le générateur d'actions ne propose
> donc **pas** « avancer la phase » pendant la pioche (il renvoie au `debut_tour` système,
> R-5.2).

## Les six contraintes de tour — `pbm_game.tour.contraintes`

Chacune rend un `Verdict` : l'accord, ou un refus qui **cite la règle** qui bloque (jamais un
refus muet). Les lots de résolution appellent ces gardes avant d'appliquer leur action, puis
lèvent le drapeau correspondant via `pbm_game.tour.drapeaux`.

| Garde | Règle(s) | Refuse quand… |
|---|---|---|
| `peut_attacher_energie(tour)` | R-5.4 | une énergie a déjà été attachée ce tour |
| `peut_jouer_supporter(tour)` | R-5.5, **R-6.2** | un Supporter a déjà été joué ce tour **ou** c'est le 1er tour du joueur qui commence |
| `peut_battre_retraite(tour)` | R-5.6 | une retraite a déjà eu lieu ce tour |
| `peut_evoluer(tour, base_id)` | **R-6.5**, R-7.3 | c'est le premier tour du joueur **ou** ce Pokémon est entré en jeu ce tour-ci |
| `attaque_permise(tour)` | **R-6.1** | c'est le premier tour du joueur qui commence |

**La règle du premier tour se dérive du seul numéro de tour** (invariant du moteur : le tour 1
est celui du joueur qui commence, R-4.7, puis alternance) :

- **premier tour du joueur qui commence** = numéro **1** → pas d'attaque (R-6.1), pas de
  Supporter (R-6.2) ;
- **premier tour de chaque joueur** = numéro **1 ou 2** → pas d'évolution (R-6.5) ;
- le joueur qui commence **pioche** normalement (R-6.3) et **peut attacher une énergie** (R-6.4)
  à son premier tour — aucune garde ne les bloque.

Les conditions qui ne relèvent pas du tour (coût de retraite R-8.2, retraite interdite sous
Sommeil/Paralysie R-8.4, coût d'attaque R-9, évolution possédée R-7.4) sont **laissées aux
lots qui disposent du catalogue** — elles ne sont pas approximées ici.

## Identité d'un Pokémon (R-7.3)

« Ce Pokémon est-il entré en jeu ce tour ? » se suit par l'`instance_id` de sa **carte de
base** (`cartes[0]`), qui ne change pas à l'évolution (R-7.1) — `identite_pokemon(pokemon)`.
`Tour.entres_en_jeu_ce_tour` est l'ensemble de ces identités ; `marquer_entree_en_jeu` l'y
ajoute (quand un Pokémon sera réellement posé, dans un lot ultérieur), et l'ensemble se vide
au tour suivant.

## Pioche impossible = défaite (R-14.2)

Vérifiée **au bon moment** — au début du tour, dans `debut_tour` — et non en exception : si le
joueur actif ne peut pas piocher (pioche vide), la partie se fige (`terminee`), l'adversaire
devient vainqueur, la raison est `pioche_impossible`, et la phase **n'avance pas**. Un
événement `partie_terminee` porte `vainqueur`, `raison` et `perdant`.

## Fenêtres de déclenchement — `pbm_game.tour.fenetres`

Entre deux actions, le moteur ouvre des **fenêtres** où des effets devront se déclencher :
`FENETRE_DEBUT_TOUR` (après la pioche, R-5.1) et `FENETRE_FIN_TOUR` (à l'entrée du Checkup,
R-12.1). `declencher(etat, fenetre, rng)` applique les déclencheurs enregistrés dans
`DECLENCHEURS` et renvoie `(etat, evenements)`.

**Au jalon J1, `DECLENCHEURS` est vide** : le squelette est câblé, la pile d'effets le
remplira (lots `j-checkup`, `j-degats-resolution`…), exactement comme les transitions
s'enregistrent dans `journal.transitions.REGISTRE`. Une fenêtre sans déclencheur ne produit
**rien** — l'absence réelle d'effet, documentée et testée, pas un repli silencieux. Demander
une fenêtre **inconnue** lève (jamais approximée).

## Ce qui est porté par l'état (repris après un F5)

Tout vit sur `Tour` (figé, sérialisable) : `numero`, `phase`, les trois drapeaux
(`energie_posee`, `supporter_joue`, `retraite_faite`) et `entres_en_jeu_ce_tour`. Le
round-trip `depuis_json(vers_json(etat)) == etat` les conserve ; un ancien JSON sans
`entres_en_jeu_ce_tour` se relit avec un ensemble vide (rétrocompatible, pas de
`schema_version` incrémentée car la lecture reste compatible).

## Architecture — pourquoi deux sous-modules séparés des transitions

- `pbm_game.tour.drapeaux` — prédicats bruts et marqueurs, **sans** dépendance à
  `pbm_game.actions` : c'est ce qui permet à `journal.transitions` de l'importer sans créer
  de cycle avec le générateur d'actions.
- `pbm_game.tour.contraintes` — les six contraintes en `Verdict` motivés ; **importé depuis
  son sous-module** (`from pbm_game.tour.contraintes import …`) et volontairement pas
  ré-exporté par `pbm_game.tour.__init__`, pour la même raison de cycle.
- `debut_tour` et `declarer_attaque` sont des **transitions journalisées** : elles vivent avec
  les autres dans `journal.transitions.REGISTRE` et ouvrent ici les fenêtres correspondantes.

## Ce que ce lot débloque

- `j-checkup` — la phase entre les deux tours : l'ordre exact de résolution (la fenêtre de fin
  de tour est son point d'ancrage) ;
- `j-degats-resolution` — coût, dégâts, faiblesse, résistance (enregistrera le vrai coup
  d'attaque jouable dans le générateur) ;
- `j-retraite-banc` — banc, retraite et promotion (consomme `peut_battre_retraite`).
