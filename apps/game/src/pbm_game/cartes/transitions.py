"""Transitions **poser** et **évoluer** — un Pokémon entre en jeu, ou sa pile grandit (R-7, R-5.3).

Module **pur** (aucune E/S), comme tout ``pbm_game``. Il enregistre ses deux transitions dans le
``REGISTRE`` du journal (``REGISTRE[ACTION_POSER] = …``), en bas du module, exactement comme
``banc`` et ``checkup`` : le noyau des transitions ne peut pas le faire lui-même (cycle d'import),
donc ``pbm_game`` importe ``cartes`` à son chargement pour garantir l'enregistrement.

**Le moteur ne devine aucune caractéristique (D9).** Les actions portent la ``definition`` de la
carte (un :class:`~pbm_game.cartes.modele.DefinitionCarte`, fourni par le service depuis le
catalogue et transporté par le journal) — le moteur la valide (marqueur de règle, stade, chaîne
d'évolution) et refuse bruyamment une fiche incohérente.

Règles servies (``docs/jeu/REGLES.md``) :

* **R-5.3** — poser / faire évoluer sont des coups de la **phase principale** du joueur actif ;
* **R-3.2 / R-8.1** — le banc contient au plus 5 Pokémon ;
* **R-7.1** — l'évolution se pose sur son prédécesseur imprimé et **conserve** énergies, Outil et
  compteurs de dégâts ;
* **R-7.2 / R-11.9** — l'évolution **retire** tous les états spéciaux (via la porte partagée
  :func:`pbm_game.etats.soigner_etats_speciaux`) ;
* **R-6.5 / R-7.3 / R-7.4** — pas d'évolution au premier tour, ni d'un Pokémon entré en jeu ce
  tour, ni deux fois le même tour (gardées par :func:`pbm_game.tour.contraintes.peut_evoluer`).
"""

from __future__ import annotations

from dataclasses import replace

from ..etats.matrice import soigner_etats_speciaux
from ..journal.modele import (
    ACTION_EVOLUER,
    ACTION_POSER,
    EVT_EVOLUTION,
    EVT_POKEMON_POSE,
    Action,
    Evenement,
)
from ..journal.transitions import REGISTRE
from ..state.modele import (
    PHASE_PRINCIPALE,
    Carte,
    EtatPartie,
    Joueur,
    PokemonEnJeu,
)
from ..tour.drapeaux import identite_pokemon, marquer_entree_en_jeu, marquer_evolution
from .modele import STADE_BASE, STADES_EVOLUTION, definition_depuis_dict

#: Les deux zones où un Pokémon peut arriver en jeu. ``banc`` est la pose ordinaire (R-5.3) ;
#: ``actif`` est le **cas particulier** d'un Pokémon qui entre directement comme Actif (place
#: vide) — p. ex. par un effet ou à la mise en place.
ZONE_BANC = "banc"
ZONE_ACTIF = "actif"

#: Capacité du banc (R-3.2 / R-8.1).
BANC_MAX = 5


def _index_joueur(etat: EtatPartie, jid: str) -> int:
    for i, joueur in enumerate(etat.joueurs):
        if joueur.id == jid:
            return i
    raise ValueError(f"Joueur « {jid} » absent de la partie.")


def _remplacer_joueur(etat: EtatPartie, index: int, joueur: Joueur) -> EtatPartie:
    joueurs = list(etat.joueurs)
    joueurs[index] = joueur
    return replace(etat, joueurs=(joueurs[0], joueurs[1]))


def _retirer_de_main(joueur: Joueur, instance_id: str) -> tuple[Carte, tuple[Carte, ...]]:
    """La carte ``instance_id`` de la main de ``joueur`` et la main sans elle, ou lève (R-5.3)."""
    for i, carte in enumerate(joueur.main):
        if carte.instance_id == instance_id:
            return carte, joueur.main[:i] + joueur.main[i + 1 :]
    raise ValueError(
        f"Carte « {instance_id} » absente de la main de « {joueur.id} » : on ne pose / ne fait "
        "évoluer qu'une carte de sa propre main (R-5.3)."
    )


def _localiser_pokemon(joueur: Joueur, base_id: str) -> tuple[str, int] | None:
    """Localise le Pokémon d'identité ``base_id`` (``("actif", -1)`` / ``("banc", i)``), ou None."""
    if joueur.actif is not None and identite_pokemon(joueur.actif) == base_id:
        return (ZONE_ACTIF, -1)
    for i, pokemon in enumerate(joueur.banc):
        if identite_pokemon(pokemon) == base_id:
            return (ZONE_BANC, i)
    return None


