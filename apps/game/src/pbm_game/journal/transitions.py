"""Application d'une action : ``appliquer(etat, action, rng) -> (etat, evenements)``.

Pur et **sans effet de bord** sur l'état : ``etat`` est figé (``frozen``), on renvoie
toujours un **nouvel** ``EtatPartie``. Le seul collaborateur mutable est le
:class:`~pbm_game.rng.Rng` — par conception : ses compteurs avancent et son journal de
tirages s'allonge, mais cette mutation est elle-même **rejouable** (même graine + mêmes
actions ⇒ mêmes tirages), donc elle ne casse pas la rejouabilité.

Ce lot (``j-journal-actions``) livre l'**ossature** du journal et un noyau de transitions
**entièrement mécaniques** — déplacer des cartes entre zones, avancer le tour — qui ne
demandent **aucune** donnée de carte (type, coût, effet) et sont donc pleinement
implémentables et testables ici. Les actions riches (attacher une énergie, poser un
Pokémon, faire évoluer, attaquer, jouer un Dresseur) arrivent avec les lots de résolution
qui disposent du catalogue : elles s'enregistrent dans le même :data:`REGISTRE`.

**D9 — un effet non implémenté n'est jamais approximé.** Un ``action.type`` absent du
registre est **refusé** (``ValueError``), jamais deviné. De même, une transition refuse
une demande mécaniquement impossible (piocher plus de cartes que la pioche n'en a) au lieu
de la replier en silence.

Règles de référence servies (``docs/jeu/REGLES.md``) :

* **R-4.1** — mélange du deck (``melanger_pioche``) ;
* **R-5.1 / R-5.2** — pioche de début de tour (``piocher``) ;
* **R-5.1 / R-12.1** — déroulé des phases et passage au tour suivant (``avancer_phase``).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

# Importé APRÈS les modules du paquet journal (modele, rng, state déjà chargés) : le paquet
# ``pbm_game.tour`` ne tire ici que ses sous-modules sans dépendance à ``pbm_game.actions``
# (fenêtres, drapeaux), ce qui évite tout cycle avec le générateur d'actions.
# La résolution des états avant l'attaque (``pbm_game.etats.attaque``) est importée **au moment
# de l'appel** dans ``_declarer_attaque`` : ce module importe ``journal.modele``, dont le paquet
# ``journal`` importe en retour ce fichier — un import au chargement formerait donc un cycle.
from ..rng import Rng, flux_melange_deck
from ..state.modele import (
    PHASE_ATTAQUE,
    PHASE_CHECKUP,
    PHASE_PIOCHE,
    PHASE_PRINCIPALE,
    EtatPartie,
    Joueur,
    Tour,
)
from ..tour.drapeaux import est_premier_tour_du_joueur_qui_commence
from ..tour.fenetres import FENETRE_DEBUT_TOUR, FENETRE_FIN_TOUR, declencher
from .empreinte import empreinte
from .modele import (
    ACTION_ABANDONNER,
    ACTION_AVANCER_PHASE,
    ACTION_DEBUT_TOUR,
    ACTION_DECLARER_ATTAQUE,
    ACTION_DEFAITE_TEMPS,
    ACTION_EXPIRER_DEMANDE,
    ACTION_MELANGER_PIOCHE,
    ACTION_PIOCHER,
    ACTION_REPONDRE_DEMANDE,
    AUTEUR_SYSTEME,
    EVT_ATTAQUE_DECLAREE,
    EVT_CARTES_PIOCHEES,
    EVT_PARTIE_TERMINEE,
    EVT_PHASE_AVANCEE,
    EVT_PIOCHE_MELANGEE,
    EVT_TOUR_COMMENCE,
    RAISON_ABANDON,
    RAISON_PIOCHE_IMPOSSIBLE,
    Action,
    Entree,
    Evenement,
    Partie,
)

# Type d'un gestionnaire de transition. Reçoit l'état, l'action et le Rng ; renvoie le
# nouvel état et la liste (ordonnée) des événements produits.
Transition = Callable[[EtatPartie, Action, Rng], tuple[EtatPartie, list[Evenement]]]

# Ordre canonique des phases d'un tour (R-5.1), ``checkup`` étant la phase entre les deux
# tours (R-12.1). ``avancer_phase`` suit cet ordre, puis repart au tour suivant.
_ORDRE_PHASES: tuple[str, ...] = (PHASE_PIOCHE, PHASE_PRINCIPALE, PHASE_ATTAQUE, PHASE_CHECKUP)

# Les seules actions permises quand une demande de décision est en cours (lot ``j-effets-choix``) :
# répondre, laisser expirer le délai, ou abandonner la partie (R-14.3, toujours permis).
_ACTIONS_PENDANT_DEMANDE: frozenset[str] = frozenset(
    {ACTION_REPONDRE_DEMANDE, ACTION_EXPIRER_DEMANDE, ACTION_ABANDONNER, ACTION_DEFAITE_TEMPS}
)


# --- Helpers immuables -------------------------------------------------------


def _index_joueur(etat: EtatPartie, jid: str) -> int:
    for i, joueur in enumerate(etat.joueurs):
        if joueur.id == jid:
            return i
    raise ValueError(f"Joueur « {jid} » absent de la partie.")


def _remplacer_joueur(etat: EtatPartie, index: int, joueur: Joueur) -> EtatPartie:
    joueurs = list(etat.joueurs)
    joueurs[index] = joueur
    return replace(etat, joueurs=(joueurs[0], joueurs[1]))


def _joueur_cible(etat: EtatPartie, action: Action) -> str:
    """Le joueur que vise l'action : ``params["joueur"]`` s'il est donné, sinon l'auteur.

    Une action **système** (mise en place) doit nommer son joueur dans ``params`` ; une
    action de joueur vise l'auteur par défaut. On refuse une cible absente plutôt que de
    choisir un joueur au hasard (pas de repli silencieux).
    """
    cible = action.params.get("joueur", action.auteur)
    if not isinstance(cible, str) or not cible or cible == AUTEUR_SYSTEME:
        raise ValueError(
            "Action sans joueur cible : préciser « params.joueur » (auteur système) "
            "ou agir sous un identifiant de joueur."
        )
    return cible


def _autre_joueur(etat: EtatPartie, jid: str) -> str:
    a, b = etat.joueurs[0].id, etat.joueurs[1].id
    if jid == a:
        return b
    if jid == b:
        return a
    raise ValueError(f"Joueur « {jid} » absent de la partie.")


# --- Transitions mécaniques --------------------------------------------------


def _melanger_pioche(
    etat: EtatPartie, action: Action, rng: Rng
) -> tuple[EtatPartie, list[Evenement]]:
    """Mélange la pioche du joueur cible (R-4.1) via le flux d'aléatoire qui lui est dédié."""
    jid = _joueur_cible(etat, action)
    index = _index_joueur(etat, jid)
    joueur = etat.joueurs[index]
    flux = flux_melange_deck(jid)
    melangee = rng.melanger(flux, f"R-4.1 mélange pioche {jid}", joueur.pioche)
    etat2 = _remplacer_joueur(etat, index, replace(joueur, pioche=tuple(melangee)))
    evt = Evenement(EVT_PIOCHE_MELANGEE, {"joueur": jid, "taille": len(melangee)})
    return etat2, [evt]


