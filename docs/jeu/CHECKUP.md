# Pokémon Checkup — `pbm_game.checkup`

> Livré par le lot `j-checkup` (jalon J1). Le code vit dans
> `apps/game/src/pbm_game/checkup/`, plus les primitives de mise K.O. partagées dans
> `apps/game/src/pbm_game/combat/ko.py`. Cette fiche documente **la phase entre les deux
> tours** et son ordre de résolution. Les règles de référence sont dans
> [`REGLES.md`](REGLES.md) §R-11, §R-12, §R-13 ; la machine à tour qui l'encadre est dans
> [`MACHINE-TOUR.md`](MACHINE-TOUR.md).

## Pourquoi

Beaucoup d'effets disent « à la fin du tour » ou « entre les tours ». Sans une phase nommée où
tout se résout dans un **ordre fixé**, ces effets se résolvent dans l'ordre où le code a été
écrit — c'est-à-dire au hasard. Le Pokémon Checkup est cette phase : un ordre, écrit une fois,
que tous les lots d'effets suivants respectent.

## L'ordre de la phase (R-12)

`resoudre_checkup(etat, rng, *, fiches)` enchaîne, dans cet ordre strict :

1. **États spéciaux de l'Actif de chaque joueur**, dans l'ordre **R-12.2** :
   **1) Empoisonné → 2) Brûlé → 3) Endormi → 4) Paralysé**.
2. **Expiration des effets temporaires** « jusqu'à la fin de ce tour » (**R-12.5**), par la
   fenêtre `FENETRE_EXPIRATION_EFFETS` — chaque retrait **journalisé** (`EVT_EFFET_EXPIRE`).
3. **K.O. survenus pendant la phase** (hors attaque, **R-12.4**) : défausse (R-13.2),
   récompenses prises par l'adversaire (R-13.3), puis **promotion demandée** (R-8.7) ou
   **défaite** si le banc est vide (R-8.9/R-14.1).

### L'ordre des deux joueurs

Le joueur **dont le tour s'achève** (`tour.joueur_actif` pendant la phase `checkup`) est résolu
**avant** son adversaire. C'est ce qui rend la suite des tirages (réveil, brûlure) et l'ordre
des événements **déterministes** et rejouables (R-12.2/R-12.4) — et c'est aussi ce qui porte la
paralysie (voir ci-dessous).

## Ce que fait chaque état au Checkup

| État | Effet au Checkup | Pile ou face | Règle |
|---|---|---|---|
| **Empoisonné** | **1 compteur** (10 dégâts) | — | R-11.7 |
| **Brûlé** | **2 compteurs** (20 dégâts) **puis** tirage | **face = guéri** (retire le marqueur) | R-11.4 |
| **Endormi** | aucun dégât | **face = réveil**, pile = reste endormi | R-11.3 |
| **Paralysé** | aucun dégât | — | R-11.6 |

**La paralysie guérit au Checkup *après le tour de son propriétaire*** (R-11.6) : seul l'Actif
du joueur **dont le tour s'achève** est guéri. Un Pokémon paralysé pendant le tour de
l'adversaire reste paralysé pendant son propre tour suivant, et guérit au Checkup qui le suit.
C'est le joueur, pas un compteur de tours, qui tranche — et c'est pour ça que l'ordre des deux
joueurs compte.

Chaque état résolu émet un `EVT_ETAT_CHECKUP` portant `joueur`, `etat`, la `regle` citée, les
`degats` posés, et (brûlure/sommeil) le `pile_ou_face` et `gueri`.

## Le pile ou face est journalisé dans un flux dédié

Le réveil (R-11.3) et la guérison de brûlure (R-11.4) tirent dans `flux_checkup("endormi", jid)`
et `flux_checkup("brule", jid)` — **un flux par état et par joueur** (`pbm_game.rng`). Un Checkup
de plus pour l'un ne décale jamais les tirages de l'autre, et `verifier_journal` recontrôle
chaque tirage a posteriori.

## K.O. hors attaque — le code de victoire ne vit pas que dans l'attaque

Le risque nommé dans la fiche du lot : *oublier que des K.O. arrivent hors des attaques*. Les
primitives de mise K.O. (R-13) vivent donc dans `pbm_game.combat.ko` — **partagées** entre le
Checkup et la future résolution d'attaque :

- `est_ko(compteurs, pv)` — K.O. quand compteurs ≥ PV (R-13.1) ;
- `cartes_a_defausser(pokemon)` — toute la pile d'évolutions, les énergies et l'Outil (R-13.2) ;
- `prendre_recompenses(joueur, n)` — l'adversaire prend ses récompenses (R-13.3).

Au Checkup : l'Actif K.O. laisse la place **vide** (`actif = None`) et un `EVT_PROMOTION_REQUISE`
demande au bon joueur de promouvoir (R-8.7, action `promouvoir` du lot `j-retraite-banc`) ;
banc vide = **défaite** (R-8.9/R-14.1), et un double K.O. des deux derniers Actifs = **égalité**
(R-14.4). L'état `actif = None` avec un banc non vide est un **transitoire** (promotion en
attente), le même que celui qu'attend déjà `promouvoir` ; il se résout avant que le tour suivant
ne commence.

## Le moteur ne devine ni PV ni récompenses (D9)

PV (R-13.1) et nombre de récompenses (marqueur de règle, R-13.3) se lisent **sur la carte, dans
le catalogue** — que le moteur ne connaît pas. L'action système `checkup` les reçoit dans
`params["fiches"]` :

```
{ "<instance_id de la carte au sommet>": {"pv": 100, "recompenses": 2}, ... }
```

que le **service** extrait du catalogue. Une fiche **manquante** pour un Pokémon endommagé, un
PV ≤ 0 ou un nombre de récompenses < 1 font **échouer bruyamment** — jamais un repli « par
défaut 1 » (la panne muette que ce dépôt a déjà payée). Portées par `params`, les fiches sont
dans le journal : le **rejeu** n'a donc pas besoin du catalogue.

## Intégration au journal

`checkup` est une **action système** (`AUTEUR_SYSTEME`), résolue en phase `checkup`, enregistrée
dans le `REGISTRE` des transitions à l'import de `pbm_game.checkup`. Elle n'est **pas** un coup
listé par le générateur d'actions (comme `debut_tour`). La machine à tour (`avancer_phase`) fait
passer en phase `checkup` et ouvre la fenêtre « fin de tour » (effets « au Checkup », R-12.3) ;
le service applique ensuite `checkup`, puis les `promouvoir` éventuels, avant d'ouvrir le tour
suivant.

## Périmètre du lot et ce qu'il débloque

Ce lot (palier 6) livre la **phase ordonnée** et la mécanique de K.O. hors attaque. Les lots
suivants s'y branchent **sans la réécrire** :

- `j-etats-speciaux` (palier 7) — la **pose** des états, la matrice de cumul, la confusion à la
  déclaration d'attaque, l'orientation de la carte ;
- `j-ko-recompenses` (palier 7) — les **conditions de victoire** complètes (plus de récompenses
  à prendre, K.O. simultané détaillé, égalité) au-dessus des primitives de `pbm_game.combat.ko` ;
- `j-effets-architecture` (palier 8) — la pile d'effets, qui remplira la fenêtre d'expiration
  (`FENETRE_EXPIRATION_EFFETS`, vide au jalon J1) et les effets « au Checkup ».
