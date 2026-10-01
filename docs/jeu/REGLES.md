# REGLES.md — Corpus de règles de référence du jeu

> **La version des règles qui fait foi.** Ce document est la vérité contre laquelle le moteur
> (`pbm_game`) est jugé. Il est écrit AVANT la première ligne de moteur (lot `j-regles-reference`).
> Chaque affirmation porte un identifiant `R-x.y` **citable par un test** : tout test de règle du
> moteur nomme le `R-x.y` qu'il vérifie, et toute action refusée par le moteur cite le `R-x.y`
> qui la motive.
>
> **Un seul comportement est écrit par mécanique.** Aucun point n'est laissé en « selon
> l'époque » : les variantes historiques sont listées en § R-17, mais le comportement retenu y
> est toujours tranché. Le risque de ce lot était de recopier une encyclopédie amateur qui
> mélange les ères — on s'en garde par une source unique, officielle et datée.

## Source et format (R-1)

- **R-1.1** — Source unique qui fait foi : le livret officiel **« Pokémon Trading Card Game
  Rules », série Écarlate & Violet (Scarlet & Violet)**, ©2023 Pokémon / ©1995–2023 Nintendo /
  Creatures Inc. / GAME FREAK inc. PDF officiel :
  `https://www.pokemon.com/static-assets/content-assets/cms2/pdf/trading-card-game/rulebook/par_rulebook_en.pdf`.
  Langue de référence : **anglais**. Consulté le **01/10/2026**. Les points non couverts par ce
  livret débutant (limite d'un Outil par Pokémon, décomptes de récompenses des cartes à Rule Box)
  sont pris dans le même corpus actuel (appendices du même livret et usage standard en vigueur),
  jamais dans une ère antérieure.
- **R-1.4** — **Série en vigueur au 01/10/2026 : Méga-Évolution** (depuis 2025). Sa règle propre —
  la Méga-Évolution Pokémon ex donne **3 récompenses** — est publiée par The Pokémon Company
  (`https://www.pokemon.com/us/pokemon-news/the-pokemon-tcg-mega-evolution-series-begins`,
  27/02/2025) et **imprimée dans le Rule Box** de chaque carte concernée. Plus généralement, les
  règles **propres à une catégorie de cartes** (récompenses, limite par deck, zone d'arrivée) se
  lisent dans le **Rule Box imprimé** de la carte, quelle que soit son ère : c'est le texte
  officiel de la carte, pas une variante d'époque (R-17 ne concerne que les règles générales).
- **R-1.2** — **Format retenu — décision DJ1, validée par JF le 01/10/2026 (2026-10-01T09:50+0200)** :
  format **« maison » sans rotation** — toute carte possédée est jouable, quelle que soit son
  époque — jouée avec le **corpus de règles ACTUEL**. Une carte ancienne se joue avec les règles
  d'aujourd'hui (faiblesse ×2, résistance −30, 6 récompenses, banc de 5, le joueur qui commence
  n'attaque pas à son premier tour).
- **R-1.3** — En cas de conflit entre une règle imprimée sur une carte ancienne et le présent
  corpus, **le corpus l'emporte**, sauf effet de carte explicitement scripté et testé (voir
  la règle R-15.12 / D9).

## Construction de deck (R-2)

- **R-2.1** — Un deck compte exactement **60 cartes**.
- **R-2.2** — Au plus **4 cartes de même nom**, sauf les cartes **Énergie de base**, illimitées.
- **R-2.3** — Au plus **1 carte ACE SPEC** (Dresseur) par deck.
- **R-2.4** — Au plus **1 Pokémon Radiant** par deck.
- **R-2.5** — Le **nom** fait foi pour la limite des 4 : « ex » fait partie du nom (Miraidon et
  Miraidon ex sont deux noms différents) ; « Pokémon ex » et « Pokémon-EX » ne sont pas le même
  nom non plus.
- **R-2.6** — **D9 (projet)** : un deck ne peut contenir que des cartes dont l'effet est **scripté
  et testé**. Une carte non scriptée est **refusée** à la construction du deck, en disant
  pourquoi. Le jeu préfère dire « je ne sais pas jouer cette carte » que de la jouer de travers.
- **R-2.7** — Au plus **1 carte Prisme Étoile (◇) de même nom** par deck (Rule Box imprimé).
- **R-2.8** — Au plus **1 Pokémon ★ (Étoile)** par deck, tous noms confondus (Rule Box imprimé).

## Zones et limites (R-3)

- **R-3.1** — Chaque joueur a ses propres zones : **pioche**, **main**, **1 Pokémon Actif**, un
  **banc**, une **défausse**, **6 récompenses**.
- **R-3.2** — Le **banc** contient **au plus 5** Pokémon.
- **R-3.3** — Il y a **exactement 1 Pokémon Actif** tant que le joueur a au moins un Pokémon en jeu.
- **R-3.4** — **6 cartes récompense**, posées **face cachée** à la mise en place.
- **R-3.5** — **Un seul Stade** en jeu à la fois (partagé par les deux joueurs). Un nouveau Stade
  défausse l'ancien et met fin à son effet ; on ne peut pas jouer un Stade de même nom qu'un
  Stade déjà en jeu.
- **R-3.6** — Un Pokémon en jeu porte : sa **pile d'évolutions**, ses **énergies attachées**, au
  plus **1 Outil**, ses **compteurs de dégâts**, ses **états spéciaux**, son **orientation**.
- **R-3.7** — Au plus **1 Outil Pokémon** attaché par Pokémon (règle de référence du corpus
  actuel ; le livret débutant permet de jouer autant d'Outils qu'on veut mais un Pokémon n'en
  porte qu'un).
- **R-3.8** — Chaque joueur a une **zone perdue** (publique, face visible). Une carte qui y est
  envoyée **n'en sort plus de la partie**. Le format maison accepte toute carte possédée (DJ1),
  y compris celles qui y envoient des cartes (Prisme Étoile, effets « zone perdue ») : la zone
  existe donc dès le modèle d'état, vide tant qu'aucune carte ne s'en sert.

## Mise en place et mulligan (R-4)

- **R-4.1** — Chaque joueur **mélange son deck de 60** et **pioche 7 cartes**.
- **R-4.2** — Chaque joueur **doit** poser **1 Pokémon de base** comme Actif ; il peut poser
  **jusqu'à 5** Pokémon de base au banc.
- **R-4.3** — On place les **6 récompenses** face cachée.
- **R-4.4** — **Mulligan** : un joueur **sans Pokémon de base** dans sa main d'ouverture révèle sa
  main et la remélange, puis repioche — il recommence jusqu'à obtenir une main avec un Pokémon de
  base.
- **R-4.5** — Pour **chaque mulligan supplémentaire** pris par un adversaire, l'autre joueur peut
  **piocher 1 carte de plus** (après que l'adversaire a fini sa mise en place).
- **R-4.6** — Si **les deux** joueurs n'ont aucun Pokémon de base, les deux **révèlent et
  recommencent**, sans carte bonus.
- **R-4.7** — On détermine **au hasard** (pile ou face) qui commence.

## Déroulé d'un tour (R-5)

- **R-5.1** — Un tour se déroule en trois temps : **(1)** piocher 1 carte ; **(2)** phase
  principale ; **(3)** attaque qui termine le tour.
- **R-5.2** — Au **début du tour**, piocher 1 carte est **obligatoire** (voir R-14.2 pour la
  pioche impossible).
- **R-5.3** — **Phase principale**, actions libres et dans n'importe quel ordre : poser des
  Pokémon de base au banc, faire évoluer, attacher 1 énergie, jouer des Dresseurs, battre en
  retraite, utiliser des talents.
- **R-5.4** — Attacher une énergie : **une seule fois par tour**.
- **R-5.5** — Jouer un **Supporter** : **un seul par tour**. **Objets** et **Outils** : autant
  qu'on veut. **Stade** : **un seul par tour**.
- **R-5.6** — Battre en **retraite** : **une seule fois par tour**.
- **R-5.7** — Déclarer une **attaque termine le tour** : une fois l'attaque déclarée, on ne peut
  plus rien faire.
- **R-5.8** — Déclarer une attaque **termine le tour même si elle n'inflige aucun dégât** : une
  attaque sans dégât reste une attaque.

## Règle du premier tour (R-6)

- **R-6.1** — Le joueur **qui commence NE peut PAS attaquer** à son premier tour (il saute
  l'étape d'attaque). *(DJ1 ; livret § « 3) Attack and End Your Turn ».)*
- **R-6.2** — Le joueur qui commence **NE peut PAS jouer de carte Supporter** à son premier tour.
  *(livret § « D) Play Trainer cards ».)*
- **R-6.3** — Le joueur qui commence **pioche normalement** à son premier tour : aucune règle du
  corpus actuel ne supprime la pioche initiale (voir R-17.3 pour l'ancienne variante).
- **R-6.4** — Le joueur qui commence **peut attacher une énergie** à son premier tour (aucune
  restriction d'énergie au premier tour).
- **R-6.5** — **Aucun** joueur ne peut **faire évoluer** un Pokémon à son **premier tour**.

## Évolution (R-7)

- **R-7.1** — On fait évoluer en posant la carte d'évolution sur le Pokémon ; il **conserve**
  énergies, cartes attachées et compteurs de dégâts.
- **R-7.2** — L'évolution **retire tous les états spéciaux** et les effets d'attaque en cours sur
  ce Pokémon.
- **R-7.3** — On ne peut pas faire évoluer un Pokémon **le tour où il est entré en jeu** (il est
  « nouveau en jeu »).
- **R-7.4** — On ne peut pas faire évoluer un Pokémon **deux fois le même tour**.

## Retraite, banc, promotion, échange forcé (R-8)

- **R-8.1** — Le banc contient au plus 5 Pokémon (rappel de R-3.2).
- **R-8.2** — **Retraite** : défausser de l'Actif **une énergie par symbole** du coût de retraite,
  **au choix du joueur** ; coût nul = retraite gratuite. Puis échanger l'Actif avec un Pokémon du
  banc, en conservant compteurs de dégâts et cartes attachées.
- **R-8.3** — **Une seule retraite par tour**.
- **R-8.4** — Un Pokémon **Endormi** ou **Paralysé** **ne peut pas** battre en retraite.
- **R-8.5** — Après une retraite, le **nouveau Pokémon Actif peut attaquer** le même tour.
- **R-8.6** — Le **passage au banc** (retraite, promotion ou échange forcé) **retire les états
  spéciaux et les effets d'attaque** ; il **conserve** énergies, Outil, compteurs de dégâts et
  pile d'évolutions.
- **R-8.7** — **Promotion** : après un K.O., le joueur dont le Pokémon est K.O. choisit un Pokémon
  de son banc comme nouvel Actif. La promotion est **obligatoire**.
- **R-8.8** — **Échange forcé** (provoqué par un effet) : **ne consomme ni** la retraite du tour
  **ni** d'énergie, et **peut** viser un Pokémon Endormi ou Paralysé (contrairement à la retraite
  volontaire, R-8.4).
- **R-8.9** — **Banc vide** au moment où une promotion est requise = **défaite** (voir R-14.1).

## Attaque : coût et déclaration (R-9)

- **R-9.1** — Déclarer une attaque = choisir une attaque de l'Actif dont le coût est satisfait,
  puis l'annoncer (l'attaque termine le tour, R-5.7).
- **R-9.2** — **Coût** : l'Actif doit porter **au moins** l'énergie requise ; le coût **incolore**
  accepte n'importe quel type d'énergie ; une énergie peut **fournir plusieurs unités** (énergies
  spéciales) — on compte les unités fournies.
- **R-9.3** — **Ordre officiel de résolution d'une attaque** *(livret § « Full details of
  attacking »)* : **A)** choix de l'attaque et vérification de l'énergie ; **B)** effets qui
  modifient ou annulent l'attaque ; **C)** vérification de la **Confusion** ; **D)** choix imposés
  par l'attaque (cibles…) ; **E)** actions imposées (pile ou face…) ; **F)** effets avant dégâts,
  pose des dégâts, puis tous les autres effets.

