# Backlog du jeu — plateau, moteur de règles et parties

> GÉNÉRÉ par `docs/roadmap/jeu/build-jeu.py` depuis `docs/roadmap/jeu/plan/`. Ne pas éditer à la main.
> Version 1.0 — 2026-09-21 — 67 lots.

**Objet.** Deux joueurs s'affrontent en ligne avec les cartes qu'ils possèdent vraiment : recherche d'un adversaire, choix du deck, mise en place, partie au tour par tour sur un plateau animé, puis une fin de partie qui laisse une trace sur le compte. Le moteur applique les règles officielles et sait jouer les cartes — attaques, défense, appâts, Dresseurs, talents, états spéciaux — sans jamais approximer un effet qu'il ne connaît pas.

**Pourquoi une section à part.** Ce plan n'a ni date de début ni date de fin : le jeu est la partie la plus incertaine du produit, et une date y serait une fiction. L'ordre est donné par les dépendances entre lots (palier calculé), et l'avancement se lit en jalons fonctionnels — « une partie honnête tient debout », « toutes les cartes sont vraiment jouées », etc. Le plan daté du produit (docs/roadmap/roadmap.json) reste la référence pour tout le reste.

## Principes

- **Le serveur fait autorité.** Le client n'est qu'un écran : il n'apprend jamais la main de l'adversaire ni l'ordre de la pioche, et toute action qu'il propose est rejouée et validée côté serveur.
- **Un effet non implémenté n'est jamais approximé** (D9). Une carte dont l'effet n'est pas scripté et testé est refusée à la construction du deck, en disant pourquoi. Le jeu préfère dire « je ne sais pas jouer cette carte » que de la jouer de travers.
- **Tout est rejouable.** Une partie est un état initial, une graine d'aléatoire et un journal d'actions numéroté. Rejouer le journal doit redonner exactement le même état — c'est ce qui fait tenir la reprise après un F5, le replay, le support et l'anti-triche.
- **Le moteur ne connaît ni HTTP ni React.** Fonctions pures, état sérialisable, aucune entrée/sortie : c'est la seule façon de le tester par milliers de cas et de le faire jouer par des bots.
- **L'interface ne décide de rien.** Elle affiche les actions que le moteur déclare légales, et affiche la raison quand un coup est refusé. Aucune règle n'est réécrite côté écran.
- **Le jeu est celui d'un enfant de onze ans.** Lisible sans connaître les règles, animé, sonore, indulgent : on peut annuler avant de valider, on comprend pourquoi un coup est interdit, et on n'attend jamais devant un écran muet.

## Comment lire ce plan

- **Palier** : rang calculé depuis les dépendances. Palier 0 = rien devant. Deux lots du même palier peuvent avancer **en parallèle** s'ils sont dans des couloirs différents.
- **Jalon** : ce que le jeu sait faire quand le lot est livré. C'est l'avancement qu'on montre à JF, à la place d'une date.
- **Couloir** : un couloir porte un lot à la fois, dans son propre worktree, sur la machine indiquée.
- **Taille** : S ≈ une session, M ≈ deux à trois, L ≈ une semaine de couloir. Aucune date n'en est déduite.

| Couloir | Machine | Rôle |
|---|---|---|
| `J-MOT` | devAI | Moteur de règles (Python pur), tests de règles. |
| `J-SRV` | devAI | Service de parties, temps réel, horloges, autorité et anti-triche. |
| `J-EFF` | chimera | Langage d'effets, scripts de cartes, couverture du catalogue (gros volume, IA). |
| `J-UI` | chimera | Plateau, interactions, décisions, journal, écrans de partie. |
| `J-GFX` | chimera | Assets, animations, effets typés, décors, son (GPU disponible). |
| `J-QUA` | chimera | Simulation, e2e Playwright à deux navigateurs, charge, observabilité. |

| Piste | Nom | Ce qu'elle couvre |
|---|---|---|
| `R` | Règles & moteur | L'état d'une partie, le tour, le combat, les récompenses — le cœur pur, sans réseau ni écran. |
| `E` | Effets & cartes | Le langage d'effets, sa pile de résolution, et la traduction du catalogue en cartes réellement jouables. |
| `S` | Serveur de parties | Appariement, session de partie, temps réel, horloges, reprise, anti-triche. |
| `U` | Interface de jeu | Le plateau, les interactions, les fenêtres de décision, le journal lisible, la fin de partie. |
| `G` | Graphisme & animations | Ma photo ou l'image officielle, les effets d'attaque par type, les apparitions, les décors, le son. |
| `C` | Compte & progression | Ce qu'une partie laisse : historique, statistiques, classement privé, badges. |
| `Q` | Qualité & exploitation | Cas de règles, bots de simulation, e2e à deux navigateurs, charge, observabilité, sécurité. |

## Roadmap — cinq jalons, aucune date

### J1 — Deux joueurs jouent une partie honnête

_Une partie complète se joue de bout en bout entre deux navigateurs, avec des Pokémon, des énergies et des attaques simples — sans Dresseur, sans talent, sans état spécial. Laid mais juste : les règles sont appliquées, la partie reprend après un F5, et le vainqueur est le bon._

**Preuve attendue.** Une partie test jouée en entier à deux navigateurs, rejouable depuis son journal, gagnée par les six récompenses.

**28 lots**, poids 50 (S=1, M=2, L=3), paliers 0 → 14. Les jalons se chevauchent : pendant que l'interface se construit, les cartes se scriptent dans un autre couloir. Un jalon est atteint quand son dernier lot est livré.

