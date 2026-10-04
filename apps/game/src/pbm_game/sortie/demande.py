"""Enrichit une demande de décision avec les cartes à afficher (lot ``j-plateau-decisions``).

Une demande de catégorie carte (``carte`` / ``cartes`` / ``ordre``) porte, dans la vue projetée,
des ``options`` qui sont des **instance_id** nus (voir :mod:`pbm_game.state.projection`). L'écran
ne peut ni rendre, ni laisser **chercher** dans une pioche de soixante cartes, une liste
d'identifiants opaques. Ce module résout chaque option en une carte affichable (``ref``, ``nom``,
``type``), pour que le composant de décision générique montre des cartes réelles et les filtre.

Même partage des rôles que :mod:`pbm_game.sortie.indicateurs` : le moteur reste **pur** — il ne lit
jamais le catalogue (D9). Les noms et les types entrent en **données**, résolus du catalogue par
l'adaptateur API (:mod:`pbm_api.games.indicateurs`). Ici, on ne fait que **mapper** un instance_id
sur sa ``ref`` (lue dans l'état), puis sur ces données.

**Anti-fuite.** On n'enrichit que les ``options`` que la projection a **déjà choisi d'exposer** :
une demande à ensemble caché (``ensemble_cache``) ne porte pas ``options`` mais ``options_nombre``
— il n'y a alors rien à enrichir, et aucune identité ne fuit. On ne révèle jamais une carte que la
projection n'a pas déjà révélée au destinataire.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from ..state.modele import Carte, EtatPartie


def _cartes_etat(etat: EtatPartie) -> Iterable[Carte]:
    """Toutes les cartes de l'état, zone par zone — pour résoudre un instance_id en ``ref``.

    On parcourt **toutes** les zones (y compris pioche, main et récompenses, cachées côté client) :
    le mappage instance_id → ref ne sert qu'aux options que la projection a **déjà** exposées au
    destinataire, donc parcourir l'état complet ici ne révèle rien de plus (voir l'en-tête).
    """
    for joueur in etat.joueurs:
        yield from joueur.pioche
        yield from joueur.main
        yield from joueur.defausse
        yield from joueur.recompenses
        yield from joueur.zone_perdue
        pokemons = ((joueur.actif,) if joueur.actif is not None else ()) + joueur.banc
        for pokemon in pokemons:
            yield from pokemon.cartes
            yield from pokemon.energies
            if pokemon.outil is not None:
                yield pokemon.outil
    if etat.stade is not None:
        yield etat.stade


def refs_demande(etat: EtatPartie) -> set[str]:
    """Les ``ref`` catalogue des cartes désignées par les options de la demande en cours.

    Vide s'il n'y a pas de demande, ou si ses options ne désignent **aucune** carte de l'état (une
    demande de **type** ou **oui/non**, dont les options sont des libellés, pas des cartes). Sert à
    l'adaptateur API pour charger du catalogue **aussi** les cartes d'une zone cachée que l'on fait
    fouiller (la pioche) — que :func:`refs_en_jeu` ne relève pas, puisqu'elle s'en tient au visible.
    """
    if etat.resolution is None:
        return set()
    options = set(etat.resolution.demande.options)
    if not options:
        return set()
    return {c.ref for c in _cartes_etat(etat) if c.instance_id in options}


def enrichir_demande(
    vue: dict,
    etat: EtatPartie,
    *,
    noms: Mapping[str, str],
    types: Mapping[str, str | None],
) -> dict:
    """Ajoute à ``vue["demande"]`` la liste ``options_cartes`` (une carte affichable par option).

    ``vue`` est le dict projeté (muté **en place**) ; ``etat`` l'état non projeté d'où se lit la
    ``ref`` de chaque carte. Pour chaque id d'``options`` qui **désigne une carte** de l'état, on
    produit ``{"id", "ref", "nom", "type"}`` — dans l'**ordre** des options (il compte pour la
    catégorie « ordre »). Un nom absent du catalogue retombe sur la ``ref`` (jamais inventé :
    l'écran montre au moins de quoi distinguer la carte). Les options qui ne désignent aucune carte
    (type, oui/non) sont **laissées telles quelles** : l'écran les rend selon la catégorie.

    Ne fait rien si la vue ne porte pas de demande, ou si la demande n'expose pas d'``options``
    (ensemble caché : seul ``options_nombre`` est présent — rien à enrichir, aucune fuite).
    """
    demande = vue.get("demande")
    if not isinstance(demande, dict):
        return vue
    options = demande.get("options")
    if not isinstance(options, list) or not options:
        return vue
    ref_par_id = {c.instance_id: c.ref for c in _cartes_etat(etat)}
    cartes: list[dict] = []
    for oid in options:
        ref = ref_par_id.get(oid)
        if ref is None:
            continue  # option qui n'est pas une carte (type, oui/non) : pas de descripteur
        cartes.append(
            {"id": oid, "ref": ref, "nom": noms.get(ref, ref), "type": types.get(ref)}
        )
    if cartes:
        demande["options_cartes"] = cartes
    return vue


__all__ = ["refs_demande", "enrichir_demande"]
