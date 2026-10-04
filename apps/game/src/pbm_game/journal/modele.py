"""Structures du **journal d'actions** — une partie *est* sa suite de coups.

Ce module est **pur** : aucune entrée/sortie, aucune dépendance à HTTP, à une base de
données ou à React, comme tout le moteur ``pbm_game`` (principe du jalon J1).

Principe porté ici — « **tout est rejouable** » : une partie n'est pas une photo de son
plateau, c'est un **état initial**, une **graine d'aléatoire** et un **journal d'actions
numéroté**. Rejouer le journal redonne exactement le même état (voir :mod:`.rejeu`). La
forme sérialisée est **versionnée** (:data:`JOURNAL_VERSION`) : relire un journal produit
sous une version inconnue est refusé, jamais replié en silence.

Ce qui est enregistré, par entrée (:class:`Entree`) : ce qui a été **DEMANDÉ**
(l':class:`Action`), ce que le moteur en a **FAIT** (les :class:`Evenement`), qui l'a
demandé, quand, et l'**empreinte** de l'état résultant — jamais une photo du plateau
(c'est le piège que ce lot évite : journaliser l'état, c'est perdre la divergence au coup
près et laisser le replay mentir).

Format documenté pour une réimplémentation indépendante : ``docs/jeu/JOURNAL.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..state.modele import EtatPartie

# Version du schéma du journal : toute évolution INCOMPATIBLE de la forme sérialisée
# (champ d'une entrée, forme d'une action, d'un événement, d'un instantané) l'incrémente.
# ``partie_depuis_json`` refuse une version inconnue (jamais de repli silencieux).
JOURNAL_VERSION = 1

#: Auteur d'une action non imputable à un joueur (mise en place, Checkup automatique).
#: Les actions d'un joueur portent son identifiant ; celles-ci portent cette constante.
AUTEUR_SYSTEME = "systeme"

# --- Types d'action reconnus (ce que porte ``Action.type``) ------------------
# Un type absent de ce catalogue est REFUSÉ à l'application (D9 : un effet non
# implémenté n'est jamais approximé). Les lots de résolution (attaques, Dresseurs,
# talents) en ajoutent, chacun scripté et testé.
ACTION_MELANGER_PIOCHE = "melanger_pioche"
ACTION_PIOCHER = "piocher"
ACTION_AVANCER_PHASE = "avancer_phase"
#: Abandon de la partie (R-14.3) : action légale d'un joueur, à tout moment, sans aucune
#: donnée de carte. Ajoutée par le lot ``j-actions-legales`` (elle est purement mécanique,
#: comme la pioche et l'avancée de phase).
ACTION_ABANDONNER = "abandonner"
#: Début de tour (R-5.1/R-5.2) — action **système**, pas un coup libre du joueur : pioche
#: obligatoire d'1 carte, et si la pioche est vide, **défaite** du joueur actif (R-14.2) ;
#: puis ouverture de la fenêtre « début de tour » et passage en phase principale. Ajoutée
#: par ``j-machine-tour``.
ACTION_DEBUT_TOUR = "debut_tour"
#: Déclarer une attaque (R-5.7/R-5.8) : **termine le tour**, même si l'attaque n'inflige
#: aucun dégât. Ce lot (``j-machine-tour``) ne mécanise QUE la fin de tour ; le coût, les
#: dégâts, la faiblesse et la résistance arrivent avec ``j-degats-resolution`` (D9 : on
#: n'approxime rien). Ce n'est donc pas encore un coup *listé* par le générateur.
ACTION_DECLARER_ATTAQUE = "declarer_attaque"
#: Battre en **retraite** (R-8.2/R-8.3/R-8.4) — coup volontaire du joueur actif : défausser
#: une énergie par symbole du coût de retraite (au CHOIX du joueur), puis échanger l'Actif
#: avec un Pokémon du banc. ``params`` : ``banc_index`` (le Pokémon du banc qui monte),
#: ``cout_retraite`` (nombre de symboles, fourni par le service depuis le catalogue) et
#: ``energies_defaussees`` (les ``instance_id`` des énergies que le joueur choisit de
#: défausser). Ajoutée par ``j-retraite-banc``. La *liste* du coup par le générateur attend
#: le catalogue (coût de retraite imprimé) : elle arrive avec ``j-cartes-pokemon`` (D9).
ACTION_RETRAITE = "retraite"
#: **Promotion** après un K.O. (R-8.7) — le joueur dont l'Actif est K.O. (donc absent)
#: choisit un Pokémon de son banc comme nouvel Actif. ``params`` : ``banc_index``. Si le banc
#: est **vide**, c'est une **défaite** (R-8.9/R-14.1), pas une exception. Ajoutée par
#: ``j-retraite-banc``. Action imputée au joueur qui promeut (pas forcément le joueur actif :
#: un K.O. au Checkup peut toucher les deux).
ACTION_PROMOUVOIR = "promouvoir"
#: **Échange forcé** provoqué par un effet (R-8.8) — change l'Actif d'un joueur **sans**
#: consommer la retraite du tour ni d'énergie, et **autorisé** même sous Sommeil ou Paralysie
#: (R-16.12, contrairement à la retraite volontaire). ``params`` : ``joueur`` (celui dont
#: l'Actif change) et ``banc_index``. Auteur : :data:`AUTEUR_SYSTEME` (l'effet), ou le joueur
#: qui joue l'effet. Ajoutée par ``j-retraite-banc`` ; l'effet qui la déclenche viendra plus
#: tard (D9).
ACTION_ECHANGE_FORCE = "echange_force"
#: **Pokémon Checkup** (R-12) — action **système** résolue en phase ``checkup``, entre la fin
#: d'un tour et le début du suivant. Elle résout, dans l'ordre fixé par le corpus : les états
#: spéciaux de chaque Actif (Empoisonné, Brûlé, Endormi, Paralysé — R-12.2), l'expiration des
#: effets « jusqu'à la fin de ce tour » (R-12.5), puis les K.O. qui en découlent (R-12.4) avec
#: récompenses (R-13) et promotion demandée. ``params`` : ``fiches`` — un mapping
#: ``instance_id de la carte au sommet → {"pv": int, "recompenses": int}`` que le **service**
#: extrait du catalogue (le moteur ne connaît ni PV ni marqueur de règle : D9, il ne devine
#: rien). Ajoutée par ``j-checkup``. Auteur : :data:`AUTEUR_SYSTEME`.
ACTION_CHECKUP = "checkup"
#: **Poser** un Pokémon de base en jeu (R-5.3) — coup de la phase principale du joueur actif :
#: une carte de base de la main entre au banc (``zone: "banc"``) ou directement comme Actif sur
#: une place vide (``zone: "actif"``, cas particulier). ``params`` : ``carte_main`` (instance_id
#: dans la main), ``definition`` (la fiche catalogue de la carte, D9), ``zone``. Ajoutée par
#: ``j-cartes-pokemon``. Le Pokémon posé est « nouveau en jeu » ce tour (R-7.3).
ACTION_POSER = "poser"
#: **Faire évoluer** un Pokémon en jeu (R-7) — coup de la phase principale du joueur actif : la
#: carte d'évolution de la main coiffe la pile du Pokémon. ``params`` : ``base`` (identité du
#: Pokémon), ``carte_main`` (instance_id de l'évolution), ``definition`` (sa fiche catalogue),
#: ``nom_base`` (nom du sommet actuel, pour la chaîne R-7.1). Conserve énergies/Outil/compteurs
#: (R-7.1), retire les états (R-7.2). Ajoutée par ``j-cartes-pokemon``.
ACTION_EVOLUER = "evoluer"
#: **Attacher une énergie** à un Pokémon en jeu (R-5.4) — coup de la phase principale du joueur
#: actif, **une seule fois par tour** (R-5.4). ``params`` : ``carte_main`` (instance_id de la carte
#: Énergie dans la main), ``cible`` (identité du Pokémon en jeu qui la reçoit) et ``definition``
#: (fiche catalogue de l'énergie — sa fourniture, D9 ; le journal la transporte, donc le rejeu
#: n'a pas besoin du catalogue). Ajoutée par ``j-coups-joueur``.
ACTION_ATTACHER_ENERGIE = "attacher_energie"
#: **Jouer une carte Objet** (R-5.5) — coup de la phase principale du joueur actif, jouable **autant
#: de fois qu'on veut** (contrairement au Supporter, R-5.5). La carte quitte la main pour la
#: défausse, puis son **script d'effet** (langage d'effets) se résout : recherche, pioche, défausse,
#: soin, déplacement d'énergie, changement d'Actif, **appât** (sortir du banc l'Actif adverse).
#: ``params`` : ``carte_main`` (instance_id dans la main), ``programme`` (le script DSL en JSON),
#: ``source`` (``{libelle, ref, instance_id}`` pour le journal), ``metadonnees`` (``ref →
#: {categorie, stade, type}`` du catalogue, pour les sélecteurs filtrés), ``nom``. Le **service**
#: fournit le script et les métadonnées (le moteur ne lit pas le catalogue : D9). Ajoutée par
#: ``j-cartes-objets``.
ACTION_JOUER_OBJET = "jouer_objet"
#: **Jouer une carte Supporter** (R-5.5) — coup de la phase principale du joueur actif, **un seul
#: par tour** (R-5.5) et **jamais** au premier tour du joueur qui commence (R-6.2). Comme un Objet,
#: la carte quitte la main pour la défausse puis son **script d'effet** se résout — mais ici des
#: effets de **pioche**, de **recherche** et de **perturbation de l'adversaire** (mélanger sa main
#: dans son deck et la faire repiocher, la faire défausser), et des effets **conditionnés** (« si
#: vous avez moins de récompenses »). ``params`` : identiques à ``jouer_objet`` (``carte_main``,
#: ``programme``, ``source``, ``metadonnees``, ``nom``). Refusé sous le verrou
#: ``pas_de_supporter``, qui **nomme la carte responsable**. Ajoutée par ``j-cartes-supporters``.
ACTION_JOUER_SUPPORTER = "jouer_supporter"
#: **Activer un talent** (R-5) — coup du joueur actif : un talent **activé** (« une fois
#: pendant votre tour, vous pouvez… », type *Bibarel*) se résout. ``params`` : ``pokemon``
#: (identité du porteur en jeu), ``nom``, ``programme`` (le script DSL), ``desactive_si_etat``
#: (états qui le désactivent, selon la carte), ``une_fois_par_tour``, ``source``,
#: ``metadonnees``. Suivi **par Pokémon** via ``Tour.talents_actives_ce_tour`` ; refusé sous
#: un verrou ``talents_sans_effet``, qui **nomme la carte responsable**. Ajoutée par
#: ``j-cartes-talents``.
ACTION_ACTIVER_TALENT = "activer_talent"
#: **Répondre à une demande de décision** (R-9.3 étape D, et tout effet qui fait choisir un joueur)
#: — coup d'un joueur quand une résolution est **suspendue** sur une demande. ``params`` : ``choix``
#: (la liste des identifiants d'option retenus ; vide = abandon d'un effet facultatif). L'``auteur``
#: doit être le **destinataire** de la demande — y compris l'adversaire, pendant le tour de l'autre.
#: Ajoutée par ``j-effets-choix`` ; sa transition reprend la résolution (``pbm_game.demandes``).
ACTION_REPONDRE_DEMANDE = "repondre_demande"
#: **Expiration du délai** d'une demande de décision — action **système** déclenchée par l'extérieur
#: (lot ``j-timer``) quand l'horloge d'une demande tombe à zéro. Applique la **réponse par défaut**
#: (premier choix valide, ou abandon de l'effet facultatif) et la journalise. Aucun ``params``.
ACTION_EXPIRER_DEMANDE = "expirer_demande"
#: **Mise en place initiale** (R-4.1/R-4.4/R-4.6) — action **système**, tout ce qui est
#: **déterministe à partir de la graine** : mélange des deux decks, pioche de sept cartes, et la
#: boucle de **mulligan** (main sans Pokémon de base révélée, remélangée, repiochée) jusqu'à ce que
#: les deux joueurs aient une main valide. Elle compte aussi les cartes bonus dues à l'adversaire
#: (R-4.5). ``params`` : ``definitions`` — un mapping ``ref → fiche catalogue`` que le **service**
#: fournit depuis le catalogue (le moteur ne devine aucun stade : D9, c'est ainsi qu'il sait si une
#: carte est un Pokémon **de base**). Aucun choix de joueur ici ; le placement vient après. Ajoutée
#: par ``j-initialisation``. Auteur : :data:`AUTEUR_SYSTEME`.
ACTION_MISE_EN_PLACE_INITIALE = "mise_en_place_initiale"
#: **Placer l'Actif et le banc face cachée** (R-4.2) — coup de **chaque** joueur à la mise en
#: place : il choisit, parmi sa main, le Pokémon de base posé comme Actif (obligatoire) et au plus
#: cinq Pokémon de base posés au banc. Le choix reste **face caché** (invisible de l'adversaire)
#: tant que les deux n'ont pas placé. Quand le **second** joueur place, la même transition résout
#: la **révélation simultanée** : Actif/banc deviennent publics, six récompenses sont posées face
#: cachée (R-4.3), les cartes bonus sont piochées (R-4.5), et la partie commence. ``params`` :
#: ``actif`` (instance_id), ``banc`` (liste d'instance_id), ``definitions`` (fiches catalogue des
#: cartes choisies, D9). Ajoutée par ``j-initialisation``.
ACTION_PLACER_MISE_EN_PLACE = "placer_mise_en_place"
#: **Fin de tour forcée** — action **système** déclenchée à l'expiration de l'horloge par
#: tour (lot ``j-timer``, DJ4). Termine le tour du joueur actif (entrée en Checkup), sans
#: déclarer d'attaque. Aucun ``params``. Peut aussi être un passage volontaire du joueur actif.
ACTION_FIN_TOUR = "fin_tour"
#: **Défaite au temps** — action **système** déclenchée quand le budget total d'un joueur est
#: épuisé (lot ``j-timer``, DJ4 « sinon défaite au temps »). ``params["joueur"]`` nomme le
#: perdant ; l'adversaire gagne, raison :data:`RAISON_TEMPS_ECOULE`.
ACTION_DEFAITE_TEMPS = "defaite_temps"
#: **Désertion** — action **système** (lot ``j-deconnexion-abandon``) déclenchée quand un joueur
#: déconnecté ne revient pas avant la fin de son délai de grâce (``pause_deconnexion_s``). C'est un
#: **forfait** : ``params["joueur"]`` nomme le déserteur, l'adversaire gagne, raison
#: :data:`RAISON_DESERTION`. Distincte de l'abandon volontaire (R-14.3) — mêmes effets de fin, mais
#: un motif propre, pour que l'historique dise *pourquoi* la partie s'est close.
ACTION_DESERTER = "deserter"
#: **Expiration pour inactivité** — action **système** (lot ``j-deconnexion-abandon``) du balayage
#: périodique des parties fantômes : une partie sans aucune activité au-delà du plafond configuré
#: est close d'office. Personne n'a joué, donc **aucun vainqueur** (``vainqueur=None``), raison
#: :data:`RAISON_INACTIVITE` — à distinguer d'une fin méritée. Aucun ``params``. C'est le filet qui
#: garantit qu'« aucune partie ne reste en cours plus longtemps que le plafond », chaque clôture
#: portant son motif dans le journal (jamais un nettoyage muet, risque nommé du lot).
ACTION_EXPIRER_INACTIVITE = "expirer_inactivite"

# --- Types d'événement (ce que PRODUIT le moteur) ----------------------------
EVT_PIOCHE_MELANGEE = "pioche_melangee"
EVT_CARTES_PIOCHEES = "cartes_piochees"
EVT_PHASE_AVANCEE = "phase_avancee"
EVT_TOUR_COMMENCE = "tour_commence"
#: Une attaque est déclarée (R-5.7). Produit par la transition ``declarer_attaque`` ; au
#: jalon J1 (ce lot) il ne porte aucun dégât — seul l'effet « termine le tour » est mécanisé.
EVT_ATTAQUE_DECLAREE = "attaque_declaree"
#: Le pile ou face de **confusion** a été résolu **avant** l'attaque (R-11.5). Produit par la
#: transition ``declarer_attaque`` quand l'Actif est Confus : porte le joueur, le ``pile_ou_face``
#: tiré, ``attaque_annulee`` (vrai sur **pile** : l'attaque n'a pas lieu et 3 compteurs sont
#: posés sur le Pokémon confus) et les ``degats`` d'auto-blessure (0 sur face, 30 sur pile).
#: Ajouté par ``j-etats-speciaux``.
EVT_CONFUSION = "confusion_resolue"
#: Des dégâts sont résolus et posés sur un Pokémon (R-10). Produit par la résolution d'attaque
#: (lot ``j-degats-resolution``) : il porte la cible, les dégâts, le nombre de compteurs et le
#: **détail de calcul** lisible (R-10.9) qu'affichent le journal de partie et l'aide en jeu.
EVT_DEGATS = "degats"
#: La partie se termine (R-14.6) : l'événement porte vainqueur, raison et, pour l'abandon,
#: le joueur qui a abandonné. Produit par la transition ``abandonner`` (lot j-actions-legales).
EVT_PARTIE_TERMINEE = "partie_terminee"
#: Une **retraite** a eu lieu (R-8.2). Produit par la transition ``retraite`` (lot
#: ``j-retraite-banc``) : porte le joueur, l'ancien et le nouvel Actif (identités stables), le
#: coût payé et les énergies défaussées.
EVT_RETRAITE = "retraite_effectuee"
#: Une **promotion** a eu lieu après un K.O. (R-8.7). Produit par la transition ``promouvoir``
#: (lot ``j-retraite-banc``) : porte le joueur et le nouvel Actif promu depuis le banc.
EVT_PROMOTION = "promotion_effectuee"
#: Un **échange forcé** a eu lieu (R-8.8). Produit par la transition ``echange_force`` (lot
#: ``j-retraite-banc``) : porte le joueur, l'ancien et le nouvel Actif. Ne marque **pas** la
#: retraite du tour et ne défausse **aucune** énergie.
EVT_ECHANGE_FORCE = "echange_force_effectue"
#: Une **carte Objet a été jouée** (R-5.5). Produit par la transition ``jouer_objet`` : porte le
#: joueur, la ``ref`` et le ``nom`` de l'Objet, l'``instance_id`` défaussé, et ``devient_actif`` —
#: la liste des ``[joueur, pokemon]`` qu'il a forcés à devenir Actifs (appât, *Switch*). C'est cette
#: liste que l'orchestrateur relit pour publier :data:`EJ_DEVIENT_ACTIF` sur le bus (les événements
#: propres du script, eux, suivent cet événement dans le journal).
EVT_OBJET_JOUE = "objet_joue"
#: Une **carte Supporter a été jouée** (R-5.5). Produit par la transition ``jouer_supporter`` : même
#: forme que :data:`EVT_OBJET_JOUE` (joueur, ``ref``, ``nom``, ``instance_id`` défaussé, et
#: ``devient_actif`` — p. ex. un Supporter d'appât). Le drapeau « un Supporter ce tour » (R-5.5) est
#: porté par ``Tour.supporter_joue`` (marqué par la transition), pas par cet événement.
EVT_SUPPORTER_JOUE = "supporter_joue"
#: Un **talent activé a été joué** (R-5). Produit par la transition ``activer_talent`` :
#: porte le joueur, l'identité du ``pokemon`` porteur, le ``nom`` du talent, sa ``ref`` et
#: ``devient_actif`` (Pokémon forcés à l'Actif par le script, pour le bus). Le « une fois par
#: tour » est porté par ``Tour.talents_actives_ce_tour`` (marqué par la transition), pas ici.
EVT_TALENT_ACTIVE = "talent_active"
#: Un **état spécial** a été résolu au Checkup (R-12.2) sur l'Actif d'un joueur. Produit par
#: ``j-checkup`` : porte le joueur, l'état (``empoisonne``/``brule``/``endormi``/``paralyse``),
#: la règle citée, les dégâts posés (poison/brûlure) et, le cas échéant, le pile ou face
#: (``endormi``/``brulure``) et si l'état est **guéri** à ce Checkup.
EVT_ETAT_CHECKUP = "etat_checkup"
#: Un **effet temporaire** « jusqu'à la fin de ce tour » a **expiré** au Checkup (R-12.5).
#: Produit par la fenêtre d'expiration : journalise chaque retrait, pour qu'un effet temporaire
#: ne devienne jamais éternel sans que rien ne le dise. Vide au jalon J1 (aucun effet temporaire).
EVT_EFFET_EXPIRE = "effet_expire"
#: Un Pokémon est **K.O.** (R-13.1) — ses compteurs de dégâts ont atteint ses PV. Produit par
#: ``j-checkup`` pour les K.O. survenus **hors attaque** (poison, brûlure…). Porte le joueur
#: dont le Pokémon est K.O., son identité, le nombre de **récompenses prises** par l'adversaire
#: (R-13.3) et l'adversaire qui les prend.
EVT_KO = "ko"
#: Une **promotion est requise** (R-8.7/R-12.4) : l'Actif d'un joueur est K.O. et son banc n'est
#: pas vide ; ce joueur doit choisir un Pokémon du banc (action ``promouvoir``) avant que le
#: tour suivant ne commence. Produit par ``j-checkup`` ; porte le joueur concerné.
EVT_PROMOTION_REQUISE = "promotion_requise"
#: Un Pokémon de base a été **posé** en jeu (R-5.3). Produit par la transition ``poser``
#: (lot ``j-cartes-pokemon``) : porte le joueur, l'identité du Pokémon posé, la zone et sa ref.
EVT_POKEMON_POSE = "pokemon_pose"
#: Un Pokémon a **évolué** (R-7.1). Produit par la transition ``evoluer`` (lot
#: ``j-cartes-pokemon``) : porte le joueur, l'identité (base) du Pokémon, la ref de la carte
#: d'évolution, son nom et les états spéciaux retirés par l'évolution (R-7.2).
EVT_EVOLUTION = "evolution"
#: Une **énergie a été attachée** à un Pokémon (R-5.4). Produit par la transition
#: ``attacher_energie`` (lot ``j-coups-joueur``) : porte le joueur, l'énergie (instance_id, ref),
#: l'identité du Pokémon qui la reçoit et ce qu'elle fournit.
EVT_ENERGIE_ATTACHEE = "energie_attachee"
#: La main d'ouverture d'un joueur est **révélée** (R-4.4) : elle n'a aucun Pokémon de base, donc
#: elle est montrée à l'adversaire avant d'être remélangée. Produit par ``mise_en_place_initiale``
#: (lot ``j-initialisation``) : porte le joueur et le **contenu révélé** (``instance_id`` + ``ref``
#: de chaque carte) — c'est le seul moment où une main est publique, et le journal en garde la
#: trace (l'exigence « le contenu révélé est journalisé »).
EVT_MAIN_REVELEE = "main_revelee"
#: Un **mulligan** a eu lieu (R-4.4/R-4.6). Produit par ``mise_en_place_initiale`` : porte le
#: joueur, son numéro de mulligan (1, 2, 3…), si le mulligan est **simultané** (les deux joueurs
#: sans base, R-4.6 — alors aucune carte bonus) et, le cas échéant, l'adversaire à qui une carte
#: bonus est due (R-4.5).
EVT_MULLIGAN = "mulligan"
#: La mise en place initiale (système) est **résolue** : les deux mains valides sont en place, le
#: placement peut commencer. Produit par ``mise_en_place_initiale`` : porte, par joueur, le nombre
#: de mulligans pris et le nombre de cartes bonus dues (R-4.5). Résumé public de la phase.
EVT_MISE_EN_PLACE_PRETE = "mise_en_place_prete"
#: Un joueur a **placé** son Actif et son banc face cachée (R-4.2). Produit par
#: ``placer_mise_en_place`` : porte **seulement** le joueur — **jamais** le contenu placé, qui
#: reste secret jusqu'à la révélation (non-fuite). Public : l'adversaire sait que l'autre est prêt.
EVT_PLACEMENT_CACHE = "placement_cache"
#: La mise en place est **révélée simultanément** (R-4.2/R-4.3) : les placements des deux joueurs
#: deviennent publics **en même temps**, six récompenses sont posées face cachée par joueur et les
#: cartes bonus sont piochées. Produit par ``placer_mise_en_place`` quand le second joueur place :
#: porte, par joueur, l'Actif et le banc révélés (identités), le nombre de récompenses et de cartes
#: bonus piochées. Un **seul** événement pour les deux : aucun joueur n'est révélé avant l'autre.
EVT_MISE_EN_PLACE_REVELEE = "mise_en_place_revelee"
#: Un tour se **termine** (R-5.8) sur expiration de l'horloge par tour ou passage volontaire.
#: Produit par la transition ``fin_tour`` (lot ``j-timer``) : porte le joueur et la phase quittée.
EVT_FIN_TOUR = "fin_tour"

#: Raison de fin pour un abandon (R-14.3), portée par ``EtatPartie.raison_fin`` et par
#: l'événement :data:`EVT_PARTIE_TERMINEE`.
RAISON_ABANDON = "abandon"
#: Raison de fin pour une pioche impossible en début de tour (R-14.2) : le joueur qui ne
#: peut pas piocher perd. Ce n'est **pas** une exception mais une condition de défaite.
RAISON_PIOCHE_IMPOSSIBLE = "pioche_impossible"
#: Raison de fin quand un joueur n'a **plus de Pokémon à promouvoir** après un K.O. (R-8.9,
#: R-14.1 cas 2) : son banc est vide au moment où une promotion est requise. Comme la pioche
#: impossible, c'est une **condition de défaite** vérifiée au bon moment, jamais une exception.
#: Posée par ``j-retraite-banc`` ; réutilisée par ``j-ko-recompenses`` (conditions de victoire).
RAISON_PLUS_DE_POKEMON = "plus_de_pokemon"
#: Raison de fin de la **première** façon de gagner (R-14.1 cas 1) : un joueur vient de prendre
#: sa **dernière** carte récompense (sa réserve passe à zéro à la suite d'un K.O.). Posée par
#: ``j-ko-recompenses``. Ce n'est pas un K.O. de l'adversaire : c'est la victoire par les
#: récompenses, distincte de :data:`RAISON_PLUS_DE_POKEMON`.
RAISON_DERNIERE_RECOMPENSE = "derniere_recompense"
#: Raison de fin pour une **défaite au temps** (R-14.6) : le budget total d'un joueur est
#: épuisé (DJ4). Posée par ``j-timer`` via la transition système ``defaite_temps``.
RAISON_TEMPS_ECOULE = "temps_ecoule"
#: Raison de fin pour une **désertion** (R-14.6) : un joueur déconnecté n'est pas revenu avant la
#: fin du délai de grâce → forfait. Posée par ``j-deconnexion-abandon`` via la transition système
#: ``deserter``. L'adversaire gagne, comme pour l'abandon, mais le motif distingue les deux.
RAISON_DESERTION = "desertion"
#: Raison de clôture pour **inactivité** : une partie fantôme (plus personne ne joue) close d'office
#: par le balayage périodique. Il n'y a **pas** de vainqueur — ce n'est pas une fin méritée mais un
#: ménage. Posée par ``j-deconnexion-abandon`` via la transition système ``expirer_inactivite``.
RAISON_INACTIVITE = "inactivite"


@dataclass(frozen=True)
class Action:
    """Ce qu'un acteur **demande** au moteur — autosuffisant et sérialisable.

    * ``type`` — un type reconnu (voir les constantes ``ACTION_*``) ; un type inconnu est
      refusé à l'application, jamais approximé (D9) ;
    * ``auteur`` — l'identifiant du joueur qui demande, ou :data:`AUTEUR_SYSTEME` ;
    * ``params`` — les paramètres de l'action, en valeurs **JSON natives** uniquement
      (``str``/``int``/``bool``/``list``/``dict``/``None``), pour que l'entrée se
      sérialise et se rejoue sans surprise.
    """

    type: str
    auteur: str
    params: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Evenement:
    """Ce que le moteur **a fait** en réponse à une action — fait observable et journalisé.

    ``type`` est un des ``EVT_*`` ; ``donnees`` porte les détails (valeurs JSON natives).
    Les événements sont la trace de ce qui a changé : rejouer l'action les reproduit à
    l'identique, ce que :func:`.rejeu.rejouer` contrôle.
    """

    type: str
    donnees: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Entree:
    """Une entrée du journal — **numérotée**, append-only, autosuffisante.

    * ``numero`` — rang dans le journal (0-based), la suite 0, 1, 2… sans trou ;
    * ``auteur`` — qui a demandé l'action (recopié de ``action.auteur`` pour la lecture) ;
    * ``action`` — ce qui a été demandé ;
    * ``evenements`` — ce que le moteur en a fait, dans l'ordre ;
    * ``horodatage`` — quand, en chaîne ISO fournie par l'appelant. Le moteur est **pur**
      et n'appelle aucune horloge : l'horodatage est une **donnée d'entrée**, pas une
      sortie — le rejeu le relit, il ne le recalcule jamais ;
    * ``empreinte`` — l'empreinte de l'état **après** ce coup (voir :func:`.empreinte`).
      Une divergence se détecte ainsi **au coup près**, pas à la fin de la partie.
    """

    numero: int
    auteur: str
    action: Action
    evenements: tuple[Evenement, ...]
    horodatage: str
    empreinte: str


@dataclass(frozen=True)
class Partie:
    """Une partie **persistée** : état initial + graine + journal. La source de vérité.

    L'état courant n'est qu'un **cache** reconstructible : il se recalcule en rejouant le
    journal depuis ``etat_initial`` sous ``graine`` (:func:`.rejeu.rejouer`). C'est cette
    forme-là qu'on stocke, pas une photo du plateau.

    * ``etat_initial`` — l'état au coup 0, avant toute action ;
    * ``graine`` — la graine d'aléatoire **en hexadécimal** (le moteur est pur : il ne la
      fabrique pas, l'appelant la tire et la lui passe) ;
    * ``entrees`` — le journal, dans l'ordre ;
    * ``journal_version`` — version du schéma du journal.
    """

    etat_initial: EtatPartie
    graine: str
    entrees: tuple[Entree, ...] = ()
    journal_version: int = JOURNAL_VERSION


@dataclass(frozen=True)
class Instantane:
    """Un **instantané** de compaction : l'état à un point du journal, pour ne pas tout rejouer.

    Reprendre une partie de 400 coups ne doit pas coûter 400 applications : on garde un
    instantané périodique + la **queue** des entrées postérieures, et on ne rejoue que la
    queue (:func:`.rejeu.reprendre`). L'instantané est un **cache**, jamais la source de
    vérité (qui reste le journal).

    * ``numero_entrees`` — combien d'entrées du journal ont été appliquées pour arriver là
      (donc l'état après ``entrees[:numero_entrees]``) ;
    * ``etat`` — l'état à ce point ;
    * ``rng_etat`` — l'état sérialisé du :class:`~pbm_game.rng.Rng` à ce point (graine,
      compteurs, journal des tirages), pour reprendre les tirages sans décalage ;
    * ``empreinte`` — l'empreinte de ``etat`` (contrôle de cohérence de l'instantané) ;
    * ``journal_version`` — version du schéma.
    """

    numero_entrees: int
    etat: EtatPartie
    rng_etat: dict
    empreinte: str
    journal_version: int = JOURNAL_VERSION
