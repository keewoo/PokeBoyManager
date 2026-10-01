"""Vue de débogage : rendre une entrée de journal **lisible par un humain sans outil**.

Pure, sans E/S. Le moteur ne connaît pas le catalogue (il est pur) : les **noms** de
cartes sont fournis par l'appelant, une table ``instance_id -> nom``. La vue résout les
identifiants de cartes qui apparaissent dans l'action et les événements, pour qu'une
entrée se lise « *alice pioche Dracaufeu, Pikachu* » plutôt que « *p-7, p-12* ».

Un identifiant **absent** de la table n'est pas masqué (pas de repli silencieux) : il est
rendu explicitement ``«id» (nom inconnu)``, pour qu'un trou dans la table se voie au lieu
de se confondre avec une carte nommée.
"""

from __future__ import annotations

from collections.abc import Mapping

from .modele import (
    EVT_CARTES_PIOCHEES,
    EVT_ECHANGE_FORCE,
    EVT_PARTIE_TERMINEE,
    EVT_PHASE_AVANCEE,
    EVT_PIOCHE_MELANGEE,
    EVT_PROMOTION,
    EVT_RETRAITE,
    EVT_TOUR_COMMENCE,
    Entree,
    Evenement,
)

# Clés de ``donnees``/``params`` qui portent des identifiants de carte à résoudre.
_CLE_ID_UNIQUE = "instance_id"
_CLE_IDS_LISTE = "instance_ids"


def resoudre_id(instance_id: str, noms: Mapping[str, str]) -> str:
    """Rend un ``instance_id`` lisible via ``noms`` ; un id inconnu est signalé, pas masqué."""
    nom = noms.get(instance_id)
    if nom is None:
        return f"«{instance_id}» (nom inconnu)"
    return f"{nom} [{instance_id}]"


def _decrire_evenement(evenement: Evenement, noms: Mapping[str, str]) -> str:
    d = evenement.donnees
    if evenement.type == EVT_CARTES_PIOCHEES:
        ids = d.get(_CLE_IDS_LISTE, [])
        cartes = ", ".join(resoudre_id(i, noms) for i in ids) or "(aucune)"
        return f"{d.get('joueur', '?')} pioche {d.get('nombre', len(ids))} : {cartes}"
    if evenement.type == EVT_PIOCHE_MELANGEE:
        return f"{d.get('joueur', '?')} mélange sa pioche ({d.get('taille', '?')} cartes)"
    if evenement.type == EVT_PHASE_AVANCEE:
        return (
            f"phase {d.get('de', '?')} → {d.get('vers', '?')} "
            f"(tour {d.get('numero', '?')}, actif {d.get('joueur_actif', '?')})"
        )
    if evenement.type == EVT_TOUR_COMMENCE:
        return f"tour {d.get('numero', '?')} commence (actif {d.get('joueur_actif', '?')})"
    if evenement.type == EVT_PARTIE_TERMINEE:
        raison = d.get("raison", "?")
        vainqueur = d.get("vainqueur")
        issue = f"vainqueur {vainqueur}" if vainqueur is not None else "égalité"
        par = d.get("abandon_par")
        suffixe = f", abandon de {par}" if par is not None else ""
        return f"partie terminée ({issue}, raison {raison}{suffixe})"
    if evenement.type == EVT_RETRAITE:
        energies = d.get("energies_defaussees", [])
        cartes = ", ".join(resoudre_id(i, noms) for i in energies) or "(aucune)"
        return (
            f"{d.get('joueur', '?')} bat en retraite "
            f"{resoudre_id(d.get('ancien_actif', '?'), noms)} → "
            f"{resoudre_id(d.get('nouvel_actif', '?'), noms)} "
            f"(coût {d.get('cout', '?')}, défausse {cartes})"
        )
    if evenement.type == EVT_PROMOTION:
        return (
            f"{d.get('joueur', '?')} promeut "
            f"{resoudre_id(d.get('nouvel_actif', '?'), noms)} comme Actif"
        )
    if evenement.type == EVT_ECHANGE_FORCE:
        return (
            f"{d.get('joueur', '?')} subit un échange forcé "
            f"{resoudre_id(d.get('ancien_actif', '?'), noms)} → "
            f"{resoudre_id(d.get('nouvel_actif', '?'), noms)}"
        )
    # Événement d'un lot ultérieur, non encore gré ici : on le rend brut plutôt que de
    # prétendre le comprendre (pas d'approximation).
    return f"{evenement.type} {dict(d)}"


def decrire_entree(entree: Entree, noms: Mapping[str, str]) -> str:
    """Une ligne lisible décrivant l'entrée, identifiants de cartes résolus en noms.

    Forme : ``#<n> [<horodatage>] <auteur> · <action> → <événements>``. L'empreinte n'y
    figure pas (c'est du contrôle, pas de la lecture) ; elle reste dans l'entrée.
    """
    params = dict(entree.action.params)
    detail_params = f"({params})" if params else ""
    evenements = (
        " ; ".join(_decrire_evenement(e, noms) for e in entree.evenements)
        if entree.evenements
        else "(aucun événement)"
    )
    return (
        f"#{entree.numero} [{entree.horodatage}] {entree.auteur} · "
        f"{entree.action.type}{detail_params} → {evenements}"
    )


def decrire_journal(entrees: tuple[Entree, ...], noms: Mapping[str, str]) -> list[str]:
    """La liste des lignes lisibles d'un journal, une par entrée, dans l'ordre."""
    return [decrire_entree(e, noms) for e in entrees]
