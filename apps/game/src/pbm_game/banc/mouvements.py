"""Les trois façons dont l'Actif change de place — retraite, promotion, échange forcé (R-8).

Module **pur** (aucune E/S, ni HTTP, ni base, ni React), comme tout ``pbm_game``. Il porte le
geste défensif du jeu : le Pokémon Actif quitte le front, un autre prend sa place. **Trois
mouvements distincts**, aux règles différentes — les confondre rendrait injouables les cartes
d'appât (risque nommé dans la fiche du lot) :

* **retraite** (R-8.2/R-8.3/R-8.4) — volontaire, pendant son tour : défausser une énergie par
  symbole du coût de retraite (au **choix** du joueur), **une seule fois par tour** (R-5.6),
  **impossible** sous Sommeil ou Paralysie (R-8.4/R-11.10) ;
* **promotion** (R-8.7) — **obligatoire** après un K.O. : le joueur dont l'Actif est K.O. (donc
  absent) choisit un Pokémon du banc ; **banc vide = défaite** (R-8.9/R-14.1) ;
* **échange forcé** (R-8.8) — provoqué par un effet : **ne consomme ni** la retraite du tour
  **ni** d'énergie, et **peut** viser un Pokémon Endormi ou Paralysé (R-16.12).

Les trois partagent le **passage au banc** (R-8.6) : le Pokémon qui descend **perd** ses états
spéciaux et les effets d'attaque, mais **conserve** énergies, Outil, compteurs de dégâts et pile
d'évolutions. C'est ce que teste « il soigne ce qu'il doit, et rien d'autre ».

**Le moteur ne devine rien (D9).** Il reçoit le **coût de retraite** (nombre de symboles, lu sur
la carte par le service qui dispose du catalogue) et le **choix** du joueur (quelles énergies
défausser, quel Pokémon du banc promouvoir) ; il **valide** et **applique**. Un refus lève une
``ValueError`` qui **cite la règle** — jamais un refus muet (pas de repli silencieux). La *liste*
de la retraite comme coup jouable par le générateur attend le catalogue : elle arrive avec
``j-cartes-pokemon`` (que ce lot débloque).

Ces trois transitions sont **journalisées** : leurs gestionnaires s'enregistrent dans le même
``REGISTRE`` que les transitions mécaniques, **en bas de ce module** (``REGISTRE[...] = ...``).
C'est le module qui s'y inscrit, pas ``journal.transitions`` qui le tire — sinon le noyau des
transitions dépendrait de ``banc`` qui dépend de lui (cycle d'import). Pour que cet
enregistrement ait toujours lieu, ``pbm_game`` importe ``banc`` à son chargement.
"""

from __future__ import annotations

from dataclasses import replace

from ..etats.matrice import soigner_etats_speciaux
from ..journal.modele import (
    ACTION_ECHANGE_FORCE,
    ACTION_PROMOUVOIR,
    ACTION_RETRAITE,
    AUTEUR_SYSTEME,
    EVT_ECHANGE_FORCE,
    EVT_PARTIE_TERMINEE,
    EVT_PROMOTION,
    EVT_RETRAITE,
    RAISON_PLUS_DE_POKEMON,
    Action,
    Evenement,
)
from ..journal.transitions import REGISTRE
from ..rng import Rng
from ..state.modele import (
    ENDORMI,
    PARALYSE,
    PHASE_ATTAQUE,
    PHASE_PRINCIPALE,
    Carte,
    EtatPartie,
    Joueur,
    PokemonEnJeu,
)
from ..tour.drapeaux import identite_pokemon, marquer_retraite_faite, retraite_deja_faite

# Phases pendant lesquelles une retraite **volontaire** est permise : le corps du tour
# (R-5.1), comme la déclaration d'attaque. La promotion et l'échange forcé ne sont pas liés à
# une phase (un K.O. ou un effet survient aussi au Checkup).
_PHASES_RETRAITE: tuple[str, ...] = (PHASE_PRINCIPALE, PHASE_ATTAQUE)


# --- Helpers immuables (dupliqués de journal.transitions à dessein : ce module ne doit pas
# importer journal.transitions, qui l'importe lui — voir l'en-tête du module) ---------------


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


def _param_banc_index(action: Action) -> int:
    """Lit ``params["banc_index"]`` en exigeant un entier ≥ 0 (jamais un index deviné)."""
    index = action.params.get("banc_index")
    if not isinstance(index, int) or isinstance(index, bool) or index < 0:
        raise ValueError(
            f"« banc_index » invalide : {index!r} — un entier ≥ 0 désignant le Pokémon du "
            "banc est requis (R-8.7)."
        )
    return index


# --- Passage au banc (R-8.6) — le cœur partagé des trois mouvements ----------------------


