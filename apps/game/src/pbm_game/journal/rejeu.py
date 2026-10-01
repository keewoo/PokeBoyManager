"""Rejeu et compaction : reconstruire l'état d'une partie depuis son journal.

Pur, sans E/S. Deux garanties, toutes deux contrôlées **au coup près** :

1. **Rejeu fidèle** — :func:`rejouer` repart de l'état initial sous la graine et applique
   chaque action du journal ; à chaque coup, l'empreinte de l'état recalculé doit égaler
   l'empreinte enregistrée dans l'entrée, et les événements recalculés doivent égaler ceux
   enregistrés. Un écart lève :class:`RejeuDivergent` **sur le coup fautif** — pas à la
   fin de la partie.
2. **Compaction** — rejouer 400 coups à chaque reconnexion est inutile : :func:`compacter`
   fige un **instantané** (état + état du Rng) après *k* coups, et :func:`reprendre` ne
   rejoue que la **queue** des entrées postérieures. Le résultat est, par construction,
   identique au rejeu complet — c'est un critère d'acceptation du lot.

L'instantané est un **cache** : la source de vérité reste le journal. On ne le croit pas
sur parole — :func:`reprendre` revérifie d'abord que son empreinte correspond à son état.
"""

from __future__ import annotations

from ..rng import Rng
from ..state.modele import EtatPartie
from .empreinte import empreinte
from .modele import Entree, Instantane, Partie
from .transitions import appliquer


class RejeuDivergent(Exception):
    """Levée quand le rejeu diverge du journal — jamais tue en silence.

    Porte le ``numero`` du coup fautif, ce qui ``quoi`` divergeait (empreinte d'état,
    événements, empreinte d'instantané), l'``attendu`` (du journal) et l'``obtenu``
    (recalculé).
    """

    def __init__(self, numero: int, quoi: str, attendu: object, obtenu: object) -> None:
        self.numero = numero
        self.quoi = quoi
        self.attendu = attendu
        self.obtenu = obtenu
        super().__init__(
            f"Rejeu divergent au coup {numero} ({quoi}) : "
            f"journal={attendu!r}, recalculé={obtenu!r}."
        )


def _rng_depuis_graine(graine: str) -> Rng:
    try:
        octets = bytes.fromhex(graine)
    except ValueError as exc:
        raise ValueError(f"Graine de partie illisible (hex attendu) : {exc}.") from exc
    return Rng(octets)


def _appliquer_et_verifier(
    etat: EtatPartie, entree: Entree, rng: Rng, *, verifier_evenements: bool
) -> EtatPartie:
    """Applique l'action de ``entree`` et vérifie empreinte (et événements) au coup près."""
    etat2, evenements = appliquer(etat, entree.action, rng)
    empr = empreinte(etat2)
    if empr != entree.empreinte:
        raise RejeuDivergent(entree.numero, "empreinte d'état", entree.empreinte, empr)
    if verifier_evenements and evenements != entree.evenements:
        raise RejeuDivergent(entree.numero, "événements", entree.evenements, evenements)
    return etat2


def rejouer(partie: Partie, *, verifier_evenements: bool = True) -> tuple[EtatPartie, Rng]:
    """Rejoue tout le journal depuis l'état initial et renvoie ``(etat_final, rng_final)``.

    Vérifie l'empreinte de chaque coup (et, par défaut, ses événements). Lève
    :class:`RejeuDivergent` au premier écart, :class:`ValueError` si une action est
    inapplicable (type inconnu, demande impossible) — ce qui signale un journal corrompu
    aussi nettement qu'une divergence d'empreinte.
    """
    etat = partie.etat_initial
    rng = _rng_depuis_graine(partie.graine)
    for entree in partie.entrees:
        etat = _appliquer_et_verifier(etat, entree, rng, verifier_evenements=verifier_evenements)
    return etat, rng


def compacter(partie: Partie, jusqu_a: int) -> Instantane:
    """Fige un :class:`Instantane` de l'état après les ``jusqu_a`` premières entrées.

    ``jusqu_a`` ∈ ``[0, len(partie.entrees)]`` : 0 instantané-ise l'état initial,
    ``len`` l'état final. Le rejeu partiel vérifie les empreintes jusque-là : un
    instantané n'est jamais figé sur un état déjà divergent.
    """
    n = len(partie.entrees)
    if not isinstance(jusqu_a, int) or isinstance(jusqu_a, bool) or not (0 <= jusqu_a <= n):
        raise ValueError(f"« jusqu_a » hors bornes : {jusqu_a!r} (attendu 0..{n}).")
    etat = partie.etat_initial
    rng = _rng_depuis_graine(partie.graine)
    for entree in partie.entrees[:jusqu_a]:
        etat = _appliquer_et_verifier(etat, entree, rng, verifier_evenements=True)
    return Instantane(
        numero_entrees=jusqu_a,
        etat=etat,
        rng_etat=rng.etat(),
        empreinte=empreinte(etat),
    )


def reprendre(
    instantane: Instantane, queue: tuple[Entree, ...], *, verifier_evenements: bool = True
) -> tuple[EtatPartie, Rng]:
    """Reprend depuis un instantané + la ``queue`` des entrées postérieures.

    ``queue`` doit être exactement ``partie.entrees[instantane.numero_entrees:]``. On
    revérifie d'abord la cohérence de l'instantané (son empreinte contre son état), puis on
    ne rejoue que la queue. Le résultat est identique au rejeu complet.
    """
    empr_instantane = empreinte(instantane.etat)
    if empr_instantane != instantane.empreinte:
        raise RejeuDivergent(
            instantane.numero_entrees,
            "empreinte d'instantané",
            instantane.empreinte,
            empr_instantane,
        )
    etat = instantane.etat
    rng = Rng.depuis_etat(instantane.rng_etat)
    for entree in queue:
        etat = _appliquer_et_verifier(etat, entree, rng, verifier_evenements=verifier_evenements)
    return etat, rng


def reprendre_partie(
    partie: Partie, instantane: Instantane, *, verifier_evenements: bool = True
) -> tuple[EtatPartie, Rng]:
    """Comme :func:`reprendre`, mais tranche la queue depuis ``partie`` et la contrôle.

    Refuse un instantané dont ``numero_entrees`` dépasse le journal (instantané étranger à
    cette partie) — jamais de reprise sur une queue tronquée en silence.
    """
    n = len(partie.entrees)
    if not (0 <= instantane.numero_entrees <= n):
        raise ValueError(
            f"Instantané incompatible : numero_entrees={instantane.numero_entrees}, "
            f"la partie a {n} entrée(s)."
        )
    queue = partie.entrees[instantane.numero_entrees :]
    return reprendre(instantane, queue, verifier_evenements=verifier_evenements)
