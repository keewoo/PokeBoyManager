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

---

# L'écran de fin, le récapitulatif et la revanche — lot `j-partie-fin-ui`

> Jalon J4 (« la partie laisse une trace »). Le moteur décidait déjà de la fin ; ce lot la **dit**
> au joueur, en tire un récapitulatif, et lui propose de recommencer. Code : module pur
> `apps/game/src/pbm_game/journal/recapitulatif.py`, adaptateurs
> `apps/api/src/pbm_api/games/recapitulatif.py` et `.../revanche.py`, écran
> `apps/web/src/components/game/fin-partie.tsx`, libellés `apps/web/src/lib/game/fin.ts`.

## Les huit raisons de fin, et leurs libellés

Il y a **huit** raisons, pas sept : l'égalité en est une. Chacune a un nom court et **trois**
phrases — une par issue (victoire, défaite, partie nulle) — dans le registre `RAISONS_FIN` de
`apps/web/src/lib/game/fin.ts`.

| Raison | Constante moteur | Vainqueur ? |
|---|---|---|
| `derniere_recompense` | `RAISON_DERNIERE_RECOMPENSE` (R-14.1 cas 1) | oui |
| `plus_de_pokemon` | `RAISON_PLUS_DE_POKEMON` (R-14.1 cas 2, R-8.9) | oui |
| `pioche_impossible` | `RAISON_PIOCHE_IMPOSSIBLE` (R-14.2) | oui |
| `abandon` | `RAISON_ABANDON` (R-14.3) | oui |
| `temps_ecoule` | `RAISON_TEMPS_ECOULE` (R-14.6, DJ4) | oui |
| `desertion` | `RAISON_DESERTION` | oui |
| `inactivite` | `RAISON_INACTIVITE` | **non** — ménage, pas une fin méritée |
| `egalite` | `RAISON_EGALITE` (R-14.4/R-14.5) | **non** |

Trois phrases plutôt qu'une neutre, et c'est le point : « tu as pris ta dernière récompense » et
« ton adversaire a pris sa dernière récompense » racontent le même fait sans le même goût. La
consigne du lot est de **ne pas humilier le perdant** — on dit ce qui s'est passé, jamais ce que ça
dit du joueur. Un test verrouille le vocabulaire qu'on s'est interdit
(`apps/web/src/lib/game/fin.test.ts`).

**La parité est gardée en CI**, dans le job `game` :
`apps/game/tests/test_parite_raisons_fin_front.py` relève **statiquement** toutes les constantes
`RAISON_* = "…"` du paquet moteur et les compare aux clés de `RAISONS_FIN`, dans les deux sens. Une
raison ajoutée au moteur sans libellé casse la CI, au lieu d'afficher `plus_de_pokemon` à un enfant
de onze ans. Les libellés ne vivent qu'**à un endroit** : le journal de partie (`journal.ts`) y
délègue aussi, parce que sa propre table avait déjà divergé — elle ignorait l'égalité.

## Le récapitulatif se **recalcule**, il ne s'accumule pas

C'est le risque nommé du lot, et il est concret : le canal temps réel rejoue la partie **depuis le
coup 0** à chaque reconnexion (un F5, un réseau qui cligne). Un compteur incrémenté à l'arrivée des
événements compterait donc deux fois tout ce qui a été rediffusé. D'où trois décisions :

1. **Le calcul est une fonction du journal.** `construire_recapitulatif(entrees, joueurs)` est
   **pure** : même journal → même résultat, et rien à mémoriser. Le journal ne contient chaque coup
   qu'une fois : il n'y a donc rien à doubler.
2. **Il tourne côté serveur**, sur le journal **en base**. Les événements diffusés au client sont
   *projetés par destinataire* : un récapitulatif calculé à l'écran aurait des chiffres différents
   selon qui regarde — ce ne serait pas un récapitulatif. Les deux joueurs voient le même
   (`test_les_deux_joueurs_voient_le_meme_recapitulatif`).
3. **Il ne s'ouvre qu'à la fin** (409 sur une partie en cours), comme le replay : une fenêtre qui
   ne s'ouvre qu'après la fin ne peut pas fuiter pendant.

### Ce que chaque chiffre vaut exactement

Chaque chiffre par joueur vient d'un champ que l'événement porte **explicitement** — jamais d'une
déduction. Attribuer un dégât « à l'adversaire du propriétaire du Pokémon touché » semblerait
naturel et serait faux sur un auto-dégât (confusion R-12.3, recul) : on ne devine pas (D9).

| Chiffre | Sa source dans le journal |
|---|---|
| `coups` | le nombre d'entrées |
| `tours` | le plus grand `numero` d'un `EVT_TOUR_COMMENCE` (une **valeur**, pas un compteur) |
| `duree_s` | l'écart entre le premier et le dernier `horodatage` ; `None` si illisible |
| `degats_infliges` | Σ `degats` des `EVT_ATTAQUE_DECLAREE`, par `joueur` (R-10.9 : total final) |
| `kos_infliges` / `recompenses_prises` | les `EVT_KO`, par leur champ **`par`** (R-13.3) |
| `cartes_jouees` | Objets, Supporters, Stades, Outils, Pokémon posés, évolutions — par `joueur` |
| `energies_attachees` | les `EVT_ENERGIE_ATTACHEE`, par `joueur` |
| `coups_joues` | les entrées dont l'`auteur` est ce joueur |
| `meilleur_coup` | l'entrée dont l'attaque a infligé le plus de dégâts (à égalité : la première) |