## Calcul des dégâts (R-10)

- **R-10.1** — **Ordre strict** *(livret § « follow these steps in this order »)* :
  1. dégâts de **base** imprimés ;
  2. **modificateurs côté attaquant** (effets d'attaques précédentes, Dresseurs, Énergies) —
     **s'arrêter si le résultat est 0** (ou si l'attaque ne fait pas de dégâts) ;
  3. **+ faiblesse** ;
  4. **− résistance** ;
  5. **modificateurs côté défenseur** (réductions de dégâts) ;
  6. poser **1 compteur par 10 dégâts** ; si le total est ≤ 0, **aucun compteur**.
- **R-10.2** — **Faiblesse** : par défaut **×2** (multiplie les dégâts à l'étape 3). *(DJ1.)*
- **R-10.3** — **Résistance** : par défaut **−30** (réduit à l'étape 4). *(DJ1.)*
- **R-10.4** — Les dégâts se posent en **COMPTEURS de dégâts** sur le Pokémon, **jamais** en
  soustrayant des PV : les soins et les effets « PV restants » en dépendent.
- **R-10.5** — Les dégâts infligés au **banc** n'appliquent **NI faiblesse NI résistance**.
- **R-10.6** — Un **compteur de dégâts posé directement par un effet** (« placez N compteurs »)
  n'est affecté par **aucune** faiblesse, résistance ni modificateur.
- **R-10.7** — **Plancher** : si le résultat est ≤ 0 (par ex. résistance supérieure aux dégâts),
  aucun compteur n'est posé.
- **R-10.8** — Pokémon **bi-type** : si la cible a une faiblesse à un type et une résistance à
  l'autre, appliquer **faiblesse puis résistance** (dans cet ordre).
- **R-10.9** — Le **détail de calcul** est produit et journalisé (« 60 base, ×2 faiblesse,
  −30 résistance = 90 ») pour le journal de partie et l'aide en jeu.

## États spéciaux et matrice de cumul (R-11)

- **R-11.1** — Les cinq états : **Endormi** (Asleep), **Brûlé** (Burned), **Confus** (Confused),
  **Paralysé** (Paralyzed), **Empoisonné** (Poisoned).
- **R-11.2** — Un état spécial ne frappe que le Pokémon **Actif**.
- **R-11.3** — **Endormi** : ne peut ni attaquer ni battre en retraite ; au Checkup, **pile ou
  face** — face = guéri, pile = reste endormi. Oriente la carte (sens anti-horaire).
- **R-11.4** — **Brûlé** : marqueur ; au Checkup, **2 compteurs de dégâts** puis **pile ou face**
  — face = guéri (retirer le marqueur). Un **seul** marqueur de brûlure (un nouveau remplace
  l'ancien).
- **R-11.5** — **Confus** : **avant d'attaquer**, pile ou face — face = l'attaque a lieu
  normalement, pile = l'attaque **n'a pas lieu** et on pose **3 compteurs de dégâts** sur le
  Pokémon confus. Oriente la carte (haut vers soi).
- **R-11.6** — **Paralysé** : ne peut ni attaquer ni battre en retraite ; guérit **au Checkup
  après le tour suivant de son propriétaire**. Oriente la carte (sens horaire).
- **R-11.7** — **Empoisonné** : marqueur ; au Checkup, **1 compteur de dégâts**. Un **seul**
  marqueur de poison (un nouveau remplace l'ancien).
- **R-11.8** — **Matrice de cumul** *(livret § « Removing Special Conditions »)* : Endormi, Confus
  et Paralysé **orientent tous la carte** → **un seul des trois à la fois**, le **dernier posé
  remplace** le précédent. Empoisonné et Brûlé utilisent des **marqueurs** → **cumulables entre
  eux ET avec** l'état d'orientation en cours. L'exemple officiel : un Pokémon peut être **Brûlé +
  Paralysé + Empoisonné** en même temps.

  | posé \ en place | — | Endormi | Confus | Paralysé | Brûlé | Empoisonné |
  |---|---|---|---|---|---|---|
  | **Endormi** | Endormi | Endormi | Endormi (remplace) | Endormi (remplace) | Endormi + Brûlé | Endormi + Empoisonné |
  | **Confus** | Confus | Confus (remplace) | Confus | Confus (remplace) | Confus + Brûlé | Confus + Empoisonné |
  | **Paralysé** | Paralysé | Paralysé (remplace) | Paralysé (remplace) | Paralysé | Paralysé + Brûlé | Paralysé + Empoisonné |
  | **Brûlé** | Brûlé | Endormi + Brûlé | Confus + Brûlé | Paralysé + Brûlé | Brûlé (remplace marqueur) | Brûlé + Empoisonné |
  | **Empoisonné** | Empoisonné | Endormi + Empois. | Confus + Empois. | Paralysé + Empois. | Brûlé + Empois. | Empoisonné (remplace marqueur) |

- **R-11.9** — **Guérison de TOUS les états** : **passage au banc** ou **évolution**.
- **R-11.10** — Seuls **Endormi** et **Paralysé** empêchent la **retraite** (rappel de R-8.4).

## Phase entre les deux tours — Pokémon Checkup (R-12)

- **R-12.1** — Entre la **fin d'un tour** et le **début du suivant** se tient le **Pokémon
  Checkup**.
- **R-12.2** — **Ordre de résolution des états** : **1) Empoisonné, 2) Brûlé, 3) Endormi,
  4) Paralysé**. *(livret § « 4) Pokémon Checkup ».)*
