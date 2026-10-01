"""Sérialisation JSON **bidirectionnelle** de l'état de partie.

Pur : produit et lit des structures Python natives (``dict``/``list``/``str``/``int``/
``bool``/``None``) directement sérialisables par ``json`` — mais ne fait lui-même
**aucune** entrée/sortie (pas de ``json.dumps`` ni de fichier). L'appelant sérialise.

Garantie centrale (rejouabilité, R de forme) : pour tout état *valide*,
``depuis_json(vers_json(etat)) == etat``. La sortie est **déterministe** — les
ensembles d'états spéciaux sont sérialisés **triés** — pour que deux états égaux
produisent le même JSON (comparaison, replay, anti-triche).
"""

from __future__ import annotations

from .modele import (
    SCHEMA_VERSION,
    Carte,
    EtatPartie,
    Joueur,
    PokemonEnJeu,
    Tour,
)


def _carte_vers(carte: Carte) -> dict:
    return {"instance_id": carte.instance_id, "ref": carte.ref}


def _carte_depuis(donnees: object) -> Carte:
    if not isinstance(donnees, dict):
        raise ValueError("Une carte doit être un mapping {instance_id, ref}.")
    instance_id = donnees.get("instance_id")
    ref = donnees.get("ref")
    if not isinstance(instance_id, str) or not instance_id:
        raise ValueError("Carte : « instance_id » manquant ou invalide.")
    if not isinstance(ref, str) or not ref:
        raise ValueError(f"Carte « {instance_id} » : « ref » manquante ou invalide.")
    return Carte(instance_id=instance_id, ref=ref)


def _pokemon_vers(pokemon: PokemonEnJeu) -> dict:
    return {
        "cartes": [_carte_vers(c) for c in pokemon.cartes],
        "energies": [_carte_vers(c) for c in pokemon.energies],
        "outil": _carte_vers(pokemon.outil) if pokemon.outil is not None else None,
        "compteurs_degats": pokemon.compteurs_degats,
        # Trié pour un JSON déterministe (un frozenset n'a pas d'ordre).
        "etats_speciaux": sorted(pokemon.etats_speciaux),
    }


def _pokemon_depuis(donnees: object) -> PokemonEnJeu:
    if not isinstance(donnees, dict):
        raise ValueError("Un Pokémon en jeu doit être un mapping.")
    cartes = donnees.get("cartes")
    if not isinstance(cartes, list) or not cartes:
        raise ValueError("Pokémon en jeu : « cartes » doit être une liste non vide (R-3.6).")
    energies = donnees.get("energies", [])
    if not isinstance(energies, list):
        raise ValueError("Pokémon en jeu : « energies » doit être une liste.")
    compteurs = donnees.get("compteurs_degats", 0)
    if not isinstance(compteurs, int) or isinstance(compteurs, bool):
        raise ValueError("Pokémon en jeu : « compteurs_degats » doit être un entier.")
    etats = donnees.get("etats_speciaux", [])
    if not isinstance(etats, list) or not all(isinstance(e, str) for e in etats):
        raise ValueError("Pokémon en jeu : « etats_speciaux » doit être une liste de chaînes.")
    outil_brut = donnees.get("outil")
    outil = _carte_depuis(outil_brut) if outil_brut is not None else None
    return PokemonEnJeu(
        cartes=tuple(_carte_depuis(c) for c in cartes),
        energies=tuple(_carte_depuis(c) for c in energies),
        outil=outil,
        compteurs_degats=compteurs,
        etats_speciaux=frozenset(etats),
    )


def _joueur_vers(joueur: Joueur) -> dict:
    return {
        "id": joueur.id,
        "pioche": [_carte_vers(c) for c in joueur.pioche],
        "main": [_carte_vers(c) for c in joueur.main],
        "actif": _pokemon_vers(joueur.actif) if joueur.actif is not None else None,
        "banc": [_pokemon_vers(p) for p in joueur.banc],
        "defausse": [_carte_vers(c) for c in joueur.defausse],
        "recompenses": [_carte_vers(c) for c in joueur.recompenses],
        "zone_perdue": [_carte_vers(c) for c in joueur.zone_perdue],
    }


def _liste_cartes(donnees: dict, cle: str) -> tuple[Carte, ...]:
    brut = donnees.get(cle, [])
    if not isinstance(brut, list):
        raise ValueError(f"Joueur : « {cle} » doit être une liste.")
    return tuple(_carte_depuis(c) for c in brut)


def _joueur_depuis(donnees: object) -> Joueur:
    if not isinstance(donnees, dict):
        raise ValueError("Un joueur doit être un mapping.")
    jid = donnees.get("id")
    if not isinstance(jid, str) or not jid:
        raise ValueError("Joueur : « id » manquant ou invalide.")
    actif_brut = donnees.get("actif")
    banc_brut = donnees.get("banc", [])
    if not isinstance(banc_brut, list):
        raise ValueError(f"Joueur « {jid} » : « banc » doit être une liste.")
    return Joueur(
        id=jid,
        pioche=_liste_cartes(donnees, "pioche"),
        main=_liste_cartes(donnees, "main"),
        actif=_pokemon_depuis(actif_brut) if actif_brut is not None else None,
        banc=tuple(_pokemon_depuis(p) for p in banc_brut),
        defausse=_liste_cartes(donnees, "defausse"),
        recompenses=_liste_cartes(donnees, "recompenses"),
        zone_perdue=_liste_cartes(donnees, "zone_perdue"),
    )