Deux lectures à ne pas se tromper :

- **les dégâts d'un état spécial au Checkup** (poison, brûlure) ne sont infligés par personne : ils
  ne sont donc dans la colonne de personne. Ils restent dans le journal, qui les raconte ;
- **`cartes_jouees` exclut les Énergies**, comptées à part. Attacher une Énergie est le geste le
  plus fréquent de la partie (R-5.4, une par tour) : mélangées, elles écraseraient tout le reste.

Le `EVT_KO` est crédité à son champ `par`, et **pas** à l'auteur de l'entrée : un K.O. au Checkup
est écrit par le **système**, et créditer l'auteur afficherait zéro K.O. aux deux joueurs. C'est le
test qui le dit le plus clairement :
`test_les_kos_sont_credites_au_joueur_nomme_par_l_evenement_pas_a_l_auteur`.

Route : `GET /games/{id}/recapitulatif` → `RecapitulatifOut`. Réservée aux **deux joueurs** (404
sinon, jamais 403). Un compte à qui un replay a été *ouvert* n'y a pas droit : il a le journal coup
par coup, qui porte déjà tout — lui ajouter une route n'apporterait rien et agrandirait la surface.

## La revanche : même partie, sans repasser par la file

`POST /games/{id}/revanche` → `RevancheOut`. Le module ne réinvente aucune création de partie : il
relit les deux sièges et rappelle `creer_partie` + `demarrer_partie` (ou
`creer_partie_entrainement`). Quatre décisions lui sont propres.

1. **Le perdant commence** (siège 0). Donner la revanche au vainqueur serait lui offrir deux fois
   l'avantage du premier tour. Sans vainqueur (égalité, inactivité), les sièges sont **échangés** :
   une alternance s'explique, un tirage de plus ne s'expliquerait pas.
2. **Les deux decks sont recontrôlés** par `verifier_lancable` : propriété, scripts D9, possession.
   Une carte vendue entre les deux parties arrête la revanche **en nommant la carte** — jamais une
   partie fantôme sur un deck mort. Et `game_players.deck_id` est `ON DELETE SET NULL` : un siège
   sans deck est un cas nommé (`SiegeSansDeck`, 422), pas un `None` qui filerait jusqu'à une trace
   de pile.
3. **Les deux clics mènent au même plateau.** Les deux joueurs cliquent « Revanche » presque en même
   temps : c'est le cas normal, pas le cas rare. Avant de refuser pour « déjà en partie », on
   cherche une partie en cours **entre ces deux comptes** ; si elle existe, on la rend
   (`deja_creee`, réponse **200** au lieu de 201). L'idempotence vaut mieux qu'une course.
4. **Une revanche d'entraînement reste un entraînement** (DJ7) : même niveau, même adversaire (bot
   ou IA du joueur), par le chemin de l'entraînement — mêmes gardes, même clé IA exigée.

La revanche **ne demande pas** l'accord de l'adversaire : le critère du lot est qu'elle relance
« sans repasser par la file », et une poignée de main serait exactement ce détour. L'adversaire
retrouve la partie là où il retrouve toutes les siennes — le salon la propose en reprise, et le
canal temps réel l'y attend.

## L'écran

`FinPartie` est posé **hors du flux** (`fixed inset-0`, défilement interne) — pas par goût : la page
`/jeu/parties/{id}` ne tolère **aucun** défilement (e2e `plateau-responsive.spec.ts`), et un panneau
en flux normal l'allongerait sans qu'aucun test unitaire ne s'en aperçoive. L'e2e couvre désormais
le cas « partie finie », en paysage et en portrait.

Il porte : le titre de l'issue, la phrase de la raison, le récapitulatif, ce que la partie laisse sur
le compte (série de victoires en cours, calculée hors entraînement), et quatre sorties — **Revanche**,
**Revoir la partie** (le replay), **Retour au salon**, et **Voir le plateau** (qui replie le panneau
en une pastille : l'écran de fin n'emprisonne pas le joueur sur le résumé).

Un refus du serveur sur la revanche est **affiché tel quel** (la raison du serveur : deck vendu,
adversaire déjà en partie). Un bouton qui ne fait rien sans un mot est la panne muette que ce dépôt
a déjà payée quatre fois.

## Ce qui reste à faire ailleurs

La section « Sur ton compte » montre une **série calculée côté écran** depuis la liste des parties du
joueur (`GET /games`). Les statistiques par deck, les badges et la page d'historique dédiée sont le
lot **`j-stats-joueur`**, que celui-ci débloque : tant qu'il n'est pas livré, « Voir mes parties »
mène au salon, qui porte déjà le dernier résultat. On nomme le report, on ne l'approxime pas (D9).
