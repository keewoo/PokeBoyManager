# Les Stades — zone partagée, un seul en jeu, effets continus (lot `j-cartes-stades`)

Fiche du **jeu** (moteur `pbm_game`). Le corpus de règles qui fait foi reste `docs/jeu/REGLES.md` ;
cette fiche dit **comment** les Stades sont implémentés et pourquoi.

## Le principe : un Stade n'est jamais une mutation, c'est une source consultée au calcul

Un Stade ne modifie **jamais** l'état des Pokémon quand on le joue. Son effet se **dérive** de ce
qui est en jeu à chaque calcul (`pbm_game.effets.continus.collecter_effets_continus`), exactement
comme un Outil attaché ou un talent. Conséquence directe (critère d'acceptation n°1) : **remplacer
le Stade suffit à faire disparaître son effet** — au calcul suivant, l'ancien producteur n'est plus
consulté. Rien n'est « défacé » : c'est vrai *par construction*. C'est le piège que la fiche du lot
nommait — appliquer l'effet à la pose laisse des traces indélébiles au remplacement.

La zone Stade est **partagée** : `EtatPartie.stade` (la carte) + `EtatPartie.stade_proprietaire`
(qui l'a posée, pour sa défausse). Comme la `cible` d'un effet de Stade est `None` (il n'appartient
à personne, R-3.5), ses effets frappent **les deux camps** (critère n°2).

## Jouer un Stade : la transition `jouer_stade` (R-3.5 / R-5.5)

`pbm_game.effets.stades.appliquer_jouer_stade` (enregistrée dans le `REGISTRE` du journal) :

1. gardes serveur : partie vivante, **joueur actif**, **un seul Stade par tour** (R-5.5, drapeau
   `Tour.stade_joue` — porté par l'état, donc un second Stade est refusé et le drapeau survit à un
   F5), carte réellement **en main** ;
2. la carte quitte la main pour la zone `etat.stade` ;
3. s'il y avait un Stade, il part à la **défausse de son propriétaire** (`stade_proprietaire`) —
   c'est la fin de son effet, par simple disparition de l'état (R-3.5) ;
4. le nouveau propriétaire devient l'auteur ; `EVT_STADE_JOUE` est émis (`joueur`, `ref`, `nom`,
   `carte`, `remplace`, `proprietaire_remplace`).

**R-3.5 « pas deux Stades de même nom »** est portée de façon **autoritaire** par
`FamilleJouerStade` (qui connaît le catalogue, donc les noms) et que `valider` recalcule : un Stade
de même **nom** que celui en jeu n'est pas listé, donc refusé (R-3.5). La transition ajoute un filet
par **référence** (rejeu / sécurité). Aucune restriction de premier tour : un Stade se joue dès le
tour 1 (R-6.2 ne vise que les Supporters).

## Les effets continus : PV et coût de retraite

`EffetContinu` (dans `pbm_game.effets.continus`) porte désormais, en plus des modificateurs de
dégâts et des deltas de PV, un **delta de coût de retraite** (`cout_retraite`). Deux fonctions pures
le servent : `delta_cout_retraite(effets, pokemon)` et `cout_retraite_effectif(base, effets,
pokemon)` (plancher à 0). `FamilleRetraite` liste la retraite au **coût effectif** = coût imprimé +
deltas continus ; sans Stade (registre vide, défaut au jalon J2) c'est le coût imprimé, inchangé.

Les conditions d'un Stade portent sur des **données de catalogue** (« Pokémon de base », « Niveau
2 », « Psykokwak ») que le moteur pur ne lit jamais (D9). Les producteurs sont donc des
**fabriques** qui captent une métadonnée `ref → {stade, nom}` (ce que le service extrait du
catalogue), sur le modèle des talents (`construire_registre_continus`). Le service assemble le
registre continu de la partie (`CatalogueJeu.registre_continus`) depuis les decks ; au jalon J2 il
est vide et ne sera peuplé que lorsqu'une partie réelle jouera ces cartes.

## Les trois Stades réels scriptés (critère n°3)

| Carte | `ref` | Effet (les deux camps) |
|---|---|---|
| **Stade en Liesse** | `sv08-180` | chaque Pokémon **de base** gagne **+30 PV** (R-13.1) |
| **Montagne Gravité** | `sv08-177` | chaque Pokémon de **Niveau 2** **perd 30 PV** |
| **Hôtel « Au paradis des Pokémon »** | `svp-224` | le **coût de retraite** de chaque **Psykokwak** baisse de **1** |

`pbm_game.effets.stades.registre_stades(meta)` renvoie les trois producteurs prêts à fusionner dans
`CatalogueJeu.registre_continus`. Tests : `apps/game/tests/test_cartes_stades.py`.
