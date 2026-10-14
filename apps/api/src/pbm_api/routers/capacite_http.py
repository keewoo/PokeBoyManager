"""La traduction HTTP d'un **refus de capacité**, écrite une fois pour les trois portes du jeu.

Trois routes peuvent créer une partie — entraînement, lancement d'une invitation, revanche — et
c'est précisément le genre d'endroit où trois copies divergent : l'une renvoie 503, l'autre 429,
la troisième oublie ``Retry-After``, et l'écran du joueur se met à dire trois choses différentes de
la même panne. Le critère du lot ``j-charge-temps-reel`` est « un refus **clair** » : il est donc
produit ici, et nulle part ailleurs.

Pourquoi **503** et pas 429 : il n'y a aucun quota attaché au joueur. C'est la machine qui est
pleine, et le même joueur passera sans rien changer dès qu'une place se libère. 429 dirait « tu
demandes trop », ce qui serait faux et renverrait le joueur vers un problème qui n'est pas le sien.
"""

from __future__ import annotations

from fastapi import HTTPException, status

from pbm_api.games.capacite import RETRY_APRES_SECONDES
from pbm_api.games.errors import PlafondPartiesAtteint


def erreur_capacite(exc: PlafondPartiesAtteint) -> HTTPException:
    """L'exception HTTP à lever pour un plafond atteint : 503, message en clair, ``Retry-After``.

    Le message de :class:`PlafondPartiesAtteint` est repris tel quel : il dit le nombre de parties
    tenues, le plafond, et que les parties en cours ne sont pas ralenties — ce que le joueur a
    besoin de savoir pour ne pas croire à une panne. ``Retry-After`` donne au client de quoi
    réessayer sans que chacun invente son propre délai.
    """
    return HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        str(exc),
        headers={"Retry-After": str(RETRY_APRES_SECONDES)},
    )


__all__ = ["erreur_capacite"]
