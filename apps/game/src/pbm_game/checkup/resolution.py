"""Pokémon Checkup — la **phase entre les deux tours**, dans un ordre fixé (R-12).

Module **pur** (aucune E/S, ni HTTP, ni base, ni React), comme tout ``pbm_game``. Beaucoup
d'effets disent « à la fin du tour » ou « entre les tours » ; sans une phase nommée où tout se
résout dans un **ordre fixé**, ces effets se résoudraient dans l'ordre où le code a été écrit —
c'est-à-dire au hasard. Ce module est cette phase.

L'ordre, point par point depuis le corpus (``docs/jeu/REGLES.md``) :

1. **États spéciaux** de l'Actif de chaque joueur, dans l'ordre **R-12.2** :
   **1) Empoisonné (R-11.7), 2) Brûlé (R-11.4), 3) Endormi (R-11.3), 4) Paralysé (R-11.6)** ;
2. **Expiration** des effets temporaires « jusqu'à la fin de ce tour » (**R-12.5**), chaque
   retrait **journalisé** (sinon un effet temporaire devient éternel sans que rien ne le dise) ;
3. **K.O.** survenus pendant la phase — hors attaque (**R-12.4**) : défausse (R-13.2),
   récompenses prises par l'adversaire (R-13.3), puis **promotion demandée** au bon joueur
   (R-8.7) ou **défaite** si son banc est vide (R-8.9/R-14.1).

**Ordre des deux joueurs.** Le joueur **dont le tour s'achève** (``tour.joueur_actif`` pendant
la phase ``checkup``) est résolu **avant** son adversaire — pour que la suite des tirages
(réveil, brûlure) et l'ordre des événements soient **déterministes** et rejouables (R-12.2/
R-12.4). C'est aussi cet ordre qui porte la paralysie : elle guérit **au Checkup après le tour
de son propriétaire** (R-11.6), donc seulement sur l'Actif du joueur dont le tour s'achève.

**Le moteur ne devine ni PV ni récompenses (D9).** La détection d'un K.O. (compteurs ≥ PV,
R-13.1) et le nombre de récompenses (marqueur de règle, R-13.3) se lisent **sur la carte**, dans
le catalogue — que le moteur ne connaît pas. L'action système ``checkup`` les reçoit dans
``params["fiches"]`` (``instance_id de la carte au sommet → {"pv", "recompenses"}``), que le
service extrait du catalogue. Une fiche **manquante** pour un Pokémon qui pourrait être K.O. fait
**échouer bruyamment** — jamais un repli silencieux.

**Périmètre du lot ``j-checkup`` (palier 6).** Ce lot livre la **phase ordonnée** et sa
mécanique de K.O. hors attaque. Les lots suivants s'y branchent sans la réécrire :
``j-etats-speciaux`` (palier 7) ajoute la **pose** des états, la matrice de cumul, la confusion
à la déclaration d'attaque et l'orientation ; ``j-ko-recompenses`` (palier 7) ajoute les
**conditions de victoire** complètes (plus de récompenses à prendre, K.O. simultané détaillé,
égalité) au-dessus des primitives partagées de :mod:`pbm_game.combat.ko`.
"""

from __future__ import annotations

from dataclasses import replace

from ..combat.fin import resoudre_kos, valider_fiches
from ..journal.modele import (
    ACTION_CHECKUP,
    EVT_ETAT_CHECKUP,
    Action,
    Evenement,
)
from ..journal.transitions import REGISTRE
from ..rng import FACE, Rng, flux_checkup
from ..state.modele import (
    BRULE,
    EMPOISONNE,
    ENDORMI,
    PARALYSE,
    PHASE_CHECKUP,
    EtatPartie,
    Joueur,
)
from ..tour.fenetres import FENETRE_EXPIRATION_EFFETS, Declencheur, declencher

#: Dégâts posés par l'empoisonnement à chaque Checkup (R-11.7) — **1** compteur.
POISON_DEGATS = 10
#: Dégâts posés par la brûlure à chaque Checkup (R-11.4) — **2** compteurs.
BRULURE_DEGATS = 20


# --- Helpers immuables (même forme que journal.transitions / banc.mouvements) ------------


