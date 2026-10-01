"""Sérialisation **versionnée** du journal : ``*_vers_json`` / ``*_depuis_json``.

Pure : produit et lit des structures Python natives (``dict``/``list``/``str``/``int``/
``bool``/``None``) directement sérialisables par ``json`` — mais ne fait elle-même
**aucune** entrée/sortie (pas de ``json.dumps`` ni de fichier). L'appelant sérialise.

Garantie de round-trip : pour toute partie (ou instantané) valide,
``partie_depuis_json(partie_vers_json(p)) == p``. Une forme malformée ou une
``journal_version`` inconnue est **refusée** (``ValueError``), jamais repliée sur un
journal partiel : relire à moitié un journal, c'est fabriquer une partie qui n'a jamais
existé.
"""

from __future__ import annotations

from ..state.serialisation import depuis_json as etat_depuis_json
from ..state.serialisation import vers_json as etat_vers_json
from .modele import (
    JOURNAL_VERSION,
    Action,
    Entree,
    Evenement,
    Instantane,
    Partie,
)


def _dict(donnees: object, quoi: str) -> dict:
    if not isinstance(donnees, dict):
        raise ValueError(f"{quoi} : mapping attendu, reçu {type(donnees).__name__}.")
    return donnees


def _chaine(donnees: dict, cle: str, quoi: str, *, autorise_vide: bool = False) -> str:
    valeur = donnees.get(cle)
    if not isinstance(valeur, str) or (not valeur and not autorise_vide):
        raise ValueError(f"{quoi} : « {cle} » manquant ou invalide (chaîne attendue).")
    return valeur


def _entier(donnees: dict, cle: str, quoi: str) -> int:
    valeur = donnees.get(cle)
    if not isinstance(valeur, bool) and isinstance(valeur, int):
        return valeur
    raise ValueError(f"{quoi} : « {cle} » doit être un entier.")


def _params(donnees: dict, quoi: str) -> dict:
    valeur = donnees.get("params", {})
    if not isinstance(valeur, dict):
        raise ValueError(f"{quoi} : « params » doit être un mapping.")
    return valeur


# --- Action ------------------------------------------------------------------


def action_vers_json(action: Action) -> dict:
    """Projette une :class:`Action` en ``dict`` JSON-sérialisable."""
    return {"type": action.type, "auteur": action.auteur, "params": dict(action.params)}


def action_depuis_json(donnees: object) -> Action:
    """Relit un ``dict`` produit par :func:`action_vers_json` (ou lève ``ValueError``)."""
    d = _dict(donnees, "Action")
    return Action(
        type=_chaine(d, "type", "Action"),
        auteur=_chaine(d, "auteur", "Action"),
        params=_params(d, "Action"),
    )


# --- Événement ---------------------------------------------------------------


def evenement_vers_json(evenement: Evenement) -> dict:
    """Projette un :class:`Evenement` en ``dict`` JSON-sérialisable."""
    return {"type": evenement.type, "donnees": dict(evenement.donnees)}


def evenement_depuis_json(donnees: object) -> Evenement:
    """Relit un ``dict`` produit par :func:`evenement_vers_json` (ou lève ``ValueError``)."""
    d = _dict(donnees, "Événement")
    donnees_evt = d.get("donnees", {})
    if not isinstance(donnees_evt, dict):
        raise ValueError("Événement : « donnees » doit être un mapping.")
    return Evenement(type=_chaine(d, "type", "Événement"), donnees=donnees_evt)


# --- Entrée ------------------------------------------------------------------


def entree_vers_json(entree: Entree) -> dict:
    """Projette une :class:`Entree` en ``dict`` JSON-sérialisable."""
    return {
        "numero": entree.numero,
        "auteur": entree.auteur,
        "action": action_vers_json(entree.action),
        "evenements": [evenement_vers_json(e) for e in entree.evenements],
        "horodatage": entree.horodatage,
        "empreinte": entree.empreinte,
    }


def entree_depuis_json(donnees: object) -> Entree:
    """Relit un ``dict`` produit par :func:`entree_vers_json` (ou lève ``ValueError``)."""
    d = _dict(donnees, "Entrée")
    numero = _entier(d, "numero", "Entrée")
    if numero < 0:
        raise ValueError(f"Entrée : « numero » négatif ({numero}).")
    evenements_bruts = d.get("evenements", [])
    if not isinstance(evenements_bruts, list):
        raise ValueError("Entrée : « evenements » doit être une liste.")
    return Entree(
        numero=numero,
        auteur=_chaine(d, "auteur", "Entrée"),
        action=action_depuis_json(d.get("action")),
        evenements=tuple(evenement_depuis_json(e) for e in evenements_bruts),
        horodatage=_chaine(d, "horodatage", "Entrée"),
        empreinte=_chaine(d, "empreinte", "Entrée"),
    )


# --- Partie ------------------------------------------------------------------


def _verifier_version(d: dict, quoi: str) -> int:
    version = d.get("journal_version")
    if version != JOURNAL_VERSION:
        raise ValueError(
            f"{quoi} : journal_version inconnue {version!r} "
            f"(ce moteur lit la version {JOURNAL_VERSION})."
        )
    return version


def partie_vers_json(partie: Partie) -> dict:
    """Projette une :class:`Partie` en ``dict`` JSON-sérialisable et versionné."""
    return {
        "journal_version": partie.journal_version,
        "etat_initial": etat_vers_json(partie.etat_initial),
        "graine": partie.graine,
        "entrees": [entree_vers_json(e) for e in partie.entrees],
    }


def partie_depuis_json(donnees: object) -> Partie:
    """Relit un ``dict`` produit par :func:`partie_vers_json` (ou lève ``ValueError``).

    Refuse une ``journal_version`` inconnue : un journal d'une version future ne se relit
    pas « au mieux », il se refuse.
    """
    d = _dict(donnees, "Partie")
    version = _verifier_version(d, "Partie")
    entrees_brutes = d.get("entrees", [])
    if not isinstance(entrees_brutes, list):
        raise ValueError("Partie : « entrees » doit être une liste.")
    return Partie(
        etat_initial=etat_depuis_json(d.get("etat_initial")),
        graine=_chaine(d, "graine", "Partie"),
        entrees=tuple(entree_depuis_json(e) for e in entrees_brutes),
        journal_version=version,
    )


# --- Instantané --------------------------------------------------------------


def instantane_vers_json(instantane: Instantane) -> dict:
    """Projette un :class:`Instantane` en ``dict`` JSON-sérialisable et versionné."""
    return {
        "journal_version": instantane.journal_version,
        "numero_entrees": instantane.numero_entrees,
        "etat": etat_vers_json(instantane.etat),
        "rng_etat": instantane.rng_etat,
        "empreinte": instantane.empreinte,
    }


def instantane_depuis_json(donnees: object) -> Instantane:
    """Relit un ``dict`` produit par :func:`instantane_vers_json` (ou lève ``ValueError``)."""
    d = _dict(donnees, "Instantané")
    version = _verifier_version(d, "Instantané")
    numero = _entier(d, "numero_entrees", "Instantané")
    if numero < 0:
        raise ValueError(f"Instantané : « numero_entrees » négatif ({numero}).")
    rng_etat = d.get("rng_etat")
    if not isinstance(rng_etat, dict):
        raise ValueError("Instantané : « rng_etat » doit être un mapping (état du Rng).")
    return Instantane(
        numero_entrees=numero,
        etat=etat_depuis_json(d.get("etat")),
        rng_etat=rng_etat,
        empreinte=_chaine(d, "empreinte", "Instantané"),
        journal_version=version,
    )
