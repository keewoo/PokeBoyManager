"""Vérification du **coût d'une attaque** (R-9.1, R-9.2) — en verdict motivé.

Module **pur** (aucune E/S). Il répond à une seule question : *l'Actif porte-t-il de quoi
payer cette attaque ?* — et, s'il ne la porte pas, **pourquoi** (règle citée), jamais un
refus muet (pas de repli silencieux).

**Ce que le moteur reçoit.** Les ``Carte`` d'énergie attachées à un Pokémon ne portent, au
jalon J1, aucune donnée de type (le catalogue, câblé par ``j-cartes-pokemon``, la fournira).
La vérification travaille donc sur des **fournitures** déjà extraites : pour chaque énergie
attachée, ce qu'elle **fournit** — un mapping ``{type: unités}``. Exemples :

* une Énergie Feu de base → ``{"feu": 1}`` ;
* une Double Énergie Incolore → ``{"incolore": 2}`` (R-9.2 : une énergie peut fournir
  plusieurs unités) ;
* une énergie spéciale bi-type → ``{"feu": 1, "eau": 1}``.

**Règle de paiement (R-9.2).** Le coût demande « **au moins** » l'énergie requise : de
l'énergie en trop ne gêne pas. Un symbole **coloré** d'un type se paie par **une unité de ce
type exact** ; un symbole **incolore** (★) se paie par **n'importe quelle** unité. On paie
donc d'abord les symboles colorés (ils n'acceptent que leur type), puis les incolores avec
ce qui reste : c'est optimal, puisque l'incolore accepte tout ce que le coloré a laissé.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence

from ..actions.modele import ACCORD, Verdict, refus
from .modele import CoutAttaque


def pool_energies(fournitures: Sequence[Mapping[str, int]]) -> Counter[str]:
    """Agrège les fournitures de chaque énergie en un **pool** ``{type: unités totales}``.

    Lève ``ValueError`` si une fourniture est malformée (type vide, unités négatives ou non
    entières) : une énergie dont on ne sait pas ce qu'elle fournit est une panne, jamais un
    zéro silencieux.
    """
    pool: Counter[str] = Counter()
    for i, fourniture in enumerate(fournitures):
        if not isinstance(fourniture, Mapping):
            raise ValueError(f"Fourniture d'énergie #{i} : attendu un mapping {{type: unités}}.")
        for t, n in fourniture.items():
            if not isinstance(t, str) or not t:
                raise ValueError(f"Fourniture d'énergie #{i} : type invalide {t!r}.")
            if not isinstance(n, int) or isinstance(n, bool) or n < 0:
                raise ValueError(
                    f"Fourniture d'énergie #{i} : unités invalides pour « {t} » : {n!r} "
                    "(entier ≥ 0)."
                )
            pool[t] += n
    return pool


def cout_satisfait(cout: CoutAttaque, fournitures: Sequence[Mapping[str, int]]) -> Verdict:
    """L'énergie ``fournitures`` paie-t-elle ``cout`` (R-9.2) ? Accord, ou refus motivé.

    Renvoie :data:`~pbm_game.actions.ACCORD` si le coût est satisfait, sinon un refus citant
    **R-9.2** et nommant ce qui manque. Un coût vide est toujours satisfait (attaque gratuite).
    """
    pool = pool_energies(fournitures)

    # (1) Symboles COLORÉS : chacun n'accepte que son type exact (R-9.2).
    manquants: dict[str, int] = {}
    for type_requis, besoin in cout.types.items():
        disponible = pool.get(type_requis, 0)
        if disponible < besoin:
            manquants[type_requis] = besoin - disponible
            pool[type_requis] = 0
        else:
            pool[type_requis] = disponible - besoin
    if manquants:
        detail = ", ".join(f"{n} « {t} »" for t, n in sorted(manquants.items()))
        return refus(
            "R-9.2",
            f"Coût non satisfait : il manque {detail} (l'Actif doit porter au moins "
            "l'énergie colorée requise, R-9.2).",
        )

    # (2) Symboles INCOLORES : payés par n'importe quelle unité restante (R-9.2).
    restant = sum(pool.values())
    if restant < cout.incolore:
        return refus(
            "R-9.2",
            f"Coût incolore non satisfait : {cout.incolore} symbole(s) incolore(s) requis, "
            f"{restant} unité(s) d'énergie restante(s) pour les payer (R-9.2).",
        )
    return ACCORD


__all__ = ["pool_energies", "cout_satisfait"]