def _nettoyer_pour_banc(pokemon: PokemonEnJeu) -> PokemonEnJeu:
    """Le Pokémon qui **descend au banc** (R-8.6) : perd ses états spéciaux et les effets
    d'attaque, **conserve** énergies, Outil, compteurs de dégâts et pile d'évolutions.

    La guérison de **tous** les états passe par :func:`pbm_game.etats.soigner_etats_speciaux`
    (R-11.9), **partagée** avec l'évolution et les effets de soin : une seule porte, pour que
    « que garde / que perd un Pokémon qui guérit » ne diverge pas entre ces chemins. Au jalon J1,
    « effets d'attaque » n'existe encore sur aucune carte (D9) ; quand les effets temporaires
    seront portés par l'état (lots d'effets), ils se retireront **ici**, au même endroit.
    """
    return soigner_etats_speciaux(pokemon)


def _echanger_actif_et_banc(joueur: Joueur, banc_index: int) -> Joueur:
    """Promeut ``banc[banc_index]`` en Actif et renvoie l'ancien Actif, **nettoyé** (R-8.6),
    à sa place dans le banc. Suppose un Actif présent et un ``banc_index`` déjà validé.
    """
    promu = joueur.banc[banc_index]
    descendu = _nettoyer_pour_banc(joueur.actif)
    banc = list(joueur.banc)
    banc[banc_index] = descendu
    return replace(joueur, actif=promu, banc=tuple(banc))


# --- Retraite volontaire (R-8.2/R-8.3/R-8.4) ---------------------------------------------


def battre_en_retraite(
    etat: EtatPartie,
    jid: str,
    banc_index: int,
    cout_retraite: int,
    energies_defaussees: tuple[str, ...],
) -> tuple[EtatPartie, list[Evenement]]:
    """Fait battre en retraite l'Actif de ``jid`` (R-8.2). Pur ; lève ``ValueError`` motivée.

    ``cout_retraite`` est le nombre de symboles du coût de retraite (fourni par le service depuis
    le catalogue) ; ``energies_defaussees`` sont les ``instance_id`` des énergies que le joueur
    **choisit** de défausser — exactement une par symbole (R-8.2). L'ancien Actif descend au banc
    **nettoyé** (R-8.6) et le Pokémon ``banc[banc_index]`` devient Actif (il peut attaquer le
    même tour, R-8.5). Marque la retraite du tour (R-5.6/R-8.3).
    """
    if etat.terminee:
        raise ValueError("Partie terminée : aucune retraite (R-14.6).")
    if jid != etat.tour.joueur_actif:
        raise ValueError(
            f"Seul le joueur actif bat en retraite ; le tour est à "
            f"« {etat.tour.joueur_actif} » (R-5.1)."
        )
    if etat.tour.phase not in _PHASES_RETRAITE:
        raise ValueError(
            f"La retraite se fait pendant le corps du tour (phase : {etat.tour.phase!r}, R-5.1)."
        )
    if retraite_deja_faite(etat.tour):
        raise ValueError("Une retraite a déjà eu lieu ce tour : une seule par tour (R-5.6/R-8.3).")

    index = _index_joueur(etat, jid)
    joueur = etat.joueurs[index]
    actif = joueur.actif
    if actif is None:
        raise ValueError("Aucun Pokémon Actif ne peut battre en retraite (R-8.2).")

    # R-8.4 / R-11.10 : Sommeil ou Paralysie interdisent la retraite volontaire.
    bloquants = sorted(actif.etats_speciaux & {ENDORMI, PARALYSE})
    if bloquants:
        raise ValueError(
            f"L'Actif ne peut pas battre en retraite sous l'état {bloquants} (R-8.4/R-11.10)."
        )

    # R-8.2 : il faut un Pokémon de banc pour prendre la place.
    if not joueur.banc:
        raise ValueError("Aucun Pokémon de banc pour prendre la place de l'Actif (R-8.2).")
    if banc_index >= len(joueur.banc):
        raise ValueError(
            f"« banc_index » {banc_index} hors du banc ({len(joueur.banc)} Pokémon, R-8.2)."
        )

    actif2, defaussees = _retirer_energies(actif, cout_retraite, energies_defaussees)
    joueur = replace(joueur, actif=actif2, defausse=joueur.defausse + defaussees)
    joueur = _echanger_actif_et_banc(joueur, banc_index)

    etat2 = _remplacer_joueur(etat, index, joueur)
    etat2 = replace(etat2, tour=marquer_retraite_faite(etat2.tour))  # R-5.6/R-8.3
    evt = Evenement(
        EVT_RETRAITE,
        {
            "joueur": jid,
            "ancien_actif": identite_pokemon(actif),
            "nouvel_actif": identite_pokemon(joueur.actif),
            "cout": cout_retraite,
            "energies_defaussees": [c.instance_id for c in defaussees],
        },
    )
    return etat2, [evt]


