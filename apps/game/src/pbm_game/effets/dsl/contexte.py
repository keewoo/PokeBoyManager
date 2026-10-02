"""Le **contexte** d'exécution d'un effet DSL — qui le joue, sur qui, avec quelles métadonnées.

Module **pur** (aucune E/S). Un script d'effet est générique (« soignez 1 de **vos** Pokémon ») :
le contexte dit *de qui* parle « vos », *qui* est l'adversaire, et — pour un effet d'attaque —
*quel* Pokémon porte l'effet et *lequel* défend. Il porte aussi les **métadonnées de catalogue**
dont un sélecteur filtré a besoin, parce que l'état d'une partie ne connaît pas la catégorie ni le
stade d'une carte (seule sa ``ref`` et son ``instance_id`` ; le reste vit au catalogue, D9).

Tout y est en valeurs **JSON natives** (ou des :class:`~pbm_game.effets.pile.SourceEffet`,
sérialisables) : le contexte voyage avec un effet suspendu et se reprend après un F5.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..pile import SourceEffet
from .vocabulaire import PROPRIO_ADVERSAIRE, PROPRIO_LES_DEUX, PROPRIO_MOI


@dataclass(frozen=True)
class ContexteEffet:
    """Le cadre dans lequel un script s'exécute.

    * ``source`` — la carte **responsable** (:class:`~pbm_game.effets.pile.SourceEffet`), pour que
      le journal nomme « à cause de X » ;
    * ``joueur`` — l'identifiant du joueur qui **joue** l'effet (ce que « moi / vos » désigne) ;
    * ``adversaire`` — l'identifiant de l'autre joueur ;
    * ``acteur_actif`` — ``instance_id`` du Pokémon qui porte l'effet (l'attaquant, pour une
      attaque), ou ``None`` (effet de Dresseur sans Pokémon source) ;
    * ``defenseur`` — ``instance_id`` du Pokémon Défenseur (pour un effet d'attaque), ou ``None`` ;
    * ``metadonnees`` — ``{ref: {"categorie", "stade", "type"}}`` fourni par le service depuis le
      catalogue, pour les sélecteurs **filtrés**. Une ``ref`` absente = la carte n'est **pas**
      retenue par un filtre (on ne devine pas une catégorie, D9) — l'absence de cible est alors
      journalisée par la primitive, jamais avalée.
    """

    source: SourceEffet
    joueur: str
    adversaire: str
    acteur_actif: str | None = None
    defenseur: str | None = None
    metadonnees: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.joueur or not self.adversaire:
            raise ValueError("Un contexte d'effet doit nommer le joueur et son adversaire.")
        if self.joueur == self.adversaire:
            raise ValueError("Le joueur et son adversaire ne peuvent pas être le même.")

    def ids_proprietaire(self, proprietaire: str) -> tuple[str, ...]:
        """Les identifiants de joueur visés par ``moi`` / ``adversaire`` / ``les_deux``."""
        if proprietaire == PROPRIO_MOI:
            return (self.joueur,)
        if proprietaire == PROPRIO_ADVERSAIRE:
            return (self.adversaire,)
        if proprietaire == PROPRIO_LES_DEUX:
            return (self.joueur, self.adversaire)
        raise ValueError(f"Propriétaire inconnu : {proprietaire!r}.")


__all__ = ["ContexteEffet"]