def _piocher(etat: EtatPartie, action: Action, rng: Rng) -> tuple[EtatPartie, list[Evenement]]:
    """Déplace les ``nombre`` cartes du sommet de la pioche vers la main (R-5.2, R-4.1).

    Convention : le **sommet** du deck est le début de la pioche (``pioche[0]``). Refuse
    une pioche insuffisante : la conséquence d'une pioche impossible (défaite, R-14.2) est
    une règle à part, résolue dans un lot ultérieur — on ne l'approxime pas ici.
    """
    jid = _joueur_cible(etat, action)
    index = _index_joueur(etat, jid)
    joueur = etat.joueurs[index]
    nombre = action.params.get("nombre", 1)
    if not isinstance(nombre, int) or isinstance(nombre, bool) or nombre < 1:
        raise ValueError(f"« nombre » de cartes à piocher invalide : {nombre!r} (entier ≥ 1).")
    if len(joueur.pioche) < nombre:
        raise ValueError(
            f"Pioche insuffisante pour « {jid} » : {len(joueur.pioche)} carte(s), "
            f"{nombre} demandée(s) (R-5.2 ; conséquence de pioche impossible R-14.2, "
            "hors de ce lot)."
        )
    piochees = joueur.pioche[:nombre]
    reste = joueur.pioche[nombre:]
    etat2 = _remplacer_joueur(
        etat, index, replace(joueur, pioche=reste, main=joueur.main + piochees)
    )
    evt = Evenement(
        EVT_CARTES_PIOCHEES,
        {"joueur": jid, "nombre": nombre, "instance_ids": [c.instance_id for c in piochees]},
    )
    return etat2, [evt]