def _index_joueur(etat: EtatPartie, jid: str) -> int:
    for i, joueur in enumerate(etat.joueurs):
        if joueur.id == jid:
            return i
    raise ValueError(f"Joueur « {jid} » absent de la partie.")


def _remplacer_joueur(etat: EtatPartie, index: int, joueur: Joueur) -> EtatPartie:
    joueurs = list(etat.joueurs)
    joueurs[index] = joueur
    return replace(etat, joueurs=(joueurs[0], joueurs[1]))


def _autre_joueur(etat: EtatPartie, jid: str) -> str:
    a, b = etat.joueurs[0].id, etat.joueurs[1].id
    if jid == a:
        return b
    if jid == b:
        return a
    raise ValueError(f"Joueur « {jid} » absent de la partie.")


# --- Étape 1 : résolution des états spéciaux de l'Actif (R-12.2) --------------------------


def _resoudre_etats_actif(
    etat: EtatPartie, jid: str, rng: Rng
) -> tuple[EtatPartie, list[Evenement]]:
    """Résout les états de l'Actif de ``jid`` dans l'ordre R-12.2 (poison, brûlure, sommeil,
    paralysie) et journalise chacun. Pur ; sans Actif, ne fait rien (R-11.2).

    Poison et brûlure **posent des compteurs** (R-11.7/R-11.4) ; brûlure et sommeil tirent un
    **pile ou face** (face = guéri, R-11.4/R-11.3), journalisé dans son flux dédié. La paralysie
    ne guérit (R-11.6) que si ``jid`` est le joueur **dont le tour s'achève** — c'est le sens de
    « guérit au Checkup après le tour suivant de son propriétaire ».
    """
    index = _index_joueur(etat, jid)
    joueur = etat.joueurs[index]
    actif = joueur.actif
    if actif is None:  # R-11.2 : un état spécial ne frappe que l'Actif.
        return etat, []

    evenements: list[Evenement] = []
    etats = set(actif.etats_speciaux)
    compteurs = actif.compteurs_degats
    tour_du_proprietaire = jid == etat.tour.joueur_actif

    # 1) Empoisonné (R-11.7) — 1 compteur, pas de pile ou face.
    if EMPOISONNE in etats:
        compteurs += POISON_DEGATS
        evenements.append(
            Evenement(
                EVT_ETAT_CHECKUP,
                {"joueur": jid, "etat": EMPOISONNE, "regle": "R-11.7",
                 "degats": POISON_DEGATS, "gueri": False},
            )
        )

    # 2) Brûlé (R-11.4) — 2 compteurs PUIS pile ou face (face = guéri, retirer le marqueur).
    if BRULE in etats:
        compteurs += BRULURE_DEGATS
        tirage = rng.pile_ou_face(flux_checkup("brule", jid), "R-11.4 guérison brûlure")
        gueri = tirage == FACE
        if gueri:
            etats.discard(BRULE)
        evenements.append(
            Evenement(
                EVT_ETAT_CHECKUP,
                {"joueur": jid, "etat": BRULE, "regle": "R-11.4", "degats": BRULURE_DEGATS,
                 "pile_ou_face": tirage, "gueri": gueri},
            )
        )

    # 3) Endormi (R-11.3) — pile ou face : face = réveil, pile = reste endormi.
    if ENDORMI in etats:
        tirage = rng.pile_ou_face(flux_checkup("endormi", jid), "R-11.3 réveil")
        gueri = tirage == FACE
        if gueri:
            etats.discard(ENDORMI)
        evenements.append(
            Evenement(
                EVT_ETAT_CHECKUP,
                {"joueur": jid, "etat": ENDORMI, "regle": "R-11.3", "degats": 0,
                 "pile_ou_face": tirage, "gueri": gueri},
            )
        )

    # 4) Paralysé (R-11.6) — guérit au Checkup APRÈS le tour de son propriétaire, sinon persiste.
    if PARALYSE in etats:
        gueri = tour_du_proprietaire
        if gueri:
            etats.discard(PARALYSE)
        evenements.append(
            Evenement(
                EVT_ETAT_CHECKUP,
                {"joueur": jid, "etat": PARALYSE, "regle": "R-11.6", "degats": 0, "gueri": gueri},
            )
        )

    if not evenements:
        return etat, []
    actif2 = replace(actif, compteurs_degats=compteurs, etats_speciaux=frozenset(etats))
    etat2 = _remplacer_joueur(etat, index, replace(joueur, actif=actif2))
    return etat2, evenements