- **R-12.3** — Les effets « au Checkup / entre les tours » (talents, Dresseurs) se résolvent dans
  la **même phase** ; on peut faire **d'abord les états puis les autres effets**, ou l'inverse,
  mais **jamais en les entrelaçant**.
- **R-12.4** — Après que **les deux joueurs** ont fait leurs vérifications, tout Pokémon **sans PV
  restant est K.O.** : promotion (R-8.7) + récompense (R-13), puis le tour suivant commence. Le
  code de victoire ne vit donc **pas uniquement** dans la résolution d'attaque.
- **R-12.5** — Les effets temporaires « **jusqu'à la fin de ce tour** » **expirent ici** ; chaque
  expiration est **journalisée** (sinon un effet temporaire devient éternel sans que rien ne le
  dise).

## Mises K.O. et récompenses (R-13)

- **R-13.1** — Un Pokémon est **K.O.** quand ses **compteurs de dégâts ≥ ses PV**.
- **R-13.2** — Un K.O. **défausse** le Pokémon avec **toute sa pile d'évolutions, ses énergies et
  son Outil**.
- **R-13.3** — **Récompenses prises par l'adversaire** selon le **marqueur de règle** de la carte
  K.O. :
  - **1** : Pokémon ordinaire, Radiant, Pokémon BREAK, Prisme Étoile, Pokémon LV.X, Pokémon ★.
  - **2** : Pokémon ex (y compris Tera ex et Pokémon-ex de l'ère EX), Pokémon-EX (y compris
    M Pokémon-EX), Pokémon-GX, Pokémon V, Pokémon VSTAR, LÉGENDE.
  - **3** : **Méga-Évolution Pokémon ex**, Pokémon VMAX, TAG TEAM, V-UNION.