def _entrer_checkup(etat: EtatPartie, rng: Rng, *, de: str) -> tuple[EtatPartie, list[Evenement]]:
    """Entre en phase Checkup (fin du tour) et ouvre la fenêtre « fin de tour » (R-12.1).

    Renvoie ``(etat, evenements)`` avec l'événement de phase, **puis** les événements produits
    par la fenêtre de fin de tour (vide au jalon J1 : elle ne produit rien, voir
    :mod:`pbm_game.tour.fenetres`). Partagé par ``avancer_phase`` (attaque → checkup) et
    ``declarer_attaque`` : une seule porte vers le Checkup, donc une seule fenêtre de fin de tour.
    """
    tour2 = replace(etat.tour, phase=PHASE_CHECKUP)
    etat2 = replace(etat, tour=tour2)
    evenements = [
        Evenement(
            EVT_PHASE_AVANCEE,
            {
                "de": de,
                "vers": PHASE_CHECKUP,
                "numero": tour2.numero,
                "joueur_actif": tour2.joueur_actif,
            },
        )
    ]
    etat2, evts_fenetre = declencher(etat2, FENETRE_FIN_TOUR, rng)
    evenements.extend(evts_fenetre)
    return etat2, evenements


def _avancer_phase(
    etat: EtatPartie, action: Action, rng: Rng
) -> tuple[EtatPartie, list[Evenement]]:
    """Avance d'une phase (R-5.1) ; depuis ``checkup`` (R-12.1), ouvre le tour suivant.

    Progression : ``pioche → principale → attaque → checkup``. L'entrée en ``checkup`` (fin
    du tour) ouvre la fenêtre « fin de tour ». Après ``checkup``, un nouveau tour s'ouvre :
    numéro + 1, joueur actif adverse, drapeaux « une fois par tour » (R-5.4/5/6) **et**
    l'ensemble « entrés en jeu ce tour » (R-7.3) remis à zéro par construction d'un ``Tour``
    neuf, phase ``pioche``. Refuse d'avancer une partie terminée (R-14.6) ou depuis une phase
    inconnue.

    Transition **mécanique** : elle n'effectue PAS la pioche obligatoire de début de tour —
    c'est le rôle de l'action système ``debut_tour`` (R-5.2), qui seule quitte proprement la
    phase de pioche. Le générateur d'actions ne propose donc pas « avancer la phase » pendant
    la pioche (voir ``FamilleAvancerPhase``).
    """
    if etat.terminee:
        raise ValueError("Partie terminée : aucune phase n'avance (R-14.6).")
    phase = etat.tour.phase
    if phase not in _ORDRE_PHASES:
        raise ValueError(f"Phase inconnue : {phase!r} — avancée impossible (R-5.1).")

    if phase == PHASE_CHECKUP:
        suivant = _autre_joueur(etat, etat.tour.joueur_actif)
        tour2 = Tour(joueur_actif=suivant, numero=etat.tour.numero + 1, phase=PHASE_PIOCHE)
        etat2 = replace(etat, tour=tour2)
        return etat2, [
            Evenement(
                EVT_PHASE_AVANCEE,
                {
                    "de": phase,
                    "vers": PHASE_PIOCHE,
                    "numero": tour2.numero,
                    "joueur_actif": suivant,
                },
            ),
            Evenement(EVT_TOUR_COMMENCE, {"numero": tour2.numero, "joueur_actif": suivant}),
        ]

    vers = _ORDRE_PHASES[_ORDRE_PHASES.index(phase) + 1]
    if vers == PHASE_CHECKUP:
        return _entrer_checkup(etat, rng, de=phase)
    tour2 = replace(etat.tour, phase=vers)
    etat2 = replace(etat, tour=tour2)
    evt = Evenement(
        EVT_PHASE_AVANCEE,
        {
            "de": phase,
            "vers": vers,
            "numero": tour2.numero,
            "joueur_actif": tour2.joueur_actif,
        },
    )
    return etat2, [evt]


