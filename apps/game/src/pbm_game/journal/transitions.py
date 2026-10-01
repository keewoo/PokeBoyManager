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
from .empreinte import empreinte
from .modele import (
    ACTION_AVANCER_PHASE,
    ACTION_MELANGER_PIOCHE,
    ACTION_PIOCHER,
    AUTEUR_SYSTEME,
    EVT_CARTES_PIOCHEES,
    EVT_PHASE_AVANCEE,
    EVT_PIOCHE_MELANGEE,
    EVT_TOUR_COMMENCE,
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


def _avancer_phase(
    etat: EtatPartie, action: Action, rng: Rng
) -> tuple[EtatPartie, list[Evenement]]:
    """Avance d'une phase (R-5.1) ; depuis ``checkup`` (R-12.1), ouvre le tour suivant.

    Progression : ``pioche → principale → attaque → checkup``. Après ``checkup``, un
    nouveau tour s'ouvre : numéro + 1, joueur actif adverse, drapeaux « une fois par tour »
    (R-5.4/5/6) remis à zéro, phase ``pioche``. Refuse d'avancer une partie terminée
    (R-14.6) ou depuis une phase inconnue.
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


#: Registre des transitions reconnues. Un type d'action absent est refusé (D9). Les lots
#: de résolution y ajoutent leurs actions (``REGISTRE[ACTION_XXX] = _handler``).
REGISTRE: dict[str, Transition] = {
    ACTION_MELANGER_PIOCHE: _melanger_pioche,
    ACTION_PIOCHER: _piocher,
    ACTION_AVANCER_PHASE: _avancer_phase,
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