| Palier | Lot | Titre | Piste | Couloir | Prio | Taille | Après |
|---|---|---|---|---|---|---|---|
| 0 | [`j-regles-reference`](#j-regles-reference) | Corpus de règles de référence : la version des règles qui fait foi, écrite et citée | R | `J-MOT` | P0 | M | — |
| 1 | [`j-modele-etat`](#j-modele-etat) | État d'une partie : zones, attachements, compteurs, et vues par joueur | R | `J-MOT` | P0 | L | `j-regles-reference` |
| 2 | [`j-aleatoire-determinisme`](#j-aleatoire-determinisme) | Aléatoire reproductible : mélange, pile ou face, et graine vérifiable | R | `J-MOT` | P0 | S | `j-modele-etat` |
| 3 | [`j-journal-actions`](#j-journal-actions) | Journal d'actions : la partie est sa suite de coups, pas son état | R | `J-MOT` | P0 | M | `j-aleatoire-determinisme` |
| 4 | [`j-actions-legales`](#j-actions-legales) | Générateur d'actions légales : ce qui est jouable, et pourquoi le reste ne l'est pas | R | `J-MOT` | P0 | M | `j-journal-actions` |
| 5 | [`j-machine-tour`](#j-machine-tour) | Déroulé d'un tour : phases, contraintes du tour, et fin de tour | R | `J-MOT` | P0 | M | `j-actions-legales` |
| 6 | [`j-checkup`](#j-checkup) | Phase entre les deux tours : l'ordre exact de résolution | R | `J-MOT` | P0 | S | `j-machine-tour` |
| 6 | [`j-degats-resolution`](#j-degats-resolution) | Attaque et dégâts : coût, faiblesse, résistance, modificateurs | R | `J-MOT` | P0 | M | `j-machine-tour` |
| 6 | [`j-retraite-banc`](#j-retraite-banc) | Banc, retraite et promotion : le Pokémon actif change de place | R | `J-MOT` | P0 | S | `j-machine-tour` |
| 7 | [`j-cartes-pokemon`](#j-cartes-pokemon) | Cartes Pokémon : base, évolutions, marqueurs de règle | E | `J-EFF` | P0 | M | `j-degats-resolution`, `j-retraite-banc` |
| 7 | [`j-etats-speciaux`](#j-etats-speciaux) | États spéciaux : Empoisonné, Brûlé, Endormi, Paralysé, Confus | R | `J-MOT` | P0 | M | `j-retraite-banc`, `j-checkup` |
| 7 | [`j-ko-recompenses`](#j-ko-recompenses) | Mises K.O., récompenses et conditions de victoire | R | `J-MOT` | P0 | M | `j-degats-resolution` |
| 8 | [`j-cartes-energies`](#j-cartes-energies) | Énergies : de base fournies, spéciales possédées | E | `J-EFF` | P0 | M | `j-cartes-pokemon` |
| 8 | [`j-partie-service`](#j-partie-service) | Service de parties : créer, persister, reprendre, expirer | S | `J-SRV` | P0 | M | `j-journal-actions`, `j-cartes-pokemon` |
| 8 | [`j-tests-regles`](#j-tests-regles) | Batterie de cas de règles : la table qui dit si le moteur a raison | Q | `J-MOT` | P0 | M | `j-regles-reference`, `j-ko-recompenses` |
| 9 | [`j-autorite-vues`](#j-autorite-vues) | Autorité du serveur : le client ne voit que ce qu'il a le droit de voir | S | `J-SRV` | P0 | M | `j-partie-service` |
| 9 | [`j-file-attente`](#j-file-attente) | Recherche d'un adversaire : file d'attente privée et appariement | S | `J-SRV` | P0 | M | `j-partie-service` |
| 10 | [`j-invitations`](#j-invitations) | Inviter quelqu'un à jouer : par pseudo ou par lien | S | `J-SRV` | P1 | S | `j-file-attente` |
| 10 | [`j-temps-reel`](#j-temps-reel) | Canal temps réel : diffusion des coups, reconnexion et reprise après F5 | S | `J-SRV` | P0 | M | `j-autorite-vues` |
| 11 | [`j-lancement-partie`](#j-lancement-partie) | Lancement : choix du deck, contrôle, prêt à jouer, tirage au sort | S | `J-SRV` | P0 | S | `j-invitations`, `j-aleatoire-determinisme` |
| 11 | [`j-salon-partie`](#j-salon-partie) | Salon de jeu : jouer, inviter, reprendre, s'entraîner | U | `J-UI` | P0 | S | `j-file-attente`, `j-invitations` |
| 11 | [`j-timer`](#j-timer) | Horloges : par tour, par partie, par décision — et ce qui se passe à l'expiration | S | `J-SRV` | P0 | M | `j-temps-reel`, `j-effets-choix` |
| 12 | [`j-deconnexion-abandon`](#j-deconnexion-abandon) | Déconnexion, abandon, désertion : une partie ne reste jamais suspendue | S | `J-SRV` | P1 | S | `j-timer` |
| 12 | [`j-initialisation`](#j-initialisation) | Mise en place : mélange, main de sept, mulligans, actif et banc face cachée, six récompenses | S | `J-MOT` | P0 | M | `j-lancement-partie`, `j-cartes-pokemon` |
| 12 | [`j-plateau-layout`](#j-plateau-layout) | Plateau : la table de jeu, du grand écran au téléphone | U | `J-UI` | P0 | L | `j-temps-reel`, `j-salon-partie` |
| 13 | [`j-plateau-etat-visuel`](#j-plateau-etat-visuel) | Lire le plateau d'un coup d'œil : dégâts, énergies, états, récompenses | U | `J-UI` | P0 | M | `j-plateau-layout` |
| 13 | [`j-plateau-interactions`](#j-plateau-interactions) | Jouer un coup : cibles valides, annulation, confirmation | U | `J-UI` | P0 | M | `j-plateau-layout`, `j-actions-legales` |
| 14 | [`j-plateau-journal`](#j-plateau-journal) | Journal de partie : ce qui vient de se passer, en français | U | `J-UI` | P0 | S | `j-plateau-etat-visuel` |

### J2 — Toutes les cartes du deck sont vraiment jouées

_Objets, Supporters, Stades, Outils, talents, états spéciaux, appâts, attaques à effet, énergies spéciales : ce que la carte dit, le moteur le fait. Et ce qu'il ne sait pas faire, il le refuse au deck au lieu de l'inventer._

**Preuve attendue.** Un deck entièrement construit depuis la collection d'Aymeric est déclaré jouable, et chacune de ses cartes a un script testé.

**15 lots**, poids 29 (S=1, M=2, L=3), paliers 8 → 14. Les jalons se chevauchent : pendant que l'interface se construit, les cartes se scriptent dans un autre couloir. Un jalon est atteint quand son dernier lot est livré.

| Palier | Lot | Titre | Piste | Couloir | Prio | Taille | Après |
|---|---|---|---|---|---|---|---|
| 8 | [`j-effets-architecture`](#j-effets-architecture) | Pile d'effets et déclencheurs : l'architecture qui accueille toutes les cartes | E | `J-EFF` | P0 | L | `j-checkup`, `j-ko-recompenses` |
| 9 | [`j-cartes-outils`](#j-cartes-outils) | Outils Pokémon : un par Pokémon, attaché, défaussé au K.O. | E | `J-EFF` | P1 | S | `j-effets-architecture` |
| 9 | [`j-cartes-stades`](#j-cartes-stades) | Stades : un seul en jeu, des effets qui s'appliquent aux deux joueurs | E | `J-EFF` | P1 | S | `j-effets-architecture` |
| 9 | [`j-effets-dsl`](#j-effets-dsl) | Langage d'effets : décrire ce que fait une carte, sans écrire de code par carte | E | `J-EFF` | P0 | L | `j-effets-architecture` |
| 10 | [`j-cartes-attaques-effets`](#j-cartes-attaques-effets) | Attaques à effet : pile ou face, dégâts variables, blocages, états infligés | E | `J-EFF` | P0 | M | `j-effets-dsl`, `j-etats-speciaux` |
| 10 | [`j-cartes-regles-speciales`](#j-cartes-regles-speciales) | Règles de cartes particulières : ACE SPEC, Radiant, VSTAR, GX, Prism Star | E | `J-EFF` | P1 | S | `j-effets-dsl`, `j-ko-recompenses` |
| 10 | [`j-effets-catalogue-compilation`](#j-effets-catalogue-compilation) | Du catalogue aux cartes jouables : compilation, versions et errata | E | `J-EFF` | P0 | L | `j-effets-dsl`, `j-cartes-pokemon` |
| 10 | [`j-effets-choix`](#j-effets-choix) | Demandes de décision : quand le moteur doit attendre un joueur — y compris l'adversaire | E | `J-EFF` | P0 | M | `j-effets-dsl` |
| 10 | [`j-simulation-bots`](#j-simulation-bots) | Bots de simulation : des milliers de parties pour débusquer les blocages | Q | `J-QUA` | P0 | M | `j-tests-regles`, `j-effets-dsl` |
| 11 | [`j-cartes-objets`](#j-cartes-objets) | Cartes Objet, dont les appâts qui forcent l'échange de l'actif adverse | E | `J-EFF` | P0 | M | `j-effets-choix` |
| 11 | [`j-cartes-supporters`](#j-cartes-supporters) | Supporters : un par tour, et les effets qui perturbent l'adversaire | E | `J-EFF` | P0 | M | `j-effets-choix` |
| 11 | [`j-cartes-talents`](#j-cartes-talents) | Talents : passifs, activés une fois par tour, déclenchés — et annulables | E | `J-EFF` | P0 | M | `j-effets-architecture`, `j-effets-choix` |
| 11 | [`j-effets-assistance-ia`](#j-effets-assistance-ia) | Assistance IA : proposer le script d'une carte, jamais le valider seule | E | `J-EFF` | P1 | M | `j-effets-catalogue-compilation` |
| 11 | [`j-effets-couverture-outil`](#j-effets-couverture-outil) | Tableau de couverture : ce qui est jouable, ce qui manque, et pour qui | E | `J-EFF` | P1 | S | `j-effets-catalogue-compilation` |
| 14 | [`j-plateau-decisions`](#j-plateau-decisions) | Fenêtres de décision : choisir des cartes, ordonner, répondre pendant le tour adverse | U | `J-UI` | P0 | M | `j-plateau-interactions`, `j-effets-choix` |

### J3 — Le plateau donne envie d'y jouer

_La carte, c'est SA photo ou l'image officielle. Une attaque Feu brûle la carte d'en face, l'éclair fait trembler le plateau, certains Pokémon apparaissent au-dessus de leur carte. Le tout reste lisible, coupable en un clic, et respecte « animations réduites »._

**Preuve attendue.** Une partie filmée où chaque type d'attaque a son effet, sans jamais faire perdre de vue l'état réel du jeu.

**10 lots**, poids 19 (S=1, M=2, L=3), paliers 13 → 15. Les jalons se chevauchent : pendant que l'interface se construit, les cartes se scriptent dans un autre couloir. Un jalon est atteint quand son dernier lot est livré.

| Palier | Lot | Titre | Piste | Couloir | Prio | Taille | Après |
|---|---|---|---|---|---|---|---|
| 13 | [`j-rendu-carte`](#j-rendu-carte) | Ma photo ou l'image officielle : la carte telle qu'elle est jouée | G | `J-GFX` | P0 | M | `j-plateau-layout` |
| 14 | [`j-anim-socle`](#j-anim-socle) | Socle d'animation : les effets suivent les événements, jamais l'inverse | G | `J-GFX` | P0 | M | `j-plateau-etat-visuel` |
| 14 | [`j-assets-pipeline`](#j-assets-pipeline) | Fabrique d'images : vignettes, variantes, cache et budget de poids | G | `J-GFX` | P1 | M | `j-rendu-carte` |
| 15 | [`j-accessibilite-jeu`](#j-accessibilite-jeu) | Confort et accessibilité : jouable par un enfant, lisible par tous | U | `J-UI` | P1 | S | `j-plateau-decisions`, `j-anim-socle` |
| 15 | [`j-anim-attaques-typees`](#j-anim-attaques-typees) | Une attaque Feu brûle la carte d'en face : un effet par type | G | `J-GFX` | P1 | L | `j-anim-socle` |
| 15 | [`j-anim-evolution-ko`](#j-anim-evolution-ko) | Évolution, K.O., récompense : les moments qui comptent | G | `J-GFX` | P1 | M | `j-anim-socle` |
| 15 | [`j-anim-pokemon-apparition`](#j-anim-pokemon-apparition) | Le Pokémon apparaît au-dessus de sa carte | G | `J-GFX` | P2 | L | `j-anim-socle`, `j-rendu-carte` |
| 15 | [`j-arene-decors`](#j-arene-decors) | Décors d'arène : jouer quelque part, pas sur un fond gris | G | `J-GFX` | P2 | S | `j-anim-socle` |
| 15 | [`j-plateau-aide`](#j-plateau-aide) | Aide en jeu : pourquoi je ne peux pas faire ça, et que puis-je faire | U | `J-UI` | P1 | M | `j-plateau-journal` |
| 15 | [`j-son`](#j-son) | Sons du jeu : entendre l'attaque, la pioche et la victoire | G | `J-GFX` | P2 | S | `j-anim-socle` |

### J4 — La partie laisse une trace

_La fin de partie écrit sur le compte : historique, statistiques par deck, classement privé entre comptes invités, badges. On revient parce qu'il y a quelque chose à suivre._

**Preuve attendue.** Après dix parties, la page « Mes parties » raconte qui gagne, avec quoi, et contre qui.

**9 lots**, poids 11 (S=1, M=2, L=3), paliers 9 → 17. Les jalons se chevauchent : pendant que l'interface se construit, les cartes se scriptent dans un autre couloir. Un jalon est atteint quand son dernier lot est livré.

| Palier | Lot | Titre | Piste | Couloir | Prio | Taille | Après |
|---|---|---|---|---|---|---|---|
| 9 | [`j-replay`](#j-replay) | Replay d'une partie : la rejouer coup par coup, et la partager | S | `J-SRV` | P2 | S | `j-journal-actions`, `j-partie-service` |
| 11 | [`j-echanges-emotes`](#j-echanges-emotes) | Emotes prédéfinies : se parler sans chat libre | S | `J-SRV` | P2 | S | `j-temps-reel` |
| 11 | [`j-mode-solo`](#j-mode-solo) | Partie d'entraînement contre un bot | R | `J-MOT` | P2 | S | `j-simulation-bots`, `j-partie-service` |
| 12 | [`j-notifications-jeu`](#j-notifications-jeu) | Être prévenu : invitation reçue, c'est ton tour, partie reprise | C | `J-UI` | P2 | S | `j-invitations`, `j-timer` |
| 13 | [`j-fin-effets-compte`](#j-fin-effets-compte) | Ce qu'une partie laisse sur le compte : écriture unique et exacte | C | `J-SRV` | P0 | M | `j-ko-recompenses`, `j-deconnexion-abandon` |
| 14 | [`j-classement-prive`](#j-classement-prive) | Classement privé entre comptes invités | C | `J-SRV` | P2 | S | `j-fin-effets-compte` |
| 15 | [`j-partie-fin-ui`](#j-partie-fin-ui) | Fin de partie : qui a gagné, pourquoi, et ce qu'on en retient | U | `J-UI` | P0 | S | `j-plateau-journal`, `j-ko-recompenses` |
| 16 | [`j-stats-joueur`](#j-stats-joueur) | Mes parties : historique, statistiques et ce que ça dit de mes decks | C | `J-UI` | P1 | M | `j-fin-effets-compte`, `j-partie-fin-ui` |
| 17 | [`j-profil-jeu`](#j-profil-jeu) | Profil de joueur : avatar, carte fétiche, badges | C | `J-UI` | P2 | S | `j-stats-joueur` |

### J5 — Le jeu tient debout tout seul

_Des bots jouent des milliers de parties sans bloquer, l'e2e passe en CI, le petit serveur encaisse les parties simultanées prévues, et une règle qui casse se voit dans une métrique avant de se voir dans une plainte._

**Preuve attendue.** 10 000 parties simulées sans blocage ni état impossible, e2e vert en CI, tenue en charge mesurée et écrite.

**5 lots**, poids 8 (S=1, M=2, L=3), paliers 9 → 18. Les jalons se chevauchent : pendant que l'interface se construit, les cartes se scriptent dans un autre couloir. Un jalon est atteint quand son dernier lot est livré.

| Palier | Lot | Titre | Piste | Couloir | Prio | Taille | Après |
|---|---|---|---|---|---|---|---|
| 9 | [`j-observabilite-jeu`](#j-observabilite-jeu) | Voir ce qui se passe : métriques du jeu et alertes de règles | Q | `J-SRV` | P1 | S | `j-partie-service` |
| 11 | [`j-charge-temps-reel`](#j-charge-temps-reel) | Tenue en charge : combien de parties simultanées sur deux cœurs | Q | `J-QUA` | P1 | S | `j-simulation-bots`, `j-temps-reel` |
| 16 | [`j-e2e-deux-navigateurs`](#j-e2e-deux-navigateurs) | Partie complète jouée automatiquement, à deux navigateurs | Q | `J-QUA` | P0 | M | `j-partie-fin-ui`, `j-plateau-decisions` |
| 17 | [`j-securite-jeu`](#j-securite-jeu) | Revue de sécurité du jeu avant ouverture | Q | `J-SRV` | P0 | M | `j-autorite-vues`, `j-e2e-deux-navigateurs` |
| 18 | [`j-mise-en-ligne-jeu`](#j-mise-en-ligne-jeu) | Mettre le jeu en ligne sur le serveur partagé | Q | `J-SRV` | P0 | M | `j-securite-jeu`, `j-charge-temps-reel`, `j-fin-effets-compte` |

## Ordre d'exécution — les paliers

Un palier ne peut commencer que quand tout ce dont il dépend est livré. À l'intérieur d'un palier, les lots sont indépendants : ils partent ensemble, autant que les couloirs le permettent.

| Palier | Lots | Couloirs mobilisés |
|---|---|---|
| **0** | [`j-regles-reference`](#j-regles-reference) | `J-MOT` |
| **1** | [`j-modele-etat`](#j-modele-etat) | `J-MOT` |
| **2** | [`j-aleatoire-determinisme`](#j-aleatoire-determinisme) | `J-MOT` |
| **3** | [`j-journal-actions`](#j-journal-actions) | `J-MOT` |
| **4** | [`j-actions-legales`](#j-actions-legales) | `J-MOT` |
| **5** | [`j-machine-tour`](#j-machine-tour) | `J-MOT` |
| **6** | [`j-checkup`](#j-checkup), [`j-degats-resolution`](#j-degats-resolution), [`j-retraite-banc`](#j-retraite-banc) | `J-MOT` |
| **7** | [`j-cartes-pokemon`](#j-cartes-pokemon), [`j-etats-speciaux`](#j-etats-speciaux), [`j-ko-recompenses`](#j-ko-recompenses) | `J-EFF`, `J-MOT` |
| **8** | [`j-cartes-energies`](#j-cartes-energies), [`j-effets-architecture`](#j-effets-architecture), [`j-partie-service`](#j-partie-service), [`j-tests-regles`](#j-tests-regles) | `J-EFF`, `J-MOT`, `J-SRV` |
| **9** | [`j-autorite-vues`](#j-autorite-vues), [`j-cartes-outils`](#j-cartes-outils), [`j-cartes-stades`](#j-cartes-stades), [`j-effets-dsl`](#j-effets-dsl), [`j-file-attente`](#j-file-attente), [`j-observabilite-jeu`](#j-observabilite-jeu), [`j-replay`](#j-replay) | `J-EFF`, `J-SRV` |
| **10** | [`j-cartes-attaques-effets`](#j-cartes-attaques-effets), [`j-cartes-regles-speciales`](#j-cartes-regles-speciales), [`j-effets-catalogue-compilation`](#j-effets-catalogue-compilation), [`j-effets-choix`](#j-effets-choix), [`j-invitations`](#j-invitations), [`j-simulation-bots`](#j-simulation-bots), [`j-temps-reel`](#j-temps-reel) | `J-EFF`, `J-QUA`, `J-SRV` |
| **11** | [`j-cartes-objets`](#j-cartes-objets), [`j-cartes-supporters`](#j-cartes-supporters), [`j-cartes-talents`](#j-cartes-talents), [`j-charge-temps-reel`](#j-charge-temps-reel), [`j-echanges-emotes`](#j-echanges-emotes), [`j-effets-assistance-ia`](#j-effets-assistance-ia), [`j-effets-couverture-outil`](#j-effets-couverture-outil), [`j-lancement-partie`](#j-lancement-partie), [`j-mode-solo`](#j-mode-solo), [`j-salon-partie`](#j-salon-partie), [`j-timer`](#j-timer) | `J-EFF`, `J-MOT`, `J-QUA`, `J-SRV`, `J-UI` |
| **12** | [`j-deconnexion-abandon`](#j-deconnexion-abandon), [`j-initialisation`](#j-initialisation), [`j-notifications-jeu`](#j-notifications-jeu), [`j-plateau-layout`](#j-plateau-layout) | `J-MOT`, `J-SRV`, `J-UI` |
| **13** | [`j-fin-effets-compte`](#j-fin-effets-compte), [`j-plateau-etat-visuel`](#j-plateau-etat-visuel), [`j-plateau-interactions`](#j-plateau-interactions), [`j-rendu-carte`](#j-rendu-carte) | `J-GFX`, `J-SRV`, `J-UI` |
| **14** | [`j-anim-socle`](#j-anim-socle), [`j-assets-pipeline`](#j-assets-pipeline), [`j-classement-prive`](#j-classement-prive), [`j-plateau-decisions`](#j-plateau-decisions), [`j-plateau-journal`](#j-plateau-journal) | `J-GFX`, `J-SRV`, `J-UI` |
| **15** | [`j-accessibilite-jeu`](#j-accessibilite-jeu), [`j-anim-attaques-typees`](#j-anim-attaques-typees), [`j-anim-evolution-ko`](#j-anim-evolution-ko), [`j-anim-pokemon-apparition`](#j-anim-pokemon-apparition), [`j-arene-decors`](#j-arene-decors), [`j-partie-fin-ui`](#j-partie-fin-ui), [`j-plateau-aide`](#j-plateau-aide), [`j-son`](#j-son) | `J-GFX`, `J-UI` |
| **16** | [`j-e2e-deux-navigateurs`](#j-e2e-deux-navigateurs), [`j-stats-joueur`](#j-stats-joueur) | `J-QUA`, `J-UI` |
| **17** | [`j-profil-jeu`](#j-profil-jeu), [`j-securite-jeu`](#j-securite-jeu) | `J-SRV`, `J-UI` |
| **18** | [`j-mise-en-ligne-jeu`](#j-mise-en-ligne-jeu) | `J-SRV` |

### Chemin critique

La plus longue chaîne de dépendances, pondérée par la taille des lots. C'est elle qui fixe la durée du chantier : tout retard pris ici se paie intégralement.

[`j-regles-reference`](#j-regles-reference) → [`j-modele-etat`](#j-modele-etat) → [`j-aleatoire-determinisme`](#j-aleatoire-determinisme) → [`j-journal-actions`](#j-journal-actions) → [`j-actions-legales`](#j-actions-legales) → [`j-machine-tour`](#j-machine-tour) → [`j-degats-resolution`](#j-degats-resolution) → [`j-cartes-pokemon`](#j-cartes-pokemon) → [`j-partie-service`](#j-partie-service) → [`j-autorite-vues`](#j-autorite-vues) → [`j-temps-reel`](#j-temps-reel) → [`j-plateau-layout`](#j-plateau-layout) → [`j-plateau-etat-visuel`](#j-plateau-etat-visuel) → [`j-plateau-journal`](#j-plateau-journal) → [`j-partie-fin-ui`](#j-partie-fin-ui) → [`j-e2e-deux-navigateurs`](#j-e2e-deux-navigateurs) → [`j-securite-jeu`](#j-securite-jeu) → [`j-mise-en-ligne-jeu`](#j-mise-en-ligne-jeu)

*18 lots, poids cumulé 35.*

## Décisions à prendre par JF

Aucune n'empêche de commencer : le premier palier n'en dépend pas. Mais chacune bloque un lot précis, et la prendre tard coûte une reprise.

### DJ1 — Quelle version des règles fait foi ? Standard actuel (rotation), Étendu, ou un format « maison » sans rotation acceptant toute carte de la collection ?

**Enjeu.** Tout en dépend : faiblesse ×2 ou +30, résistance −30 ou −20, cumul des états spéciaux, règle du premier tour, nombre de récompenses. Le moteur doit encoder UNE version datée et citée, pas un mélange.

**Proposition du pilote.** Format maison sans rotation (on joue ce qu'on possède), mais avec le corpus de règles ACTUEL (faiblesse ×2, résistance −30, 6 récompenses, banc de 5, le joueur qui commence n'attaque pas à son premier tour). Une carte ancienne est jouée avec les règles actuelles.

**Bloque :** [`j-regles-reference`](#j-regles-reference), [`j-degats-resolution`](#j-degats-resolution), [`j-etats-speciaux`](#j-etats-speciaux)

### DJ2 — Quel périmètre de cartes scripter en premier ?

**Enjeu.** Il existe des dizaines de milliers de cartes ; les scripter toutes est sans fin. Mais un deck refusé pour une seule carte manquante gâche la première partie.

**Proposition du pilote.** Piloté par la collection : on script d'abord les cartes réellement possédées par les comptes invités, puis les cartes les plus fréquentes du catalogue. Le tableau de couverture dit à tout moment ce qui manque pour rendre un deck jouable.

**Bloque :** [`j-effets-catalogue-compilation`](#j-effets-catalogue-compilation), [`j-effets-couverture-outil`](#j-effets-couverture-outil)

### DJ3 — Les Pokémon peuvent-ils apparaître en image animée au-dessus de leur carte — et avec quelles images ?

**Enjeu.** JF le demande explicitement (« les faire apparaître dans un bel effet »). Or utiliser des sprites ou des modèles officiels hors de l'illustration de la carte est un usage d'images protégées, sur un espace privé sans revenu mais tout de même en ligne.

**Proposition du pilote.** Par défaut, l'apparition est fabriquée à partir de l'illustration de la carte elle-même (découpe du Pokémon par segmentation, détourage, mise en volume, particules) : aucune image nouvelle n'est introduite. Une liste restreinte de Pokémon « vedettes » reçoit une animation soignée. À trancher par JF avant tout autre choix d'assets.

**Bloque :** [`j-anim-pokemon-apparition`](#j-anim-pokemon-apparition)

### DJ4 — Quelles durées ? Temps par tour, temps total par joueur, temps par décision.

**Enjeu.** Trop court, un enfant perd sur le chrono ; trop long, une partie abandonnée bloque une place et l'adversaire attend devant un écran mort.

**Proposition du pilote.** 90 s par tour, 25 min par joueur sur la partie, 30 s par décision hors de son tour, avec 10 s de tolérance réseau et une pause automatique de 120 s en cas de déconnexion. Expiration = action par défaut si elle existe, sinon défaite au temps.

**Bloque :** [`j-timer`](#j-timer)

### DJ5 — La photo personnelle d'une carte est-elle montrée à l'adversaire ?

**Enjeu.** C'est le charme du produit (on joue avec SES cartes, cornées, avec leur reflet) — mais c'est une photo prise chez soi, éventuellement avec un bout de table, une main, un salon.

**Proposition du pilote.** Oui par défaut côté joueur, et réglage par deck : « mes cartes telles que je les ai photographiées » ou « images officielles ». L'adversaire voit ce que le joueur a choisi de montrer ; un réglage « ne jamais montrer mes photos » existe.

**Bloque :** [`j-rendu-carte`](#j-rendu-carte)

### DJ6 — Que laisse une partie sur le compte : un simple historique, ou une progression (points, saisons, badges) ?

**Enjeu.** Une progression donne envie de revenir, mais elle crée une pression de performance chez un enfant, et un classement entre deux frères se règle rarement bien.

**Proposition du pilote.** Historique et statistiques d'office ; classement privé et badges en option, activables par JF, sans saison ni perte de points.

**Bloque :** [`j-fin-effets-compte`](#j-fin-effets-compte), [`j-classement-prive`](#j-classement-prive), [`j-profil-jeu`](#j-profil-jeu)

### DJ7 — Mode solo contre un bot ?

**Enjeu.** Le jeu est privé entre quelques comptes invités (D11) : il y aura des soirs sans adversaire. Le moteur et les bots de simulation rendent le solo presque gratuit — mais un bot qui joue mal donne une fausse idée du jeu.

**Proposition du pilote.** Oui, en réutilisant le bot heuristique de la simulation, annoncé comme « entraînement » et non compté au classement.

**Bloque :** [`j-mode-solo`](#j-mode-solo)

### DJ8 — Jusqu'où l'IA écrit-elle les scripts de cartes, et sous quel contrôle ?

**Enjeu.** Scripter dix mille cartes à la main est hors de portée ; laisser une IA écrire des règles de jeu sans contrôle produit des parties injustes et indétectables.

**Proposition du pilote.** L'IA propose un script ET ses cas de test à partir du texte de la carte ; le script n'entre en jeu que si ses tests passent et qu'un humain a validé la famille d'effets. Budget plafonné, comme pour v4-insights-batch.

**Bloque :** [`j-effets-assistance-ia`](#j-effets-assistance-ia)

### DJ9 — Sons et musique : activés par défaut ?

**Enjeu.** Le son fait beaucoup pour l'effet « vrai jeu », mais une partie ouverte en classe ou à côté d'un adulte qui travaille doit rester muette.

**Proposition du pilote.** Bruitages activés, musique coupée, réglage mémorisé par appareil.

**Bloque :** [`j-son`](#j-son)

### DJ10 — Échanges entre joueurs pendant la partie : rien, emotes prédéfinies, ou chat libre ?

**Enjeu.** Les comptes sont privés et invités, mais l'un des joueurs est mineur. Un chat libre demande une modération que ce projet n'aura pas.

**Proposition du pilote.** Emotes prédéfinies seulement (« bien joué », « oups », « ton tour »), désactivables, jamais de texte libre.

**Bloque :** [`j-echanges-emotes`](#j-echanges-emotes)

## Les lots, un par un

<a id="j-regles-reference"></a>
### `j-regles-reference` — Corpus de règles de référence : la version des règles qui fait foi, écrite et citée

**Palier 0** · jalon **J1** · piste R (Règles & moteur) · couloir `J-MOT` (devAI) · P0 · taille M · complexité 2/5 · difficulté 3/5 · décision **DJ1**

**Pourquoi ce lot.** Sans une référence écrite, chaque lot du moteur invente sa propre version des règles et personne ne peut arbitrer un désaccord. Ce document est la vérité contre laquelle le moteur est jugé, et il est écrit AVANT la première ligne de moteur.

**Ce qu'il fait.** Un document unique qui fixe, pour la version retenue en DJ1 : zones et leurs limites, déroulé d'un tour, règle du premier tour, calcul des dégâts, faiblesse et résistance, retraite, banc, états spéciaux et leur cumul, phase entre les tours, mises K.O., récompenses par marqueur de règle, conditions de victoire, mulligan, et les règles de cartes particulières (ACE SPEC, Radiant, VSTAR, GX, Pokémon-ex). Chaque point cite sa source et la date de la version.

**Mission**

- Choisir la version des règles avec JF (DJ1) et la citer : édition du livret officiel, date, langue de référence.
- Rédiger `docs/jeu/REGLES.md` : une section par mécanique, chaque affirmation numérotée (`R-3.4`) pour être citée par un test.
- Lister explicitement les points où les règles ont changé selon les époques (faiblesse ×2 contre +30, résistance −20 contre −30, cumul des états spéciaux, premier tour) et écrire lequel s'applique ici.
- Dresser la table des cas limites connus : pioche vide en début de tour, banc vide après un K.O., K.O. simultané, dernier Pokémon mis K.O. par un effet hors attaque, abandon, égalité.
- Produire la table de cas de test initiale (`docs/jeu/cas-de-regles.yaml`) : chaque cas nomme la règle qu'il vérifie.

**Critères d'acceptation**

- Chaque section du document porte un identifiant de règle citable par un test.
- Aucun point de règle n'est laissé en « selon l'époque » : un seul comportement est choisi et écrit.
- La table de cas couvre au minimum les dix cas limites listés dans la mission.
- JF a validé DJ1 et la validation est datée dans le document.

**Livrables** : docs/jeu/REGLES.md (règles numérotées), docs/jeu/cas-de-regles.yaml (table de cas).

**Risque à surveiller.** Le piège est de recopier une page d'encyclopédie amateur : les règles y mélangent les époques. Une seule source officielle, datée, et tout écart assumé par écrit.

**Vient après** : — (rien ne le précède)  
**Débloque** : [`j-modele-etat`](#j-modele-etat), [`j-tests-regles`](#j-tests-regles)

<a id="j-modele-etat"></a>
### `j-modele-etat` — État d'une partie : zones, attachements, compteurs, et vues par joueur

**Palier 1** · jalon **J1** · piste R (Règles & moteur) · couloir `J-MOT` (devAI) · P0 · taille L · complexité 4/5 · difficulté 4/5

**Pourquoi ce lot.** Toute la suite manipule cet objet. S'il est mal taillé — information cachée mélangée à l'information publique, attachements traités à part des cartes — chaque lot suivant paie la dette, et l'anti-triche devient impossible à greffer.

**Ce qu'il fait.** Structures pures et sérialisables en JSON : les deux joueurs, leurs zones (pioche, main, Pokémon actif, banc de 5, défausse, 6 récompenses, zone perdue si le format la connaît), chaque Pokémon en jeu avec ses cartes empilées (évolutions), ses énergies attachées, son outil, ses compteurs de dégâts, ses états spéciaux et son orientation ; le stade en jeu ; le tour courant, son numéro, sa phase, les drapeaux du tour (énergie posée, supporter joué, retraite faite) ; la version du schéma d'état.

**Mission**

- Définir les structures (dataclasses figées, aucune méthode d'entrée/sortie) et leur sérialisation JSON bidirectionnelle, avec `schema_version`.
- Séparer nettement l'information publique de l'information cachée : la pioche est une liste ordonnée, la main est privée, les récompenses sont face cachée.
- Implémenter la projection `vue(etat, joueur)` : ce qu'un joueur a le droit de savoir — nombre de cartes en main de l'adversaire, mais pas leur identité ; nombre de cartes en pioche, jamais leur ordre.
- Écrire les invariants vérifiables (`verifier(etat)`) : total des cartes constant, banc ≤ 5, un seul outil par Pokémon, un seul stade en jeu, pas de carte dans deux zones.
- Tests de propriété : sérialiser puis désérialiser un état quelconque le laisse identique ; la vue d'un joueur ne contient jamais un identifiant de carte cachée.

**Critères d'acceptation**

- `vue(etat, joueur)` ne laisse fuir aucune carte cachée — vérifié par un test qui parcourt la structure produite à la recherche des identifiants de la main adverse.
- Les invariants sont vérifiés après chaque action dans toute la suite de tests du moteur.
- Un état complet se sérialise, se relit et se compare à l'identique.
- Aucune dépendance à FastAPI, SQLAlchemy ou au réseau dans le paquet du moteur (vérifié par un test d'import).

**Livrables** : paquet `pbm_game.state` pur, projection par joueur, invariants + tests de propriété.

**Risque à surveiller.** La tentation de mettre des méthodes pratiques (« piocher », « attacher ») sur l'état : toute mutation doit passer par une action journalisée, sinon la rejouabilité est perdue dès le premier raccourci.

**Vient après** : [`j-regles-reference`](#j-regles-reference)  
**Débloque** : [`j-aleatoire-determinisme`](#j-aleatoire-determinisme)

<a id="j-aleatoire-determinisme"></a>
### `j-aleatoire-determinisme` — Aléatoire reproductible : mélange, pile ou face, et graine vérifiable

**Palier 2** · jalon **J1** · piste R (Règles & moteur) · couloir `J-MOT` (devAI) · P0 · taille S · complexité 3/5 · difficulté 3/5

**Pourquoi ce lot.** Sans aléatoire reproductible, une partie ne se rejoue pas, un bug ne se reproduit pas, et rien ne prouve au perdant que le mélange n'était pas truqué.

**Ce qu'il fait.** Un générateur à graine par partie, des flux séparés (mélange de chaque joueur, pile ou face, effets aléatoires), chaque tirage journalisé avec son motif ; engagement de la graine publié avant la partie et révélé à la fin (commit-reveal) pour que chacun puisse vérifier après coup que le mélange n'a pas été rejoué en boucle jusqu'à un bon résultat.

**Mission**

- Encapsuler l'aléatoire dans un objet passé explicitement : aucun appel à `random` ailleurs dans le moteur (vérifié par un test de grep).
- Un flux par usage, pour qu'ajouter un pile ou face quelque part ne décale pas tous les mélanges suivants.
- Journaliser chaque tirage : motif, flux, résultat.
- Publier l'empreinte de la graine à la création de la partie, révéler la graine à la fin ; un vérificateur indépendant recalcule le mélange.
- Tests : deux parties à graine identique et actions identiques donnent un état final identique, octet pour octet.

**Critères d'acceptation**

- Aucun appel à un aléatoire global dans le moteur.
- Rejouer une partie depuis (graine + journal) redonne l'état final à l'identique, sur une centaine de parties simulées.
- La vérification a posteriori du mélange est documentée et outillée en une commande.

**Livrables** : `pbm_game.rng` (flux nommés, journalisé), vérificateur commit-reveal.

**Risque à surveiller.** Un flux partagé entre le mélange et les pile ou face suffit à casser la reproductibilité quand une carte ajoute un tirage : séparer dès le départ, c'est gratuit ; après, c'est une reprise de tous les tests.

**Vient après** : [`j-modele-etat`](#j-modele-etat)  
**Débloque** : [`j-journal-actions`](#j-journal-actions), [`j-lancement-partie`](#j-lancement-partie)

<a id="j-journal-actions"></a>
### `j-journal-actions` — Journal d'actions : la partie est sa suite de coups, pas son état

**Palier 3** · jalon **J1** · piste R (Règles & moteur) · couloir `J-MOT` (devAI) · P0 · taille M · complexité 3/5 · difficulté 4/5

**Pourquoi ce lot.** C'est la pièce qui rend possibles quatre choses d'un coup : la reprise après un F5, le replay, le support (« montre-moi la partie ») et l'anti-triche. La stocker dès le premier jour coûte peu ; la rajouter après coûte une réécriture.

**Ce qu'il fait.** Journal append-only numéroté : chaque entrée porte son numéro, son auteur, l'action demandée, les événements produits par le moteur, l'horodatage et l'empreinte de l'état résultant. `rejouer(journal)` reconstruit l'état. Le journal est la source de vérité persistée ; l'état n'est qu'un cache.

**Mission**

- Définir le format d'une entrée et sa sérialisation stable (versionnée).
- Implémenter `appliquer(etat, action) -> (etat, evenements)` sans effet de bord, et `rejouer(journal) -> etat`.
- Empreinte de l'état après chaque coup : une divergence se détecte au coup près, pas à la fin de la partie.
- Test de propriété : pour toute partie simulée, `rejouer(journal) == etat` et les empreintes concordent.
- Prévoir la compaction : instantané périodique + queue de journal, pour ne pas rejouer 400 coups à chaque reconnexion.

**Critères d'acceptation**

- Sur 1 000 parties simulées, rejouer le journal redonne exactement l'état final et toutes les empreintes intermédiaires.
- Une entrée de journal est lisible par un humain sans outil (identifiants de cartes résolus en noms dans la vue de débogage).
- La reprise depuis un instantané + queue donne le même état que le rejeu complet.

**Livrables** : format de journal versionné, `rejouer()` + empreintes, instantanés.

**Risque à surveiller.** Journaliser l'état plutôt que les actions : le fichier gonfle, la divergence ne se voit plus, et le replay ment. Le journal enregistre ce qui a été DEMANDÉ et ce que le moteur en a FAIT, pas une photo du plateau.

**Vient après** : [`j-aleatoire-determinisme`](#j-aleatoire-determinisme)  
**Débloque** : [`j-actions-legales`](#j-actions-legales), [`j-partie-service`](#j-partie-service), [`j-replay`](#j-replay)

<a id="j-actions-legales"></a>
### `j-actions-legales` — Générateur d'actions légales : ce qui est jouable, et pourquoi le reste ne l'est pas

**Palier 4** · jalon **J1** · piste R (Règles & moteur) · couloir `J-MOT` (devAI) · P0 · taille M · complexité 4/5 · difficulté 4/5

**Pourquoi ce lot.** L'interface n'a plus à connaître les règles : elle affiche la liste que le moteur lui donne. Les bots s'en servent aussi. Et quand un coup est refusé, le joueur lit la raison au lieu de croire à un bug.

**Ce qu'il fait.** `actions_legales(etat, joueur)` rend la liste exhaustive des coups possibles, chacun avec ses cibles valides et une étiquette lisible. `valider(etat, action)` rend soit l'accord, soit un refus motivé par une règle citée (`R-3.4 : une seule énergie par tour`). Toute action passe par là, y compris celles venues du serveur.

**Mission**

- Énumérer les familles d'actions : piocher, poser un Pokémon de base au banc, faire évoluer, attacher une énergie, jouer un Objet, un Supporter, un Stade, un Outil, utiliser un talent, battre en retraite, déclarer une attaque, passer le tour, abandonner, répondre à une demande de décision.
- Pour chacune, calculer les cibles valides à partir de l'état — jamais depuis l'interface.
- Motiver chaque refus par un identifiant de règle du corpus de référence.
- Garantir que jouer une action tirée de `actions_legales` ne lève jamais d'exception (test de propriété sur parties aléatoires).
- Mesurer le coût : la liste doit se calculer en quelques millisecondes, elle est demandée à chaque changement d'état.

**Critères d'acceptation**

- Sur 10 000 états tirés de parties simulées, toute action de la liste s'applique sans erreur, et aucune action hors liste n'est acceptée par `valider`.
- Chaque refus porte un identifiant de règle existant dans `REGLES.md`.
- Le calcul reste sous 5 ms sur un état complet.

**Livrables** : `actions_legales()` exhaustif, `valider()` avec raisons citées.

**Risque à surveiller.** Dupliquer la logique entre « je liste » et « je valide » : les deux divergent inévitablement. Une seule source, la liste, et la validation vérifie l'appartenance plus les conditions de fraîcheur.

**Vient après** : [`j-journal-actions`](#j-journal-actions)  
**Débloque** : [`j-machine-tour`](#j-machine-tour), [`j-plateau-interactions`](#j-plateau-interactions)

<a id="j-machine-tour"></a>
### `j-machine-tour` — Déroulé d'un tour : phases, contraintes du tour, et fin de tour

**Palier 5** · jalon **J1** · piste R (Règles & moteur) · couloir `J-MOT` (devAI) · P0 · taille M · complexité 3/5 · difficulté 3/5

**Pourquoi ce lot.** C'est le squelette de la partie : sans lui, les actions existent mais aucune ne sait quand elle a le droit de survenir.

**Ce qu'il fait.** Début de tour (pioche obligatoire ; pioche impossible = défaite), phase principale libre (pose au banc, évolutions, une énergie, Dresseurs, talents, retraite), déclaration d'attaque qui termine le tour, passage de tour, drapeaux remis à zéro. Contraintes : une énergie par tour, un Supporter par tour, une retraite par tour, pas d'évolution d'un Pokémon posé ce tour-ci, pas d'évolution au premier tour de chaque joueur, règle du premier tour retenue en DJ1.

**Mission**

- Implémenter la machine à phases et les drapeaux de tour, tous portés par l'état (donc sérialisés, donc repris après un F5).
- Traiter la pioche impossible comme une condition de défaite vérifiée au bon moment, pas comme une exception.
- Brancher les fenêtres de déclenchement (début de tour, fin de tour) que la pile d'effets utilisera plus tard — même vides pour l'instant.
- Écrire les tests de tour : chaque contrainte a son cas passant et son cas refusé, avec la raison attendue.

**Critères d'acceptation**

- Les six contraintes de tour sont testées dans les deux sens (autorisé / refusé motivé).
- Le drapeau d'énergie, de Supporter et de retraite survit à une sérialisation/reprise.
- Déclarer une attaque termine le tour même si l'attaque n'inflige aucun dégât.

**Livrables** : machine à phases, tests de contraintes de tour.

**Risque à surveiller.** Coder les contraintes dans l'interface « pour l'ergonomie » : le serveur doit les tenir seul, l'interface ne fait que griser.

**Vient après** : [`j-actions-legales`](#j-actions-legales)  
**Débloque** : [`j-checkup`](#j-checkup), [`j-degats-resolution`](#j-degats-resolution), [`j-retraite-banc`](#j-retraite-banc)

<a id="j-checkup"></a>
### `j-checkup` — Phase entre les deux tours : l'ordre exact de résolution

**Palier 6** · jalon **J1** · piste R (Règles & moteur) · couloir `J-MOT` (devAI) · P0 · taille S · complexité 3/5 · difficulté 3/5

**Pourquoi ce lot.** Beaucoup d'effets disent « à la fin du tour » ou « entre les tours ». Sans une phase nommée où tout se résout dans un ordre fixé, ces effets se résolvent dans l'ordre où le code a été écrit — c'est-à-dire au hasard.

**Ce qu'il fait.** Une phase explicite entre la fin d'un tour et le début du suivant : poison, brûlure, réveil, effets déclenchés « entre les tours », expiration des effets « jusqu'à la fin de ce tour », retrait des marqueurs temporaires, vérification des K.O. provoqués par ces effets et prise des récompenses correspondantes.

**Mission**

- Implémenter la phase et son ordre, point par point depuis `REGLES.md`.
- Gérer les K.O. survenus pendant cette phase (hors attaque) et la promotion qui s'ensuit.
- Nettoyer les effets temporaires et journaliser chaque expiration (sinon les effets « jusqu'à la fin du tour » deviennent éternels sans que rien ne le dise).
- Tests : un Pokémon empoisonné meurt entre les tours, l'adversaire prend sa récompense, la promotion est demandée au bon joueur.

**Critères d'acceptation**

- L'ordre de la phase est testé sur un cas qui combine poison, brûlure et réveil sur les deux joueurs.
- Un K.O. survenu dans cette phase donne bien ses récompenses et déclenche la promotion.
- Aucun effet temporaire ne survit à la phase sans une entrée de journal qui l'explique.

**Livrables** : phase intermédiaire ordonnée, expiration journalisée des effets.

**Risque à surveiller.** Oublier que des K.O. arrivent hors des attaques : le code de victoire ne doit pas vivre uniquement dans la résolution d'attaque.

**Vient après** : [`j-machine-tour`](#j-machine-tour)  
**Débloque** : [`j-effets-architecture`](#j-effets-architecture), [`j-etats-speciaux`](#j-etats-speciaux)

<a id="j-degats-resolution"></a>
### `j-degats-resolution` — Attaque et dégâts : coût, faiblesse, résistance, modificateurs

**Palier 6** · jalon **J1** · piste R (Règles & moteur) · couloir `J-MOT` (devAI) · P0 · taille M · complexité 4/5 · difficulté 4/5 · décision **DJ1**

**Pourquoi ce lot.** C'est le geste central du jeu, et celui dont le calcul est le plus souvent faux : l'ordre des opérations entre faiblesse, résistance et modificateurs change le résultat.

**Ce qu'il fait.** Vérification du coût de l'attaque (énergies typées et incolores, énergies fournissant plusieurs unités), calcul des dégâts de base, application dans l'ordre officiel : modificateurs qui changent les dégâts de base, puis faiblesse, puis résistance, puis effets de réduction ; plancher à zéro ; pose des compteurs de dégâts ; dégâts au banc qui ignorent faiblesse et résistance ; auto-dégâts.

**Mission**

- Implémenter le paiement du coût, en traitant correctement l'incolore et les énergies multiples.
- Implémenter la chaîne de calcul dans l'ordre fixé par `REGLES.md`, chaque étape étant un point d'accroche nommé pour les effets à venir.
- Poser les dégâts sous forme de compteurs sur le Pokémon, jamais en soustrayant des PV : les soins et les effets « PV restants » en dépendent.
- Produire un détail de calcul lisible (« 60 base, ×2 faiblesse, −30 résistance = 90 ») exploité par le journal de partie et l'aide en jeu.
- Tests : table de cas issue du corpus de règles, y compris résistance supérieure aux dégâts, faiblesse sur dégâts nuls, dégâts au banc.

**Critères d'acceptation**

- Tous les cas de dégâts de `cas-de-regles.yaml` passent.
- Le détail de calcul est produit pour chaque attaque et affiché dans le journal.
- Les dégâts au banc n'appliquent ni faiblesse ni résistance.

**Livrables** : résolution d'attaque + détail de calcul, table de cas verte.

**Risque à surveiller.** Appliquer la faiblesse après les réductions, ou soustraire des PV : les deux erreurs sont invisibles jusqu'au jour où un joueur compte et découvre qu'il a perdu à tort.

**Vient après** : [`j-machine-tour`](#j-machine-tour)  
**Débloque** : [`j-cartes-pokemon`](#j-cartes-pokemon), [`j-ko-recompenses`](#j-ko-recompenses)

<a id="j-retraite-banc"></a>
### `j-retraite-banc` — Banc, retraite et promotion : le Pokémon actif change de place

**Palier 6** · jalon **J1** · piste R (Règles & moteur) · couloir `J-MOT` (devAI) · P0 · taille S · complexité 2/5 · difficulté 2/5

**Pourquoi ce lot.** Le déplacement de l'actif est le geste défensif du jeu, et c'est aussi la cible des effets d'appât : il doit exister proprement avant qu'on lui ajoute des effets.

**Ce qu'il fait.** Banc limité à cinq, coût de retraite payé en défaussant des énergies attachées (au choix du joueur), une retraite par tour, retraite impossible sous certains états spéciaux, promotion obligatoire après un K.O., échange forcé provoqué par un effet (qui ne consomme ni la retraite du tour ni d'énergie), banc vide = défaite.

**Mission**

- Implémenter la retraite avec choix des énergies défaussées (demande de décision au joueur).
- Distinguer trois mouvements différents : retraite volontaire, promotion après K.O., échange forcé par un effet — leurs règles ne sont pas les mêmes.
- Conserver les compteurs de dégâts, énergies et outils lors d'un passage au banc ; retirer les états spéciaux selon `REGLES.md`.
- Tests : retraite sans énergie suffisante, banc plein, échange forcé sous paralysie, promotion quand le banc est vide.

**Critères d'acceptation**

- Les trois types de mouvement ont des chemins distincts et testés.
- Le passage au banc soigne bien ce qu'il doit soigner, et rien d'autre.
- Le banc vide après K.O. termine la partie avec la bonne raison.

**Livrables** : retraite / promotion / échange forcé, tests de mouvement.

**Risque à surveiller.** Confondre échange forcé et retraite : les cartes d'appât deviendraient injouables sous paralysie, ou consommeraient la retraite du tour.

**Vient après** : [`j-machine-tour`](#j-machine-tour)  
**Débloque** : [`j-cartes-pokemon`](#j-cartes-pokemon), [`j-etats-speciaux`](#j-etats-speciaux)

<a id="j-cartes-pokemon"></a>
### `j-cartes-pokemon` — Cartes Pokémon : base, évolutions, marqueurs de règle

**Palier 7** · jalon **J1** · piste E (Effets & cartes) · couloir `J-EFF` (chimera) · P0 · taille M · complexité 3/5 · difficulté 3/5

**Pourquoi ce lot.** Sans elles il n'y a pas de partie du tout : ce sont les seules cartes indispensables au jalon J1.

**Ce qu'il fait.** Pokémon de base posables au banc, évolutions de stade 1 et 2 (sur le bon Pokémon, pas le tour de sa pose, pas au premier tour), PV, type, faiblesse, résistance, coût de retraite, marqueur de règle (récompenses données), conservation des énergies et des compteurs de dégâts à l'évolution, guérison des états spéciaux à l'évolution.

**Mission**

- Charger les cartes Pokémon sans passer par le langage d'effets : à ce stade, seules les attaques à dégâts secs sont jouables ; les attaques à effet arrivent avec `j-cartes-attaques-effets`.
- Charger ces caractéristiques depuis le catalogue (`cards.attacks`, `weaknesses`, `resistances`, `retreat_cost`, `rule_marker`) plutôt que de les redéclarer.
- Implémenter la pile d'évolution et ce qu'elle conserve ou efface.
- Traiter les cas particuliers de pose (Pokémon qui arrivent directement en jeu par un effet).
- Tests : évolution interdite le tour de la pose, évolution qui soigne le sommeil, K.O. d'une pile d'évolution qui défausse toute la pile.

**Critères d'acceptation**

- Aucune caractéristique de Pokémon n'est écrite en dur dans le moteur.
- Une carte du catalogue dont le marqueur de règle est inconnu est refusée avec un message clair, jamais jouée par défaut.
- Les tests d'évolution couvrent les six cas de `cas-de-regles.yaml`.

**Livrables** : cartes Pokémon jouables depuis le catalogue.

**Risque à surveiller.** Les données du catalogue sont hétérogènes selon la source (TCGdex / Pokémon TCG API) : les champs manquants doivent bloquer la carte, pas être devinés.

**Vient après** : [`j-degats-resolution`](#j-degats-resolution), [`j-retraite-banc`](#j-retraite-banc)  
**Débloque** : [`j-cartes-energies`](#j-cartes-energies), [`j-effets-catalogue-compilation`](#j-effets-catalogue-compilation), [`j-initialisation`](#j-initialisation), [`j-partie-service`](#j-partie-service)

<a id="j-etats-speciaux"></a>
### `j-etats-speciaux` — États spéciaux : Empoisonné, Brûlé, Endormi, Paralysé, Confus

**Palier 7** · jalon **J1** · piste R (Règles & moteur) · couloir `J-MOT` (devAI) · P0 · taille M · complexité 4/5 · difficulté 4/5 · décision **DJ1**

**Pourquoi ce lot.** JF les a explicitement mis dans la première version (D9). Ce sont aussi les règles les plus souvent jouées de travers, parce que leur cumul et leur ordre de résolution changent selon les époques.

**Ce qu'il fait.** Les cinq états, leur pose, leurs règles de cumul (un seul état « couché » à la fois, poison et brûlure cumulables avec les autres selon la version retenue), leurs effets (pas d'attaque ni de retraite sous paralysie ou sommeil, pile ou face de confusion avec auto-dégâts, compteurs de poison et de brûlure), leur guérison (passage au banc, évolution, effets de soin, réveil au pile ou face).

**Mission**

- Encoder les cinq états et la matrice de cumul exacte de la version retenue.
- Brancher leur résolution sur la phase entre les tours (`j-checkup`), dans l'ordre officiel.
- Implémenter la confusion : pile ou face à la déclaration d'attaque, auto-dégâts sur échec, attaque annulée.
- Représenter l'orientation de la carte (couchée, tournée) dans l'état, pour que l'interface la montre comme sur une vraie table.
- Tests : un cas par état, un cas par combinaison autorisée, guérison par retraite, par évolution, par effet.

**Critères d'acceptation**

- La matrice de cumul est testée exhaustivement (toutes les paires).
- Un Pokémon endormi ou paralysé ne peut ni attaquer ni battre en retraite, mais peut être échangé de force.
- Les compteurs de poison et de brûlure s'appliquent au bon moment, et le pile ou face de brûlure est journalisé.

**Livrables** : cinq états + matrice de cumul, résolution en phase intermédiaire.

**Risque à surveiller.** Le cumul est le piège : selon la version, poison + sommeil coexistent mais sommeil + paralysie non. Le seul garde-fou est la matrice écrite dans `REGLES.md` et testée paire par paire.

**Vient après** : [`j-retraite-banc`](#j-retraite-banc), [`j-checkup`](#j-checkup)  
**Débloque** : [`j-cartes-attaques-effets`](#j-cartes-attaques-effets)

<a id="j-ko-recompenses"></a>
### `j-ko-recompenses` — Mises K.O., récompenses et conditions de victoire

**Palier 7** · jalon **J1** · piste R (Règles & moteur) · couloir `J-MOT` (devAI) · P0 · taille M · complexité 4/5 · difficulté 4/5

**Pourquoi ce lot.** La fin d'une partie est le moment où une erreur de moteur coûte le plus cher : c'est là que le résultat se décide.

**Ce qu'il fait.** Détection du K.O. (compteurs ≥ PV), défausse du Pokémon avec toute sa pile d'évolutions, ses énergies et son outil, prise du bon nombre de récompenses selon le marqueur de règle (1 pour un Pokémon ordinaire, 2 pour un Pokémon-ex/V/GX, 3 pour un TAG TEAM), K.O. simultané, promotion obligatoire d'un Pokémon du banc, et les trois conditions de victoire : plus de récompenses à prendre, adversaire sans Pokémon à promouvoir, adversaire incapable de piocher. Abandon et égalité.

**Mission**

- Résoudre les K.O. dans l'ordre officiel, y compris quand une attaque en provoque plusieurs.
- Lire le nombre de récompenses depuis la carte du catalogue (marqueur de règle) et non depuis une liste en dur.
- Traiter le K.O. simultané et l'égalité selon `REGLES.md`.
- Interrompre la partie proprement : état final figé, vainqueur, raison, journal clos.
- Tests : chaque condition de victoire, le double K.O., le K.O. du dernier Pokémon, la victoire par pioche vide.

**Critères d'acceptation**

- Les trois conditions de victoire et l'égalité sont couvertes par des tests nommés.
- Le nombre de récompenses vient du catalogue ; une carte inconnue au marqueur inconnu fait échouer bruyamment, pas silencieusement à 1.
- Une partie terminée refuse toute action supplémentaire.

**Livrables** : résolution des K.O., fin de partie normalisée (vainqueur + raison).

**Risque à surveiller.** Le repli silencieux « marqueur inconnu → 1 récompense » : c'est exactement la panne muette que ce dépôt a déjà payée quatre fois. Un marqueur inconnu est une erreur qui remonte.

**Vient après** : [`j-degats-resolution`](#j-degats-resolution)  
**Débloque** : [`j-cartes-regles-speciales`](#j-cartes-regles-speciales), [`j-effets-architecture`](#j-effets-architecture), [`j-fin-effets-compte`](#j-fin-effets-compte), [`j-partie-fin-ui`](#j-partie-fin-ui), [`j-tests-regles`](#j-tests-regles)

<a id="j-cartes-energies"></a>
### `j-cartes-energies` — Énergies : de base fournies, spéciales possédées

**Palier 8** · jalon **J1** · piste E (Effets & cartes) · couloir `J-EFF` (chimera) · P0 · taille M · complexité 3/5 · difficulté 3/5 · décision **D10**

**Pourquoi ce lot.** Les énergies décident de ce qu'on peut attaquer et quand. La règle de JF (énergies de base illimitées, spéciales possédées) est déjà tranchée : le moteur doit l'appliquer sans que le joueur ait à y penser.

**Ce qu'il fait.** Énergies de base fournies en quantité illimitée et non décomptées de la collection (D10) ; énergies spéciales traitées comme des cartes ordinaires (possession et règle des quatre exemplaires) ; une énergie attachée par tour ; énergies qui fournissent plusieurs unités ou plusieurs types ; énergies porteuses d'effets (soins, dégâts supplémentaires, coût de retraite modifié) ; défausse et déplacement d'énergies.

**Mission**

- Représenter la fourniture d'énergie comme une capacité de la carte (types et quantités fournis), pas comme un type figé.
- Implémenter le paiement d'un coût d'attaque à partir des énergies attachées, y compris les incolores et les fournitures multiples — avec un algorithme qui trouve une combinaison valide et l'explique.
- Brancher les effets portés par les énergies spéciales sur la pile d'effets.
- Tests : coût mixte payé par une énergie double incolore, énergie spéciale qui ne compte que pour un type, défausse d'énergie à la retraite.

**Critères d'acceptation**

- Le paiement d'un coût trouve une combinaison valide quand elle existe, et l'explique dans le journal.
- Les énergies de base n'apparaissent jamais dans le décompte de la collection.
- Les énergies spéciales sont soumises à la règle des quatre, vérifié avec le service de légalité des decks.

**Livrables** : fourniture d'énergie générique, paiement de coût expliqué.

**Risque à surveiller.** Coder le paiement comme une simple comparaison de compteurs : les énergies multi-types rendent le problème combinatoire, et une mauvaise combinaison refuse une attaque parfaitement légale.

**Vient après** : [`j-cartes-pokemon`](#j-cartes-pokemon)  
**Débloque** : — (rien n'en dépend)

<a id="j-partie-service"></a>
### `j-partie-service` — Service de parties : créer, persister, reprendre, expirer

**Palier 8** · jalon **J1** · piste S (Serveur de parties) · couloir `J-SRV` (devAI) · P0 · taille M · complexité 4/5 · difficulté 4/5

**Pourquoi ce lot.** C'est l'enveloppe qui transforme un moteur de règles en parties réelles : deux comptes, deux decks, un journal persistant, et une partie qui survit à un redémarrage du serveur.

**Ce qu'il fait.** Tables `games`, `game_players`, `game_events` (journal), `game_snapshots` (instantanés) ; création d'une partie à partir de deux decks résolus en scripts ; application d'une action (validation, journalisation, diffusion) ; reprise d'une partie depuis l'instantané et la queue de journal ; expiration des parties abandonnées ; purge.

**Mission**

- Écrire le modèle et les migrations Alembic, en gardant le journal append-only (aucune mise à jour d'une entrée existante).
- Implémenter la boucle : action reçue → validation par le moteur → écriture du journal → nouvel état → événements diffusés, le tout dans une transaction.
- Résoudre les decks en scripts au moment de la création, et refuser la partie si une carte n'est pas jouable (`j-effets-catalogue-compilation`).
- Reprise : recharger depuis le dernier instantané, rejouer la queue, comparer l'empreinte.
- Purge des parties mortes et des instantanés anciens, avec une métrique de ce qui a été purgé.

**Critères d'acceptation**

- Une partie survit à un redémarrage complet de l'API : la reprise redonne l'état exact, empreinte comprise.
- Deux actions concurrentes sur la même partie ne peuvent pas être appliquées deux fois (verrou testé).
- Une partie dont le deck contient une carte non scriptée est refusée à la création, avec la liste des cartes.

**Livrables** : modèle + migrations, boucle d'application transactionnelle, reprise et purge.

**Risque à surveiller.** La partie est l'endroit où deux requêtes arrivent en même temps (le joueur clique deux fois, le réseau rejoue). L'idempotence par numéro d'action est obligatoire dès le premier jour.

**Vient après** : [`j-journal-actions`](#j-journal-actions), [`j-cartes-pokemon`](#j-cartes-pokemon)  
**Débloque** : [`j-autorite-vues`](#j-autorite-vues), [`j-file-attente`](#j-file-attente), [`j-mode-solo`](#j-mode-solo), [`j-observabilite-jeu`](#j-observabilite-jeu), [`j-replay`](#j-replay)

<a id="j-tests-regles"></a>
### `j-tests-regles` — Batterie de cas de règles : la table qui dit si le moteur a raison

**Palier 8** · jalon **J1** · piste Q (Qualité & exploitation) · couloir `J-MOT` (devAI) · P0 · taille M · complexité 3/5 · difficulté 3/5

**Pourquoi ce lot.** Un moteur de règles ne se relit pas, il se prouve. Cette table est ce qui permettra de modifier le moteur dans six mois sans tout casser en silence.

**Ce qu'il fait.** Des cas écrits en données (état de départ, action, état attendu, règle citée), une par mécanique et une par cas limite, exécutés en CI ; un rapport de couverture par règle du corpus ; l'obligation, pour tout lot de moteur, d'ajouter ses cas.

**Mission**

- Formaliser le format des cas et l'exécuteur, lisible par un humain qui connaît les règles mais pas Python.
- Écrire les cas des mécaniques déjà livrées, en citant l'identifiant de règle de `REGLES.md`.
- Publier la couverture par règle : quelles règles n'ont aucun cas.
- Faire échouer la CI si une règle du corpus n'a aucun cas associé.

**Critères d'acceptation**

- Au moins 200 cas verts, tous rattachés à une règle du corpus.
- Aucune règle du corpus n'est sans cas (ou l'exception est écrite et justifiée).
- Un cas se lit et s'écrit sans toucher au code du moteur.

**Livrables** : format de cas + exécuteur, ≥ 200 cas, couverture par règle.

**Risque à surveiller.** Des tests écrits depuis le code plutôt que depuis les règles : ils valident le comportement actuel, y compris ses erreurs.

**Vient après** : [`j-regles-reference`](#j-regles-reference), [`j-ko-recompenses`](#j-ko-recompenses)  
**Débloque** : [`j-simulation-bots`](#j-simulation-bots)

<a id="j-effets-architecture"></a>
### `j-effets-architecture` — Pile d'effets et déclencheurs : l'architecture qui accueille toutes les cartes

**Palier 8** · jalon **J2** · piste E (Effets & cartes) · couloir `J-EFF` (chimera) · P0 · taille L · complexité 5/5 · difficulté 5/5 · décision **D9**

**Pourquoi ce lot.** C'est le lot qui décide si les mille cartes suivantes coûtent une heure ou une semaine chacune. Un moteur qui traite les effets au fil de l'eau se réécrit à la première carte qui dit « votre adversaire ne peut pas ».

**Ce qu'il fait.** Un bus d'événements de jeu (avant et après les dégâts, à la pose, à l'évolution, au K.O., au début et à la fin du tour, à l'attachement d'énergie, à la pioche, entre les tours), une pile d'effets résolue en dernier entré premier sorti, des fenêtres d'interruption, la distinction entre effets ponctuels et effets continus, et des verrous nommés (« pas de Supporter ce tour », « ce Pokémon ne peut pas attaquer », « les talents sont sans effet »).

**Mission**

- Définir la liste des événements et leurs charges utiles, à partir des besoins réels relevés sur 200 cartes prises au hasard du catalogue.
- Implémenter la pile, l'ordre de résolution et les fenêtres d'interruption ; toute résolution est journalisée avec sa source (« à cause de l'Outil X »).
- Implémenter les effets continus comme des modificateurs consultés au calcul, jamais comme des mutations de l'état (sinon leur retrait est impossible à faire proprement).
- Implémenter les verrous et leur portée (ce tour, tant que ce Pokémon est actif, tant que ce Stade est en jeu).
- Documenter l'architecture dans `docs/jeu/EFFETS.md` avec trois exemples complets de bout en bout.

**Critères d'acceptation**

- Les 200 cartes de l'échantillon sont exprimables sans ajouter d'événement nouveau — ou la liste est complétée et le test refait.
- Le retrait d'un effet continu (Outil défaussé, Stade remplacé) restaure exactement l'état antérieur du calcul.
- Chaque résolution d'effet est journalisée avec sa carte source.
- Le moteur socle (`j-machine-tour`, `j-degats-resolution`) n'a pas été modifié pour accueillir les effets : ils se branchent sur les points d'accroche existants.

**Livrables** : bus d'événements + pile d'effets, effets continus par modificateurs, docs/jeu/EFFETS.md.

**Risque à surveiller.** Sous-estimer les effets qui modifient les règles elles-mêmes (« les attaques de votre adversaire coûtent une énergie de plus », « les Pokémon de base ne peuvent pas être mis K.O. »). Si la pile ne sait pas les porter, ils seront codés en dur dans le socle, et le socle pourrira.

**Vient après** : [`j-checkup`](#j-checkup), [`j-ko-recompenses`](#j-ko-recompenses)  
**Débloque** : [`j-cartes-outils`](#j-cartes-outils), [`j-cartes-stades`](#j-cartes-stades), [`j-cartes-talents`](#j-cartes-talents), [`j-effets-dsl`](#j-effets-dsl)

<a id="j-autorite-vues"></a>
### `j-autorite-vues` — Autorité du serveur : le client ne voit que ce qu'il a le droit de voir

**Palier 9** · jalon **J1** · piste S (Serveur de parties) · couloir `J-SRV` (devAI) · P0 · taille M · complexité 4/5 · difficulté 4/5

**Pourquoi ce lot.** Sans cette règle tenue dès le début, l'anti-triche ne se rajoute jamais : il suffit d'ouvrir les outils du navigateur pour lire la main de l'adversaire, et plus personne n'a envie de jouer.

**Ce qu'il fait.** Toute action passe par `valider()` côté serveur ; le client reçoit exclusivement `vue(etat, joueur)` ; les événements diffusés sont filtrés par destinataire (le même K.O. n'est pas décrit pareil aux deux joueurs quand une information est cachée) ; les identifiants de cartes cachées sont remplacés par des jetons opaques, changés à chaque mélange.

**Mission**

- Filtrer toute sortie de l'API et du canal temps réel par la projection joueur — un seul point de sortie, pas un filtrage par route.
- Remplacer les identifiants des cartes cachées par des jetons opaques non corrélables entre deux mélanges.
- Écrire le test de non-fuite : pour 1 000 états, aucun identifiant de carte cachée n'apparaît dans ce qui part vers le client ; ce test tourne en CI sur chaque lot de scripts de cartes.
- Journaliser toute action refusée avec son motif, et alerter sur les motifs anormaux (un client qui propose des actions illégales en rafale).

**Critères d'acceptation**

- Le test de non-fuite est vert et tourne sur chaque modification du moteur ou des scripts.
- Un client modifié qui envoie une action illégale reçoit un refus motivé et n'altère jamais l'état.
- Les jetons de cartes cachées ne permettent pas de suivre une carte d'un mélange à l'autre.

**Livrables** : point de sortie unique filtré, jetons opaques, test de non-fuite en CI.

**Risque à surveiller.** Le filtrage par route : il suffit d'une route oubliée. Le filtrage doit être structurel, au sérialiseur, et vérifié par un test qui cherche les fuites plutôt que de les supposer absentes.

**Vient après** : [`j-partie-service`](#j-partie-service)  
**Débloque** : [`j-securite-jeu`](#j-securite-jeu), [`j-temps-reel`](#j-temps-reel)

<a id="j-file-attente"></a>
### `j-file-attente` — Recherche d'un adversaire : file d'attente privée et appariement

**Palier 9** · jalon **J1** · piste S (Serveur de parties) · couloir `J-SRV` (devAI) · P0 · taille M · complexité 3/5 · difficulté 3/5 · décision **D11**

**Pourquoi ce lot.** C'est la porte d'entrée du jeu : « je veux jouer » doit aboutir à une partie en quelques secondes, ou à une réponse claire (« personne en ligne »).

**Ce qu'il fait.** File d'attente réservée aux comptes invités (D11), entrée avec un deck choisi et vérifié, appariement par ordre d'arrivée (et par proximité de niveau si le classement existe), annulation, présence en ligne (« 2 joueurs disponibles »), refus si le deck n'est pas jouable, protection contre l'entrée simultanée dans deux parties.

**Mission**

- Implémenter la file (Redis) et l'appariement, avec un verrou qui empêche un joueur d'être apparié deux fois.
- Vérifier le deck à l'entrée : légalité, possession, scripts disponibles — et dire précisément ce qui manque.
- Afficher la présence : qui est en ligne parmi les comptes invités, qui est en partie.
- Traiter le cas « personne en ligne » : proposer l'invitation directe ou l'entraînement contre le bot.
- Tests : deux joueurs appariés, trois joueurs dont un annule, deck refusé à l'entrée.

**Critères d'acceptation**

- Un joueur ne peut jamais se retrouver dans deux parties (test de concurrence).
- Le refus d'un deck nomme les cartes en cause et la raison.
- L'attente affiche l'état réel : nombre de joueurs disponibles, temps d'attente.

**Livrables** : file d'attente + appariement, vérification du deck à l'entrée, présence en ligne.

**Risque à surveiller.** L'appariement est le classique des conditions de course : deux joueurs appariés chacun avec un troisième. Le verrou atomique est obligatoire, et c'est un test, pas une relecture.

**Vient après** : [`j-partie-service`](#j-partie-service)  
**Débloque** : [`j-invitations`](#j-invitations), [`j-salon-partie`](#j-salon-partie)

<a id="j-cartes-outils"></a>
### `j-cartes-outils` — Outils Pokémon : un par Pokémon, attaché, défaussé au K.O.

**Palier 9** · jalon **J2** · piste E (Effets & cartes) · couloir `J-EFF` (chimera) · P1 · taille S · complexité 3/5 · difficulté 3/5

**Pourquoi ce lot.** Les Outils portent les modificateurs de dégâts et de PV les plus courants ; ils testent la bonne tenue des effets continus attachés à une cible.

**Ce qu'il fait.** Un Outil par Pokémon, attaché lors de son tour, effets continus (PV supplémentaires, dégâts supplémentaires, coût de retraite réduit, protection), effets déclenchés, défausse à la mise K.O. du porteur, retrait par un effet adverse, interdiction d'attacher un deuxième Outil.

**Mission**

- Attacher l'Outil au Pokémon dans l'état, avec son effet continu consulté au calcul.
- Traiter les PV supplémentaires correctement : ils changent le seuil de K.O., pas les compteurs déjà posés — et leur retrait peut provoquer un K.O. immédiat.
- Défausser l'Outil avec son porteur, et journaliser le retrait de ses effets.
- Tests : retrait d'un Outil qui donnait des PV et K.O. immédiat, deuxième Outil refusé, Outil sur un Pokémon du banc.

**Critères d'acceptation**

- Le retrait d'un Outil de PV provoque bien le K.O. si les compteurs dépassent le nouveau seuil.
- Un Pokémon ne porte jamais deux Outils.
- Trois Outils réels sont scriptés et testés.

**Livrables** : attachement d'Outils + effets continus ciblés.

**Risque à surveiller.** Le cas « je retire l'Outil qui maintenait ce Pokémon en vie » est rarement testé et arrive en tournoi : il est dans la table de cas.

**Vient après** : [`j-effets-architecture`](#j-effets-architecture)  
**Débloque** : — (rien n'en dépend)

<a id="j-cartes-stades"></a>
### `j-cartes-stades` — Stades : un seul en jeu, des effets qui s'appliquent aux deux joueurs

**Palier 9** · jalon **J2** · piste E (Effets & cartes) · couloir `J-EFF` (chimera) · P1 · taille S · complexité 3/5 · difficulté 3/5

**Pourquoi ce lot.** Les Stades sont le premier vrai test de l'architecture d'effets continus : ils modifient les règles pour les deux joueurs, et leur remplacement doit tout défaire proprement.

**Ce qu'il fait.** Un seul Stade en jeu ; jouer un Stade défausse le précédent (et un Stade identique ne peut pas être rejoué pour rien) ; effets continus symétriques ou conditionnels ; effets déclenchés par le Stade ; défausse par un effet.

**Mission**

- Implémenter la zone Stade, partagée entre les deux joueurs, et sa règle de remplacement.
- Exprimer les effets de Stade comme des modificateurs continus, retirés au remplacement.
- Tests : remplacement d'un Stade qui donnait un bonus (le bonus disparaît au bon moment), Stade identique refusé, Stade qui modifie le coût de retraite des deux camps.

**Critères d'acceptation**

- Le retrait d'un Stade restaure exactement les calculs antérieurs.
- Le Stade appartient à la partie, pas à un joueur : les deux camps en subissent les effets.
- Trois Stades réels sont scriptés et testés.

**Livrables** : zone Stade + effets continus symétriques.

**Risque à surveiller.** Appliquer l'effet d'un Stade au moment où il est joué (mutation) au lieu de le consulter au calcul : son remplacement laisse alors des traces indélébiles.

**Vient après** : [`j-effets-architecture`](#j-effets-architecture)  
**Débloque** : — (rien n'en dépend)

<a id="j-effets-dsl"></a>
### `j-effets-dsl` — Langage d'effets : décrire ce que fait une carte, sans écrire de code par carte

**Palier 9** · jalon **J2** · piste E (Effets & cartes) · couloir `J-EFF` (chimera) · P0 · taille L · complexité 5/5 · difficulté 5/5

**Pourquoi ce lot.** Dix mille cartes ne s'écrivent pas en dix mille fonctions Python. Un langage déclaratif rend les cartes lisibles, relisibles, testables, et écrivables par une IA sous contrôle.

**Ce qu'il fait.** Des primitives (piocher, chercher dans la pioche, défausser, attacher, déplacer, soigner, poser des compteurs, mélanger, révéler, regarder, choisir, pile ou face, changer l'actif, poser un état spécial, annuler, empêcher), des sélecteurs de cibles (mon actif, un de mes Pokémon de banc, un Pokémon de base dans ma pioche, une carte Objet de ma défausse), des conditions, des coûts, des répétitions et des branchements. Le tout sérialisé, versionné, validé par un schéma.

**Mission**

- Concevoir le jeu de primitives à partir d'un dépouillement réel : classer les textes d'effet de 500 cartes et en extraire le vocabulaire minimal qui les couvre.
- Écrire le schéma du langage (JSON Schema) et son interpréteur au-dessus de la pile d'effets.
- Rendre chaque primitive testable isolément, avec un état de départ et un état attendu.
- Gérer les cibles vides et les effets impossibles : un effet qui ne peut rien faire ne bloque pas la partie, il le dit dans le journal.
- Écrire `docs/jeu/DSL.md` : chaque primitive, ses paramètres, un exemple de carte réelle.

**Critères d'acceptation**

- Le vocabulaire couvre au moins 80 % des 500 textes dépouillés sans primitive « code libre ».
- Chaque primitive a ses tests unitaires, y compris le cas « aucune cible ».
- Un script non conforme au schéma est refusé au chargement, pas en pleine partie.
- Le langage est versionné : un script écrit pour la v1 reste lisible quand la v2 sort.

**Livrables** : schéma du langage + interpréteur, docs/jeu/DSL.md, tests par primitive.

**Risque à surveiller.** La primitive fourre-tout qui exécute du code arbitraire : elle apparaît au bout de trois jours, et à partir de là plus rien n'est vérifiable ni générable. Si une carte ne s'exprime pas, elle est déclarée non supportée — c'est la règle D9.

**Vient après** : [`j-effets-architecture`](#j-effets-architecture)  
**Débloque** : [`j-cartes-attaques-effets`](#j-cartes-attaques-effets), [`j-cartes-regles-speciales`](#j-cartes-regles-speciales), [`j-effets-catalogue-compilation`](#j-effets-catalogue-compilation), [`j-effets-choix`](#j-effets-choix), [`j-simulation-bots`](#j-simulation-bots)

<a id="j-replay"></a>
### `j-replay` — Replay d'une partie : la rejouer coup par coup, et la partager

**Palier 9** · jalon **J4** · piste S (Serveur de parties) · couloir `J-SRV` (devAI) · P2 · taille S · complexité 2/5 · difficulté 3/5

**Pourquoi ce lot.** Le journal existe déjà : en faire un replay coûte peu et sert trois fois — revoir sa partie, comprendre un désaccord de règle, et diagnostiquer une panne sans interroger le joueur.

**Ce qu'il fait.** Rejouer une partie terminée coup par coup, avance et retour, vitesse réglable, vue d'un joueur ou vue complète une fois la partie finie, lien de partage vers les seuls comptes autorisés, export du journal pour le support.

**Mission**

- Servir le journal d'une partie terminée avec la vue choisie, en révélant l'information cachée seulement après la fin.
- Implémenter la navigation coup par coup côté client en rejouant le journal localement.
- Restreindre le partage aux comptes invités et aux deux joueurs.
- Tests : replay identique à la partie jouée, replay d'une partie interrompue par abandon.

**Critères d'acceptation**

- Le replay reproduit exactement les états successifs (empreintes comparées).
- Aucune information cachée n'est servie avant la fin de la partie.
- Le lien de replay n'est pas accessible à un compte non autorisé.

**Livrables** : replay coup par coup, partage restreint.

**Risque à surveiller.** Servir le journal complet d'une partie en cours sous prétexte de replay : c'est la fuite d'information la plus facile à commettre.

**Vient après** : [`j-journal-actions`](#j-journal-actions), [`j-partie-service`](#j-partie-service)  
**Débloque** : — (rien n'en dépend)

<a id="j-observabilite-jeu"></a>
### `j-observabilite-jeu` — Voir ce qui se passe : métriques du jeu et alertes de règles

**Palier 9** · jalon **J5** · piste Q (Qualité & exploitation) · couloir `J-SRV` (devAI) · P1 · taille S · complexité 2/5 · difficulté 3/5

**Pourquoi ce lot.** Une règle qui casse doit se voir dans une métrique avant de se voir dans une plainte. C'est particulièrement vrai ici : les joueurs sont deux ou trois, ils ne signaleront pas tout.

**Ce qu'il fait.** Métriques : parties en cours, créées, terminées par raison, durée moyenne, tours moyens, actions refusées par motif, expirations d'horloge, déconnexions, erreurs de moteur, scripts de cartes en échec. Alerte sur les motifs anormaux (explosion des refus, erreurs de moteur non nulles, parties qui n'aboutissent pas).

**Mission**

- Exposer les métriques et les brancher sur la sonde d'infrastructure existante (mail vers direction@upgreg.ai).
- Traiter toute erreur de moteur comme une alerte, jamais comme une ligne de journal.
- Suivre les actions refusées par motif : une hausse signale soit un bug d'interface, soit une tentative de triche.
- Publier un récapitulatif hebdomadaire des parties jouées.

**Critères d'acceptation**

- Une erreur de moteur en production déclenche une alerte, vérifié par un test d'injection.
- Les métriques sont visibles sans se connecter en SSH.
- Le récapitulatif hebdomadaire arrive, et son absence est elle-même un signal.

**Livrables** : métriques du jeu, alertes branchées sur la sonde.

**Risque à surveiller.** Dupliquer la sonde existante par des scripts ad hoc : la consigne du poste est de modifier la sonde, pas de la doubler.

**Vient après** : [`j-partie-service`](#j-partie-service)  
**Débloque** : — (rien n'en dépend)

<a id="j-invitations"></a>
### `j-invitations` — Inviter quelqu'un à jouer : par pseudo ou par lien

**Palier 10** · jalon **J1** · piste S (Serveur de parties) · couloir `J-SRV` (devAI) · P1 · taille S · complexité 2/5 · difficulté 2/5 · décision **D11**

**Pourquoi ce lot.** Entre deux frères ou deux amis, on ne « cherche pas un adversaire » : on invite quelqu'un de précis. C'est l'usage le plus probable de ce jeu.

**Ce qu'il fait.** Inviter un compte par pseudo, ou fabriquer un lien d'invitation à usage unique et limité dans le temps ; notification de l'invitation ; acceptation, refus, annulation, expiration ; salon d'attente à deux avant le lancement.

**Mission**

- Modéliser l'invitation (émetteur, destinataire ou lien, deck choisi, expiration) et ses transitions.
- Notifier dans l'application, et prévoir le relais par e-mail ou notification PWA plus tard.
- Empêcher un lien d'invitation d'ouvrir un compte : il rejoint une partie, il ne crée jamais d'accès (D11).
- Tests : invitation acceptée, refusée, expirée, lien réutilisé (refusé).

**Critères d'acceptation**

- Un lien d'invitation ne sert qu'une fois et expire.
- Une invitation n'ouvre aucun droit au-delà de la partie concernée.
- Les deux joueurs voient le même salon d'attente et le même deck annoncé.

**Livrables** : invitations par pseudo et par lien, salon d'attente à deux.

**Risque à surveiller.** Un lien d'invitation qui vaut authentification est une porte ouverte : il rejoint une partie, rien d'autre.

**Vient après** : [`j-file-attente`](#j-file-attente)  
**Débloque** : [`j-lancement-partie`](#j-lancement-partie), [`j-notifications-jeu`](#j-notifications-jeu), [`j-salon-partie`](#j-salon-partie)

<a id="j-temps-reel"></a>
### `j-temps-reel` — Canal temps réel : diffusion des coups, reconnexion et reprise après F5

**Palier 10** · jalon **J1** · piste S (Serveur de parties) · couloir `J-SRV` (devAI) · P0 · taille M · complexité 4/5 · difficulté 4/5

**Pourquoi ce lot.** Un jeu au tour par tour sans temps réel, c'est un formulaire. Et une partie qu'un F5 tue, c'est une partie qu'on ne recommence pas.

**Ce qu'il fait.** WebSocket authentifié, souscription à une partie, diffusion des événements dans l'ordre avec numéro de séquence, accusés de réception, détection de coupure, reconnexion avec resynchronisation depuis le dernier numéro connu, repli en interrogation périodique si le WebSocket est impossible (réseau d'école, proxy).

**Mission**

- Authentifier la connexion avec la session du compte, refuser un joueur étranger à la partie.
- Numéroter les événements et permettre au client de demander « donne-moi tout depuis le numéro N ».
- Traiter les envois en double et le désordre : le client applique par numéro, jamais par ordre d'arrivée.
- Reprise : à la reconnexion, le client reçoit l'état complet de sa vue plus la queue d'événements.
- Repli en interrogation périodique, annoncé dans l'interface (« connexion dégradée »).

**Critères d'acceptation**

- Un F5 au milieu d'une partie, y compris au milieu d'une demande de décision, ramène le joueur exactement où il était.
- Une coupure de réseau de 60 s ne perd aucun événement.
- Le repli en interrogation permet de finir une partie, plus lentement, et le dit au joueur.

**Livrables** : canal WebSocket numéroté, resynchronisation, repli dégradé.

**Risque à surveiller.** Compter sur l'ordre d'arrivée des messages : il n'est pas garanti. Le numéro de séquence est ce qui rend la reprise possible, et il coûte trois lignes au départ.

**Vient après** : [`j-autorite-vues`](#j-autorite-vues)  
**Débloque** : [`j-charge-temps-reel`](#j-charge-temps-reel), [`j-echanges-emotes`](#j-echanges-emotes), [`j-plateau-layout`](#j-plateau-layout), [`j-timer`](#j-timer)

<a id="j-cartes-attaques-effets"></a>
### `j-cartes-attaques-effets` — Attaques à effet : pile ou face, dégâts variables, blocages, états infligés

**Palier 10** · jalon **J2** · piste E (Effets & cartes) · couloir `J-EFF` (chimera) · P0 · taille M · complexité 4/5 · difficulté 4/5

**Pourquoi ce lot.** Une attaque qui n'inflige que des dégâts est l'exception. Tant que les attaques à effet ne sont pas scriptées, aucun deck réel n'est jouable.

**Ce qu'il fait.** Pile ou face (un, plusieurs, jusqu'à échec), dégâts variables (nombre d'énergies attachées, cartes en main, PV manquants, compteurs posés, récompenses restantes), dégâts au banc, auto-dégâts, défausse d'énergies en coût, soins, poses d'états spéciaux, blocage du tour suivant (« ce Pokémon ne peut pas attaquer au prochain tour »), effets conditionnés au type de la cible.

**Mission**

- Scripter ces familles dans le langage d'effets, en réutilisant les primitives existantes.
- Traiter les effets qui durent (blocage du tour suivant) via des marqueurs à expiration journalisée.
- Journaliser chaque pile ou face avec sa graine et son résultat, pour que le joueur puisse vérifier.
- Tests : attaque à dégâts variables sur trois états différents, blocage qui expire bien au bon tour, KO par auto-dégâts.

**Critères d'acceptation**

- Chaque famille est couverte par au moins trois cartes réelles testées.
- Un blocage « au prochain tour » expire exactement au bon moment, avec sa ligne de journal.
- Tous les pile ou face sont rejouables depuis la graine.

**Livrables** : familles d'attaques à effet scriptées.

**Risque à surveiller.** Les dégâts variables se calculent au moment de la résolution, pas de la déclaration : un joueur qui défausse une carte entre les deux obtiendrait sinon un résultat faux.

**Vient après** : [`j-effets-dsl`](#j-effets-dsl), [`j-etats-speciaux`](#j-etats-speciaux)  
**Débloque** : — (rien n'en dépend)

<a id="j-cartes-regles-speciales"></a>
### `j-cartes-regles-speciales` — Règles de cartes particulières : ACE SPEC, Radiant, VSTAR, GX, Prism Star

**Palier 10** · jalon **J2** · piste E (Effets & cartes) · couloir `J-EFF` (chimera) · P1 · taille S · complexité 3/5 · difficulté 3/5

**Pourquoi ce lot.** Ces règles ne concernent que quelques cartes, mais elles cassent les règles générales : les ignorer rend injouables des cartes que les joueurs possèdent et veulent jouer.

**Ce qu'il fait.** Limites de deck propres (une seule carte ACE SPEC, un seul Pokémon Radiant), pouvoirs utilisables une fois par partie (VSTAR, GX), cartes Prism Star qui vont en zone perdue au lieu de la défausse, marqueurs de règle donnant deux ou trois récompenses.

**Mission**

- Porter ces contraintes dans le service de légalité des decks (`v7-decks-legalite`) et dans le moteur.
- Suivre l'usage « une fois par partie » dans l'état du joueur, pas dans celui de la carte.
- Implémenter la zone perdue si le format la connaît (DJ1).
- Tests : deux ACE SPEC refusées au deck, deuxième pouvoir VSTAR refusé en partie, Prism Star qui part en zone perdue.

**Critères d'acceptation**

- Chaque règle particulière est vérifiée au deck ET en partie.
- L'usage unique par partie survit à une reprise après F5.
- Une carte portant une règle particulière inconnue est refusée au deck avec sa raison.

**Livrables** : règles particulières au deck et en partie.

**Risque à surveiller.** Ces règles se trouvent dans le texte de la carte, pas dans un champ structuré du catalogue : leur détection fait partie de la compilation, et doit échouer bruyamment quand elle hésite.

**Vient après** : [`j-effets-dsl`](#j-effets-dsl), [`j-ko-recompenses`](#j-ko-recompenses)  
**Débloque** : — (rien n'en dépend)

<a id="j-effets-catalogue-compilation"></a>
### `j-effets-catalogue-compilation` — Du catalogue aux cartes jouables : compilation, versions et errata

**Palier 10** · jalon **J2** · piste E (Effets & cartes) · couloir `J-EFF` (chimera) · P0 · taille L · complexité 4/5 · difficulté 4/5 · décision **DJ2**

**Pourquoi ce lot.** C'est le pont entre les trente mille cartes du catalogue et les cartes réellement jouables. Sans lui, chaque carte est un travail manuel sans mémoire.

**Ce qu'il fait.** Une table `card_scripts` : carte, version du langage, script, statut (scripté / non supporté / à revoir), empreinte du texte source, auteur, date de validation, tests associés. Quand le texte d'une carte change en base (correction du catalogue, errata), l'empreinte ne correspond plus et le script repasse « à revoir » — il ne peut plus être joué tant qu'il n'a pas été confirmé.

**Mission**

- Créer la table et ses migrations, avec l'empreinte du texte source par langue.
- Écrire le chargeur qui, au lancement d'une partie, résout chaque carte du deck vers son script validé — et refuse la partie si l'une manque.
- Détecter les textes modifiés et basculer automatiquement les scripts concernés en « à revoir ».
- Regrouper les cartes par texte identique : des centaines de cartes partagent le même effet, un script doit pouvoir en couvrir plusieurs.
- Commande de maintenance : importer, valider, lister, diffuser les scripts.

**Critères d'acceptation**

- Une carte dont le texte a changé ne se joue plus avec l'ancien script : elle passe « à revoir » et le deck le dit.
- Le regroupement par texte identique réduit mesurablement le nombre de scripts à écrire (chiffre publié dans le compte rendu).
- Le lancement d'une partie avec une carte non scriptée est refusé avant la mise en place, jamais en plein milieu.

**Livrables** : table `card_scripts` + migrations, chargeur de partie, détection d'errata.

**Risque à surveiller.** La tentation d'un repli « script manquant → effet neutre » : c'est précisément l'approximation interdite par D9. Une carte sans script bloque le deck, et le dit.

**Vient après** : [`j-effets-dsl`](#j-effets-dsl), [`j-cartes-pokemon`](#j-cartes-pokemon)  
**Débloque** : [`j-effets-assistance-ia`](#j-effets-assistance-ia), [`j-effets-couverture-outil`](#j-effets-couverture-outil)

<a id="j-effets-choix"></a>
### `j-effets-choix` — Demandes de décision : quand le moteur doit attendre un joueur — y compris l'adversaire

**Palier 10** · jalon **J2** · piste E (Effets & cartes) · couloir `J-EFF` (chimera) · P0 · taille M · complexité 4/5 · difficulté 5/5

**Pourquoi ce lot.** C'est le point où beaucoup de moteurs se cassent : une carte demande à l'ADVERSAIRE de choisir, pendant le tour de l'autre. Il faut une partie qui sait se mettre en pause, en ligne, avec une horloge et une reprise après coupure.

**Ce qu'il fait.** Un mécanisme de demande : à qui, quoi choisir (une carte, plusieurs, un ordre, oui/non, un type, un nombre), combien, obligatoire ou facultatif, parmi quel ensemble (visible ou caché), avec une réponse par défaut et un délai. Le moteur suspend la résolution, l'état porte la demande en cours, et la reprise après F5 retrouve la demande intacte.

**Mission**

- Modéliser la demande dans l'état (donc sérialisée, donc reprise) et non dans une variable d'exécution.
- Traiter les demandes adressées à l'adversaire pendant le tour courant, avec leur propre horloge.
- Définir la réponse par défaut de chaque type de demande (le premier choix valide, ou l'abandon de l'effet facultatif) pour l'expiration du délai.
- Empêcher toute autre action tant qu'une demande est en cours, sauf l'abandon.
- Tests : demande à l'adversaire, expiration, reprise après reconnexion au milieu d'une demande, demande imbriquée (un effet qui en déclenche un autre).

**Critères d'acceptation**

- Une partie interrompue au milieu d'une demande reprend exactement à cette demande, avec le temps restant.
- Les demandes imbriquées se résolvent dans le bon ordre et se voient dans le journal.
- L'expiration applique la réponse par défaut et l'écrit dans le journal.

**Livrables** : demandes de décision dans l'état, réponses par défaut, horloge par demande.

**Risque à surveiller.** Implémenter les demandes en bloquant un fil d'exécution côté serveur : une partie sur deux reste bloquée à la première déconnexion. La demande est une donnée, pas une attente de code.

**Vient après** : [`j-effets-dsl`](#j-effets-dsl)  
**Débloque** : [`j-cartes-objets`](#j-cartes-objets), [`j-cartes-supporters`](#j-cartes-supporters), [`j-cartes-talents`](#j-cartes-talents), [`j-plateau-decisions`](#j-plateau-decisions), [`j-timer`](#j-timer)

<a id="j-simulation-bots"></a>
### `j-simulation-bots` — Bots de simulation : des milliers de parties pour débusquer les blocages

**Palier 10** · jalon **J2** · piste Q (Qualité & exploitation) · couloir `J-QUA` (chimera) · P0 · taille M · complexité 4/5 · difficulté 4/5

**Pourquoi ce lot.** Les cas de règles vérifient ce qu'on a prévu. Les bots trouvent ce qu'on n'a pas prévu : boucles infinies, états impossibles, parties qui ne finissent jamais, scripts de cartes qui se bloquent mutuellement.

**Ce qu'il fait.** Un bot aléatoire (joue n'importe quelle action légale) et un bot heuristique (attaque, évolue, économise ses ressources) ; exécution massive en parallèle sur chimera ; détection des anomalies (partie sans fin, état invalide, action légale qui lève une exception, durée anormale) ; reproduction d'une anomalie depuis sa graine ; rapport par lot de scripts de cartes.

**Mission**

- Écrire les deux bots sur la seule vue joueur (jamais l'état complet).
- Lancer les campagnes sur chimera et collecter les anomalies avec leur graine.
- Mesurer la distribution des durées de partie et le nombre de tours : une dérive signale un script de carte fautif.
- Intégrer une campagne réduite en CI à chaque lot de scripts, et une campagne longue chaque nuit.
- Faire échouer bruyamment sur toute anomalie — jamais de `continue` silencieux.

**Critères d'acceptation**

- 10 000 parties simulées sans état invalide ni blocage, et le chiffre est publié.
- Toute anomalie est reproductible depuis sa graine en une commande.
- La campagne de CI tourne sur chaque lot de scripts de cartes.

**Livrables** : bots aléatoire et heuristique, campagnes massives, reproduction par graine.

**Risque à surveiller.** Ignorer les parties « trop longues » comme un artefact : c'est exactement la forme que prend une boucle d'effets entre deux cartes.

**Vient après** : [`j-tests-regles`](#j-tests-regles), [`j-effets-dsl`](#j-effets-dsl)  
**Débloque** : [`j-charge-temps-reel`](#j-charge-temps-reel), [`j-mode-solo`](#j-mode-solo)

<a id="j-lancement-partie"></a>
### `j-lancement-partie` — Lancement : choix du deck, contrôle, prêt à jouer, tirage au sort

**Palier 11** · jalon **J1** · piste S (Serveur de parties) · couloir `J-SRV` (devAI) · P0 · taille S · complexité 3/5 · difficulté 3/5

**Pourquoi ce lot.** C'est le moment que JF a nommé : le jeton « qui commence ». Il doit être visible, vérifiable, et donner au gagnant le choix que les règles lui accordent.

**Ce qu'il fait.** Choix du deck parmi les siens, dernier contrôle de légalité et de possession, état « prêt » des deux côtés, publication de l'empreinte de graine, tirage au sort animé du premier joueur, choix du gagnant du tirage (commencer ou non, selon `REGLES.md`), compte à rebours et bascule en partie.

**Mission**

- Enchaîner les étapes comme une machine à états persistée : un rechargement au milieu ne perd rien.
- Publier l'empreinte de la graine avant le tirage, révéler la graine en fin de partie.
- Implémenter le choix laissé au gagnant du tirage, avec un délai et un choix par défaut.
- Refuser le lancement si un deck est devenu injouable entre la file et le lancement (carte vendue, script retiré).
- Tests : un joueur se déconnecte avant d'être prêt, deck devenu invalide, tirage rejoué à l'identique depuis la graine.

**Critères d'acceptation**

- Le tirage est vérifiable après coup par les deux joueurs.
- Un rechargement pendant la mise en place reprend à la bonne étape.
- Un deck devenu injouable arrête le lancement avec sa raison, sans partie fantôme.

**Livrables** : machine de lancement persistée, tirage vérifiable.

**Risque à surveiller.** Un tirage au sort côté client, même « pour l'animation » : le résultat vient du serveur, l'animation ne fait que le montrer.

**Vient après** : [`j-invitations`](#j-invitations), [`j-aleatoire-determinisme`](#j-aleatoire-determinisme)  
**Débloque** : [`j-initialisation`](#j-initialisation)

<a id="j-salon-partie"></a>
### `j-salon-partie` — Salon de jeu : jouer, inviter, reprendre, s'entraîner

**Palier 11** · jalon **J1** · piste U (Interface de jeu) · couloir `J-UI` (chimera) · P0 · taille S · complexité 2/5 · difficulté 2/5

**Pourquoi ce lot.** C'est l'écran d'où part tout le jeu. S'il est confus, la meilleure partie du monde ne sera jamais lancée.

**Ce qu'il fait.** Un bouton « Jouer » qui demande le deck et entre dans la file ; la liste des joueurs en ligne avec invitation en un clic ; les parties en cours à reprendre, bien visibles ; l'entraînement contre le bot ; les invitations reçues ; le rappel du dernier résultat.

**Mission**

- Dessiner l'écran depuis la maquette existante du jeu et l'étendre (file, invitations, reprise).
- Mettre la reprise d'une partie en cours en tête : c'est l'action la plus urgente quand elle existe.
- Afficher l'état réel de la file (attente, joueurs disponibles) sans faire attendre devant un écran muet.
- Traiter le cas « personne en ligne » par une proposition concrète : inviter, ou s'entraîner.

**Critères d'acceptation**

- Une partie en cours est visible et reprenable en un clic depuis l'accueil du jeu.
- Le choix du deck affiche sa jouabilité avant l'entrée en file.
- L'écran reste lisible sur téléphone.

**Livrables** : écran salon, entrée en file avec deck, reprise visible.

**Risque à surveiller.** Cacher la partie en cours sous un onglet : le joueur croit l'avoir perdue et en lance une autre, ce qui bloque les deux.

**Vient après** : [`j-file-attente`](#j-file-attente), [`j-invitations`](#j-invitations)  
**Débloque** : [`j-plateau-layout`](#j-plateau-layout)

<a id="j-timer"></a>
### `j-timer` — Horloges : par tour, par partie, par décision — et ce qui se passe à l'expiration

**Palier 11** · jalon **J1** · piste S (Serveur de parties) · couloir `J-SRV` (devAI) · P0 · taille M · complexité 4/5 · difficulté 4/5 · décision **DJ4**

**Pourquoi ce lot.** Sans horloge, un joueur qui part dîner bloque l'autre indéfiniment. Avec une horloge mal faite, un enfant perd une partie gagnée parce qu'il réfléchissait. Le réglage est un choix de JF (DJ4), pas un détail technique.

**Ce qu'il fait.** Trois horloges : temps par tour, temps total par joueur, temps par décision (y compris hors de son tour). Décompte autoritaire côté serveur, affichage côté client, avertissements sonores et visuels, tolérance réseau, pause automatique en cas de déconnexion avec délai de reprise, expiration = action par défaut si elle existe (réponse par défaut d'une demande, fin de tour) sinon défaite au temps.

**Mission**

- Porter les horloges dans l'état de la partie (donc reprises après un F5) et non dans un minuteur en mémoire.
- Décompter côté serveur ; le client n'affiche qu'une estimation, corrigée à chaque événement.
- Implémenter la pause de déconnexion et sa reprise, avec un affichage honnête des deux côtés (« l'adversaire s'est déconnecté, 1 min 47 »).
- Définir l'action par défaut de chaque situation d'expiration et la journaliser comme telle.
- Tests : expiration pendant une demande adressée à l'adversaire, reprise après pause, dérive d'horloge client.

**Critères d'acceptation**

- Les durées sont des paramètres de configuration, modifiables sans redéploiement du moteur.
- Une expiration produit toujours une action journalisée et jamais un blocage.
- Le temps affiché ne s'écarte jamais de plus de deux secondes du temps serveur.

**Livrables** : trois horloges dans l'état, pause de déconnexion, actions par défaut.

**Risque à surveiller.** Un minuteur en mémoire meurt au redéploiement et fait perdre des parties. L'horloge est une donnée de la partie, calculée à partir d'horodatages, pas un compte à rebours vivant.

**Vient après** : [`j-temps-reel`](#j-temps-reel), [`j-effets-choix`](#j-effets-choix)  
**Débloque** : [`j-deconnexion-abandon`](#j-deconnexion-abandon), [`j-notifications-jeu`](#j-notifications-jeu)

<a id="j-cartes-objets"></a>
### `j-cartes-objets` — Cartes Objet, dont les appâts qui forcent l'échange de l'actif adverse

**Palier 11** · jalon **J2** · piste E (Effets & cartes) · couloir `J-EFF` (chimera) · P0 · taille M · complexité 4/5 · difficulté 4/5

**Pourquoi ce lot.** Les Objets sont la moitié d'un deck moderne, et l'appât — sortir du banc le Pokémon fragile de l'adversaire pour l'achever — est le geste tactique que JF a explicitement demandé.

**Ce qu'il fait.** Objets jouables en nombre illimité pendant son tour : recherche dans la pioche, pioche, défausse, soins, déplacement d'énergie, retrait d'outil, changement d'actif de son côté, et **effets d'appât** qui forcent l'adversaire à promouvoir un Pokémon de son banc (type *Boss's Orders*, *Pokémon Catcher*). Restrictions portées par la carte (une fois par tour, conditions d'usage).

**Mission**

- Exprimer ces familles dans le langage d'effets ; aucune ne doit demander de code spécifique.
- Traiter l'appât comme un échange forcé (distinct de la retraite, sans coût, non bloqué par les états spéciaux du Pokémon échangé).
- Gérer le cas où l'appât n'a pas de cible (banc adverse vide) : l'effet ne fait rien et le dit.
- Tests : appât sur un banc vide, appât suivi d'une attaque, Objet joué pendant une demande de décision (refusé).

**Critères d'acceptation**

- L'appât change l'actif adverse sans consommer la retraite du tour et sans payer d'énergie.
- Chaque famille d'Objet couverte a au moins trois cartes réelles scriptées et testées.
- Un Objet sans cible valide n'est pas jouable, et la raison s'affiche.

**Livrables** : familles d'Objets scriptées, effet d'appât testé.

**Risque à surveiller.** L'appât est aussi une carte qui déclenche des effets adverses (« quand ce Pokémon devient actif… ») : sans passage par le bus d'événements, ces déclencheurs seront oubliés.

**Vient après** : [`j-effets-choix`](#j-effets-choix)  
**Débloque** : — (rien n'en dépend)

<a id="j-cartes-supporters"></a>
### `j-cartes-supporters` — Supporters : un par tour, et les effets qui perturbent l'adversaire

**Palier 11** · jalon **J2** · piste E (Effets & cartes) · couloir `J-EFF` (chimera) · P0 · taille M · complexité 3/5 · difficulté 3/5

**Pourquoi ce lot.** Un Supporter par tour est la contrainte qui structure tout le rythme d'une partie ; ses effets de pioche et de perturbation sont ce qui rend un deck jouable.

**Ce qu'il fait.** Limite d'un Supporter par tour (drapeau porté par l'état), effets de pioche et de recherche, effets qui agissent sur la main adverse (mélanger et repiocher, faire défausser), effets conditionnés (« seulement si vous avez moins de récompenses »), et interdiction par un verrou adverse.

**Mission**

- Brancher la limite sur le drapeau de tour et la rendre visible dans les actions légales.
- Scripter les familles : pioche pure, recherche, perturbation, conditionnels.
- Traiter les effets qui touchent la main adverse en respectant la confidentialité : le joueur actif apprend le nombre, pas le contenu, sauf si la carte le dit.
- Tests : deuxième Supporter refusé avec sa raison, Supporter sous verrou adverse, Supporter qui vide la pioche.

**Critères d'acceptation**

- Un Supporter joué sous verrou est refusé avec la carte responsable nommée dans la raison.
- Aucun effet ne révèle la main adverse au-delà de ce que la carte autorise (test de non-fuite).
- Le drapeau survit à une reprise après F5.

**Livrables** : familles de Supporters scriptées, verrous respectés.

**Risque à surveiller.** Les effets de perturbation sont ceux qui font fuir l'information cachée : chaque script doit passer le test de non-fuite de `j-autorite-vues`.

**Vient après** : [`j-effets-choix`](#j-effets-choix)  
**Débloque** : — (rien n'en dépend)

<a id="j-cartes-talents"></a>
### `j-cartes-talents` — Talents : passifs, activés une fois par tour, déclenchés — et annulables

**Palier 11** · jalon **J2** · piste E (Effets & cartes) · couloir `J-EFF` (chimera) · P0 · taille M · complexité 5/5 · difficulté 5/5 · décision **D9**

**Pourquoi ce lot.** Les talents sont la partie la plus difficile du jeu moderne : ils agissent depuis le banc, en permanence, parfois pour annuler d'autres talents. C'est le vrai examen de passage de l'architecture d'effets.

**Ce qu'il fait.** Trois natures de talents — continus (toujours actifs, y compris depuis le banc), activés (une fois par tour, à son tour), déclenchés (sur un événement) ; talents qui annulent les talents adverses ; talents qui modifient les règles (coûts, dégâts, pioche) ; désactivation quand le Pokémon est affecté d'un état spécial, selon la carte.

**Mission**

- Représenter les trois natures et leur enregistrement automatique quand le Pokémon entre en jeu, leur retrait quand il en sort.
- Résoudre l'annulation mutuelle de talents (un talent qui éteint les talents, éteint-il celui qui l'éteint ?) selon `REGLES.md`, et le tester explicitement.
- Suivre les talents « une fois par tour » par Pokémon, et non par joueur.
- Tests : talent de banc qui soigne entre les tours, talent annulé par un talent adverse, talent activé deux fois refusé.

**Critères d'acceptation**

- Le cas d'annulation mutuelle est tranché par écrit et testé.
- Un talent cesse d'agir dès que son Pokémon quitte le jeu, au même instant.
- Cinq talents réels de natures différentes sont scriptés et testés.

**Livrables** : trois natures de talents, annulation de talents.

**Risque à surveiller.** Les talents continus consultés au mauvais moment (au début du tour au lieu du calcul) donnent des résultats justes en apparence et faux dans les cas limites, ceux qu'un joueur remarque.

**Vient après** : [`j-effets-architecture`](#j-effets-architecture), [`j-effets-choix`](#j-effets-choix)  
**Débloque** : — (rien n'en dépend)

<a id="j-effets-assistance-ia"></a>
### `j-effets-assistance-ia` — Assistance IA : proposer le script d'une carte, jamais le valider seule

**Palier 11** · jalon **J2** · piste E (Effets & cartes) · couloir `J-EFF` (chimera) · P1 · taille M · complexité 4/5 · difficulté 4/5 · décision **DJ8**

**Pourquoi ce lot.** Écrire des milliers de scripts à la main n'arrivera jamais au bout. L'IA du projet sait lire un texte de carte et proposer un script — à condition que rien n'entre en jeu sans être testé.

**Ce qu'il fait.** Un passage par lots : pour chaque carte non scriptée, l'IA propose un script dans le langage, ET les cas de test qui le vérifient, ET son niveau de confiance. Le script n'est activé que si ses tests passent et qu'un humain a validé la famille. Budget plafonné, journalisation des coûts, reprise après interruption — comme `v4-insights-batch`.

**Mission**

- Écrire le gabarit de requête : texte de la carte (FR et EN), schéma du langage, exemples validés proches, contraintes de sortie strictes.
- Exécuter les tests proposés ET une batterie de tests de cohérence maison (l'effet ne crée ni ne détruit de cartes, l'état reste valide).
- Mettre en file de relecture humaine par famille d'effet, pas carte par carte.
- Plafonner le budget, journaliser le coût par carte, reprendre après interruption sans reprendre les cartes déjà traitées.
- Mesurer : part des propositions acceptées sans retouche, part rejetée, coût par carte validée.

**Critères d'acceptation**

- Aucun script n'entre en jeu sans tests verts ET validation humaine de sa famille — vérifié par une contrainte en base, pas par une consigne.
- Le budget plafonné est respecté et le coût par carte validée est publié.
- Une interruption au milieu d'un lot ne perd rien et ne retraite rien.

**Livrables** : passage par lots IA → scripts + tests, file de relecture par famille, mesures de rendement.

**Risque à surveiller.** Un script plausible mais faux est plus dangereux qu'une carte non supportée : il fait perdre des parties sans que personne ne comprenne. Les tests de cohérence maison sont le vrai garde-fou, pas la confiance annoncée par le modèle.

**Vient après** : [`j-effets-catalogue-compilation`](#j-effets-catalogue-compilation)  
**Débloque** : — (rien n'en dépend)

<a id="j-effets-couverture-outil"></a>
### `j-effets-couverture-outil` — Tableau de couverture : ce qui est jouable, ce qui manque, et pour qui

**Palier 11** · jalon **J2** · piste E (Effets & cartes) · couloir `J-EFF` (chimera) · P1 · taille S · complexité 2/5 · difficulté 2/5 · décision **DJ2**

**Pourquoi ce lot.** Sans cette vue, personne ne sait où en est le chantier des cartes, ni pourquoi le deck d'Aymeric est refusé. Avec elle, l'effort se dirige : on script d'abord ce que les joueurs possèdent vraiment.

**Ce qu'il fait.** Couverture par extension, par famille d'effet et **par collection de joueur** ; liste des cartes qui bloquent le plus de decks ; état d'un deck (« jouable », « 3 cartes non supportées »), avec la raison par carte ; file de demande « je voudrais jouer cette carte » qui alimente la priorisation.

**Mission**

- Calculer la couverture et l'exposer dans l'API et dans une page d'administration.
- Classer les cartes manquantes par nombre de decks bloqués et par nombre de joueurs concernés.
- Brancher le rapport de légalité du constructeur de deck (`v7-decks-legalite`) sur cette source : la raison « carte non supportée » y devient explicite.
- Permettre à un joueur de signaler une carte qu'il veut jouer, et voir sa demande avancer.

**Critères d'acceptation**

- Le constructeur de deck affiche, pour chaque carte refusée, si c'est la possession, la légalité ou le script qui bloque.
- La page de couverture donne le chiffre par collection de joueur, pas seulement global.
- La file de demandes est visible dans le compte rendu de chaque lot de scripts.

**Livrables** : API et page de couverture, raison explicite dans la légalité des decks, file de demandes.

**Risque à surveiller.** Une couverture mesurée sur le catalogue entier (99 % de cartes que personne ne possède) donne un chiffre flatteur et inutile : la mesure qui compte est celle des collections réelles.

**Vient après** : [`j-effets-catalogue-compilation`](#j-effets-catalogue-compilation)  
**Débloque** : — (rien n'en dépend)

<a id="j-echanges-emotes"></a>
### `j-echanges-emotes` — Emotes prédéfinies : se parler sans chat libre

**Palier 11** · jalon **J4** · piste S (Serveur de parties) · couloir `J-SRV` (devAI) · P2 · taille S · complexité 1/5 · difficulté 1/5 · décision **DJ10**

**Pourquoi ce lot.** Un jeu à deux sans aucun signe de vie est froid ; un chat libre entre un adulte et un mineur demande une modération que ce projet n'aura pas. Les emotes prennent le meilleur des deux.

**Ce qu'il fait.** Une dizaine de messages prédéfinis (« bien joué », « oups », « ton tour », « belle carte »), limitation de débit, possibilité de couper les emotes de l'adversaire, aucune saisie libre, aucune trace conservée au-delà de la partie.

**Mission**

- Définir la liste avec JF, en s'assurant qu'aucune ne peut servir à narguer (pas d'emote ironique).
- Limiter le débit et permettre la coupure immédiate côté receveur.
- Ne rien persister au-delà de la partie.

**Critères d'acceptation**

- Aucune saisie de texte libre n'existe dans l'interface de jeu.
- Couper les emotes est immédiat et mémorisé.
- Le débit est limité et testé.

**Livrables** : emotes prédéfinies, coupure côté receveur.

**Risque à surveiller.** Ajouter « juste un petit chat » plus tard : ce serait un autre produit, avec une obligation de modération.

**Vient après** : [`j-temps-reel`](#j-temps-reel)  
**Débloque** : — (rien n'en dépend)

<a id="j-mode-solo"></a>
### `j-mode-solo` — Partie d'entraînement contre un bot

**Palier 11** · jalon **J4** · piste R (Règles & moteur) · couloir `J-MOT` (devAI) · P2 · taille S · complexité 2/5 · difficulté 2/5 · décision **DJ7**

**Pourquoi ce lot.** Le jeu est privé entre quelques comptes invités : il y aura des soirs sans adversaire. Le bot de simulation existe déjà pour les tests — l'ouvrir aux joueurs coûte peu et évite un écran d'attente vide.

**Ce qu'il fait.** Lancer une partie contre le bot heuristique depuis le salon, trois niveaux (hasard, correct, coriace), partie non comptée au classement et marquée « entraînement » dans l'historique, abandon libre, temps de réflexion du bot volontairement visible pour rester lisible.

**Mission**

- Brancher le bot de `j-simulation-bots` comme deuxième joueur d'une partie ordinaire du service.
- Trois niveaux d'heuristique, et un délai simulé pour que le joueur voie ce qui se passe.
- Marquer la partie « entraînement » : elle entre dans l'historique mais ne touche ni classement ni séries.
- Vérifier que le bot n'accède jamais à l'information cachée (il joue avec la vue du joueur, pas avec l'état complet).

**Critères d'acceptation**

- Une partie contre le bot se joue de bout en bout et se reprend après un F5.
- Le bot n'utilise que `vue(etat, bot)` — vérifié par un test.
- La partie apparaît dans l'historique en « entraînement » et n'affecte pas le classement.

**Livrables** : adversaire bot dans le salon, trois niveaux.

**Risque à surveiller.** Un bot qui triche en lisant la main adverse est indétectable côté joueur et ruine la confiance : la contrainte de vue est un test, pas une intention.

**Vient après** : [`j-simulation-bots`](#j-simulation-bots), [`j-partie-service`](#j-partie-service)  
**Débloque** : — (rien n'en dépend)

<a id="j-charge-temps-reel"></a>
### `j-charge-temps-reel` — Tenue en charge : combien de parties simultanées sur deux cœurs

**Palier 11** · jalon **J5** · piste Q (Qualité & exploitation) · couloir `J-QUA` (chimera) · P1 · taille S · complexité 3/5 · difficulté 3/5

**Pourquoi ce lot.** Le jeu sera servi par la machine qui héberge déjà kailo.life et ACX : deux cœurs, quatre gigaoctets, partagés. Il faut savoir avant, pas pendant.

**Ce qu'il fait.** Mesure du coût d'une partie (mémoire, CPU, connexions), montée en charge jusqu'au point de rupture, plafond de parties simultanées configuré et appliqué (file d'attente plutôt que dégradation), mesure de l'empreinte des instantanés et du journal en base, purge.

**Mission**

- Mesurer sur chimera puis vérifier sur le serveur cible, avec les autres services en fonctionnement.
- Fixer un plafond de parties simultanées et le faire appliquer par le service (refus explicite, pas ralentissement).
- Mesurer la croissance de la base par partie et dimensionner la purge en conséquence.
- Écrire les chiffres dans `docs/jeu/CHARGE.md` : ce sont eux qu'on relira le jour d'un incident.

**Critères d'acceptation**

- Le plafond est mesuré, écrit et appliqué.
- Une partie de plus que le plafond reçoit un refus clair, et les parties en cours ne ralentissent pas.
- La croissance de la base par partie est chiffrée et la purge dimensionnée.

**Livrables** : mesures de charge, plafond appliqué, docs/jeu/CHARGE.md.

**Risque à surveiller.** Mesurer sur une machine vide : le serveur cible sert déjà deux autres sites, et c'est là que se joue la vraie limite.

**Vient après** : [`j-simulation-bots`](#j-simulation-bots), [`j-temps-reel`](#j-temps-reel)  
**Débloque** : [`j-mise-en-ligne-jeu`](#j-mise-en-ligne-jeu)

<a id="j-deconnexion-abandon"></a>
### `j-deconnexion-abandon` — Déconnexion, abandon, désertion : une partie ne reste jamais suspendue

**Palier 12** · jalon **J1** · piste S (Serveur de parties) · couloir `J-SRV` (devAI) · P1 · taille S · complexité 3/5 · difficulté 3/5

**Pourquoi ce lot.** La panne la plus fréquente d'un jeu en ligne n'est pas une erreur de règle, c'est un adversaire qui ne revient pas. Ce que le jeu fait alors décide s'il reste jouable.

**Ce qu'il fait.** Détection de la coupure, pause avec délai de reprise annoncé, reprise transparente, abandon explicite (avec confirmation), désertion après expiration du délai, fin de partie par forfait, nettoyage des parties fantômes, trace dans l'historique (« gagnée par abandon »).

**Mission**

- Distinguer trois cas : coupure passagère, abandon volontaire, désertion — leurs conséquences ne sont pas les mêmes.
- Afficher des deux côtés ce qui se passe, avec le temps restant.
- Fermer proprement la partie et écrire son résultat sur les comptes (`j-fin-effets-compte`).
- Balayer périodiquement les parties sans activité et les clore avec un motif explicite — jamais les laisser dormir.
- Tests : déconnexion puis reprise dans le délai, déconnexion dépassant le délai, abandon pendant une demande de décision.

**Critères d'acceptation**

- Aucune partie ne reste « en cours » plus longtemps que le plafond configuré.
- Chaque clôture automatique porte son motif dans le journal et dans l'historique.
- La reprise dans le délai ne coûte aucun temps d'horloge au joueur déconnecté au-delà de la pause prévue.

**Livrables** : gestion des trois cas, balayage des parties mortes.

**Risque à surveiller.** Le nettoyage silencieux : une partie close sans motif ressemble à un bug pour le joueur, et masque les vraies pannes côté exploitation.

**Vient après** : [`j-timer`](#j-timer)  
**Débloque** : [`j-fin-effets-compte`](#j-fin-effets-compte)

<a id="j-initialisation"></a>
### `j-initialisation` — Mise en place : mélange, main de sept, mulligans, actif et banc face cachée, six récompenses

**Palier 12** · jalon **J1** · piste S (Serveur de parties) · couloir `J-MOT` (devAI) · P0 · taille M · complexité 4/5 · difficulté 4/5

**Pourquoi ce lot.** C'est la première chose que voit un joueur, et l'une des plus subtiles : les mulligans et la révélation simultanée sont des règles que la plupart des jeux en ligne simplifient à tort.

**Ce qu'il fait.** Mélange des deux decks, pioche de sept cartes, contrôle « au moins un Pokémon de base » ; mulligan : main révélée, remélangée, nouvelle main, l'adversaire pioche une carte supplémentaire par mulligan (selon `REGLES.md`) ; placement de l'actif et du banc **face cachée** ; six récompenses mises de côté ; révélation simultanée ; premier tour selon la règle retenue.

**Mission**

- Implémenter la boucle de mulligan et son comptage, avec la révélation de la main au bon moment.
- Placer l'actif et le banc face cachée : l'adversaire ne doit rien apprendre avant la révélation (c'est un cas du test de non-fuite).
- Rendre la révélation simultanée : aucun joueur ne voit avant l'autre, même si l'un valide plus tôt.
- Journaliser chaque mulligan, chaque pioche supplémentaire, et le contenu révélé.
- Tests : trois mulligans de suite, mulligan des deux joueurs, main sans Pokémon de base cinq fois d'affilée.

**Critères d'acceptation**

- Le placement face cachée ne laisse rien fuir avant la révélation (test dédié).
- Le comptage des cartes supplémentaires après mulligans est exact et journalisé.
- La révélation est simultanée même quand un joueur valide dix secondes avant l'autre.

**Livrables** : mise en place complète avec mulligans, révélation simultanée.

**Risque à surveiller.** Simplifier le placement face cachée « parce que c'est plus simple en ligne » : c'est une information de jeu réelle, et la révélation est un des rares moments spectaculaires du jeu.

**Vient après** : [`j-lancement-partie`](#j-lancement-partie), [`j-cartes-pokemon`](#j-cartes-pokemon)  
**Débloque** : — (rien n'en dépend)

<a id="j-plateau-layout"></a>
### `j-plateau-layout` — Plateau : la table de jeu, du grand écran au téléphone

**Palier 12** · jalon **J1** · piste U (Interface de jeu) · couloir `J-UI` (chimera) · P0 · taille L · complexité 4/5 · difficulté 4/5

**Pourquoi ce lot.** Tout le jeu se voit ici. La difficulté n'est pas graphique, elle est spatiale : neuf zones par joueur doivent tenir sur un écran de téléphone sans qu'on perde de vue l'essentiel.

**Ce qu'il fait.** Disposition des deux camps (actif, banc de cinq, main, pioche, défausse, six récompenses, Stade partagé), zoom sur une carte au survol ou au maintien, consultation des zones publiques (défausse), compteur des zones cachées, bascule bureau/tablette/téléphone, orientation paysage recommandée sur mobile.

**Mission**

- Poser la grille responsive et la hiérarchie visuelle : l'actif adverse et le sien dominent, la main reste accessible.
- Implémenter le zoom de carte (texte lisible, attaques, coûts) sans quitter la partie.
- Rendre consultables les zones publiques et afficher les compteurs des zones cachées.
- Vérifier la lisibilité réelle sur un téléphone d'enfant (petit écran, doigt, lumière) avant de continuer.

**Critères d'acceptation**

- Toutes les zones sont atteignables sans défilement sur un écran de 390 px de large en paysage.
- Le texte d'une carte zoomée est lisible sans pincer l'écran.
- Le plateau se redessine sans perdre l'état lors d'une rotation d'écran.

**Livrables** : plateau responsive, zoom de carte, consultation des zones.

**Risque à surveiller.** Dessiner d'abord pour le grand écran : le plateau devient injouable sur téléphone, qui sera pourtant l'écran le plus utilisé.

**Vient après** : [`j-temps-reel`](#j-temps-reel), [`j-salon-partie`](#j-salon-partie)  
**Débloque** : [`j-plateau-etat-visuel`](#j-plateau-etat-visuel), [`j-plateau-interactions`](#j-plateau-interactions), [`j-rendu-carte`](#j-rendu-carte)

<a id="j-notifications-jeu"></a>
### `j-notifications-jeu` — Être prévenu : invitation reçue, c'est ton tour, partie reprise

**Palier 12** · jalon **J4** · piste C (Compte & progression) · couloir `J-UI` (chimera) · P2 · taille S · complexité 2/5 · difficulté 2/5

**Pourquoi ce lot.** Un jeu à deux où personne ne sait que l'autre attend ne se joue pas. Une notification bien placée remplace dix messages.

**Ce qu'il fait.** Dans l'application : invitation reçue, adversaire trouvé, c'est ton tour, il te reste une minute, l'adversaire est revenu, partie terminée par forfait. Hors application : notification web (PWA) quand elle existe, e-mail seulement pour l'invitation. Réglages par type, silence nocturne.

**Mission**

- Poser le canal de notification dans l'application et ses réglages.
- Brancher les notifications hors application sur la PWA (`v6-pwa`) quand elle existe, sans en dépendre.
- Limiter strictement le nombre de notifications par partie : au-delà, c'est du harcèlement.
- Respecter un silence nocturne configurable — le joueur est un enfant.

**Critères d'acceptation**

- Chaque type de notification est désactivable séparément.
- Le silence nocturne est respecté, y compris pour les invitations.
- Aucune partie ne produit plus de notifications que le plafond fixé.

**Livrables** : notifications en application, réglages et silence nocturne.

**Risque à surveiller.** Notifier chaque tour : le jeu devient une sonnerie permanente et se fait couper au niveau du système, y compris pour les invitations.

**Vient après** : [`j-invitations`](#j-invitations), [`j-timer`](#j-timer)  
**Débloque** : — (rien n'en dépend)

<a id="j-plateau-etat-visuel"></a>
### `j-plateau-etat-visuel` — Lire le plateau d'un coup d'œil : dégâts, énergies, états, récompenses

**Palier 13** · jalon **J1** · piste U (Interface de jeu) · couloir `J-UI` (chimera) · P0 · taille M · complexité 3/5 · difficulté 3/5

**Pourquoi ce lot.** Un enfant doit comprendre la situation sans lire un tableau de chiffres : c'est ce qui sépare un jeu d'un formulaire.

**Ce qu'il fait.** Compteurs de dégâts posés sur la carte (comme les vrais jetons) avec PV restants, pastilles d'énergies typées empilées, Outil visible, états spéciaux montrés par l'orientation de la carte (couchée pour endormi, tournée pour confus) et par une icône, récompenses restantes de chaque côté, nombre de cartes en main et en pioche, mise en évidence du Pokémon qui vient d'agir.

**Mission**

- Dessiner chaque indicateur à partir de l'état projeté, sans recalcul.
- Reprendre les codes de la vraie table (jetons, rotation de carte) : c'est ce que l'enfant connaît déjà.
- Doubler chaque couleur d'un signe (type d'énergie, état) pour rester lisible en cas de daltonisme.
- Afficher les PV restants en plus des compteurs de dégâts — le calcul mental ne doit pas être imposé.

**Critères d'acceptation**

- L'état complet d'un Pokémon (dégâts, énergies, outil, états) se lit sans clic.
- Aucun indicateur ne dépend uniquement de la couleur.
- Les PV restants sont exacts, y compris avec un Outil qui ajoute des PV.

**Livrables** : indicateurs de plateau complets.

**Risque à surveiller.** Afficher les dégâts comme des PV soustraits : dès qu'un effet soigne ou change les PV maximum, l'affichage ment.

**Vient après** : [`j-plateau-layout`](#j-plateau-layout)  
**Débloque** : [`j-anim-socle`](#j-anim-socle), [`j-plateau-journal`](#j-plateau-journal)

<a id="j-plateau-interactions"></a>
### `j-plateau-interactions` — Jouer un coup : cibles valides, annulation, confirmation

**Palier 13** · jalon **J1** · piste U (Interface de jeu) · couloir `J-UI` (chimera) · P0 · taille M · complexité 4/5 · difficulté 4/5

**Pourquoi ce lot.** C'est là que le joueur sent si le jeu est bien fait. Et c'est là que le moteur paie : les cibles valides viennent de lui, l'interface ne recalcule aucune règle.

**Ce qu'il fait.** Glisser-déposer et tap-tap (les deux marchent), mise en évidence des cibles valides dès qu'une carte est saisie, actions grisées avec leur raison au survol, annulation tant que le coup n'est pas validé, confirmation explicite des coups irréversibles (attaquer, défausser, passer le tour), retour tactile et sonore.

**Mission**

- Consommer `actions_legales` pour illuminer les cibles ; aucune règle n'est réécrite côté client.
- Implémenter les deux modes d'interaction et les rendre interchangeables en cours de partie.
- Afficher la raison d'un refus telle que le moteur la donne, en langage clair.
- Distinguer coups annulables et coups irréversibles, et ne demander confirmation que pour les seconds.
- Empêcher le double envoi d'une action (clic répété, réseau lent) par un verrou d'interface et l'idempotence côté serveur.

**Critères d'acceptation**

- Aucune règle du jeu n'est implémentée côté client (revue de code explicite dans le compte rendu).
- Un coup refusé affiche la raison du moteur, pas un message générique.
- Un double clic ne joue jamais deux fois la même action.

**Livrables** : interactions glisser-déposer et tap-tap, cibles illuminées, annulation et confirmation.

**Risque à surveiller.** Recopier « juste une petite règle » côté client pour éviter un aller-retour : c'est le début de deux moteurs divergents, et le client finit par proposer des coups que le serveur refuse.

**Vient après** : [`j-plateau-layout`](#j-plateau-layout), [`j-actions-legales`](#j-actions-legales)  
**Débloque** : [`j-plateau-decisions`](#j-plateau-decisions)

<a id="j-rendu-carte"></a>
### `j-rendu-carte` — Ma photo ou l'image officielle : la carte telle qu'elle est jouée

**Palier 13** · jalon **J3** · piste G (Graphisme & animations) · couloir `J-GFX` (chimera) · P0 · taille M · complexité 3/5 · difficulté 3/5 · décision **DJ5**

**Pourquoi ce lot.** C'est la promesse du produit : on joue avec SES cartes, celles qu'on a photographiées, cornées, avec leur reflet — pas avec un catalogue anonyme. C'est aussi ce qui distingue ce jeu de tous les autres.

**Ce qu'il fait.** Trois rendus par carte : photo personnelle redressée, image officielle, dos de carte. Choix global et par deck (DJ5) ; repli sur l'image officielle si la photo manque ou est trop sombre ; redressement et recadrage au format carte ; indicateur discret « photo de Aymeric » ; réglage « ne jamais montrer mes photos à l'adversaire ».

**Mission**

- Réutiliser le redressement de `v3-detection` pour produire une image de jeu au bon format depuis la photo d'origine.
- Noter la qualité de chaque photo (netteté, luminosité, cadrage) et replier automatiquement sous un seuil, en le disant au joueur dans le constructeur de deck.
- Implémenter le choix global/par deck et le réglage de confidentialité.
- Vérifier la lisibilité en jeu : une photo au flash ne doit pas rendre la carte illisible sur le plateau.

**Critères d'acceptation**

- Une carte sans photo exploitable se joue avec l'image officielle, sans trou ni attente.
- Le réglage de confidentialité est respecté côté adversaire (test de bout en bout).
- Les trois rendus sont lisibles à la taille du plateau sur téléphone.

**Livrables** : rendu à trois variantes, note de qualité et repli, réglages.

**Risque à surveiller.** Servir la photo d'origine pleine résolution : une partie chargerait plusieurs dizaines de mégaoctets. Le format de jeu est produit à l'avance.

**Vient après** : [`j-plateau-layout`](#j-plateau-layout)  
**Débloque** : [`j-anim-pokemon-apparition`](#j-anim-pokemon-apparition), [`j-assets-pipeline`](#j-assets-pipeline)

<a id="j-fin-effets-compte"></a>
### `j-fin-effets-compte` — Ce qu'une partie laisse sur le compte : écriture unique et exacte

**Palier 13** · jalon **J4** · piste C (Compte & progression) · couloir `J-SRV` (devAI) · P0 · taille M · complexité 3/5 · difficulté 4/5 · décision **DJ6**

**Pourquoi ce lot.** C'est la demande de JF (« la fin de jeu, avec ses effets sur le compte joueur »). Le piège est technique : une partie peut se terminer deux fois — reprise, rejeu, double événement — et doubler les victoires.

**Ce qu'il fait.** À la clôture d'une partie : écriture de son résultat (vainqueur, raison, durée, tours), mise à jour des compteurs du joueur (parties, victoires, défaites, série en cours et meilleure série, temps de jeu), statistiques par deck et par adversaire, attribution des badges, mise à jour du classement privé si activé. Le tout en une transaction idempotente, déclenchée par un événement de fin unique.

**Mission**

- Poser une clé d'idempotence sur la partie : deux clôtures ne produisent qu'une écriture (contrainte en base, pas un `if`).
- Recalculer les statistiques de fin depuis le journal, jamais depuis des compteurs tenus pendant la partie.
- Traiter les fins anormales (abandon, désertion, temps) avec le même chemin d'écriture.
- Prévoir la reprise après panne : une partie close dont l'écriture a échoué est reprise par un balayage, et le signale.
- Tests : clôture rejouée deux fois, clôture pendant une reprise, clôture d'une partie d'entraînement (aucun effet de classement).

**Critères d'acceptation**

- Rejouer la clôture d'une partie ne modifie rien la deuxième fois (test explicite).
- Les statistiques recalculées depuis le journal correspondent à la partie jouée.
- Une partie d'entraînement contre le bot n'affecte ni classement ni série.

**Livrables** : clôture idempotente, statistiques recalculées depuis le journal.

**Risque à surveiller.** Compter les victoires au fil de l'eau : c'est la panne muette classique — personne ne remarque un compteur faux avant que quelqu'un ne compte.

**Vient après** : [`j-ko-recompenses`](#j-ko-recompenses), [`j-deconnexion-abandon`](#j-deconnexion-abandon)  
**Débloque** : [`j-classement-prive`](#j-classement-prive), [`j-mise-en-ligne-jeu`](#j-mise-en-ligne-jeu), [`j-stats-joueur`](#j-stats-joueur)

<a id="j-plateau-journal"></a>
### `j-plateau-journal` — Journal de partie : ce qui vient de se passer, en français

**Palier 14** · jalon **J1** · piste U (Interface de jeu) · couloir `J-UI` (chimera) · P0 · taille S · complexité 2/5 · difficulté 2/5

**Pourquoi ce lot.** C'est ce qui rend le jeu compréhensible quand on apprend : « Aymeric attache une Énergie Feu à Salamèche, puis attaque : 60 dégâts, ×2 faiblesse = 120 ». Sans ce fil, l'enfant subit des changements qu'il ne relie à rien.

**Ce qu'il fait.** Fil des coups en langage naturel, dernier coup mis en évidence sur le plateau, détail du calcul des dégâts, filtres (mes coups, ceux de l'adversaire, effets automatiques), retour visuel sur un coup passé, tout en restant dans la partie.

**Mission**

- Traduire les événements du moteur en phrases françaises, avec les noms de cartes et les images en vignette.
- Relier chaque ligne du journal à l'endroit du plateau concerné (surbrillance au survol).
- Inclure les effets automatiques (poison entre les tours, expiration d'un blocage) : ce sont ceux qu'on ne comprend pas autrement.
- Garder le fil lisible sur téléphone (panneau escamotable).

**Critères d'acceptation**

- Chaque événement du moteur a sa formulation française — aucun `event_type` brut affiché.
- Le détail du calcul de dégâts est consultable pour chaque attaque.
- Les effets automatiques apparaissent au journal.

**Livrables** : journal en langage naturel, liaison journal ↔ plateau.

**Risque à surveiller.** Afficher les identifiants techniques quand une traduction manque : mieux vaut un test qui échoue en CI sur un événement non traduit.

**Vient après** : [`j-plateau-etat-visuel`](#j-plateau-etat-visuel)  
**Débloque** : [`j-partie-fin-ui`](#j-partie-fin-ui), [`j-plateau-aide`](#j-plateau-aide)

<a id="j-plateau-decisions"></a>
### `j-plateau-decisions` — Fenêtres de décision : choisir des cartes, ordonner, répondre pendant le tour adverse

**Palier 14** · jalon **J2** · piste U (Interface de jeu) · couloir `J-UI` (chimera) · P0 · taille M · complexité 4/5 · difficulté 4/5

**Pourquoi ce lot.** C'est l'interface des cartes à effet. Sans elle, les Objets et Supporters restent injouables même quand le moteur sait les résoudre.

**Ce qu'il fait.** Sélecteurs adaptés à chaque type de demande : choisir N cartes dans un ensemble (pioche, défausse, main), ordonner des cartes, oui/non, choisir un Pokémon en jeu, choisir un type ou un nombre ; affichage du temps restant ; demandes reçues pendant le tour adverse, annoncées clairement ; réponse par défaut visible avant l'expiration.

**Mission**

- Construire un composant générique piloté par la description de la demande, pas un écran par carte.
- Traiter le cas « c'est à l'adversaire de décider » : le joueur actif voit qu'il attend et pourquoi.
- Afficher le compte à rebours de la décision et ce qui se passera à l'expiration.
- Rendre les grands ensembles utilisables : recherche et filtres dans une pioche de soixante cartes.
- Tests d'interface : demande imbriquée, expiration, reprise après F5 au milieu d'une demande.

**Critères d'acceptation**

- Toute demande du moteur s'affiche correctement sans code spécifique à la carte.
- Chercher une carte dans la pioche prend moins de cinq secondes (recherche et filtres).
- L'attente d'une décision adverse est explicite des deux côtés.

**Livrables** : composant de décision générique, recherche dans les grands ensembles.

**Risque à surveiller.** Un écran par carte : le nombre de cartes rend l'approche impossible dès la deuxième extension.

**Vient après** : [`j-plateau-interactions`](#j-plateau-interactions), [`j-effets-choix`](#j-effets-choix)  
**Débloque** : [`j-accessibilite-jeu`](#j-accessibilite-jeu), [`j-e2e-deux-navigateurs`](#j-e2e-deux-navigateurs)

<a id="j-anim-socle"></a>
### `j-anim-socle` — Socle d'animation : les effets suivent les événements, jamais l'inverse

**Palier 14** · jalon **J3** · piste G (Graphisme & animations) · couloir `J-GFX` (chimera) · P0 · taille M · complexité 4/5 · difficulté 4/5

**Pourquoi ce lot.** C'est la pièce qui décide si les animations sont un plaisir ou un bug : elles doivent raconter ce que le serveur a déjà décidé, sans jamais afficher un état qui n'existe pas.

**Ce qu'il fait.** Une file d'animations alimentée par les événements du moteur ; chaque animation a une durée bornée et peut être accélérée ou sautée ; l'état affiché reste celui du serveur (l'animation est une transition, pas une source de vérité) ; respect de `prefers-reduced-motion` ; rattrapage quand plusieurs événements arrivent d'un coup (reprise après coupure).

**Mission**

- Implémenter la file, ses durées et son mode accéléré ; interdire toute animation bloquante.
- Garantir qu'un événement non animé (type inconnu) applique tout de même son changement d'état — visible, sans effet.
- Traiter la reprise : à la reconnexion, les vingt événements manqués ne se rejouent pas un par un, ils se résument.
- Mesurer la fluidité sur un téléphone d'entrée de gamme et fixer un plancher d'images par seconde.

**Critères d'acceptation**

- Aucune animation ne peut empêcher une action légale d'être jouée (l'animation se saute).
- Un événement sans animation définie ne bloque ni ne disparaît.
- Le plancher d'images par seconde est tenu sur l'appareil de référence.

**Livrables** : file d'animations, mode accéléré et réduit, mesure de fluidité.

**Risque à surveiller.** Faire dépendre l'état affiché de la fin d'une animation : au moindre onglet en arrière-plan, le plateau se fige dans un état faux.

**Vient après** : [`j-plateau-etat-visuel`](#j-plateau-etat-visuel)  
**Débloque** : [`j-accessibilite-jeu`](#j-accessibilite-jeu), [`j-anim-attaques-typees`](#j-anim-attaques-typees), [`j-anim-evolution-ko`](#j-anim-evolution-ko), [`j-anim-pokemon-apparition`](#j-anim-pokemon-apparition), [`j-arene-decors`](#j-arene-decors), [`j-son`](#j-son)

<a id="j-assets-pipeline"></a>
### `j-assets-pipeline` — Fabrique d'images : vignettes, variantes, cache et budget de poids

**Palier 14** · jalon **J3** · piste G (Graphisme & animations) · couloir `J-GFX` (chimera) · P1 · taille M · complexité 3/5 · difficulté 3/5

**Pourquoi ce lot.** Une partie affiche jusqu'à 120 cartes. Sans pré-calcul et sans budget, le plateau se charge pendant une minute sur un téléphone en 4G, et le jeu meurt là.

**Ce qu'il fait.** Génération des variantes (plateau, main, zoom, vignette de journal) en WebP/AVIF, au moment de l'ajout à la collection et non pendant la partie ; cache avec empreinte ; pré-chargement du deck au lancement de la partie ; budget de poids par partie mesuré et tenu ; images officielles mises en cache localement.

**Mission**

- Produire les variantes par lots sur chimera (GPU disponible) et les stocker à côté des photos d'origine.
- Pré-charger les images du deck pendant la mise en place, avec une barre de progression honnête.
- Mesurer le poids réel d'une partie et poser un plafond ; dépasser le plafond doit faire échouer la CI, pas ralentir le joueur.
- Prévoir la régénération quand une photo est remplacée.

**Critères d'acceptation**

- Le poids total d'une partie reste sous le plafond fixé, mesuré en CI.
- Aucune génération d'image n'a lieu pendant une partie.
- Le pré-chargement se termine avant la fin de la mise en place dans les conditions de test (4G simulée).

**Livrables** : génération par lots, pré-chargement, budget mesuré en CI.

**Risque à surveiller.** Générer à la volée « pour commencer » : le serveur qui sert kailo.life a deux cœurs, et une partie suffirait à le mettre à genoux.

**Vient après** : [`j-rendu-carte`](#j-rendu-carte)  
**Débloque** : — (rien n'en dépend)

<a id="j-classement-prive"></a>
### `j-classement-prive` — Classement privé entre comptes invités

**Palier 14** · jalon **J4** · piste C (Compte & progression) · couloir `J-SRV` (devAI) · P2 · taille S · complexité 2/5 · difficulté 2/5 · décision **DJ6**

**Pourquoi ce lot.** Entre deux ou trois joueurs, un tableau amical suffit à donner un enjeu. Mais c'est aussi ce qui peut transformer un jeu entre frères en dispute : le format se choisit avec JF (DJ6).

**Ce qu'il fait.** Tableau des comptes invités, points ou simple décompte de victoires, évolution dans le temps, parties d'entraînement exclues, pas de saison ni de perte de points sauf si DJ6 en décide autrement, possibilité de désactiver entièrement le classement.

**Mission**

- Implémenter le calcul retenu en DJ6, en le gardant remplaçable (la formule n'est pas dans le code de clôture).
- Exclure les parties d'entraînement et les parties closes par désertion selon la règle choisie.
- Permettre à JF de désactiver le classement sans déployer.
- Tests : recalcul complet du classement depuis l'historique donne le même résultat que le calcul incrémental.

**Critères d'acceptation**

- Le classement se recalcule intégralement depuis l'historique et retrouve le même état.
- La désactivation est un réglage, pas un déploiement.
- Les parties d'entraînement n'y figurent jamais.

**Livrables** : classement privé paramétrable.

**Risque à surveiller.** Un classement incrémental non recalculable : la première erreur devient définitive.

**Vient après** : [`j-fin-effets-compte`](#j-fin-effets-compte)  
**Débloque** : — (rien n'en dépend)

<a id="j-accessibilite-jeu"></a>
### `j-accessibilite-jeu` — Confort et accessibilité : jouable par un enfant, lisible par tous

**Palier 15** · jalon **J3** · piste U (Interface de jeu) · couloir `J-UI` (chimera) · P1 · taille S · complexité 2/5 · difficulté 3/5

**Pourquoi ce lot.** Le public de ce jeu est un enfant et son entourage. Contraste, taille des cibles tactiles, animations coupables et daltonisme ne sont pas des options tardives : ce sont des conditions pour que la partie se joue.

**Ce qu'il fait.** Contraste conforme, cibles tactiles suffisantes, navigation clavier complète, respect de `prefers-reduced-motion` (animations réduites ou supprimées), mode « temps rallongé » pour les décisions, taille de texte réglable, types d'énergie identifiables autrement que par la couleur, annonces pour lecteur d'écran des événements importants.

**Mission**

- Passer l'audit d'accessibilité du projet sur les écrans de jeu (le même que pour le reste du produit).
- Rendre chaque animation coupable, globalement et individuellement.
- Vérifier la jouabilité au clavier seul, de la file d'attente à la fin de partie.
- Ajouter le mode temps rallongé et le brancher sur les horloges (DJ4).

**Critères d'acceptation**

- L'audit passe sur tous les écrans de jeu.
- Une partie complète se joue au clavier seul.
- `prefers-reduced-motion` supprime les animations sans changer la lisibilité de l'état.

**Livrables** : audit passé, navigation clavier, mode temps rallongé.

**Risque à surveiller.** Traiter l'accessibilité après les animations : les effets visuels sont alors tellement intriqués qu'on ne peut plus les couper proprement.

**Vient après** : [`j-plateau-decisions`](#j-plateau-decisions), [`j-anim-socle`](#j-anim-socle)  
**Débloque** : — (rien n'en dépend)

<a id="j-anim-attaques-typees"></a>
### `j-anim-attaques-typees` — Une attaque Feu brûle la carte d'en face : un effet par type

**Palier 15** · jalon **J3** · piste G (Graphisme & animations) · couloir `J-GFX` (chimera) · P1 · taille L · complexité 4/5 · difficulté 4/5

**Pourquoi ce lot.** C'est la demande explicite de JF, et c'est ce qui fait qu'un enfant a envie de rejouer : l'attaque doit se voir et se sentir, pas s'afficher en chiffres.

**Ce qu'il fait.** Un effet par type d'énergie, joué sur la carte cible : **Feu** — flammes qui lèchent la carte adverse, bords qui noircissent, braises qui retombent ; **Eau** — vague qui traverse, ruissellement, carte trempée ; **Plante** — lianes qui enserrent, pétales ; **Électrique** — arc, flash blanc, tremblement du plateau ; **Psy** — onde concentrique, distorsion de l'image de la carte ; **Combat** — impact, fissure, recul ; **Obscurité** — ombre qui engloutit ; **Métal** — éclat, étincelles ; **Dragon** — souffle ; **Fée** — étoiles. Intensité proportionnelle aux dégâts, effet renforcé en cas de faiblesse, effet atténué en cas de résistance, effet particulier pour un échec au pile ou face.

**Mission**

- Écrire les effets en shaders/canvas légers réutilisables, paramétrés par intensité — pas dix animations sans rapport entre elles.
- Lier l'intensité au résultat réel : dégâts infligés, faiblesse appliquée, résistance, échec.
- Faire subsister une trace brève (la carte brûlée reste noircie une seconde) sans jamais masquer les compteurs de dégâts.
- Prévoir la version réduite de chaque effet pour `prefers-reduced-motion` et pour les appareils lents.
- Faire valider le rendu par JF et par Aymeric avant d'industrialiser les dix types.

**Critères d'acceptation**

- Les dix types ont leur effet, et l'intensité reflète le résultat du calcul.
- L'effet ne masque jamais l'état du plateau plus d'une seconde.
- La version réduite existe pour chaque effet et reste compréhensible.
- Le plancher d'images par seconde est tenu avec l'effet le plus lourd.

**Livrables** : dix effets typés paramétrés, versions réduites, validation par JF.

**Risque à surveiller.** Dix animations écrites séparément : impossible à maintenir, et l'une d'elles finira par cacher un compteur de dégâts au moment décisif.

**Vient après** : [`j-anim-socle`](#j-anim-socle)  
**Débloque** : — (rien n'en dépend)

<a id="j-anim-evolution-ko"></a>
### `j-anim-evolution-ko` — Évolution, K.O., récompense : les moments qui comptent

**Palier 15** · jalon **J3** · piste G (Graphisme & animations) · couloir `J-GFX` (chimera) · P1 · taille M · complexité 3/5 · difficulté 3/5

**Pourquoi ce lot.** Ce sont les trois instants forts d'une partie. Les jouer platement, c'est perdre l'essentiel de l'émotion du jeu.

**Ce qu'il fait.** Évolution (la carte d'évolution se pose en fondu lumineux sur la précédente, halo, la pile se voit), mise K.O. (la carte bascule, se désature et rejoint la défausse), prise de récompense (la carte quitte la ligne des récompenses et rejoint la main, au dos puis révélée), mise en place initiale (les cartes se distribuent, les récompenses s'alignent, la révélation simultanée est un moment), mulligan (main révélée puis remélangée), pile ou face animé et honnête.

**Mission**

- Écrire les six animations sur le socle, avec leurs durées et leurs versions réduites.
- Soigner la révélation simultanée de la mise en place : c'est le premier effet que voit un joueur.
- Rendre le pile ou face lisible et non truqué en apparence : le résultat vient du serveur, l'animation s'arrête dessus.
- Vérifier que chaque animation reste juste quand plusieurs événements s'enchaînent (double K.O., deux récompenses).

**Critères d'acceptation**

- Un double K.O. affiche deux animations sans se chevaucher ni se perdre.
- La prise de deux récompenses se voit comme deux cartes.
- Le pile ou face ne donne jamais une impression de résultat prédéterminé côté client.

**Livrables** : six animations de moments clés.

**Risque à surveiller.** Faire durer l'animation de K.O. plus que le plaisir : au-delà d'une seconde et demie, elle agace au lieu de marquer.

**Vient après** : [`j-anim-socle`](#j-anim-socle)  
**Débloque** : — (rien n'en dépend)

<a id="j-anim-pokemon-apparition"></a>
### `j-anim-pokemon-apparition` — Le Pokémon apparaît au-dessus de sa carte

**Palier 15** · jalon **J3** · piste G (Graphisme & animations) · couloir `J-GFX` (chimera) · P2 · taille L · complexité 5/5 · difficulté 5/5 · décision **DJ3**

**Pourquoi ce lot.** C'est le « bel effet » demandé par JF : la carte n'est plus un carton, le Pokémon sort de son illustration pour attaquer. C'est le moment que raconte un enfant de onze ans après sa partie.

**Ce qu'il fait.** Pour une liste restreinte de Pokémon, une apparition animée au-dessus de la carte lors de la pose, de l'évolution ou de l'attaque : le sujet est détouré de l'illustration officielle de la carte (segmentation), mis en volume par un léger déplacement en parallaxe, accompagné de particules du type correspondant, puis se replie dans la carte. Dégradation propre : un Pokémon sans apparition préparée joue l'effet de type générique.

**Mission**

- Trancher DJ3 avec JF **avant** toute production d'assets : aucune image nouvelle n'est introduite, tout part de l'illustration de la carte.
- Mettre au point la chaîne de détourage sur chimera (segmentation GPU), produire les découpes par lots, contrôler la qualité à la main sur les Pokémon vedettes.
- Animer en parallaxe et en particules, sans modèle 3D : le coût doit rester tenable sur un téléphone.
- Établir la liste des Pokémon vedettes avec Aymeric (ses préférés d'abord), et la faire grandir par lots.
- Garantir la dégradation : sans découpe, l'effet de type suffit et rien ne manque visiblement.

**Critères d'acceptation**

- DJ3 est tranchée et écrite avant la première découpe.
- Une carte sans découpe joue l'effet générique, sans trou ni message d'erreur.
- Le coût d'affichage reste sous le plafond de fluidité sur l'appareil de référence.
- Les découpes des Pokémon vedettes sont validées à l'œil, une par une.

**Livrables** : chaîne de détourage par lots, apparition en parallaxe, liste des vedettes.

**Risque à surveiller.** Introduire des sprites ou des modèles pris ailleurs : ce serait un usage d'images protégées sur un service en ligne, même privé et sans revenu. La découpe de l'illustration de la carte que le joueur possède est le chemin à tenir, et il est tranché par JF avant qu'un octet ne soit produit.

**Vient après** : [`j-anim-socle`](#j-anim-socle), [`j-rendu-carte`](#j-rendu-carte)  
**Débloque** : — (rien n'en dépend)

<a id="j-arene-decors"></a>
### `j-arene-decors` — Décors d'arène : jouer quelque part, pas sur un fond gris

**Palier 15** · jalon **J3** · piste G (Graphisme & animations) · couloir `J-GFX` (chimera) · P2 · taille S · complexité 2/5 · difficulté 2/5

**Pourquoi ce lot.** Un tapis de jeu et un décor changent l'impression générale pour un coût dérisoire, et donnent une raison de revenir (en débloquer un nouveau).

**Ce qu'il fait.** Plusieurs tapis de jeu et fonds d'arène, choix par le joueur, thème automatique selon le type dominant du deck, variation jour/nuit, respect du contraste avec les cartes, décors débloqués par les badges.

**Mission**

- Produire quatre à six décors sobres qui ne concurrencent jamais la lisibilité des cartes.
- Brancher le choix sur le profil du joueur et le thème automatique sur le deck.
- Vérifier le contraste des indicateurs sur chaque décor.
- Relier le déblocage aux badges (`j-profil-jeu`) si DJ6 le retient.

**Critères d'acceptation**

- Chaque décor passe le contrôle de contraste avec tous les indicateurs de plateau.
- Le changement de décor n'affecte ni la disposition ni la lisibilité.
- Le poids des décors entre dans le budget de la partie.

**Livrables** : décors et tapis, thème automatique par deck.

**Risque à surveiller.** Des décors trop présents : la carte, les jetons et les énergies doivent rester ce qu'on voit en premier.

**Vient après** : [`j-anim-socle`](#j-anim-socle)  
**Débloque** : — (rien n'en dépend)

<a id="j-plateau-aide"></a>
### `j-plateau-aide` — Aide en jeu : pourquoi je ne peux pas faire ça, et que puis-je faire

**Palier 15** · jalon **J3** · piste U (Interface de jeu) · couloir `J-UI` (chimera) · P1 · taille M · complexité 3/5 · difficulté 3/5

**Pourquoi ce lot.** JF vise un enfant de onze ans qui ne connaît pas toutes les règles. Un jeu qui explique ses refus s'apprend en jouant ; un jeu muet se désinstalle.

**Ce qu'il fait.** Rappel de règle contextuel (le refus du moteur cite une règle, l'aide l'explique en une phrase), suggestion « voici ce que tu peux faire » à partir des actions légales, première partie guidée pas à pas, glossaire des mots du jeu, rappel de l'objectif (« prends six récompenses »).

**Mission**

- Associer à chaque identifiant de règle du corpus une explication courte, écrite pour un enfant.
- Proposer les coups possibles quand le joueur hésite plus de N secondes, sans jamais jouer à sa place.
- Écrire le parcours guidé de la première partie (contre le bot) : poser, attacher, attaquer, prendre une récompense.
- Relire les textes avec JF : c'est le lot où le ton compte plus que le code.

**Critères d'acceptation**

- Chaque raison de refus produite par le moteur a son explication en français simple.
- La première partie guidée se termine sans aide extérieure par un joueur qui n'a jamais joué.
- L'aide ne joue jamais le coup à la place du joueur.

**Livrables** : explications par règle, partie guidée, glossaire.

**Risque à surveiller.** Écrire l'aide à partir du code plutôt que du corpus de règles : les deux divergent, et l'aide explique des règles qui ne sont pas celles appliquées.

**Vient après** : [`j-plateau-journal`](#j-plateau-journal)  
**Débloque** : — (rien n'en dépend)

<a id="j-son"></a>
### `j-son` — Sons du jeu : entendre l'attaque, la pioche et la victoire

**Palier 15** · jalon **J3** · piste G (Graphisme & animations) · couloir `J-GFX` (chimera) · P2 · taille S · complexité 2/5 · difficulté 2/5 · décision **DJ9**

**Pourquoi ce lot.** Le son fait la moitié de la sensation de jeu, pour un coût très faible. Il doit rester coupable en un geste.

**Ce qu'il fait.** Bruitages : carte posée, énergie attachée, attaque par type, K.O., récompense prise, pile ou face, minuterie qui s'épuise, victoire et défaite. Musique d'ambiance optionnelle, coupée par défaut (DJ9). Réglages mémorisés par appareil, coupure globale immédiate, sons respectant le mode silencieux du système.

**Mission**

- Choisir ou produire des sons libres de droits, courts, non agressifs.
- Brancher les sons sur les mêmes événements que les animations, avec la même file.
- Régler les volumes relatifs pour qu'aucun son ne surprenne (la minuterie surtout).
- Respecter les réglages système et le mode silencieux, et tester sur mobile.

**Critères d'acceptation**

- Tous les sons sont libres de droits, et leur origine est écrite dans le dépôt.
- La coupure est immédiate et mémorisée.
- Aucun son ne se déclenche avant une interaction du joueur (règle des navigateurs).

**Livrables** : banque de sons sourcée, réglages mémorisés.

**Risque à surveiller.** Des sons pris au hasard sur Internet : c'est un risque de droits pour quelques kilo-octets d'effet. La source de chaque son est écrite.

**Vient après** : [`j-anim-socle`](#j-anim-socle)  
**Débloque** : — (rien n'en dépend)

<a id="j-partie-fin-ui"></a>
### `j-partie-fin-ui` — Fin de partie : qui a gagné, pourquoi, et ce qu'on en retient

**Palier 15** · jalon **J4** · piste U (Interface de jeu) · couloir `J-UI` (chimera) · P0 · taille S · complexité 2/5 · difficulté 2/5

**Pourquoi ce lot.** La fin est le moment qui donne envie de rejouer, ou pas. C'est aussi là que se voit ce que la partie a laissé sur le compte.

**Ce qu'il fait.** Annonce du vainqueur et de la raison (six récompenses, banc vide, pioche vide, abandon, temps), récapitulatif (durée, nombre de tours, dégâts infligés, cartes jouées, meilleur coup), effet sur le compte (série en cours, statistiques mises à jour, badge obtenu), boutons rejouer / revanche / retour au salon, lien vers le replay.

**Mission**

- Écrire l'écran pour les deux issues, sans humilier le perdant (pas de « défaite écrasante »).
- Afficher ce qui a changé sur le compte, avec un lien vers l'historique.
- Proposer la revanche immédiate, qui relance une partie avec les mêmes joueurs et decks.
- Traiter les fins anormales (abandon, désertion, temps) avec le même soin que les fins normales.

**Critères d'acceptation**

- Chaque raison de fin possible a son libellé propre.
- La revanche relance une partie sans repasser par la file.
- Le récapitulatif est exact, recalculé depuis le journal et non compté au fil de l'eau.

**Livrables** : écran de fin, revanche, récapitulatif depuis le journal.

**Risque à surveiller.** Compter les statistiques au fil de la partie : une reprise après F5 les double. Elles se recalculent depuis le journal.

**Vient après** : [`j-plateau-journal`](#j-plateau-journal), [`j-ko-recompenses`](#j-ko-recompenses)  
**Débloque** : [`j-e2e-deux-navigateurs`](#j-e2e-deux-navigateurs), [`j-stats-joueur`](#j-stats-joueur)

<a id="j-stats-joueur"></a>
### `j-stats-joueur` — Mes parties : historique, statistiques et ce que ça dit de mes decks

**Palier 16** · jalon **J4** · piste C (Compte & progression) · couloir `J-UI` (chimera) · P1 · taille M · complexité 2/5 · difficulté 2/5

**Pourquoi ce lot.** C'est ce qui donne une suite aux parties : on voit ce qui marche, avec quel deck, contre qui — et le gestionnaire de decks s'en nourrit.

**Ce qu'il fait.** Liste des parties (adversaire, deck, résultat, durée, date, lien vers le replay), filtres, taux de victoire par deck et par adversaire, cartes les plus jouées, attaques les plus décisives, temps de jeu, séries. Vue « ce deck gagne surtout contre les decks Eau ».

**Mission**

- Construire les agrégats à partir des résultats de parties, avec des calculs lisibles et testés.
- Relier chaque ligne à son replay.
- Brancher les statistiques par deck sur la fiche de deck du gestionnaire (`v7-decks-stats`).
- Rester honnête sur les petits nombres : trois parties ne font pas un taux de victoire.

**Critères d'acceptation**

- Les agrégats correspondent aux parties réellement jouées (vérifié sur un jeu de données de test).
- Un taux calculé sur moins de cinq parties est signalé comme non significatif.
- La page se charge en moins d'une seconde avec cent parties.

**Livrables** : page Mes parties, agrégats par deck et adversaire, liaison avec la fiche de deck.

**Risque à surveiller.** Des statistiques flatteuses calculées sur trois parties : elles trompent le joueur sur son deck et faussent ses choix.

**Vient après** : [`j-fin-effets-compte`](#j-fin-effets-compte), [`j-partie-fin-ui`](#j-partie-fin-ui)  
**Débloque** : [`j-profil-jeu`](#j-profil-jeu)

<a id="j-e2e-deux-navigateurs"></a>
### `j-e2e-deux-navigateurs` — Partie complète jouée automatiquement, à deux navigateurs

**Palier 16** · jalon **J5** · piste Q (Qualité & exploitation) · couloir `J-QUA` (chimera) · P0 · taille M · complexité 4/5 · difficulté 4/5

**Pourquoi ce lot.** C'est la seule preuve qui vaut pour JF : deux navigateurs, une partie jouée du début à la fin, sans intervention.

**Ce qu'il fait.** Playwright pilotant deux contextes, parcours complet (connexion, choix du deck, file, appariement, mise en place avec mulligan, plusieurs tours, attaques, Dresseurs, K.O., fin de partie, historique mis à jour), plus les parcours dégradés : F5 au milieu, expiration d'horloge, abandon, déconnexion et reprise, repli en interrogation périodique.

**Mission**

- Écrire le parcours nominal avec un deck de test aux scripts garantis.
- Ajouter les quatre parcours dégradés, chacun avec sa preuve (capture, journal).
- Tourner en CI sur chaque modification du jeu, et publier les captures dans le compte rendu.
- Garder le test lisible : il sert aussi de documentation du parcours.

**Critères d'acceptation**

- Le parcours nominal et les quatre parcours dégradés sont verts en CI.
- Les captures d'écran de la partie sont jointes au compte rendu.
- Le test échoue si l'historique du compte n'est pas mis à jour à la fin.

**Livrables** : e2e à deux navigateurs, quatre parcours dégradés, captures en CI.

**Risque à surveiller.** Un e2e qui ne vérifie que la fin heureuse : les pannes réelles sont toutes dans les parcours dégradés.

**Vient après** : [`j-partie-fin-ui`](#j-partie-fin-ui), [`j-plateau-decisions`](#j-plateau-decisions)  
**Débloque** : [`j-securite-jeu`](#j-securite-jeu)

<a id="j-profil-jeu"></a>
### `j-profil-jeu` — Profil de joueur : avatar, carte fétiche, badges

**Palier 17** · jalon **J4** · piste C (Compte & progression) · couloir `J-UI` (chimera) · P2 · taille S · complexité 2/5 · difficulté 1/5 · décision **DJ6**

**Pourquoi ce lot.** Des récompenses symboliques, gratuites, sans monnaie ni achat : c'est ce qui fait revenir un enfant sans rien lui vendre.

**Ce qu'il fait.** Avatar et pseudo repris du compte, carte fétiche choisie dans sa collection et affichée à l'adversaire au lancement, badges (première victoire, K.O. en un coup, victoire sans perdre de récompense, dix parties, deck monotype victorieux), décors débloqués, vitrine de profil.

**Mission**

- Définir la liste des badges avec JF et Aymeric, en évitant tout badge qui pousse à jouer longtemps plutôt que bien.
- Calculer l'attribution à la clôture d'une partie, de façon idempotente.
- Afficher la carte fétiche des deux côtés au moment du lancement.
- Aucun achat, aucune monnaie, aucune récompense aléatoire.

**Critères d'acceptation**

- Un badge ne peut être attribué deux fois.
- Aucun mécanisme ne récompense le temps passé plutôt que le jeu lui-même.
- La carte fétiche s'affiche au lancement, avec le rendu choisi (photo ou officielle).

**Livrables** : badges, carte fétiche, vitrine de profil.

**Risque à surveiller.** Des badges de temps de jeu : ils transforment un jeu en obligation quotidienne, ce qui n'est pas ce qu'on veut pour un enfant de onze ans.

**Vient après** : [`j-stats-joueur`](#j-stats-joueur)  
**Débloque** : — (rien n'en dépend)

<a id="j-securite-jeu"></a>
### `j-securite-jeu` — Revue de sécurité du jeu avant ouverture

**Palier 17** · jalon **J5** · piste Q (Qualité & exploitation) · couloir `J-SRV` (devAI) · P0 · taille M · complexité 3/5 · difficulté 4/5

**Pourquoi ce lot.** Le jeu ouvre un canal permanent entre deux comptes, dont celui d'un mineur. Il mérite sa propre revue, comme le reste du produit en a eu une avant la mise en ligne.

**Ce qu'il fait.** Revue écrite : autorité du serveur et absence de fuite d'information cachée, authentification du canal temps réel, limitation de débit sur les messages et les actions, validation stricte des charges utiles, isolation des parties entre comptes, protection du mineur (aucun texte libre, blocage d'un joueur, invitation révocable), données conservées et durée, effacement en cas de suppression de compte (RGPD, `v5-rgpd`).

**Mission**

- Rejouer le test de non-fuite sur l'ensemble des scripts de cartes livrés, pas seulement sur le moteur.
- Éprouver le canal : message malformé, action hors tour, action sur une partie étrangère, rafale.
- Vérifier que les parties et journaux d'un compte supprimé disparaissent avec lui.
- Écrire la revue dans `docs/jeu/SECURITE-JEU.md` avec ses conclusions et les correctifs appliqués.

**Critères d'acceptation**

- Aucune fuite d'information cachée sur l'ensemble des scripts livrés.
- Toute action sur une partie étrangère est refusée et journalisée.
- La suppression d'un compte efface bien ses parties et ses journaux.
- La revue est écrite, datée et ses correctifs sont livrés.

**Livrables** : docs/jeu/SECURITE-JEU.md, correctifs appliqués.

**Risque à surveiller.** Faire la revue avant les derniers scripts de cartes : c'est dans un script mal écrit que la prochaine fuite d'information apparaîtra.

**Vient après** : [`j-autorite-vues`](#j-autorite-vues), [`j-e2e-deux-navigateurs`](#j-e2e-deux-navigateurs)  
**Débloque** : [`j-mise-en-ligne-jeu`](#j-mise-en-ligne-jeu)

<a id="j-mise-en-ligne-jeu"></a>
### `j-mise-en-ligne-jeu` — Mettre le jeu en ligne sur le serveur partagé

**Palier 18** · jalon **J5** · piste Q (Qualité & exploitation) · couloir `J-SRV` (devAI) · P0 · taille M · complexité 3/5 · difficulté 3/5

**Pourquoi ce lot.** Le jeu ne vaut que joué. Et il doit arriver sur une machine qui sert déjà deux autres sites, sans les mettre en péril.

**Ce qu'il fait.** Images construites sur chimera et tirées par le serveur (jamais construites sur place), service de temps réel derrière le proxy avec WebSocket, migrations appliquées, plafond de parties simultanées configuré, sauvegarde des parties, surveillance branchée, procédure de retour arrière.

**Mission**

- Construire sur chimera, publier les images, faire tirer le serveur (`pull` + `up -d`) — la règle du projet.
- Configurer le proxy pour le WebSocket et vérifier la reprise de connexion à travers lui.
- Appliquer les migrations et vérifier la purge et les sauvegardes des tables de parties.
- Écrire la procédure de retour arrière et l'essayer une fois pour de vrai.
- Ne conclure « en ligne » que sur une partie réellement jouée de bout en bout par deux comptes.

**Critères d'acceptation**

- Aucune construction d'image n'a lieu sur le serveur qui sert les visiteurs.
- Une partie complète est jouée en production par deux comptes, et la preuve est jointe.
- Le retour arrière a été exécuté une fois et documenté.
- Les autres sites du serveur ne sont pas dégradés pendant la mise en ligne (mesures avant/après).

**Livrables** : jeu en production, procédure de retour arrière éprouvée, preuve de partie jouée.

**Risque à surveiller.** Conclure « déployé » sur une ligne de journal : un build en échec laisse la plateforme debout sur les anciennes images, tout a l'air normal et rien n'est livré.

**Vient après** : [`j-securite-jeu`](#j-securite-jeu), [`j-charge-temps-reel`](#j-charge-temps-reel), [`j-fin-effets-compte`](#j-fin-effets-compte)  
**Débloque** : — (rien n'en dépend)

## Ce que ce backlog remplace dans le plan daté

Les lots V7 du plan daté étaient des blocs grossiers. Ce backlog les remplace par des lots exécutables. Les lots V7D (gestionnaire de decks) ne sont PAS repris ici : ils restent dans le plan daté et sont un préalable à la file d'attente.

| Lot du plan daté | Remplacé par |
|---|---|
| `v7-regles-moteur` | [`j-regles-reference`](#j-regles-reference), [`j-modele-etat`](#j-modele-etat), [`j-aleatoire-determinisme`](#j-aleatoire-determinisme), [`j-journal-actions`](#j-journal-actions), [`j-actions-legales`](#j-actions-legales), [`j-machine-tour`](#j-machine-tour), [`j-degats-resolution`](#j-degats-resolution), [`j-ko-recompenses`](#j-ko-recompenses), [`j-retraite-banc`](#j-retraite-banc), [`j-checkup`](#j-checkup) |
| `v7-regles-cartes` | [`j-effets-architecture`](#j-effets-architecture), [`j-effets-dsl`](#j-effets-dsl), [`j-effets-choix`](#j-effets-choix), [`j-etats-speciaux`](#j-etats-speciaux), [`j-cartes-pokemon`](#j-cartes-pokemon), [`j-cartes-energies`](#j-cartes-energies), [`j-cartes-objets`](#j-cartes-objets), [`j-cartes-supporters`](#j-cartes-supporters), [`j-cartes-stades`](#j-cartes-stades), [`j-cartes-outils`](#j-cartes-outils), [`j-cartes-talents`](#j-cartes-talents), [`j-cartes-attaques-effets`](#j-cartes-attaques-effets), [`j-cartes-regles-speciales`](#j-cartes-regles-speciales), [`j-effets-catalogue-compilation`](#j-effets-catalogue-compilation), [`j-effets-assistance-ia`](#j-effets-assistance-ia), [`j-effets-couverture-outil`](#j-effets-couverture-outil) |
| `v7-file-attente` | [`j-file-attente`](#j-file-attente), [`j-invitations`](#j-invitations), [`j-lancement-partie`](#j-lancement-partie), [`j-initialisation`](#j-initialisation) |
| `v7-temps-reel` | [`j-partie-service`](#j-partie-service), [`j-temps-reel`](#j-temps-reel), [`j-deconnexion-abandon`](#j-deconnexion-abandon), [`j-timer`](#j-timer) |
| `v7-anti-triche` | [`j-autorite-vues`](#j-autorite-vues), [`j-securite-jeu`](#j-securite-jeu) |
| `v7-plateau` | [`j-plateau-layout`](#j-plateau-layout), [`j-plateau-interactions`](#j-plateau-interactions), [`j-plateau-etat-visuel`](#j-plateau-etat-visuel), [`j-plateau-decisions`](#j-plateau-decisions) |
| `v7-partie-ui` | [`j-plateau-journal`](#j-plateau-journal), [`j-plateau-aide`](#j-plateau-aide), [`j-partie-fin-ui`](#j-partie-fin-ui), [`j-salon-partie`](#j-salon-partie) |
| `v7-images-jeu` | [`j-rendu-carte`](#j-rendu-carte), [`j-assets-pipeline`](#j-assets-pipeline) |
| `v7-effets-visuels` | [`j-anim-socle`](#j-anim-socle), [`j-anim-attaques-typees`](#j-anim-attaques-typees), [`j-anim-evolution-ko`](#j-anim-evolution-ko), [`j-anim-pokemon-apparition`](#j-anim-pokemon-apparition), [`j-arene-decors`](#j-arene-decors), [`j-son`](#j-son) |
| `v7-stats-joueur` | [`j-fin-effets-compte`](#j-fin-effets-compte), [`j-stats-joueur`](#j-stats-joueur), [`j-classement-prive`](#j-classement-prive), [`j-profil-jeu`](#j-profil-jeu) |
| `v7-e2e-jeu` | [`j-tests-regles`](#j-tests-regles), [`j-simulation-bots`](#j-simulation-bots), [`j-e2e-deux-navigateurs`](#j-e2e-deux-navigateurs), [`j-charge-temps-reel`](#j-charge-temps-reel), [`j-observabilite-jeu`](#j-observabilite-jeu) |

### Lots qui n'existaient nulle part dans le plan daté

Ce sont les manques que le découpage grossier cachait : sans eux, le jeu se livre sans être jouable en vrai, ou sans que personne ne s'en aperçoive.

| Lot | Titre |
|---|---|
| [`j-accessibilite-jeu`](#j-accessibilite-jeu) | Confort et accessibilité : jouable par un enfant, lisible par tous |
| [`j-echanges-emotes`](#j-echanges-emotes) | Emotes prédéfinies : se parler sans chat libre |
| [`j-mise-en-ligne-jeu`](#j-mise-en-ligne-jeu) | Mettre le jeu en ligne sur le serveur partagé |
| [`j-mode-solo`](#j-mode-solo) | Partie d'entraînement contre un bot |
| [`j-notifications-jeu`](#j-notifications-jeu) | Être prévenu : invitation reçue, c'est ton tour, partie reprise |
| [`j-replay`](#j-replay) | Replay d'une partie : la rejouer coup par coup, et la partager |

### Préalables qui restent dans le plan daté

| Lot | Ce qu'il apporte au jeu |
|---|---|
| `v7-decks-api` | Un deck jouable, légal, construit avec ses propres cartes (règle D10 sur les énergies). |
| `v7-decks-legalite` | Le rapport de légalité, auquel ce backlog ajoute une raison de plus : « carte non scriptée ». |
| `v4-collection` | La collection, source des cartes jouables. |
| `v2-catalogue-complet` | Attaques, faiblesses, résistances, coûts de retraite et textes d'effet de toutes les cartes. |
| `v1-auth` | Les comptes, et la liste des comptes invités (D11). |

