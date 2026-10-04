# Les Outils Pokémon — un par Pokémon, attaché, défaussé au K.O.

> Fiche du jeu, lot `j-cartes-outils` (jalon J2). Règles de référence : `docs/jeu/REGLES.md`
> (R-3.6, R-3.7, R-5.5, R-13.1, R-13.2). Le moteur vit dans `apps/game` (paquet `pbm_game`) ; il
> est **pur** (ni HTTP, ni base, ni React).

## Ce qu'est un Outil

Un **Outil Pokémon** (`trainer_type = Tool`) s'attache à **un** Pokémon en jeu et agit **tant
qu'il reste attaché**. Les règles qui le gouvernent :

- **R-3.7** — au plus **un Outil par Pokémon** (règle de référence du corpus actuel).
- **R-5.5** — on joue **autant d'Outils qu'on veut par tour** (comme un Objet) : aucun drapeau de
  tour, contrairement au Supporter ou au Stade.
- **R-13.2** — un K.O. défausse le Pokémon **avec son Outil** (déjà porté par
  `pbm_game.combat.ko.cartes_a_defausser` ; ce lot en dépend, ne le réécrit pas).
- **R-13.1** — les **PV supplémentaires** d'un Outil déplacent le **seuil de K.O.**, jamais les
  compteurs déjà posés ; leur retrait peut donc provoquer un **K.O. immédiat**.

## Comment c'est implémenté

L'effet d'un Outil n'existe **nulle part** dans l'état : il se **dérive** de l'Outil attaché à
chaque calcul, exactement comme un Stade (`docs/jeu/STADES.md`). Le cadre d'effets continus
(`pbm_game.effets.continus`) relit `pokemon.outil` à chaque calcul (`collecter_effets_continus`) ;
retirer l'Outil le fait disparaître de l'état, donc son effet s'évanouit **sans rien défaire**.

| Pièce | Où | Rôle |
|---|---|---|
| `attacher_outil` | `pbm_game/effets/outils.py` | coup du joueur actif : l'Outil quitte la main → un Pokémon (Actif ou banc), R-3.7/R-5.5 |
| `retirer_outil` | `pbm_game/effets/outils.py` | retrait par un effet : l'Outil → défausse du propriétaire (R-13.2), **K.O. immédiat** résolu (R-13.1) |
| `fiches_avec_seuils_continus` | `pbm_game/effets/continus.py` | construit le **PV effectif** (imprimé + deltas continus) pour `resoudre_kos` — un seul point de câblage pour le service |
| producteurs d'Outils | `pbm_game/effets/outils.py` | les Outils réels, en `ProducteurContinu` liés à la métadonnée catalogue |

Le **K.O. immédiat au retrait** suit exactement le patron de la résolution d'attaque : la
transition appelle `resoudre_kos(etat, params["fiches"], ordre)`, où `fiches` porte le **PV
effectif post-retrait** fourni par le service — donc le K.O. se **rejoue** sans catalogue.

## Les trois Outils réels (le catalogue de jeu n'en enrichit que trois)

Le catalogue de jeu (sous-ensemble enrichi par les lots `j-effets-catalogue-*`) ne contient à ce
jour que **trois `ref` d'Outils**, soit **deux cartes distinctes** :

| `ref` | Carte | Effet scripté |
|---|---|---|
| `B2-147`, `B2-234` | **Protective Poncho** (deux impressions) | tant que le porteur est **au banc**, **prévient tous les dégâts** (modificateur de défense `fixe 0`) |
| `B2-148` | **Metal Core Barrier** | le porteur **Metal** subit **−50 dégâts** des attaques adverses (modificateur de défense `−50`) |

« Prévient tous les dégâts » porte sur les **dégâts** (tout dégât passe par `resoudre_degats`), pas
sur les compteurs posés directement (« placez N compteurs », R-10.6), qui ne sont pas des dégâts :
le texte est respecté sans approximation (D9).

### La clause « se défausse à la fin du tour adverse » de Metal Core Barrier

Ce n'est **pas** un effet continu : c'est un retrait planifié. Le moteur fournit le retrait
(`retirer_outil`) ; **le service en orchestre l'instant** (il émet un `retirer_outil` à la fin du
tour adverse, comme il émet le `checkup` entre les tours). Le moteur reste pur ; aucune approximation
(D9) : la carte est complètement spécifiée par (producteur continu + retrait planifié).

## Ce qui reste au service (intégration, hors moteur pur)

Comme pour les Stades et les talents (`docs/jeu/STADES.md`), le moteur livre les **producteurs** ;
le **service** (`apps/api`) les assemble et les câble, le jour où une partie réelle joue ces cartes :

- fusionner `registre_outils(meta)` dans `CatalogueJeu.registre_continus` (avec `meta` portant le
  `type` de chaque Pokémon porteur, pour Metal Core Barrier) ;
- câbler les **modificateurs continus** dans la résolution d'attaque (`combat/attaque.py` ne les
  consulte pas encore — même état que les Stades) ;
- construire les `fiches` de `resoudre_kos` avec `fiches_avec_seuils_continus` (seuil effectif),
  pour l'attaque **comme** pour le retrait d'Outil ;
- émettre le `retirer_outil` d'auto-défausse de Metal Core Barrier à la fin du tour adverse ;
- surfacer le coup `attacher_outil` dans les actions légales (une `FamilleAttacherOutil`, sur le
  modèle de `FamilleAttacherEnergie`) — non livré ici, le coup se joue déjà par la transition.
