"""Projection par joueur : ``vue(etat, joueur)`` — ce qu'un joueur a le droit de savoir.

**Le serveur fait autorité.** Un client ne doit jamais apprendre la main de l'adversaire
ni l'ordre de la pioche. Cette projection est la frontière : elle produit une structure
JSON-sérialisable d'où **toute information cachée est retirée**, pas masquée après coup.

Règle de ce qui est visible, pour le joueur ``demandeur`` :

================  ====================================  ============================
Zone              Pour soi                              Pour l'adversaire
================  ====================================  ============================
main              identités visibles                    **nombre seulement**
pioche            **nombre seulement** (jamais l'ordre) **nombre seulement**
récompenses       **nombre seulement** (face cachée)    **nombre seulement**
défausse          publique (identités)                  publique (identités)
zone perdue       publique (identités)                  publique (identités)
Actif / banc      public (identités)                    public (identités)
Stade             public                                public
================  ====================================  ============================

L'ordre de la pioche n'est **jamais** exposé — pour aucun joueur, pas même son
propriétaire (anti-triche). Une zone cachée est réduite à un **entier** : aucun
``instance_id`` ni ``ref`` caché ne survit dans la structure produite — c'est
vérifiable en la parcourant (test de non-fuite).
"""

from __future__ import annotations

from .modele import Carte, EtatPartie, Joueur, PokemonEnJeu


def _carte_publique(carte: Carte) -> dict:
    return {"instance_id": carte.instance_id, "ref": carte.ref}


def _pokemon_public(pokemon: PokemonEnJeu) -> dict:
    """Un Pokémon en jeu est **entièrement public** (R-3.6) : les deux joueurs le voient."""
    return {
        "cartes": [_carte_publique(c) for c in pokemon.cartes],
        "energies": [_carte_publique(c) for c in pokemon.energies],
        "outil": _carte_publique(pokemon.outil) if pokemon.outil is not None else None,
        "compteurs_degats": pokemon.compteurs_degats,
        "etats_speciaux": sorted(pokemon.etats_speciaux),
    }


def _joueur_vu(joueur: Joueur, *, cest_soi: bool) -> dict:
    """La vue d'un joueur, selon qu'on le regarde soi-même ou l'adversaire."""
    vue: dict = {
        "id": joueur.id,
        # Zones publiques (face visible), identiques pour les deux regards.
        "actif": _pokemon_public(joueur.actif) if joueur.actif is not None else None,
        "banc": [_pokemon_public(p) for p in joueur.banc],
        "defausse": [_carte_publique(c) for c in joueur.defausse],
        "zone_perdue": [_carte_publique(c) for c in joueur.zone_perdue],
        # Zones cachées : réduites à un NOMBRE, jamais le contenu (ni soi, ni adverse,
        # pour l'ordre de la pioche et les récompenses).
        "pioche_nombre": len(joueur.pioche),
        "recompenses_nombre": len(joueur.recompenses),
    }
    if cest_soi:
        # Sa propre main est visible. (Pas sa pioche ni ses récompenses : face cachée.)
        vue["main"] = [_carte_publique(c) for c in joueur.main]
    else:
        # Main adverse : nombre seulement, jamais les identités.
        vue["main_nombre"] = len(joueur.main)
    return vue


def vue(etat: EtatPartie, joueur: str) -> dict:
    """Ce que le joueur ``joueur`` a le droit de savoir de l'état ``etat``.

    ``joueur`` est l'identifiant d'un des deux joueurs. Lève ``ValueError`` s'il ne
    participe pas à la partie — on ne projette jamais une vue « par défaut » (pas de
    repli silencieux).
    """
    ids = {j.id for j in etat.joueurs}
    if joueur not in ids:
        raise ValueError(f"« {joueur} » ne participe pas à cette partie ({sorted(ids)}).")
    return {
        "schema_version": etat.schema_version,
        "pour": joueur,
        "joueurs": [_joueur_vu(j, cest_soi=(j.id == joueur)) for j in etat.joueurs],
        "tour": {
            "joueur_actif": etat.tour.joueur_actif,
            "numero": etat.tour.numero,
            "phase": etat.tour.phase,
            "energie_posee": etat.tour.energie_posee,
            "supporter_joue": etat.tour.supporter_joue,
            "retraite_faite": etat.tour.retraite_faite,
        },
        "stade": _carte_publique(etat.stade) if etat.stade is not None else None,
        "stade_proprietaire": etat.stade_proprietaire,
        "terminee": etat.terminee,
        "vainqueur": etat.vainqueur,
        "raison_fin": etat.raison_fin,
    }