def _debut_tour(
    etat: EtatPartie, action: Action, rng: Rng
) -> tuple[EtatPartie, list[Evenement]]:
    """Début de tour (R-5.1/R-5.2) : pioche obligatoire, défaite sur pioche impossible (R-14.2).

    Action **système**, pas un coup libre du joueur (R-5.2) : le service l'applique quand un
    tour s'ouvre (en phase de pioche). Le joueur concerné est le joueur actif du tour.

    Déroulé :

    1. si sa pioche est **vide**, il ne peut pas piocher → **défaite** (R-14.2), condition
       vérifiée ici au bon moment (jamais une exception) : la partie se fige, l'adversaire
       gagne, et l'on **n'avance pas** la phase ;
    2. sinon, il pioche 1 carte (R-5.2) ;
    3. la fenêtre « début de tour » s'ouvre (R-5.1 ; vide au jalon J1) ;
    4. la phase passe en principale (R-5.1 : pioche → principale).
    """
    if etat.terminee:
        raise ValueError("Partie terminée : aucun tour ne commence (R-14.6).")
    if etat.tour.phase != PHASE_PIOCHE:
        raise ValueError(
            f"Début de tour hors de la phase de pioche (phase : {etat.tour.phase!r}, R-5.1)."
        )
    jid = etat.tour.joueur_actif
    index = _index_joueur(etat, jid)
    joueur = etat.joueurs[index]

    # (1) Pioche impossible = DÉFAITE (R-14.2) — pas une exception, une condition de fin.
    if not joueur.pioche:
        gagnant = _autre_joueur(etat, jid)
        etat2 = replace(
            etat, terminee=True, vainqueur=gagnant, raison_fin=RAISON_PIOCHE_IMPOSSIBLE
        )
        evt = Evenement(
            EVT_PARTIE_TERMINEE,
            {"vainqueur": gagnant, "raison": RAISON_PIOCHE_IMPOSSIBLE, "perdant": jid},
        )
        return etat2, [evt]

    # (2) Pioche obligatoire d'une carte (R-5.2).
    piochee = joueur.pioche[0]
    reste = joueur.pioche[1:]
    etat2 = _remplacer_joueur(
        etat, index, replace(joueur, pioche=reste, main=joueur.main + (piochee,))
    )
    evenements = [
        Evenement(
            EVT_CARTES_PIOCHEES,
            {"joueur": jid, "nombre": 1, "instance_ids": [piochee.instance_id]},
        )
    ]

    # (3) Fenêtre « début de tour » (R-5.1) — câblée, vide au jalon J1.
    etat2, evts_fenetre = declencher(etat2, FENETRE_DEBUT_TOUR, rng)
    evenements.extend(evts_fenetre)

    # (4) Passage en phase principale (R-5.1).
    etat2 = replace(etat2, tour=replace(etat2.tour, phase=PHASE_PRINCIPALE))
    evenements.append(
        Evenement(
            EVT_PHASE_AVANCEE,
            {
                "de": PHASE_PIOCHE,
                "vers": PHASE_PRINCIPALE,
                "numero": etat2.tour.numero,
                "joueur_actif": jid,
            },
        )
    )
    return etat2, evenements


