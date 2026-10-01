# Mises K.O., récompenses et conditions de victoire — `pbm_game.combat.fin`

> Livré par le lot `j-ko-recompenses` (jalon J1). Le code vit dans
> `apps/game/src/pbm_game/combat/fin.py`, au-dessus des primitives de mise K.O. partagées
> (`apps/game/src/pbm_game/combat/ko.py`). Les règles de référence sont dans
> [`REGLES.md`](REGLES.md) §R-13, §R-14, §R-15 ; la mise K.O. hors attaque (poison, brûlure)
> est décrite dans [`CHECKUP.md`](CHECKUP.md), qui appelle le **même** résolveur.

## Pourquoi

La fin d'une partie est le moment où une erreur de moteur coûte le plus cher : c'est là que le
résultat se décide. Deux pièges s'y logent et ce module les ferme :

1. **Le repli silencieux « marqueur inconnu → 1 récompense »** — c'est exactement la panne muette
   que ce dépôt a déjà payée. Le nombre de récompenses se lit sur le **marqueur de règle** de la
   carte (R-13.3/R-13.4), jamais depuis une liste de **noms** ; un marqueur inconnu **échoue
   bruyamment** (R-13.4/R-15.22), jamais « par défaut 1 ».
2. **Le code de victoire qui ne vivrait que dans la résolution d'attaque** — un K.O. survient
   aussi au Checkup (poison, brûlure). Le résolveur `resoudre_kos` est donc **partagé** : le
   Checkup et la future résolution d'attaque l'appellent tous les deux.

## Le marqueur de règle → nombre de récompenses (R-13.3)

`recompenses_pour_marqueur(marqueur)` lit la table **close** `MARQUEUR_RECOMPENSES`, keyée par
**marqueur** (sous-type / Rule Box du catalogue), jamais par nom — le suffixe du nom ne classe
pas une carte (R-13.7 : une Méga-Évolution Pokémon ex finit par « ex » mais donne 3 ; une TAG
TEAM finit par « GX » mais donne 3). Un marqueur **absent** de la table lève `ValueError`.

| Récompenses | Marqueurs (R-15) |
|---|---|
| **1** | `ordinaire`, `radiant` (R-15.9), `break` (R-15.17), `prisme_etoile` (R-15.18), `lv_x` (R-15.20), `etoile` (R-15.21) |
| **2** | `ex` (R-15.1/R-15.16), `tera_ex` (R-15.2), `pokemon_ex` (R-15.14), `m_pokemon_ex` (R-15.15), `gx` (R-15.3), `v` (R-15.4), `vstar` (R-15.6), `legende` (R-15.19) |
| **3** | `mega_ex` (R-15.13), `vmax` (R-15.5), `tag_team` (R-15.7), `v_union` (R-15.8) |

Le service fournit les **fiches** : un mapping `instance_id de la carte au sommet → {"pv": int,
(…)}`, où le nombre de récompenses vient **soit** d'un `marqueur` (préféré, la table en déduit le
nombre), **soit** d'un `recompenses` entier ≥ 1 déjà calculé. `valider_fiches` refuse toute entrée
malformée — PV absurde, ni marqueur ni récompenses, marqueur inconnu — **à la validation**
(eager), même pour un Pokémon qui ne sera jamais K.O. (D9).

## Le résolveur partagé (R-13, R-14)

`resoudre_kos(etat, fiches, ordre) -> (etat, evenements)` :

1. met K.O. **tous** les Pokémon dont les compteurs ont atteint les PV (R-13.1) — Actif **avant**
   banc, le premier joueur de `ordre` avant le second, ordre déterministe et rejouable ; une
   attaque de zone peut en mettre plusieurs K.O. à la fois ;
2. défausse chaque K.O. avec **toute** sa pile d'évolutions, ses énergies et son Outil (R-13.2) ;
3. fait prendre à l'adversaire le nombre de récompenses du marqueur (R-13.3), borné par sa
   réserve ;
4. tranche la fin de partie (voir ci-dessous).

Il émet un `EVT_KO` par K.O., puis **soit** des `EVT_PROMOTION_REQUISE` (la partie continue),
**soit** un `EVT_PARTIE_TERMINEE` (victoire ou égalité).

## Les trois façons de gagner (R-14.1)

| # | Condition | Raison de fin | Où elle est vérifiée |
|---|---|---|---|
| 1 | Prendre sa **dernière** carte récompense après un K.O. | `derniere_recompense` | `resoudre_kos` |
| 2 | L'adversaire n'a **plus de Pokémon** à promouvoir après un K.O. (banc vide, R-8.9) | `plus_de_pokemon` | `resoudre_kos` + `banc.promouvoir` |
| 3 | L'adversaire **ne peut pas piocher** en début de tour (R-14.2) | `pioche_impossible` | `journal.transitions` (`debut_tour`) |

La **troisième** ne découle pas d'un K.O. : elle se vérifie à l'ouverture du tour, pas ici.

Après la passe de K.O., `resoudre_kos` compte les **voies** de victoire de chaque joueur :

- `derniere_recompense` — il a **pris** sa dernière récompense *pendant cette passe* (on gagne en
  prenant la dernière, pas en ayant une réserve déjà vide par ailleurs) ;
- `adversaire_sans_pokemon` — l'adversaire n'a plus ni Actif ni banc, **et** son Actif est tombé
  pendant cette passe (R-14.1 « après un K.O. »).

Puis :

- aucune voie → **promotion demandée** (R-8.7) à chaque joueur dont l'Actif est tombé et qui a du
  banc ;
- une seule voie → ce joueur **gagne** ;
- les **deux** joueurs ont des voies (K.O. simultané, R-13.5) → départage par le **nombre** de
  voies (R-14.5 : « deux voies contre une » tranche) ; à nombre **égal**, la partie est **NULLE**
  (R-14.4/R-16.10 — un double K.O. qui vide les deux réserves est une égalité, jamais « le joueur
  actif gagne »).

L'**abandon** (R-14.3, action `abandonner`) et la **pioche impossible** (R-14.2, action
`debut_tour`) figent la partie de la même façon, chacune dans sa transition.

## Partie terminée, figée (R-14.6)

`terminer(etat, vainqueur, raison, **donnees)` pose `terminee=True`, le `vainqueur` (ou `None`
pour une égalité) et la `raison_fin`, et renvoie l'`EVT_PARTIE_TERMINEE` qui **clôt le journal**.
`appliquer` refuse ensuite **toute** action (garde centrale, en plus de celles des transitions) :
une partie terminée ne rejoue rien, pas même une action mécanique.

Un état terminal peut légitimement porter un **banc non promu sans Actif** (une fin par
récompenses ou un K.O. simultané fige le plateau avant la promotion) : l'invariant R-3.3
(« exactement 1 Actif tant qu'un Pokémon est en jeu ») est donc **exempté quand la partie est
terminée**.

## Périmètre du lot et ce qu'il débloque

Ce lot (palier 7) complète les conditions de victoire au-dessus des primitives de
`pbm_game.combat.ko`. Il débloque notamment `j-cartes-regles-speciales` (ACE SPEC, Radiant,
VSTAR, GX, Prism Star — qui s'appuient sur les marqueurs), `j-fin-effets-compte` (ce qu'une
partie laisse sur le compte) et `j-partie-fin-ui` (l'écran de fin : qui a gagné, pourquoi).