def _garde_phase_principale(etat: EtatPartie, jid: str, verbe: str) -> None:
    """Poser / évoluer sont des coups de la **phase principale** du joueur actif (R-5.3)."""
    if jid != etat.tour.joueur_actif:
        raise ValueError(
            f"Seul le joueur actif peut {verbe} ; le tour est à "
            f"« {etat.tour.joueur_actif} » (R-5.3)."
        )
    if etat.tour.phase != PHASE_PRINCIPALE:
        raise ValueError(
            f"« {verbe} » se joue en phase principale (phase : {etat.tour.phase!r}, R-5.3)."
        )


def _poser(etat: EtatPartie, action: Action, rng: object) -> tuple[EtatPartie, list[Evenement]]:
    """Pose un Pokémon de **base** de la main vers le banc (ou directement comme Actif, R-5.3).

    ``params`` : ``carte_main`` (``instance_id`` de la carte dans la main), ``definition`` (la
    fiche catalogue de la carte, stade **base**), ``zone`` (``banc`` par défaut, ``actif`` pour
    le cas particulier d'une entrée directe en Actif sur une place vide). Le Pokémon posé est
    noté « entré en jeu ce tour » (R-7.3) : il ne pourra pas évoluer ce tour-ci.
    """
    jid = action.auteur
    index = _index_joueur(etat, jid)
    _garde_phase_principale(etat, jid, "poser un Pokémon")

    definition = definition_depuis_dict(action.params.get("definition"))
    if definition.stade != STADE_BASE:
        raise ValueError(
            f"« {definition.nom} » (stade {definition.stade}) ne se pose pas directement : une "
            "évolution entre en jeu par « evoluer » (R-7.1, D9)."
        )

    carte_id = action.params.get("carte_main")
    if not isinstance(carte_id, str) or not carte_id:
        raise ValueError(
            "« carte_main » (instance_id de la carte dans la main) est requis (R-5.3)."
        )

    joueur = etat.joueurs[index]
    carte, reste_main = _retirer_de_main(joueur, carte_id)
    nouveau = PokemonEnJeu(cartes=(carte,))
    base_id = carte.instance_id

    zone = action.params.get("zone", ZONE_BANC)
    if zone == ZONE_BANC:
        if len(joueur.banc) >= BANC_MAX:
            raise ValueError(
                f"Le banc de « {jid} » est plein ({BANC_MAX} Pokémon) : aucune pose de plus "
                "(R-3.2/R-8.1)."
            )
        joueur = replace(joueur, main=reste_main, banc=joueur.banc + (nouveau,))
    elif zone == ZONE_ACTIF:
        # Cas particulier (R-3.3) : un Pokémon de base entre DIRECTEMENT comme Actif, uniquement
        # si la place est vide. On ne remplace jamais un Actif présent par une pose.
        if joueur.actif is not None:
            raise ValueError(
                "Un Pokémon Actif est déjà en place : une pose ne le remplace pas (R-3.3)."
            )
        joueur = replace(joueur, main=reste_main, actif=nouveau)
    else:
        raise ValueError(
            f"Zone de pose inconnue : {zone!r} — « banc » ou « actif » (jamais devinée, D9)."
        )

    etat2 = _remplacer_joueur(etat, index, joueur)
    etat2 = replace(etat2, tour=marquer_entree_en_jeu(etat2.tour, base_id))
    evt = Evenement(
        EVT_POKEMON_POSE,
        {"joueur": jid, "pokemon": base_id, "zone": zone, "ref": carte.ref},
    )
    return etat2, [evt]