def _declarer_attaque(
    etat: EtatPartie, action: Action, rng: Rng
) -> tuple[EtatPartie, list[Evenement]]:
    """Déclarer une attaque (R-5.7/R-5.8) : **termine le tour**, même sans aucun dégât.

    Ce lot (``j-machine-tour``) ne mécanise QUE la fin de tour : aucun coût d'énergie, aucun
    dégât, aucune faiblesse ni résistance (D9 — ils arrivent avec ``j-degats-resolution``, qui
    enregistrera le vrai coup jouable dans le générateur). Déclarer une attaque fait passer en
    phase Checkup (fin du tour) et ouvre la fenêtre « fin de tour ».

    Gardes serveur (le serveur tient les règles seul) : partie vivante (R-14.6), joueur actif
    seulement (R-5.7), phase principale ou d'attaque (R-5.1), pas au premier tour du joueur
    qui commence (R-6.1), et un Pokémon Actif pour porter l'attaque (R-9.1).
    """
    if etat.terminee:
        raise ValueError("Partie terminée : aucune attaque n'est déclarée (R-14.6).")
    jid = action.auteur
    if jid != etat.tour.joueur_actif:
        raise ValueError(
            f"Seul le joueur actif déclare une attaque ; le tour est à "
            f"« {etat.tour.joueur_actif} » (R-5.7)."
        )
    if etat.tour.phase not in (PHASE_PRINCIPALE, PHASE_ATTAQUE):
        raise ValueError(
            f"Une attaque se déclare en phase principale ou d'attaque "
            f"(phase : {etat.tour.phase!r}, R-5.1)."
        )
    if est_premier_tour_du_joueur_qui_commence(etat.tour):
        raise ValueError(
            "Le joueur qui commence ne peut pas attaquer à son premier tour (R-6.1)."
        )
    if etat.joueurs[_index_joueur(etat, jid)].actif is None:
        raise ValueError("Aucun Pokémon Actif ne peut porter l'attaque (R-9.1).")

    # R-11.3/R-11.5/R-11.6 : les états de l'Actif se résolvent AVANT l'attaque — Sommeil et
    # Paralysie l'interdisent (ValueError), la Confusion impose un pile ou face (face = l'attaque
    # a lieu normalement, pile = l'attaque ratée + 3 compteurs sur soi). Délégué à
    # ``pbm_game.etats.attaque`` ; import local pour casser le cycle d'import (voir l'en-tête).
    from ..etats.attaque import resoudre_etats_avant_attaque

    etat, attaque_a_lieu, evenements = resoudre_etats_avant_attaque(etat, jid, rng)

    # R-5.8 : déclarer une attaque **termine le tour**, qu'elle ait eu lieu ou non (confusion
    # tombée sur pile). Au jalon J1, « degats: 0 » est la seule vérité disponible pour une attaque
    # qui a lieu — le calcul réel arrive avec ``j-degats-resolution``.
    if attaque_a_lieu:
        evenements.append(Evenement(EVT_ATTAQUE_DECLAREE, {"joueur": jid, "degats": 0}))
    etat2, evts_checkup = _entrer_checkup(etat, rng, de=etat.tour.phase)
    evenements.extend(evts_checkup)
    return etat2, evenements


def _abandonner(
    etat: EtatPartie, action: Action, rng: Rng
) -> tuple[EtatPartie, list[Evenement]]:
    """Abandon : la partie se termine, l'adversaire gagne (R-14.3, R-14.6).

    L'auteur de l'action est le joueur qui abandonne ; l'autre joueur devient vainqueur.
    Refuse d'abandonner une partie déjà terminée (R-14.6) et refuse un auteur qui n'est pas
    un joueur de la partie (``_autre_joueur`` lève alors) — jamais de repli silencieux.
    """
    if etat.terminee:
        raise ValueError("Partie terminée : plus aucune action, l'abandon compris (R-14.6).")
    perdant = action.auteur
    gagnant = _autre_joueur(etat, perdant)  # lève si l'auteur n'est pas un joueur
    etat2 = replace(etat, terminee=True, vainqueur=gagnant, raison_fin=RAISON_ABANDON)
    evt = Evenement(
        EVT_PARTIE_TERMINEE,
        {"vainqueur": gagnant, "raison": RAISON_ABANDON, "abandon_par": perdant},
    )
    return etat2, [evt]


#: Registre des transitions reconnues. Un type d'action absent est refusé (D9). Les lots
#: de résolution y ajoutent leurs actions (``REGISTRE[ACTION_XXX] = _handler``) **depuis leur
#: propre module**, pour ne pas alourdir ni coupler ce noyau : les trois mouvements de l'Actif
#: (retraite, promotion, échange forcé) vivent dans :mod:`pbm_game.banc.mouvements` et s'y
#: enregistrent eux-mêmes (lot ``j-retraite-banc``). ``pbm_game`` importe ``banc`` à son
#: chargement pour garantir cet enregistrement.
REGISTRE: dict[str, Transition] = {
    ACTION_MELANGER_PIOCHE: _melanger_pioche,
    ACTION_PIOCHER: _piocher,
    ACTION_AVANCER_PHASE: _avancer_phase,
    ACTION_ABANDONNER: _abandonner,
    ACTION_DEBUT_TOUR: _debut_tour,
    ACTION_DECLARER_ATTAQUE: _declarer_attaque,
}


