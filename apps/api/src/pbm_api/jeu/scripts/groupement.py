"""La **mesure du regroupement** : combien de scripts écrire, et combien le partage en économise.

Module **pur** (il travaille sur des cartes déjà chargées, aucune E/S). Il répond au critère n°2 du
lot : *« le regroupement par texte identique réduit mesurablement le nombre de scripts à écrire »*.

Le compte est simple, et honnête. La voie **naïve** écrirait un script par couple (carte, effet) :
c'est ``effets_total``. La voie **groupée** n'écrit qu'un script par **texte d'effet distinct** :
c'est ``textes_distincts``. La différence est ce que le partage économise — publiée en clair dans le
compte rendu, jamais arrondie pour flatter.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from pbm_api.jeu.scripts.empreinte import effets_scriptables


@dataclass(frozen=True)
class MesureGroupement:
    """Le résultat chiffré du regroupement, tel qu'il part dans le compte rendu.

    * ``cartes_examinees`` — toutes les cartes passées à la mesure ;
    * ``cartes_porteuses`` — celles qui portent au moins un effet scriptable ;
    * ``effets_total`` — le nombre de couples (carte, effet) : ce qu'écrirait la voie naïve ;
    * ``textes_distincts`` — le nombre de textes d'effet distincts : ce qu'écrit la voie groupée ;
    * ``scripts_economises`` — ``effets_total − textes_distincts`` ;
    * ``reduction_pct`` — la part économisée, en % de ``effets_total`` (``0`` si aucun effet).
    """

    cartes_examinees: int
    cartes_porteuses: int
    effets_total: int
    textes_distincts: int
    scripts_economises: int
    reduction_pct: float


def mesurer_groupement(cartes: Iterable[object]) -> MesureGroupement:
    """Mesure le regroupement sur un ensemble de cartes du catalogue.

    Parcourt chaque carte, en extrait les effets scriptables (dé-dupliqués *dans* la carte par
    :func:`~pbm_api.jeu.scripts.empreinte.effets_scriptables`), et compte les empreintes distinctes
    sur l'**ensemble**. Déterministe et sans E/S : le même jeu de cartes donne toujours le même
    chiffre.
    """
    cartes_examinees = 0
    cartes_porteuses = 0
    effets_total = 0
    empreintes: set[str] = set()
    for card in cartes:
        cartes_examinees += 1
        effets = effets_scriptables(card)
        if effets:
            cartes_porteuses += 1
        effets_total += len(effets)
        empreintes.update(e.empreinte for e in effets)
    textes_distincts = len(empreintes)
    economises = effets_total - textes_distincts
    reduction = (economises / effets_total * 100.0) if effets_total else 0.0
    return MesureGroupement(
        cartes_examinees=cartes_examinees,
        cartes_porteuses=cartes_porteuses,
        effets_total=effets_total,
        textes_distincts=textes_distincts,
        scripts_economises=economises,
        reduction_pct=round(reduction, 2),
    )


__all__ = ["MesureGroupement", "mesurer_groupement"]
