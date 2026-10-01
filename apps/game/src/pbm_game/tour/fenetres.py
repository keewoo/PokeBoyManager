"""Fenêtres de déclenchement du tour — les points d'ancrage de la future pile d'effets.

Module **pur** (aucune E/S). Entre une action et la suivante, le moteur ouvre des
**fenêtres** où des effets « au début du tour » ou « à la fin du tour » (talents, Dresseurs,
états spéciaux résolus au Checkup) devront se déclencher. Ce lot (``j-machine-tour``) **câble
les fenêtres** sans y brancher aucun effet : la pile d'effets viendra plus tard (lots
``j-checkup``, ``j-degats-resolution`` et suivants) enregistrer ses déclencheurs dans
:data:`DECLENCHEURS`, exactement comme les transitions s'enregistrent dans
``pbm_game.journal.transitions.REGISTRE``.

**Une fenêtre sans déclencheur ne produit RIEN — et ce n'est pas un repli silencieux.** C'est
l'absence *réelle* d'effet à résoudre, documentée ici et vérifiée par un test. Le jour où un
effet sera enregistré, il produira ses événements par ce même chemin, sans qu'aucun appelant
n'ait à changer. En revanche, demander une fenêtre **inconnue** est une erreur franche
(``ValueError``), jamais un passage silencieux.

Règles servies : **R-5.1** (déroulé du tour : début puis attaque), **R-12.1/R-12.3/R-12.5**
(les effets « au Checkup / entre les tours » se résolvent dans la fenêtre de fin de tour).
"""

from __future__ import annotations

from collections.abc import Callable

from ..journal.modele import Evenement
from ..rng import Rng
from ..state.modele import EtatPartie

#: Fenêtre ouverte au **début du tour**, après la pioche obligatoire (R-5.1).
FENETRE_DEBUT_TOUR = "debut_tour"
#: Fenêtre ouverte à la **fin du tour**, à l'entrée du Pokémon Checkup (R-12.1).
FENETRE_FIN_TOUR = "fin_tour"
#: Fenêtre d'**expiration des effets temporaires** « jusqu'à la fin de ce tour » (R-12.5),
#: ouverte pendant le Pokémon Checkup par ``pbm_game.checkup``. Chaque déclencheur y retire
#: son marqueur et **journalise** l'expiration : un effet temporaire ne disparaît jamais en
#: silence (sinon un effet « jusqu'à la fin du tour » devient éternel sans que rien ne le dise).
#: **Vide au jalon J1** — aucun effet temporaire n'existe encore (la pile d'effets, lot
#: ``j-effets-architecture``, l'alimentera), mais la fenêtre est câblée et franchie à chaque
#: Checkup.
FENETRE_EXPIRATION_EFFETS = "expiration_effets"

#: Les fenêtres reconnues. En demander une autre est une erreur, jamais un silence.
FENETRES: frozenset[str] = frozenset(
    {FENETRE_DEBUT_TOUR, FENETRE_FIN_TOUR, FENETRE_EXPIRATION_EFFETS}
)

# Un déclencheur transforme l'état et rend les événements qu'il a produits. Il reçoit le
# Rng (certains effets tirent au sort) ; comme les transitions, il est pur côté état.
Declencheur = Callable[[EtatPartie, Rng], tuple[EtatPartie, list[Evenement]]]

#: Déclencheurs enregistrés par fenêtre. **VIDE au jalon J1** : le squelette est en place,
#: la pile d'effets le remplira. Chaque entrée reste une liste ordonnée (l'ordre de résolution
#: comptera, R-12.2/R-12.3).
DECLENCHEURS: dict[str, tuple[Declencheur, ...]] = {
    FENETRE_DEBUT_TOUR: (),
    FENETRE_FIN_TOUR: (),
    FENETRE_EXPIRATION_EFFETS: (),
}


def declencher(
    etat: EtatPartie,
    fenetre: str,
    rng: Rng,
    declencheurs: dict[str, tuple[Declencheur, ...]] | None = None,
) -> tuple[EtatPartie, list[Evenement]]:
    """Ouvre ``fenetre`` : applique ses déclencheurs dans l'ordre et renvoie ``(etat, events)``.

    Refuse une fenêtre inconnue (``ValueError`` : jamais approximée). Sans déclencheur
    enregistré, renvoie l'état inchangé et une liste d'événements vide — l'absence réelle
    d'effet, pas un repli masqué. ``declencheurs`` n'est à passer que pour les tests (injecter
    un déclencheur jouet) ; par défaut c'est :data:`DECLENCHEURS`, la source de vérité.
    """
    if fenetre not in FENETRES:
        raise ValueError(
            f"Fenêtre de déclenchement inconnue : {fenetre!r} — jamais approximée. "
            f"Fenêtres connues : {sorted(FENETRES)}."
        )
    table = DECLENCHEURS if declencheurs is None else declencheurs
    evenements: list[Evenement] = []
    for decl in table.get(fenetre, ()):
        etat, produits = decl(etat, rng)
        evenements.extend(produits)
    return etat, evenements


__all__ = [
    "FENETRE_DEBUT_TOUR",
    "FENETRE_FIN_TOUR",
    "FENETRE_EXPIRATION_EFFETS",
    "FENETRES",
    "Declencheur",
    "DECLENCHEURS",
    "declencher",
]
