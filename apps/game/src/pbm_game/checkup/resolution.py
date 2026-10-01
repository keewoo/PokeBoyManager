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

from ..combat.ko import cartes_a_defausser, est_ko, prendre_recompenses
from ..journal.modele import (
    ACTION_CHECKUP,
    EVT_ETAT_CHECKUP,
    EVT_KO,
    EVT_PARTIE_TERMINEE,
    EVT_PROMOTION_REQUISE,
    RAISON_PLUS_DE_POKEMON,
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
    RAISON_EGALITE,
    EtatPartie,
    Joueur,
    PokemonEnJeu,
    carte_active,
)
from ..tour.drapeaux import identite_pokemon
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


# --- Étape 3 : K.O. de la phase, récompenses, promotion / fin (R-12.4, R-13) --------------


def _fiche(fiches: dict, pokemon: PokemonEnJeu) -> dict:
    """La fiche catalogue (PV + récompenses) du Pokémon, par l'``instance_id`` de sa carte au
    sommet. **Absente = panne bruyante** (D9) : le moteur ne devine ni PV ni marqueur de règle.
    """
    cle = carte_active(pokemon).instance_id
    fiche = fiches.get(cle)
    if not isinstance(fiche, dict):
        raise ValueError(
            f"Fiche de catalogue manquante pour le Pokémon « {cle} » : PV (R-13.1) et nombre de "
            "récompenses (R-13.3) sont requis au Checkup et fournis par le service (D9)."
        )
    return fiche


def _trouver_ko(joueur: Joueur, fiches: dict) -> tuple[str, int] | None:
    """Localise un Pokémon K.O. de ``joueur`` (``("actif", -1)`` ou ``("banc", i)``), ou ``None``.

    Ne considère que les Pokémon **endommagés** (compteurs > 0) : un Pokémon intact n'est jamais
    K.O. et n'exige donc pas de fiche. Un Pokémon endommagé **sans** fiche fait échouer
    :func:`_fiche` (bruyamment). L'Actif est examiné avant le banc (ordre déterministe).
    """
    if joueur.actif is not None and joueur.actif.compteurs_degats > 0:
        if est_ko(joueur.actif.compteurs_degats, _fiche(fiches, joueur.actif)["pv"]):
            return ("actif", -1)
    for i, p in enumerate(joueur.banc):
        if p.compteurs_degats > 0 and est_ko(p.compteurs_degats, _fiche(fiches, p)["pv"]):
            return ("banc", i)
    return None


def _appliquer_ko(
    etat: EtatPartie, jid: str, cible: tuple[str, int], fiches: dict
) -> tuple[EtatPartie, Evenement]:
    """Met K.O. le Pokémon ``cible`` de ``jid`` : défausse (R-13.2), l'adversaire prend ses
    récompenses (R-13.3). L'Actif K.O. laisse la place **vide** (``None``) — la promotion suit.
    """
    index = _index_joueur(etat, jid)
    joueur = etat.joueurs[index]
    zone, i = cible
    pokemon = joueur.actif if zone == "actif" else joueur.banc[i]
    nb = _fiche(fiches, pokemon)["recompenses"]

    defausse = joueur.defausse + cartes_a_defausser(pokemon)
    if zone == "actif":
        joueur = replace(joueur, actif=None, defausse=defausse)
    else:
        banc = joueur.banc[:i] + joueur.banc[i + 1 :]
        joueur = replace(joueur, banc=banc, defausse=defausse)
    etat = _remplacer_joueur(etat, index, joueur)

    adversaire = _autre_joueur(etat, jid)
    idx_adv = _index_joueur(etat, adversaire)
    joueur_adv, prises = prendre_recompenses(etat.joueurs[idx_adv], nb)
    etat = _remplacer_joueur(etat, idx_adv, joueur_adv)

    evt = Evenement(
        EVT_KO,
        {"joueur": jid, "pokemon": identite_pokemon(pokemon),
         "compteurs": pokemon.compteurs_degats, "recompenses_prises": prises, "par": adversaire},
    )
    return etat, evt


