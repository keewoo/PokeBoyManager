"""Structures d'état de la **mise en place** (R-4) — dataclasses figées et sérialisables.

Module **pur**, comme tout ``pbm_game``. Il porte la **forme** de l'état transitoire d'une partie
*avant son premier tour* : combien de mulligans chaque joueur a pris (R-4.4), combien de cartes
bonus lui sont dues (R-4.5), et le placement **face caché** qu'il a choisi (R-4.2) — Actif et banc
— tant que la **révélation simultanée** n'a pas eu lieu.

La séparation public / caché est le cœur du lot : le placement d'un joueur est une **information de
jeu réelle** que l'adversaire ne doit pas apprendre avant la révélation. Il vit donc ICI, et non
dans l'Actif/banc publics de :class:`~pbm_game.state.modele.Joueur` (qui restent vides pendant la
mise en place) : la projection (:func:`pbm_game.state.projection.vue`) n'expose ce placement qu'à
son **propre** propriétaire. Le compte des mulligans et des cartes bonus, lui, est **public** — un
mulligan révèle la main (R-4.4), donc son existence n'est pas un secret.

Règles de référence structurées ici (``docs/jeu/REGLES.md``) :

* **R-4.2 / R-3.2** — un Actif de base obligatoire, au plus 5 Pokémon de base au banc ;
* **R-4.4** — comptage des mulligans ;
* **R-4.5 / R-16.9** — comptage des cartes bonus dues à l'adversaire ;
* **R-4.1 / R-3.4** — main de sept (:data:`MAIN_INITIALE`), six récompenses (:data:`RECOMPENSES`).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

#: Taille de la main d'ouverture (R-4.1).
MAIN_INITIALE = 7

#: Nombre de récompenses posées face cachée à la mise en place (R-3.4 / R-4.3).
RECOMPENSES = 6

#: Capacité du banc (R-3.2) — rappel local pour valider le placement sans importer ``cartes``.
BANC_MAX = 5


@dataclass(frozen=True)
class PlacementCache:
    """Le placement **face caché** d'un joueur à la mise en place (R-4.2) — secret jusqu'à révéler.

    * ``actif`` — ``instance_id`` du Pokémon de **base** posé comme Actif (obligatoire, R-4.2) ;
    * ``banc`` — ``instance_id`` des Pokémon de **base** posés au banc (au plus 5, R-3.2).

    Ce sont des ``instance_id`` de cartes **encore dans la main** du joueur : elles n'en sortent
    (vers l'Actif/banc publics) qu'à la révélation. L'adversaire n'en connaît ni le contenu ni le
    nombre tant que la partie n'est pas révélée (c'est la non-fuite que le lot garantit).
    """

    actif: str
    banc: tuple[str, ...] = ()


@dataclass(frozen=True)
class MiseEnPlace:
    """L'état transitoire de la mise en place, porté par ``EtatPartie.mise_en_place`` (R-4).

    Présent (non ``None``) **tant que la mise en place n'est pas révélée** ; ``None`` ensuite — la
    partie a alors commencé pour de bon. Les trois champs sont **alignés sur l'ordre des joueurs**
    de :class:`~pbm_game.state.modele.EtatPartie` (index 0 = siège 0 = joueur qui commence, R-4.7) :
    un tuple de longueur 2 plutôt qu'un ``dict`` par identifiant, pour que la sérialisation soit
    déterministe (un ``dict`` n'a pas d'ordre garanti à la relecture).

    * ``mulligans`` — nombre de mulligans pris par chaque joueur (R-4.4) ;
    * ``bonus`` — cartes bonus **dues** à chaque joueur, pour les mulligans que l'adversaire a pris
      **seul** (R-4.5 / R-16.9) ; piochées à la révélation ;
    * ``placements`` — le :class:`PlacementCache` choisi par chaque joueur, ou ``None`` tant qu'il
      n'a pas placé. La révélation n'a lieu que lorsque les **deux** sont non ``None``.
    """

    mulligans: tuple[int, int] = (0, 0)
    bonus: tuple[int, int] = (0, 0)
    placements: tuple[PlacementCache | None, PlacementCache | None] = (None, None)

    def avec_placement(self, index: int, placement: PlacementCache) -> MiseEnPlace:
        """Renvoie une copie où le joueur ``index`` (0 ou 1) a posé ``placement`` (immuable)."""
        if index not in (0, 1):
            raise ValueError(f"Index de joueur hors de [0, 1] : {index!r}.")
        places = list(self.placements)
        places[index] = placement
        return replace(self, placements=(places[0], places[1]))

    @property
    def tous_places(self) -> bool:
        """Vrai quand les **deux** joueurs ont placé : c'est la condition de la révélation (R-4)."""
        return self.placements[0] is not None and self.placements[1] is not None