def appliquer(
    etat: EtatPartie, action: Action, rng: Rng
) -> tuple[EtatPartie, tuple[Evenement, ...]]:
    """Applique ``action`` à ``etat`` et renvoie ``(nouvel_etat, evenements)``.

    Fonction pure côté état (``etat`` figé, nouvel état renvoyé) ; ``rng`` est le seul
    collaborateur mutable, par conception rejouable. Lève ``ValueError`` si le type
    d'action est inconnu (D9 : jamais approximé) ou si la transition refuse la demande.
    """
    if not isinstance(action, Action):
        raise TypeError(f"appliquer attend une Action, reçu {type(action).__name__}.")
    # R-14.6 — une partie terminée est figée : elle refuse TOUTE action, quel que soit son type.
    # Garde centrale (en plus de celles des transitions) : le journal est clos, plus rien ne
    # s'applique, pas même une action mécanique (mélange, pioche) oubliée par un appelant.
    if etat.terminee:
        raise ValueError(
            f"Partie terminée : elle refuse toute action supplémentaire, « {action.type} » "
            "comprise (R-14.6)."
        )
    # Une demande de décision en cours met la partie **en pause** : tant qu'elle n'est pas tranchée,
    # on n'accepte que la réponse, son expiration, ou l'abandon (R-14.3, toujours permis). Toute
    # autre action est refusée — c'est la garde du lot ``j-effets-choix`` : « empêcher toute autre
    # action tant qu'une demande est en cours, sauf l'abandon ». Jamais un repli silencieux.
    if etat.resolution is not None and action.type not in _ACTIONS_PENDANT_DEMANDE:
        raise ValueError(
            f"Décision en attente (« {etat.resolution.demande.id} » — "
            f"{etat.resolution.demande.libelle}) : seules la réponse, son expiration et l'abandon "
            f"sont permises, pas « {action.type} »."
        )
    handler = REGISTRE.get(action.type)
    if handler is None:
        raise ValueError(
            f"Type d'action inconnu : {action.type!r} — un effet non implémenté n'est "
            f"jamais approximé (D9). Types connus : {sorted(REGISTRE)}."
        )
    etat2, evenements = handler(etat, action, rng)
    return etat2, tuple(evenements)


def partie_neuve(etat_initial: EtatPartie, graine: str) -> Partie:
    """Crée une :class:`Partie` au journal vide, sur ``etat_initial`` et ``graine`` (hex)."""
    if not isinstance(graine, str) or not graine:
        raise ValueError("La graine d'une partie doit être une chaîne hexadécimale non vide.")
    return Partie(etat_initial=etat_initial, graine=graine, entrees=())


def jouer(
    partie: Partie,
    action: Action,
    horodatage: str,
    etat_courant: EtatPartie,
    rng: Rng,
) -> tuple[Partie, EtatPartie]:
    """Joue ``action`` sur l'état courant, et renvoie la partie augmentée + le nouvel état.

    L'appelant (le service de parties) tient le triplet vivant ``(partie, etat_courant,
    rng)`` : il passe l'état courant et le Rng vivant, récupère la partie dont le journal
    s'est allongé d'une entrée et le nouvel état. L'entrée porte le numéro suivant, les
    événements produits, l'horodatage fourni et l'empreinte de l'état résultant.

    ``horodatage`` est fourni par l'appelant (le moteur est pur, sans horloge).
    """
    if not isinstance(horodatage, str) or not horodatage:
        raise ValueError("L'horodatage d'une entrée doit être une chaîne non vide (fournie).")
    etat2, evenements = appliquer(etat_courant, action, rng)
    entree = Entree(
        numero=len(partie.entrees),
        auteur=action.auteur,
        action=action,
        evenements=evenements,
        horodatage=horodatage,
        empreinte=empreinte(etat2),
    )
    partie2 = replace(partie, entrees=partie.entrees + (entree,))
    return partie2, etat2