def _evoluer(etat: EtatPartie, action: Action, rng: object) -> tuple[EtatPartie, list[Evenement]]:
    """Fait **évoluer** un Pokémon en jeu : la carte d'évolution de la main coiffe sa pile (R-7.1).

    ``params`` : ``base`` (identité stable du Pokémon à faire évoluer), ``carte_main``
    (``instance_id`` de la carte d'évolution dans la main), ``definition`` (sa fiche catalogue,
    stade 1 ou 2), ``nom_base`` (le **nom** catalogue de la carte au sommet de la cible, pour
    vérifier la chaîne d'évolution R-7.1). Conserve énergies, Outil et compteurs de dégâts
    (R-7.1), **retire** tous les états spéciaux (R-7.2/R-11.9), marque l'évolution du tour (R-7.4).
    """
    # Import local : ``peut_evoluer`` tire ``pbm_game.actions`` (Verdict). On l'importe au moment
    # de l'appel pour ne créer aucun cycle à l'import de ``cartes`` par ``pbm_game`` (même motif
    # que ``journal.transitions`` pour ``etats.attaque``).
    from ..tour.contraintes import peut_evoluer

    jid = action.auteur
    index = _index_joueur(etat, jid)
    _garde_phase_principale(etat, jid, "faire évoluer")

    definition = definition_depuis_dict(action.params.get("definition"))
    if definition.stade not in STADES_EVOLUTION:
        raise ValueError(
            f"« {definition.nom} » n'est pas une carte d'évolution (stade {definition.stade}) : "
            "elle ne fait évoluer aucun Pokémon (R-7.1)."
        )

    base_id = action.params.get("base")
    if not isinstance(base_id, str) or not base_id:
        raise ValueError("« base » (identité du Pokémon à faire évoluer) est requis (R-7.1).")

    joueur = etat.joueurs[index]
    cible = _localiser_pokemon(joueur, base_id)
    if cible is None:
        raise ValueError(
            f"Aucun Pokémon de « {jid} » n'a l'identité « {base_id} » à faire évoluer (R-7.1)."
        )

    # R-6.5 / R-7.3 / R-7.4 — gardes de tour (le serveur tient les règles) : un refus cite sa règle.
    verdict = peut_evoluer(etat.tour, base_id)
    if verdict.refuse:
        raise ValueError(f"{verdict.message} ({verdict.regle})")

    # Chaîne d'évolution (R-7.1) : l'évolution se pose sur SON prédécesseur imprimé, pas un autre.
    nom_base = action.params.get("nom_base")
    if not isinstance(nom_base, str) or not nom_base:
        raise ValueError(
            "« nom_base » (nom catalogue du Pokémon au sommet de la cible) est requis pour "
            "vérifier la chaîne d'évolution (R-7.1)."
        )
    if definition.evolue_depuis != nom_base:
        raise ValueError(
            f"« {definition.nom} » évolue de « {definition.evolue_depuis} », pas de « {nom_base} » "
            ": évolution sur le mauvais Pokémon (R-7.1)."
        )

    carte_id = action.params.get("carte_main")
    if not isinstance(carte_id, str) or not carte_id:
        raise ValueError(
            "« carte_main » (instance_id de la carte d'évolution dans la main) est requis."
        )
    carte, reste_main = _retirer_de_main(joueur, carte_id)

    zone, i = cible
    pokemon = joueur.actif if zone == ZONE_ACTIF else joueur.banc[i]
    etats_soignes = sorted(pokemon.etats_speciaux)
    # R-7.1 : la pile grandit, le reste est conservé (énergies, Outil, compteurs). R-7.2/R-11.9 :
    # les états spéciaux sont retirés — par la porte PARTAGÉE avec le passage au banc et les soins.
    evolue = soigner_etats_speciaux(replace(pokemon, cartes=pokemon.cartes + (carte,)))
    if zone == ZONE_ACTIF:
        joueur = replace(joueur, main=reste_main, actif=evolue)
    else:
        banc = list(joueur.banc)
        banc[i] = evolue
        joueur = replace(joueur, main=reste_main, banc=tuple(banc))

    etat2 = _remplacer_joueur(etat, index, joueur)
    etat2 = replace(etat2, tour=marquer_evolution(etat2.tour, base_id))
    evt = Evenement(
        EVT_EVOLUTION,
        {
            "joueur": jid,
            "base": base_id,
            "vers": carte.ref,
            "nom": definition.nom,
            "etats_soignes": etats_soignes,
        },
    )
    return etat2, [evt]


# Enregistrement dans le REGISTRE des transitions (voir l'en-tête du module) : ``appliquer``
# reconnaît désormais « poser » et « evoluer ». ``pbm_game`` importe ``cartes`` à son chargement.
REGISTRE[ACTION_POSER] = _poser
REGISTRE[ACTION_EVOLUER] = _evoluer


__all__ = ["ZONE_BANC", "ZONE_ACTIF", "BANC_MAX"]
