"""Transition **attacher une énergie** (R-5.4) — une énergie de la main rejoint un Pokémon en jeu.

Module **pur** (aucune E/S), comme tout ``pbm_game``. Il enregistre sa transition dans le
``REGISTRE`` du journal **en bas du module** (comme ``cartes.transitions``, ``banc`` et
``checkup``) : le noyau des transitions ne peut pas le faire lui-même (cycle d'import), donc
``pbm_game.cartes`` importe ce module à son chargement.

**Attacher est un coup du joueur actif, une seule fois par tour (R-5.4).** La carte Énergie quitte
la main et rejoint les énergies du Pokémon ciblé ; le drapeau « énergie posée » du tour est levé
(R-5.4). Le moteur ne devine pas qu'une carte est une énergie (D9) : l'action porte sa
``definition`` (fiche catalogue de l'énergie, sa fourniture), que le service extrait du catalogue et
que le journal transporte — le rejeu n'a donc pas besoin du catalogue. Un refus **cite sa règle**,
jamais muet (pas de repli silencieux).

Règles servies (``docs/jeu/REGLES.md``) :

* **R-5.4** — attacher une énergie : une seule fois par tour ;
* **R-5.1 / R-5.3** — coup du joueur actif, pendant la phase principale de son tour.
"""

from __future__ import annotations

from dataclasses import replace

from ..journal.modele import (
    ACTION_ATTACHER_ENERGIE,
    EVT_ENERGIE_ATTACHEE,
    Action,
    Evenement,
)
from ..journal.transitions import REGISTRE
from ..rng import Rng
from ..state.modele import (
    PHASE_PRINCIPALE,
    Carte,
    EtatPartie,
    Joueur,
)
from ..tour.drapeaux import identite_pokemon, marquer_energie_posee
from .energie import definition_energie_depuis_dict

# Zones où vit un Pokémon en jeu (mêmes repères que ``cartes.transitions``).
ZONE_ACTIF = "actif"
ZONE_BANC = "banc"


def _index_joueur(etat: EtatPartie, jid: str) -> int:
    for i, joueur in enumerate(etat.joueurs):
        if joueur.id == jid:
            return i
    raise ValueError(f"Joueur « {jid} » absent de la partie.")


def _remplacer_joueur(etat: EtatPartie, index: int, joueur: Joueur) -> EtatPartie:
    joueurs = list(etat.joueurs)
    joueurs[index] = joueur
    return replace(etat, joueurs=(joueurs[0], joueurs[1]))


def _localiser_pokemon(joueur: Joueur, base_id: str) -> tuple[str, int] | None:
    """Localise le Pokémon d'identité ``base_id`` (``("actif", -1)`` / ``("banc", i)``), ou None."""
    if joueur.actif is not None and identite_pokemon(joueur.actif) == base_id:
        return (ZONE_ACTIF, -1)
    for i, pokemon in enumerate(joueur.banc):
        if identite_pokemon(pokemon) == base_id:
            return (ZONE_BANC, i)
    return None


def _retirer_de_main(joueur: Joueur, instance_id: str) -> tuple[Carte, tuple[Carte, ...]]:
    for i, carte in enumerate(joueur.main):
        if carte.instance_id == instance_id:
            return carte, joueur.main[:i] + joueur.main[i + 1 :]
    raise ValueError(
        f"Carte « {instance_id} » absente de la main de « {joueur.id} » : on n'attache qu'une "
        "énergie de sa propre main (R-5.4)."
    )


def _attacher_energie(
    etat: EtatPartie, action: Action, rng: Rng
) -> tuple[EtatPartie, list[Evenement]]:
    """Attache une énergie de la main au Pokémon ciblé (R-5.4). ``rng`` inutilisé (aucun aléa).

    ``params`` : ``carte_main`` (``instance_id`` de la carte Énergie dans la main), ``cible``
    (identité du Pokémon en jeu qui la reçoit, voir ``identite_pokemon``) et ``definition`` (fiche
    catalogue de l'énergie, D9). Lève une ``ValueError`` **citant sa règle** à tout refus.
    """
    # Import local : ``peut_attacher_energie`` tire ``pbm_game.actions`` (Verdict). On l'importe à
    # l'appel pour ne créer aucun cycle à l'import de ``cartes`` par ``pbm_game`` (même motif que
    # ``cartes.transitions`` pour ``peut_evoluer``).
    from ..tour.contraintes import peut_attacher_energie

    if etat.terminee:
        raise ValueError("Partie terminée : aucune énergie n'est attachée (R-14.6).")
    jid = action.auteur
    if jid != etat.tour.joueur_actif:
        raise ValueError(
            f"Seul le joueur actif attache une énergie ; le tour est à "
            f"« {etat.tour.joueur_actif} » (R-5.1)."
        )
    if etat.tour.phase != PHASE_PRINCIPALE:
        raise ValueError(
            f"« attacher une énergie » se joue en phase principale (phase : {etat.tour.phase!r}, "
            "R-5.3)."
        )
    verdict = peut_attacher_energie(etat.tour)
    if verdict.refuse:
        raise ValueError(f"{verdict.message} ({verdict.regle})")

    # D9 — le moteur ne devine pas qu'une carte est une énergie : il reçoit sa fiche et la valide.
    definition = definition_energie_depuis_dict(action.params.get("definition"))

    carte_id = action.params.get("carte_main")
    if not isinstance(carte_id, str) or not carte_id:
        raise ValueError(
            "« carte_main » (instance_id de l'énergie dans la main) est requis (R-5.4)."
        )
    cible_id = action.params.get("cible")
    if not isinstance(cible_id, str) or not cible_id:
        raise ValueError(
            "« cible » (identité du Pokémon qui reçoit l'énergie) est requise (R-5.4)."
        )

    index = _index_joueur(etat, jid)
    joueur = etat.joueurs[index]
    loc = _localiser_pokemon(joueur, cible_id)
    if loc is None:
        raise ValueError(
            f"Aucun Pokémon de « {jid} » n'a l'identité « {cible_id} » pour recevoir l'énergie "
            "(R-5.4)."
        )

    carte, reste_main = _retirer_de_main(joueur, carte_id)
    zone, i = loc
    cible_pk = joueur.actif if zone == ZONE_ACTIF else joueur.banc[i]
    assert cible_pk is not None  # garanti par _localiser_pokemon
    attache = replace(cible_pk, energies=cible_pk.energies + (carte,))
    if zone == ZONE_ACTIF:
        joueur = replace(joueur, main=reste_main, actif=attache)
    else:
        banc = list(joueur.banc)
        banc[i] = attache
        joueur = replace(joueur, main=reste_main, banc=tuple(banc))

    etat2 = _remplacer_joueur(etat, index, joueur)
    etat2 = replace(etat2, tour=marquer_energie_posee(etat2.tour))  # R-5.4
    evt = Evenement(
        EVT_ENERGIE_ATTACHEE,
        {
            "joueur": jid,
            "energie": carte.instance_id,
            "ref": carte.ref,
            "cible": cible_id,
            "fournit": dict(definition.fournit),
        },
    )
    return etat2, [evt]


# Enregistrement dans le REGISTRE des transitions (voir l'en-tête du module).
REGISTRE[ACTION_ATTACHER_ENERGIE] = _attacher_energie


__all__ = ["ZONE_ACTIF", "ZONE_BANC"]