# --- La phase, de bout en bout ------------------------------------------------------------
#
# Étape 3 (K.O. de la phase, récompenses, promotion / fin — R-12.4, R-13) : déléguée à
# :func:`pbm_game.combat.fin.resoudre_kos`, **partagée** avec la résolution d'attaque. Le code de
# K.O. et des conditions de victoire ne vit pas dans le Checkup : il est au même endroit pour les
# deux chemins (lot ``j-ko-recompenses``). Le Checkup lui passe l'ordre « joueur dont le tour
# s'achève d'abord » (R-12.2/R-12.4), pour que la suite des événements reste déterministe.


def resoudre_checkup(
    etat: EtatPartie,
    rng: Rng,
    *,
    fiches: object,
    declencheurs: dict[str, tuple[Declencheur, ...]] | None = None,
) -> tuple[EtatPartie, list[Evenement]]:
    """Résout un Pokémon Checkup complet (R-12) et renvoie ``(etat, evenements)``. Pur.

    Ordre : états de chaque Actif (R-12.2) → expiration des effets temporaires (R-12.5) → K.O.
    de la phase avec récompenses et promotion/fin (R-12.4, R-13). ``fiches`` porte les PV et le
    nombre de récompenses par Pokémon (catalogue, fourni par le service). ``declencheurs`` n'est
    à passer que pour les tests (injecter un effet d'expiration jouet) ; par défaut, la table
    :data:`~pbm_game.tour.fenetres.DECLENCHEURS` (vide au jalon J1).

    Lève ``ValueError`` si la partie est déjà terminée (R-14.6) ou si une fiche est malformée.
    """
    if etat.terminee:
        raise ValueError("Partie terminée : aucun Pokémon Checkup (R-14.6).")
    # Validation **eager** des fiches : une fiche malformée est une panne même si aucun Pokémon
    # n'est K.O. ce Checkup (D9 : jamais un repli silencieux).
    fiches = valider_fiches(fiches)
    evenements: list[Evenement] = []
    ordre = (etat.tour.joueur_actif, _autre_joueur(etat, etat.tour.joueur_actif))

    # 1) États spéciaux de l'Actif de chaque joueur, dans l'ordre R-12.2.
    for jid in ordre:
        etat, evts = _resoudre_etats_actif(etat, jid, rng)
        evenements.extend(evts)

    # 2) Expiration des effets « jusqu'à la fin de ce tour » (R-12.5), journalisée.
    etat, evts = declencher(etat, FENETRE_EXPIRATION_EFFETS, rng, declencheurs)
    evenements.extend(evts)

    # 3) K.O. provoqués pendant la phase (R-12.4) + récompenses + conditions de victoire (R-13,
    #    R-14) — résolveur partagé avec l'attaque.
    etat, evts = resoudre_kos(etat, fiches, ordre)
    evenements.extend(evts)

    return etat, evenements


def appliquer_checkup(
    etat: EtatPartie, action: Action, rng: Rng
) -> tuple[EtatPartie, list[Evenement]]:
    """Transition ``checkup`` : résout la phase en lisant ``params["fiches"]`` (R-12).

    Action **système** (R-12.1 : automatique entre les tours). Gardes : partie vivante (R-14.6)
    et phase ``checkup`` (R-12.1). Les fiches catalogue sont dans ``params`` pour que le journal
    les porte — donc rejouables sans que le rejeu ait besoin du catalogue.
    """
    if etat.tour.phase != PHASE_CHECKUP:
        raise ValueError(
            f"Le Pokémon Checkup se résout en phase checkup (phase : {etat.tour.phase!r}, R-12.1)."
        )
    return resoudre_checkup(etat, rng, fiches=action.params.get("fiches", {}))


# Enregistrement dans le REGISTRE des transitions (même mécanique que ``banc.mouvements``) :
# ``appliquer`` reconnaît désormais l'action système ``checkup``, journalisée et rejouable.
REGISTRE[ACTION_CHECKUP] = appliquer_checkup


__all__ = [
    "POISON_DEGATS",
    "BRULURE_DEGATS",
    "resoudre_checkup",
    "appliquer_checkup",
]
