"""``pbm_game.sortie`` — le **point de sortie unique** vers un client. Lot ``j-autorite-vues``.

**Le serveur fait autorité, et il n'a qu'une porte de sortie.** Tout ce qui part vers un client —
l'état projeté *et* les événements diffusés — passe par :func:`projeter`. Pas de filtrage « par
route » qu'une route oubliée trahirait : une seule fonction, en amont de l'API comme du canal temps
réel (lot ``j-temps-reel``), au-delà de laquelle aucune donnée brute de partie ne circule.

Elle compose les trois briques du lot :

* :func:`~pbm_game.state.projection.vue` — l'état réduit à ce que le joueur a le droit de voir
  (mains adverses et pioches en nombre seulement, etc.) ;
* les **jetons opaques** (:mod:`.jetons`) — les cartes cachées que le client doit pouvoir désigner
  (ses récompenses face cachée) sont exposées par des jetons, pas par leur ``instance_id`` ;
* la **projection des événements** (:mod:`.evenements`) — chaque événement est redécrit pour son
  destinataire, et un type non projeté est refusé plutôt que diffusé brut.

Le paquet reste **pur** (aucune E/S) : le :class:`~pbm_game.sortie.jetons.Jetonneur` lui est fourni
par l'appelant, qui dérive son secret de la graine et son époque du journal du Rng.
"""

from __future__ import annotations

from ..journal.modele import Evenement
from ..state.modele import EtatPartie
from ..state.projection import vue
from .demande import enrichir_demande, refs_demande
from .evenements import PROJECTEURS, projeter_evenement
from .indicateurs import enrichir_indicateurs, refs_en_jeu
from .jetons import Jetonneur, secret_jetons

__all__ = [
    "Jetonneur",
    "secret_jetons",
    "projeter_evenement",
    "PROJECTEURS",
    "vue",
    "projeter",
    "enrichir_indicateurs",
    "refs_en_jeu",
    "enrichir_demande",
    "refs_demande",
]


def _jetons_recompenses(etat: EtatPartie, pour: str, jetonneur: Jetonneur) -> list[str]:
    """Les jetons opaques des récompenses **du joueur ``pour``**, dans l'ordre des emplacements.

    Les récompenses sont face cachée (R-13) : leur identité reste secrète même pour leur
    propriétaire, mais il doit pouvoir **désigner** laquelle prendre après un K.O. On lui donne
    donc un jeton par emplacement — opaque (aucune identité) et qui change à chaque mélange du deck
    (non-corrélable). L'ordre des emplacements est public ; seul le contenu est caché.
    """
    joueur = next(j for j in etat.joueurs if j.id == pour)
    return [jetonneur.jeton(c.instance_id) for c in joueur.recompenses]


def projeter(
    etat: EtatPartie,
    evenements: tuple[Evenement, ...] = (),
    *,
    pour: str,
    jetonneur: Jetonneur | None = None,
) -> dict:
    """La **seule** sérialisation de partie destinée à un client : l'état projeté + les événements.

    Renvoie ``{"vue": <état projeté>, "evenements": [<événement projeté>, ...]}``, entièrement
    JSON-natif. ``pour`` est l'identifiant du joueur destinataire ; :func:`vue` lève si ce n'est
    pas un joueur de la partie (on ne projette jamais une vue « par défaut »).

    Quand un ``jetonneur`` est fourni, la vue du destinataire gagne ``recompenses_jetons`` : un
    jeton opaque par emplacement de récompense (voir :func:`_jetons_recompenses`). Sans jetonneur,
    la vue reste purement en nombres — un appelant qui n'a pas besoin de désigner de carte cachée
    (un bot, un test d'invariant) n'a pas à en fabriquer un.
    """
    v = vue(etat, pour)
    if jetonneur is not None:
        moi = next(j for j in v["joueurs"] if j["id"] == pour)
        moi["recompenses_jetons"] = _jetons_recompenses(etat, pour, jetonneur)
    evts = [
        {"type": e.type, "donnees": dict(e.donnees)}
        for e in (projeter_evenement(evt, pour=pour, jetonneur=jetonneur) for evt in evenements)
    ]
    return {"vue": v, "evenements": evts}