def _retirer_energies(
    actif: PokemonEnJeu, cout_retraite: int, energies_defaussees: tuple[str, ...]
) -> tuple[PokemonEnJeu, tuple[Carte, ...]]:
    """Retire de l'Actif les énergies choisies (R-8.2) : une par symbole, au choix du joueur.

    Exige ``cout_retraite`` entier ≥ 0, autant d'identifiants **distincts** que de symboles, et
    que chacun désigne une énergie **réellement attachée**. Un coût nul = retraite gratuite
    (aucune énergie défaussée). Renvoie l'Actif allégé et les énergies retirées (pour la
    défausse). Lève ``ValueError`` motivée — jamais une défausse approximative.
    """
    if not isinstance(cout_retraite, int) or isinstance(cout_retraite, bool) or cout_retraite < 0:
        raise ValueError(f"« cout_retraite » invalide : {cout_retraite!r} (entier ≥ 0, R-8.2).")
    choisies = tuple(energies_defaussees)
    if len(choisies) != cout_retraite:
        raise ValueError(
            f"Coût de retraite non payé : {cout_retraite} symbole(s) = {cout_retraite} "
            f"énergie(s) à défausser, {len(choisies)} choisie(s) (R-8.2)."
        )
    if len(set(choisies)) != len(choisies):
        raise ValueError("Une même énergie ne peut être défaussée deux fois (R-8.2).")
    attachees = {c.instance_id: c for c in actif.energies}
    if cout_retraite > len(actif.energies):
        raise ValueError(
            f"Énergie insuffisante pour la retraite : {cout_retraite} requise(s), "
            f"{len(actif.energies)} attachée(s) (R-8.2)."
        )
    inconnues = [iid for iid in choisies if iid not in attachees]
    if inconnues:
        raise ValueError(
            f"Énergies à défausser non attachées à l'Actif : {inconnues} (R-8.2)."
        )
    a_defausser = frozenset(choisies)
    defaussees = tuple(c for c in actif.energies if c.instance_id in a_defausser)
    restantes = tuple(c for c in actif.energies if c.instance_id not in a_defausser)
    return replace(actif, energies=restantes), defaussees


# --- Promotion après un K.O. (R-8.7) — obligatoire, banc vide = défaite (R-8.9) ----------


def promouvoir(
    etat: EtatPartie, jid: str, banc_index: int
) -> tuple[EtatPartie, list[Evenement]]:
    """Promeut un Pokémon du banc de ``jid`` en Actif après un K.O. (R-8.7). Pur.

    Précondition : l'Actif de ``jid`` est **absent** (``None``) — c'est le vide laissé par un
    K.O. que la promotion comble. Si le banc est **vide**, ``jid`` n'a plus de Pokémon : c'est
    une **défaite** (R-8.9/R-14.1), pas une exception — la partie se fige, l'adversaire gagne.
    Sinon ``banc[banc_index]`` devient Actif. Lève ``ValueError`` si l'Actif est présent (aucune
    promotion requise) ou si ``banc_index`` est hors banc.
    """
    if etat.terminee:
        raise ValueError("Partie terminée : aucune promotion (R-14.6).")
    index = _index_joueur(etat, jid)
    joueur = etat.joueurs[index]
    if joueur.actif is not None:
        raise ValueError(
            "La promotion ne s'applique qu'après un K.O. (Actif absent) ; l'Actif est présent "
            "(R-8.7)."
        )

    # R-8.9 / R-14.1 cas 2 : banc vide quand une promotion est requise = défaite.
    if not joueur.banc:
        gagnant = _autre_joueur(etat, jid)
        etat2 = replace(etat, terminee=True, vainqueur=gagnant, raison_fin=RAISON_PLUS_DE_POKEMON)
        evt = Evenement(
            EVT_PARTIE_TERMINEE,
            {"vainqueur": gagnant, "raison": RAISON_PLUS_DE_POKEMON, "perdant": jid},
        )
        return etat2, [evt]

    if banc_index >= len(joueur.banc):
        raise ValueError(
            f"« banc_index » {banc_index} hors du banc ({len(joueur.banc)} Pokémon, R-8.7)."
        )

    promu = joueur.banc[banc_index]
    banc = joueur.banc[:banc_index] + joueur.banc[banc_index + 1 :]
    joueur = replace(joueur, actif=promu, banc=banc)
    etat2 = _remplacer_joueur(etat, index, joueur)
    evt = Evenement(EVT_PROMOTION, {"joueur": jid, "nouvel_actif": identite_pokemon(promu)})
    return etat2, [evt]


# --- Échange forcé (R-8.8) — ni retraite du tour, ni énergie, autorisé sous état ---------