- **R-13.4** — Le nombre de récompenses se **lit sur la carte (catalogue)**, **jamais** depuis une
  liste en dur. Un **marqueur de règle inconnu** fait **échouer bruyamment** (interdiction du
  repli silencieux), **jamais** « par défaut 1 ».
- **R-13.7** — **Le suffixe du nom ne suffit pas** à classer une carte : une Méga-Évolution
  Pokémon ex finit par « ex » comme un Pokémon ex ordinaire, mais donne 3 récompenses (R-15.13),
  et une TAG TEAM finit par « GX » mais en donne 3 (R-15.7). Le marqueur se lit dans les
  **sous-types / le Rule Box du catalogue** ; un nom seul ne tranche jamais.
- **R-13.5** — **K.O. simultané** : les deux Pokémon sont K.O. en même temps ; **chaque joueur
  prend ses récompenses** ; si la partie n'est pas finie, chacun promeut (R-8.7). Voir R-14.4 pour
  l'égalité éventuelle.
- **R-13.6** — Après un K.O., la **promotion est obligatoire** (R-8.7) ; **banc vide = défaite**
  (R-14.1).

## Conditions de victoire, abandon, égalité (R-14)

- **R-14.1** — **Trois façons de gagner** *(livret § « How to Win the Game »)* : **(1)** prendre
  sa **dernière carte récompense** ; **(2)** l'adversaire **n'a plus de Pokémon à promouvoir**
  après un K.O. ; **(3)** l'adversaire **ne peut pas piocher** au début de son tour.