def _tour_vers(tour: Tour) -> dict:
    return {
        "joueur_actif": tour.joueur_actif,
        "numero": tour.numero,
        "phase": tour.phase,
        "energie_posee": tour.energie_posee,
        "supporter_joue": tour.supporter_joue,
        "retraite_faite": tour.retraite_faite,
        # Trié pour un JSON déterministe (un frozenset n'a pas d'ordre).
        "entres_en_jeu_ce_tour": sorted(tour.entres_en_jeu_ce_tour),
        "evolues_ce_tour": sorted(tour.evolues_ce_tour),
    }


def _tour_depuis(donnees: object) -> Tour:
    if not isinstance(donnees, dict):
        raise ValueError("Le tour doit être un mapping.")
    joueur_actif = donnees.get("joueur_actif")
    if not isinstance(joueur_actif, str) or not joueur_actif:
        raise ValueError("Tour : « joueur_actif » manquant ou invalide.")
    numero = donnees.get("numero")
    if not isinstance(numero, int) or isinstance(numero, bool):
        raise ValueError("Tour : « numero » doit être un entier.")
    phase = donnees.get("phase")
    if not isinstance(phase, str) or not phase:
        raise ValueError("Tour : « phase » manquante ou invalide.")

    def _drapeau(cle: str) -> bool:
        v = donnees.get(cle, False)
        if not isinstance(v, bool):
            raise ValueError(f"Tour : « {cle} » doit être un booléen.")
        return v

    entres = donnees.get("entres_en_jeu_ce_tour", [])
    if not isinstance(entres, list) or not all(isinstance(e, str) for e in entres):
        raise ValueError("Tour : « entres_en_jeu_ce_tour » doit être une liste de chaînes.")
    evolues = donnees.get("evolues_ce_tour", [])
    if not isinstance(evolues, list) or not all(isinstance(e, str) for e in evolues):
        raise ValueError("Tour : « evolues_ce_tour » doit être une liste de chaînes.")

    return Tour(
        joueur_actif=joueur_actif,
        numero=numero,
        phase=phase,
        energie_posee=_drapeau("energie_posee"),
        supporter_joue=_drapeau("supporter_joue"),
        retraite_faite=_drapeau("retraite_faite"),
        entres_en_jeu_ce_tour=frozenset(entres),
        evolues_ce_tour=frozenset(evolues),
    )


def vers_json(etat: EtatPartie) -> dict:
    """Projette un :class:`EtatPartie` vers un ``dict`` JSON-sérialisable et déterministe."""
    return {
        "schema_version": etat.schema_version,
        "joueurs": [_joueur_vers(etat.joueurs[0]), _joueur_vers(etat.joueurs[1])],
        "tour": _tour_vers(etat.tour),
        "stade": _carte_vers(etat.stade) if etat.stade is not None else None,
        "stade_proprietaire": etat.stade_proprietaire,
        "terminee": etat.terminee,
        "vainqueur": etat.vainqueur,
        "raison_fin": etat.raison_fin,
    }


def depuis_json(donnees: object) -> EtatPartie:
    """Relit un ``dict`` produit par :func:`vers_json` en :class:`EtatPartie`.

    Refuse une structure malformée ou une ``schema_version`` inconnue en levant
    ``ValueError`` : jamais de repli silencieux sur un état partiel.
    """
    if not isinstance(donnees, dict):
        raise ValueError("L'état doit être un mapping à la racine.")
    version = donnees.get("schema_version")
    if version != SCHEMA_VERSION:
        raise ValueError(
            f"schema_version inconnue : {version!r} (ce moteur lit la version {SCHEMA_VERSION})."
        )
    joueurs_bruts = donnees.get("joueurs")
    if not isinstance(joueurs_bruts, list) or len(joueurs_bruts) != 2:
        raise ValueError("L'état doit porter exactement deux joueurs.")
    stade_brut = donnees.get("stade")
    stade_proprietaire = donnees.get("stade_proprietaire")
    if stade_proprietaire is not None and not isinstance(stade_proprietaire, str):
        raise ValueError("« stade_proprietaire » doit être une chaîne ou None.")
    vainqueur = donnees.get("vainqueur")
    if vainqueur is not None and not isinstance(vainqueur, str):
        raise ValueError("« vainqueur » doit être une chaîne ou None.")
    raison_fin = donnees.get("raison_fin")
    if raison_fin is not None and not isinstance(raison_fin, str):
        raise ValueError("« raison_fin » doit être une chaîne ou None.")
    terminee = donnees.get("terminee", False)
    if not isinstance(terminee, bool):
        raise ValueError("« terminee » doit être un booléen.")
    return EtatPartie(
        schema_version=version,
        joueurs=(_joueur_depuis(joueurs_bruts[0]), _joueur_depuis(joueurs_bruts[1])),
        tour=_tour_depuis(donnees.get("tour")),
        stade=_carte_depuis(stade_brut) if stade_brut is not None else None,
        stade_proprietaire=stade_proprietaire,
        terminee=terminee,
        vainqueur=vainqueur,
        raison_fin=raison_fin,
    )