def _resoudre_kos(
    etat: EtatPartie, fiches: dict, ordre: tuple[str, str]
) -> tuple[EtatPartie, list[Evenement]]:
    """Met K.O. tous les Pokémon dont les compteurs ont atteint les PV (R-12.4), puis demande les
    promotions ou clôt la partie. Le joueur dont le tour s'achève est traité en premier.
    """
    evenements: list[Evenement] = []
    # On ne traite que les K.O. survenus **pendant cette phase** : un joueur qui entre déjà sans
    # Actif (promotion d'un tour précédent encore en attente) ne relève pas de ce Checkup.
    avait_actif = {jid: etat.joueurs[_index_joueur(etat, jid)].actif is not None for jid in ordre}
    for jid in ordre:
        # Boucle : retirer un K.O. du banc décale les index — on rescanne jusqu'à épuisement.
        while True:
            cible = _trouver_ko(etat.joueurs[_index_joueur(etat, jid)], fiches)
            if cible is None:
                break
            etat, evt = _appliquer_ko(etat, jid, cible, fiches)
            evenements.append(evt)

    # Après tous les K.O. : qui doit promouvoir (R-8.7), qui a perdu (banc vide, R-8.9/R-14.1) ?
    # Seuls comptent les joueurs dont l'Actif **est tombé pendant cette phase**.
    perdants: list[str] = []
    a_promouvoir: list[str] = []
    for jid in ordre:
        joueur = etat.joueurs[_index_joueur(etat, jid)]
        if avait_actif[jid] and joueur.actif is None:
            (a_promouvoir if joueur.banc else perdants).append(jid)

    if perdants:
        if len(perdants) == 2:
            # Les deux joueurs sans Pokémon au même Checkup = égalité (R-14.4 ; détail complet
            # du K.O. simultané et de l'égalité : lot j-ko-recompenses).
            etat = replace(etat, terminee=True, vainqueur=None, raison_fin=RAISON_EGALITE)
            evenements.append(
                Evenement(
                    EVT_PARTIE_TERMINEE,
                    {"vainqueur": None, "raison": RAISON_EGALITE, "perdants": perdants},
                )
            )
        else:
            perdant = perdants[0]
            gagnant = _autre_joueur(etat, perdant)
            etat = replace(
                etat, terminee=True, vainqueur=gagnant, raison_fin=RAISON_PLUS_DE_POKEMON
            )
            evenements.append(
                Evenement(
                    EVT_PARTIE_TERMINEE,
                    {"vainqueur": gagnant, "raison": RAISON_PLUS_DE_POKEMON, "perdant": perdant},
                )
            )
        return etat, evenements

    for jid in a_promouvoir:
        evenements.append(Evenement(EVT_PROMOTION_REQUISE, {"joueur": jid}))
    return etat, evenements


# --- La phase, de bout en bout ------------------------------------------------------------


def _valider_fiches(fiches: object) -> dict:
    """Valide ``params["fiches"]`` : un mapping ``instance_id → {pv ≥ 1, recompenses ≥ 1}``.

    Toute entrée malformée est une panne (D9 : jamais un repli « par défaut 1 »). Un mapping vide
    est permis — une partie sans aucun Pokémon endommagé n'a besoin d'aucune fiche.
    """
    if not isinstance(fiches, dict):
        raise ValueError(
            "« fiches » doit être un mapping instance_id → {pv, recompenses}, fourni par le "
            "service depuis le catalogue (R-13.1/R-13.3, D9)."
        )
    for cle, fiche in fiches.items():
        if not isinstance(cle, str) or not cle:
            raise ValueError(f"Fiche : clé invalide {cle!r} (un instance_id est attendu).")
        if not isinstance(fiche, dict):
            raise ValueError(f"Fiche « {cle} » : doit être un mapping {{pv, recompenses}}.")
        pv = fiche.get("pv")
        if not isinstance(pv, int) or isinstance(pv, bool) or pv <= 0:
            raise ValueError(f"Fiche « {cle} » : « pv » invalide {pv!r} (entier ≥ 1, R-13.1).")
        rec = fiche.get("recompenses")
        if not isinstance(rec, int) or isinstance(rec, bool) or rec < 1:
            raise ValueError(
                f"Fiche « {cle} » : « recompenses » invalide {rec!r} (entier ≥ 1, R-13.3)."
            )
    return fiches


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
    fiches = _valider_fiches(fiches)
    evenements: list[Evenement] = []
    ordre = (etat.tour.joueur_actif, _autre_joueur(etat, etat.tour.joueur_actif))

    # 1) États spéciaux de l'Actif de chaque joueur, dans l'ordre R-12.2.
    for jid in ordre:
        etat, evts = _resoudre_etats_actif(etat, jid, rng)
        evenements.extend(evts)

    # 2) Expiration des effets « jusqu'à la fin de ce tour » (R-12.5), journalisée.
    etat, evts = declencher(etat, FENETRE_EXPIRATION_EFFETS, rng, declencheurs)
    evenements.extend(evts)

    # 3) K.O. provoqués pendant la phase (R-12.4) + récompenses (R-13) + promotion/fin.
    etat, evts = _resoudre_kos(etat, fiches, ordre)
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