- **R-14.2** — **Pioche impossible** : si un joueur ne peut pas piocher au début de son tour (deck
  vide), il **perd** — ce n'est **pas une exception** mais une **condition de défaite** vérifiée
  au bon moment.
- **R-14.3** — **Abandon** : un joueur peut **abandonner à tout moment** ; il **perd
  immédiatement**. (Règle maison : l'abandon n'est pas dans le livret débutant mais est une
  **action légale** du service.)
- **R-14.4** — **Égalité** : si les deux joueurs remplissent une condition de victoire **exactement
  en même temps** (K.O. simultané qui fait prendre à chacun sa dernière récompense, double défaite
  au banc vide, etc.), la partie est **NULLE**. En jeu officiel cela déclenche une **« Sudden
  Death »** (nouvelle manche à 1 récompense) ; **pour le moteur J1, l'état final est `égalité`**
  et la Sudden Death est une décision du **service** (hors moteur), **explicitement différée**.
- **R-14.5** — Si un joueur gagne par **deux voies** et l'autre par **une seule** au même instant,
  **le premier est vainqueur** (pas d'égalité). *(livret § « Sudden Death ».)*
- **R-14.6** — Une partie terminée est **figée** : elle **refuse toute action supplémentaire** ;
  l'état final porte **vainqueur + raison**, et le **journal est clos**.

## Cartes particulières (R-15)

- **R-15.1** — **Pokémon ex** : **2 récompenses**. « ex » fait partie du nom (R-2.5).
- **R-15.2** — **Tera Pokémon ex** : comme un Pokémon ex (**2 récompenses**) **+ protégé des
  dégâts d'attaque tant qu'il est au banc**.
- **R-15.3** — **Pokémon-GX** : **2 récompenses** ; **une seule attaque GX par partie et par
  joueur** (tous Pokémon-GX confondus).
- **R-15.4** — **Pokémon V** : **2 récompenses**.
- **R-15.5** — **Pokémon VMAX** : **3 récompenses** ; stade d'évolution **VMAX** ; reste
  « Pokémon V » pour les effets.
- **R-15.6** — **Pokémon VSTAR** : **2 récompenses** ; **un seul VSTAR Power (attaque OU talent)
  par partie et par joueur**.
- **R-15.7** — **TAG TEAM** (Pokémon-GX de base) : **3 récompenses**.
- **R-15.8** — **V-UNION** : **3 récompenses**.
- **R-15.9** — **Radiant** : **1 récompense** ; Pokémon **de base** ; carte **à Rule Box** ;
  **1 seul par deck** (R-2.4).
- **R-15.10** — **ACE SPEC** : carte **Dresseur** ; **1 seule par deck** (R-2.3) ; **ne donne pas
  de récompense** (c'est un Dresseur, pas un Pokémon).
- **R-15.11** — **Ancien / Futur** (à partir de Paradox Rift) : label sans effet de règle propre
  au-delà de ce qu'imprime la carte.
- **R-15.12** — **D9 (projet)** : un **effet non implémenté n'est jamais approximé**. Une carte
  dont l'effet — y compris VSTAR Power, attaque GX, protection Tera — n'est pas **scripté et
  testé** est **refusée au deck** (R-2.6).
- **R-15.13** — **Méga-Évolution Pokémon ex** (série Méga-Évolution, 2025–) : **3 récompenses**.
  Elle se joue selon le **stade imprimé** ; la Méga-Évolution de cette série **ne termine pas le
  tour** (aucune règle de fin de tour n'est imprimée).
- **R-15.14** — **Pokémon-EX** (ères Noir & Blanc et XY, majuscules, avec tiret) : **2 récompenses**.
- **R-15.15** — **M Pokémon-EX** (Méga-Évolution de l'ère XY) : **2 récompenses** (c'est un
  Pokémon-EX). Son Rule Box imprimé dit que **le tour se termine** quand un de vos Pokémon
  devient une Méga-Évolution : c'est le texte de la carte, il **s'applique** (R-1.4) — et, comme
  tout effet, la carte n'entre au deck que si ce texte est scripté et testé (R-15.12).
- **R-15.16** — **Pokémon-ex** de l'ère EX (2003–2007, minuscules) : **2 récompenses** — même
  traitement que R-15.1.
- **R-15.17** — **Pokémon BREAK** : **1 récompense** ; se pose sur le Pokémon de même nom (sans
  « BREAK ») et **conserve** ses attaques, talents, faiblesse, résistance et coût de retraite,
  comme l'imprime son Rule Box.
- **R-15.18** — **Prisme Étoile (◇)** : **1 récompense** ; **1 par nom** dans le deck (R-2.7) ;
  une carte ◇ qui devrait aller dans la **défausse** va dans la **zone perdue** (R-3.8).
- **R-15.19** — **LÉGENDE** (ère HeartGold SoulSilver) : les **deux moitiés** se mettent en jeu
  **ensemble**, comme l'imprime le Rule Box ; **2 récompenses**.
- **R-15.20** — **Pokémon LV.X** : **1 récompense** ; se pose sur le Pokémon Actif de même nom
  selon son Rule Box imprimé.
- **R-15.21** — **Pokémon ★ (Étoile)** : **1 récompense** ; **1 seul par deck** (R-2.8).
- **R-15.22** — Une carte à **Rule Box** absente de R-15 est **refusée au deck** tant qu'une règle
  ne l'y ajoute pas (R-13.4, R-15.12) : jamais de récompense ni de limite devinée.

## Cas limites (R-16)

- **R-16.1** — **Pioche vide en début de tour** → défaite du joueur qui doit piocher (R-14.2).
- **R-16.2** — **Banc vide après un K.O.** → défaite du joueur sans Pokémon à promouvoir
  (R-14.1 cas 2, R-8.9).
- **R-16.3** — **K.O. simultané** → chaque joueur prend ses récompenses ; si cela n'achève pas la
  partie, chacun promeut (R-13.5).
- **R-16.4** — **Dernier Pokémon mis K.O. par un effet HORS attaque** (poison/brûlure au Checkup)
  → le K.O. est traité au Checkup (R-12.4), l'adversaire prend ses récompenses, et si le banc est
  vide c'est une défaite.
- **R-16.5** — **Abandon** → défaite immédiate (R-14.3).
- **R-16.6** — **Égalité** → partie nulle (R-14.4).
- **R-16.7** — **Résistance supérieure aux dégâts** → plancher à 0, aucun compteur (R-10.7).
- **R-16.8** — **Faiblesse appliquée à une attaque de 0 dégât** → l'attaque s'arrête à l'étape 2
  (base 0), la faiblesse n'est **jamais** appliquée (R-10.1 étape 2).
- **R-16.9** — **Mulligan multiple** → l'adversaire pioche autant de cartes bonus que de mulligans
  supplémentaires (R-4.5).
- **R-16.10** — **Double K.O. qui ferait prendre à chacun sa dernière récompense** → **égalité**
  (R-14.4), jamais « le joueur actif gagne ».
- **R-16.11** — **Premier tour du joueur qui commence** : pas d'attaque (R-6.1), pas de Supporter
  (R-6.2), pas d'évolution (R-6.5) — **mais** pioche (R-6.3) et énergie (R-6.4) permises.
- **R-16.12** — **Échange forcé d'un Pokémon Endormi ou Paralysé** → **autorisé** (R-8.8),
  contrairement à la retraite volontaire (R-8.4).

## Points qui ont changé selon les époques — variantes et comportement retenu (R-17)

> Chaque ligne liste une variante historique **et** tranche le comportement retenu ici. Aucun
> point n'est laissé en suspens : le corpus actuel (R-1.1) s'applique partout.

- **R-17.1** — **Faiblesse** : ancien « +X » fixe (ex. +20 / +30 selon les ères HGSS/Noir & Blanc)
  → actuel **« ×2 »**. **Retenu : ×2** (R-10.2).
- **R-17.2** — **Résistance** : ancien **« −20 »** → actuel **« −30 »**. **Retenu : −30** (R-10.3).
- **R-17.3** — **Premier tour — pioche** : ancienne variante « le 1er joueur **ne pioche pas** » →
  actuel « il **pioche** ». **Retenu : il pioche** (R-6.3).
- **R-17.4** — **Premier tour — Supporter** : autorisé dans certaines ères → actuel **« interdit
  pour le 1er joueur à son 1er tour »**. **Retenu : interdit** (R-6.2).
- **R-17.5** — **Premier tour — attaque** : variable selon les ères → actuel « le 1er joueur
  **n'attaque pas** à son 1er tour ». **Retenu : pas d'attaque** (R-6.1).
- **R-17.6** — **États spéciaux — cumul** : anciennes variantes « un seul état à la fois » →
  actuel « **orientation exclusive, marqueurs cumulables** ». **Retenu : matrice R-11.8**.
- **R-17.7** — **Confusion — auto-dégâts** : ancien « 30 PV » → actuel « **3 compteurs de dégâts**
  (= 30) » — identique en valeur, posés en compteurs. **Retenu : 3 compteurs** (R-11.5).
- **R-17.8** — **Taille du banc** : historiquement **5** (stable). **Retenu : 5** (R-3.2).
- **R-17.9** — **Récompenses** : **6** (stable). **Retenu : 6** (R-3.4).
- **R-17.10** — **Méga-Évolution** : ère XY (M Pokémon-EX, 2 récompenses, **le tour se termine**)
  → série Méga-Évolution (2025, Méga-Évolution Pokémon ex, **3 récompenses**, le tour continue).
  **Retenu : chaque carte suit son propre Rule Box imprimé** (R-15.13, R-15.15) — ce n'est pas
  une règle générale qui aurait changé, ce sont deux catégories de cartes distinctes.

---

## Table de cas

La table de cas de test qui nomme, pour chaque cas, la règle `R-x.y` qu'il vérifie, vit dans
**`docs/jeu/cas-de-regles.yaml`** (lot `j-tests-regles` l'étoffera avec les entrées/attendus du
moteur). Le test `apps/game/tests/test_corpus_regles.py` garantit que **chaque cas cite une règle
qui existe dans ce document** et que les dix cas limites de la mission y sont couverts.
