"""Routes des **emotes en jeu** (``/jeu/emotes``) — lot ``j-echanges-emotes``, décision DJ10.

Deux choses, et volontairement rien d'autre :

* ``GET /jeu/emotes/catalogue`` — les dix emotes que le serveur accepte, avec leur phrase. L'écran
  en a sa propre copie (pour n'attendre aucun réseau au moment d'ouvrir la palette), tenue en
  parité par un test ; cette route reste la **référence**, et c'est elle qu'on interroge pour
  savoir ce que le serveur accepte réellement ;
* ``GET|PATCH /jeu/emotes/reglages`` — « j'échange des emotes », oui ou non. C'est le seul réglage,
  et le seul octet que les emotes écrivent en base.

**Il n'existe aucune route pour envoyer une emote**, et ce n'est pas un oubli : une emote ne passe
que par le canal temps réel (``WS /games/{id}/ws``, message ``emote``), parce qu'elle n'a de sens
que si l'adversaire est là pour la voir. Pas de route HTTP veut dire pas de file d'attente, pas de
rattrapage, pas de stockage — donc rien à conserver au-delà de la partie (critère du lot). En
connexion dégradée (repli en interrogation), l'écran annonce que les emotes demandent la connexion
directe plutôt que de faire semblant.

Comme toute route du jeu, elles sont gardées par
:func:`~pbm_api.auth.dependencies.require_game_access` (D11). Le réglage est **borné au compte de la
session** : il n'y a aucun identifiant d'objet dans ces chemins, donc aucun moyen de lire ou
d'écrire le réglage d'un autre compte — un test d'accès croisé le vérifie plutôt que de le supposer.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.auth.dependencies import require_csrf, require_game_access
from pbm_api.db import get_session
from pbm_api.games import emotes_service as service
from pbm_api.games.emotes import (
    CATALOGUE,
    FENETRE_SECONDES,
    INTERVALLE_MIN_SECONDES,
    MAX_PAR_FENETRE,
    ReglagesEmotes,
)
from pbm_api.models import User

router = APIRouter(prefix="/jeu/emotes", tags=["jeu-emotes"])


class EmoteOut(BaseModel):
    """Une emote du catalogue, telle que l'écran l'affiche : code, phrase, pictogramme."""

    code: str
    phrase: str
    pictogramme: str


class CatalogueOut(BaseModel):
    """Le catalogue fermé, **plus** les limites de débit que le serveur applique.

    Publier le débit n'est pas un détail d'implémentation qui fuit : c'est ce qui permet à l'écran
    de griser la palette avant le refus, donc au joueur de comprendre le rythme au lieu de le
    découvrir par une erreur.
    """

    emotes: list[EmoteOut]
    max_par_fenetre: int
    fenetre_secondes: float
    intervalle_min_secondes: float


class ReglagesOut(BaseModel):
    """Mon réglage d'emotes. ``recevoir_emotes`` vaut pour les **deux sens** (voir
    :class:`pbm_api.games.emotes.ReglagesEmotes`)."""

    recevoir_emotes: bool

    @classmethod
    def de(cls, reglages: ReglagesEmotes) -> ReglagesOut:
        """Construit la sortie depuis la vue pure du réglage."""
        return cls(recevoir_emotes=reglages.recevoir_emotes)


class ReglagesIn(BaseModel):
    """Modification **partielle** : seuls les champs fournis changent (comme ``/jeu/rendu``)."""

    recevoir_emotes: bool | None = None


@router.get("/catalogue", response_model=CatalogueOut)
async def lire_catalogue(
    _current_user: Annotated[User, Depends(require_game_access)],
) -> CatalogueOut:
    """Les emotes que le serveur accepte, et le débit qu'il applique."""
    return CatalogueOut(
        emotes=[
            EmoteOut(code=e.code, phrase=e.phrase, pictogramme=e.pictogramme) for e in CATALOGUE
        ],
        max_par_fenetre=MAX_PAR_FENETRE,
        fenetre_secondes=FENETRE_SECONDES,
        intervalle_min_secondes=INTERVALLE_MIN_SECONDES,
    )


@router.get("/reglages", response_model=ReglagesOut)
async def lire_reglages(
    current_user: Annotated[User, Depends(require_game_access)],
    db: AsyncSession = Depends(get_session),
) -> ReglagesOut:
    """Mon réglage d'emotes — le défaut DJ10 (« j'échange ») si je n'y ai jamais touché."""
    return ReglagesOut.de(await service.charger_reglages(db, current_user.id))


@router.patch("/reglages", response_model=ReglagesOut)
async def modifier_reglages(
    corps: ReglagesIn,
    current_user: Annotated[User, Depends(require_game_access)],
    _csrf: Annotated[None, Depends(require_csrf)],
    db: AsyncSession = Depends(get_session),
) -> ReglagesOut:
    """Coupe ou rétablit mes emotes, et rend l'état complet qui en résulte.

    L'effet est **immédiat** : la diffusion relit ce réglage à chaque emote
    (:func:`pbm_api.games.emotes_service.comptes_ayant_coupe`), donc la prochaine emote de
    l'adversaire ne m'atteint déjà plus — sans rouvrir la partie ni rafraîchir la page. Et il est
    **mémorisé** : la ligne persiste, les parties suivantes la suivent.
    """
    reglages = await service.enregistrer_reglages(
        db, current_user.id, recevoir_emotes=corps.recevoir_emotes
    )
    await db.commit()
    return ReglagesOut.de(reglages)
