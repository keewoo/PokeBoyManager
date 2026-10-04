# Cartes Objet — ce que le moteur sait jouer (lot `j-cartes-objets`, jalon J2)

> Fiche du **jeu**. Les Objets sont la moitié d'un deck moderne ; ce lot les rend jouables sans
> code spécifique par carte — tout passe par le langage d'effets (`docs/jeu/DSL.md`) et le registre
> `card_scripts` (`docs/jeu/COMPILATION.md`). Un Objet dont l'effet n'est pas exprimable dans le
> vocabulaire fermé reste refusé à la construction du deck (D9).

## Jouer un Objet (R-5.5)

- Action `jouer_objet` (`pbm_game.effets.objets`) : coup de la **phase principale** du joueur
  actif, jouable **autant de fois qu'on veut** (contrairement au Supporter, R-5.5). La carte quitte
  la main pour la **défausse**, puis son script DSL se résout.
- Généré et validé par `FamilleJouerObjet` (`pbm_game.actions.familles_jeu`), à partir d'un
  `CatalogueJeu.objets` (`ref → DefinitionObjet` : nom + `Programme` validé), fourni par le service
  depuis `card_scripts`.
- **Un Objet sans cible valide n'est pas listé**, et son refus cite la raison :
  `pbm_game.effets.dsl.jouabilite.programme_jouable(etat, programme, ctx)` vérifie, sur la main
  *sans* l'Objet (son texte ne peut pas se défausser lui-même), que le coût est payable et qu'au
  moins un effet pourrait agir. Il ignore l'issue des pile-ou-face et des `si` (une carte comme
  *Roller Skates* reste jouable même si la pièce pourrait tomber sur pile).
- Pendant une **demande de décision** (`etat.resolution`), la partie est en pause : aucun Objet
  n'est proposé, et la garde centrale d'`appliquer` refuse de toute façon tout coup sauf la réponse,
  son expiration et l'abandon.

## L'appât — échange forcé de l'Actif adverse (R-8.8)

L'appât (type *Gust of Wind*, *Pokémon Catcher*) sort du banc adverse un Pokémon pour le mettre au
front. Il s'exprime avec la primitive `changer_actif` du DSL, sélecteur `proprietaire: adversaire`,
`zone: banc` (souvent enveloppée d'un `choisir`, le joueur désignant la cible) :

- **échange forcé** (R-8.8) : il ne consomme **ni** la retraite du tour **ni** d'énergie (le DSL ne
  touche ni `tour` ni les énergies), et reste valable même si l'Actif échangé est **Endormi ou
  Paralysé** (R-16.12) ;
- l'Actif qui **descend** est nettoyé de ses états spéciaux (R-8.6), par la porte partagée
  `soigner_etats_speciaux` ; il garde énergies, Outil et compteurs ;
- **banc adverse vide** : l'effet ne fait rien et le **dit** (`EVT_EFFET_SANS_CIBLE`, ou un
  `choisir` qui journalise « 0 choisi »). Jamais un repli muet.

### Le passage par le bus (le piège)

L'appât amène souvent au front un Pokémon porteur d'un talent « quand ce Pokémon devient Actif… ».
Sans passage par le bus d'événements, ces déclencheurs seraient oubliés. Le mécanisme :

1. `changer_actif` **note** chaque passage dans `ResultatProgramme.devenus_actifs`
   (`[(joueur, identité)]`) — le DSL reste **pur**, il ne publie pas lui-même ;
2. la transition `jouer_objet` reporte cette liste dans `EVT_OBJET_JOUE.devient_actif` ;
3. l'orchestrateur (qui seul connaît les réacteurs des cartes en jeu) appelle
   `pbm_game.effets.bus.publier_devient_actif(etat, devenus, bus, registre, rng)`, qui publie
   `EJ_DEVIENT_ACTIF` et résout la pile des réactions.

> **Reste à brancher** (hors moteur pur) : le fil `bus → appliquer` pour que les réactions
> `devient_actif` soient rejouées pendant le replay, et l'injection d'une `strategie_demande` dans
> `jouer_objet` pour que le choix de la cible d'un appât devienne une vraie demande (comme pour les
> attaques). Le mécanisme et ses tests existent ; le câblage service est le suivi naturel, au même
> titre que le bus n'est pour l'instant branché que via les fenêtres de la machine à tour.

## Les familles couvertes (≥ 3 cartes réelles chacune, testées)

| Famille | Primitive(s) | Cartes réelles scriptées |
|---|---|---|
| Recherche dans la pioche | `chercher` (+ coût `defausser`) | Great Ball, Ultra Ball, Quick Ball |
| Pioche | `piocher`, `choisir`, `pile_ou_face` | Bicycle, Acro Bike, Roller Skates |
| Soin | `soigner`, `retirer_etat` | Potion, Moomoo Milk, Full Heal |
| Changement d'Actif de son côté | `changer_actif` (`proprietaire: moi`) | Switch, Switch Cart, Escape Rope |
| Appât | `changer_actif` (`proprietaire: adversaire`) | Gust of Wind, Pokémon Catcher, Pokémon Reversal |

Non couverte à ≥ 3 cartes : **déplacement d'énergie** (`deplacer`) — *Energy Switch* est le seul
Objet courant qui se mette proprement dans cette forme ; la famille n'est pas revendiquée faute de
trois cartes réelles, et l'attribut « retrait d'outil » attend une primitive dédiée (aucune du
vocabulaire fermé ne retire un Outil attaché, D9) : à traiter dans un lot ultérieur.

Scripts et tests : `apps/game/tests/test_cartes_objets.py`,
`apps/game/tests/test_effets_devient_actif.py`.