def _placement_vers_json(placement: PlacementCache | None) -> dict | None:
    if placement is None:
        return None
    return {"actif": placement.actif, "banc": list(placement.banc)}


def _placement_depuis_json(donnees: object) -> PlacementCache | None:
    if donnees is None:
        return None
    if not isinstance(donnees, dict):
        raise ValueError("Un placement de mise en place doit être un mapping {actif, banc}.")
    actif = donnees.get("actif")
    if not isinstance(actif, str) or not actif:
        raise ValueError("Placement : « actif » (instance_id) manquant ou invalide (R-4.2).")
    banc = donnees.get("banc", [])
    if not isinstance(banc, list) or not all(isinstance(b, str) and b for b in banc):
        raise ValueError("Placement : « banc » doit être une liste d'instance_id (R-4.2).")
    return PlacementCache(actif=actif, banc=tuple(banc))


def _paire_entiers(donnees: object, cle: str) -> tuple[int, int]:
    brut = donnees.get(cle, [0, 0]) if isinstance(donnees, dict) else [0, 0]
    if (
        not isinstance(brut, list)
        or len(brut) != 2
        or not all(isinstance(n, int) and not isinstance(n, bool) and n >= 0 for n in brut)
    ):
        raise ValueError(f"Mise en place : « {cle} » doit être une paire d'entiers ≥ 0.")
    return (brut[0], brut[1])


def mise_en_place_vers_json(mep: MiseEnPlace) -> dict:
    """Projette une :class:`MiseEnPlace` en ``dict`` JSON-sérialisable et déterministe."""
    return {
        "mulligans": list(mep.mulligans),
        "bonus": list(mep.bonus),
        "placements": [
            _placement_vers_json(mep.placements[0]),
            _placement_vers_json(mep.placements[1]),
        ],
    }


def mise_en_place_depuis_json(donnees: object) -> MiseEnPlace:
    """Relit un ``dict`` produit par :func:`mise_en_place_vers_json`, ou lève (jamais de repli)."""
    if not isinstance(donnees, dict):
        raise ValueError("La mise en place doit être un mapping.")
    placements_brut = donnees.get("placements", [None, None])
    if not isinstance(placements_brut, list) or len(placements_brut) != 2:
        raise ValueError("Mise en place : « placements » doit être une paire (deux joueurs).")
    return MiseEnPlace(
        mulligans=_paire_entiers(donnees, "mulligans"),
        bonus=_paire_entiers(donnees, "bonus"),
        placements=(
            _placement_depuis_json(placements_brut[0]),
            _placement_depuis_json(placements_brut[1]),
        ),
    )


# Réexporté pour que ``field`` reste utilisé si une évolution future en a besoin ; sans effet ici.
__all__ = [
    "MAIN_INITIALE",
    "RECOMPENSES",
    "BANC_MAX",
    "PlacementCache",
    "MiseEnPlace",
    "mise_en_place_vers_json",
    "mise_en_place_depuis_json",
]