def echange_force(
    etat: EtatPartie, jid: str, banc_index: int
) -> tuple[EtatPartie, list[Evenement]]:
    """Échange l'Actif de ``jid`` avec ``banc[banc_index]`` sous l'effet d'une carte (R-8.8). Pur.

    **Ne consomme ni** la retraite du tour **ni** d'énergie, et reste **autorisé** même si l'Actif
    est Endormi ou Paralysé (R-16.12) — c'est ce qui le distingue de la retraite volontaire. Comme
    les autres passages au banc, l'ancien Actif descend **nettoyé** (R-8.6). Lève ``ValueError`` si
    l'Actif est absent (ce serait une promotion, R-8.7) ou si le banc est vide / l'index hors banc.
    """
    if etat.terminee:
        raise ValueError("Partie terminée : aucun échange forcé (R-14.6).")
    index = _index_joueur(etat, jid)
    joueur = etat.joueurs[index]
    if joueur.actif is None:
        raise ValueError(
            "Échange forcé impossible sans Actif : un Actif absent relève de la promotion "
            "(R-8.7), pas de l'échange forcé (R-8.8)."
        )
    if not joueur.banc:
        raise ValueError("Aucun Pokémon de banc vers qui échanger l'Actif (R-8.8).")
    if banc_index >= len(joueur.banc):
        raise ValueError(
            f"« banc_index » {banc_index} hors du banc ({len(joueur.banc)} Pokémon, R-8.8)."
        )

    ancien = joueur.actif
    joueur = _echanger_actif_et_banc(joueur, banc_index)
    etat2 = _remplacer_joueur(etat, index, joueur)
    evt = Evenement(
        EVT_ECHANGE_FORCE,
        {
            "joueur": jid,
            "ancien_actif": identite_pokemon(ancien),
            "nouvel_actif": identite_pokemon(joueur.actif),
        },
    )
    return etat2, [evt]


# --- Gestionnaires de transition (signature du REGISTRE) ---------------------------------


def appliquer_retraite(
    etat: EtatPartie, action: Action, rng: Rng
) -> tuple[EtatPartie, list[Evenement]]:
    """Transition ``retraite`` : lit les ``params`` et applique :func:`battre_en_retraite`.

    ``rng`` est inutilisé (la retraite n'a aucun aléa) mais fait partie de la signature commune
    des transitions. Le joueur est l'auteur de l'action.
    """
    banc_index = _param_banc_index(action)
    cout = action.params.get("cout_retraite", 0)
    energies = action.params.get("energies_defaussees", [])
    if not isinstance(energies, list) or any(not isinstance(e, str) for e in energies):
        raise ValueError(
            "« energies_defaussees » doit être une liste d'instance_id (chaînes) — le choix "
            "du joueur (R-8.2)."
        )
    return battre_en_retraite(etat, action.auteur, banc_index, cout, tuple(energies))


def appliquer_promotion(
    etat: EtatPartie, action: Action, rng: Rng
) -> tuple[EtatPartie, list[Evenement]]:
    """Transition ``promouvoir`` : lit ``banc_index`` et applique :func:`promouvoir`.

    Le joueur est l'auteur de l'action (celui dont l'Actif est K.O., pas forcément le joueur
    actif). ``rng`` est inutilisé.
    """
    banc_index = _param_banc_index(action)
    return promouvoir(etat, action.auteur, banc_index)


def appliquer_echange_force(
    etat: EtatPartie, action: Action, rng: Rng
) -> tuple[EtatPartie, list[Evenement]]:
    """Transition ``echange_force`` : lit ``joueur`` + ``banc_index`` et applique
    :func:`echange_force`.

    L'échange est provoqué par un effet : son auteur peut être :data:`AUTEUR_SYSTEME` ou le
    joueur qui joue l'effet, mais la **cible** (le joueur dont l'Actif change) doit être nommée
    dans ``params["joueur"]`` — on ne la devine pas. ``rng`` est inutilisé.
    """
    jid = action.params.get("joueur")
    if not isinstance(jid, str) or not jid or jid == AUTEUR_SYSTEME:
        raise ValueError(
            "Échange forcé sans cible : préciser « params.joueur » (le joueur dont l'Actif "
            "change, R-8.8)."
        )
    banc_index = _param_banc_index(action)
    return echange_force(etat, jid, banc_index)


# Enregistrement dans le REGISTRE des transitions (voir l'en-tête du module) : ``appliquer``
# reconnaît désormais les trois mouvements, qui sont donc journalisés et rejouables.
REGISTRE[ACTION_RETRAITE] = appliquer_retraite
REGISTRE[ACTION_PROMOUVOIR] = appliquer_promotion
REGISTRE[ACTION_ECHANGE_FORCE] = appliquer_echange_force


__all__ = [
    "battre_en_retraite",
    "promouvoir",
    "echange_force",
    "appliquer_retraite",
    "appliquer_promotion",
    "appliquer_echange_force",
]
