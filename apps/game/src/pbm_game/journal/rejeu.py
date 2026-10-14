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

:func:`rejouer` et :func:`reprendre` ne rendent que l'état **final** : elles répondent à la
question « où en est la partie ». Le **replay** (lot ``j-replay``) en pose une autre — « par
où est-elle passée » — et c'est :func:`etapes` qui y répond : la suite des :class:`Etape`,
un rang par coup, chacune portant l'état à ce point, le coup qui y a mené et ses événements.
Mêmes contrôles d'empreinte, au coup près : un replay ne se sert jamais d'un état douteux.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from ..rng import Rng
from ..state.modele import EtatPartie
from .empreinte import empreinte
from .modele import Entree, Evenement, Instantane, Partie
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


def _pas(
    etat: EtatPartie, entree: Entree, rng: Rng, *, verifier_evenements: bool
) -> tuple[EtatPartie, tuple[Evenement, ...]]:
    """Un pas de rejeu contrôlé : ``(etat_après, evenements_recalculés)``.

    Le cœur commun de :func:`rejouer`, :func:`compacter` et :func:`etapes` — chacune a besoin
    du même contrôle au coup près, mais seule :func:`etapes` a besoin des événements, d'où le
    couple en retour.
    """
    etat2, evenements = appliquer(etat, entree.action, rng)
    empr = empreinte(etat2)
    if empr != entree.empreinte:
        raise RejeuDivergent(entree.numero, "empreinte d'état", entree.empreinte, empr)
    if verifier_evenements and evenements != entree.evenements:
        raise RejeuDivergent(entree.numero, "événements", entree.evenements, evenements)
    return etat2, evenements


def _appliquer_et_verifier(
    etat: EtatPartie, entree: Entree, rng: Rng, *, verifier_evenements: bool
) -> EtatPartie:
    """Applique l'action de ``entree`` et vérifie empreinte (et événements) au coup près."""
    etat2, _ = _pas(etat, entree, rng, verifier_evenements=verifier_evenements)
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


def _verifier_instantane(instantane: Instantane) -> None:
    """Contrôle qu'un instantané est cohérent avec lui-même (son empreinte contre son état).

    Un instantané est un **cache** : on ne le croit pas sur parole. Toute reprise — reprise de
    partie comme replay — passe par ce contrôle avant de rejouer quoi que ce soit.
    """
    empr_instantane = empreinte(instantane.etat)
    if empr_instantane != instantane.empreinte:
        raise RejeuDivergent(
            instantane.numero_entrees,
            "empreinte d'instantané",
            instantane.empreinte,
            empr_instantane,
        )


def reprendre(
    instantane: Instantane, queue: tuple[Entree, ...], *, verifier_evenements: bool = True
) -> tuple[EtatPartie, Rng]:
    """Reprend depuis un instantané + la ``queue`` des entrées postérieures.

    ``queue`` doit être exactement ``partie.entrees[instantane.numero_entrees:]``. On
    revérifie d'abord la cohérence de l'instantané (son empreinte contre son état), puis on
    ne rejoue que la queue. Le résultat est identique au rejeu complet.
    """
    _verifier_instantane(instantane)
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


# --- Replay : la suite des états, pas seulement le dernier (lot ``j-replay``) ------------


@dataclass(frozen=True)
class Etape:
    """Un **rang** du replay : où en était la partie à ce point, et par quel coup on y est venu.

    * ``rang`` — combien d'entrées du journal ont été appliquées pour arriver là. Le rang 0 est
      l'état d'avant tout coup ; une partie de *n* coups a donc *n+1* rangs (0..n) ;
    * ``entree`` — l'entrée du journal qui a mené à ce rang, ``None`` au rang de départ (aucun
      coup ne mène à l'état initial) ;
    * ``etat`` — l'état **après** ce coup ;
    * ``evenements`` — ce que le moteur a produit à ce coup, **recalculé** (pas recopié du
      journal) : c'est précisément ce qui a été comparé à l'entrée. Vide au rang de départ ;
    * ``empreinte`` — l'empreinte de ``etat``, recalculée elle aussi.

    ``Etape`` est une donnée de **lecture** : elle ne sert jamais à rejouer un coup (le journal
    reste la source de vérité), seulement à montrer un état déjà joué et vérifié.
    """

    rang: int
    entree: Entree | None
    etat: EtatPartie
    evenements: tuple[Evenement, ...]
    empreinte: str


def etapes(
    instantane: Instantane,
    queue: tuple[Entree, ...],
    *,
    verifier_evenements: bool = True,
) -> Iterator[Etape]:
    """Égrène les :class:`Etape` depuis un instantané et la ``queue`` des entrées postérieures.

    Rend d'abord le rang de l'instantané (``entree=None``), puis un rang par entrée de la queue.
    C'est le même rejeu contrôlé que :func:`reprendre` — empreinte de l'instantané d'abord, puis
    empreinte (et événements) de **chaque** coup — mais il **rend** chaque état au lieu de ne
    garder que le dernier : c'est ce dont le replay a besoin pour avancer et reculer.

    **Paresseux** : les contrôles ont lieu au fil de l'itération, donc une divergence lève au
    moment où l'on atteint le coup fautif. Un appelant qui ne consomme qu'un début de partie
    (pagination) ne paie, et ne vérifie, que ce début — et c'est ce qui permet de servir une
    partie de quatre cents coups sans la rejouer entièrement à chaque page.
    """
    _verifier_instantane(instantane)
    etat = instantane.etat
    rng = Rng.depuis_etat(instantane.rng_etat)
    rang = instantane.numero_entrees
    yield Etape(
        rang=rang, entree=None, etat=etat, evenements=(), empreinte=instantane.empreinte
    )
    for entree in queue:
        etat, evenements = _pas(etat, entree, rng, verifier_evenements=verifier_evenements)
        rang += 1
        yield Etape(
            rang=rang,
            entree=entree,
            etat=etat,
            evenements=evenements,
            empreinte=entree.empreinte,
        )


def etapes_partie(partie: Partie, *, verifier_evenements: bool = True) -> Iterator[Etape]:
    """Comme :func:`etapes`, mais depuis le début de ``partie`` (rangs 0..*n*).

    Le chemin de référence des tests : il n'emprunte **aucun** instantané persisté, donc ce
    qu'il rend ne dépend que de l'état initial, de la graine et du journal — les trois seules
    choses qu'on stocke. Comparer ses empreintes à celles du journal, c'est comparer le replay
    à la partie réellement jouée.
    """
    return etapes(
        compacter(partie, 0), partie.entrees, verifier_evenements=verifier_evenements
    )
