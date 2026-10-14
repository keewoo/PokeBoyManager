"""Routes du **confort de jeu** (``/jeu/confort``) — lot ``j-accessibilite-jeu``.

Deux routes, et rien d'autre : ``GET|PATCH /jeu/confort/reglages`` — mes animations, ma taille de
texte, le temps rallongé (DJ4) et mon décor d'arène (lot ``j-arene-decors``).

Comme toute route du jeu, elles sont gardées par
:func:`~pbm_api.auth.dependencies.require_game_access` (D11) : un compte sans accès au jeu reçoit un
**404**, pas un 403.

Le routeur ne décide rien : le vocabulaire et le facteur de temps vivent dans
:mod:`pbm_api.jeu.confort` (pur), la persistance dans :mod:`pbm_api.jeu.confort_service`, et
l'application du temps rallongé au lancement dans :mod:`pbm_api.games.service`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.auth.dependencies import require_csrf, require_game_access
from pbm_api.db import get_session
from pbm_api.jeu import confort_service as service
from pbm_api.jeu.confort import (
    ANIMATIONS,
    FACTEUR_TEMPS_RALLONGE,
    TAILLES_TEXTE,
    ReglagesConfort,
)
from pbm_api.jeu.decors import DECORS
from pbm_api.models import User

router = APIRouter(prefix="/jeu/confort", tags=["jeu-confort"])


class ConfortOut(BaseModel):
    """Mes réglages de confort, plus le vocabulaire et le facteur que le produit **impose**.

    ``animations_possibles`` et ``tailles_possibles`` donnent le vocabulaire complet pour que
    l'écran liste les choix sans les coder en dur ; ``facteur_temps_rallonge`` dit de combien les
    horloges sont multipliées — un joueur qui active « j'ai besoin de plus de temps » mérite de lire
    le chiffre plutôt que de le deviner.
    """

    animations: str
    taille_texte: str
    temps_rallonge: bool
    #: Décor d'arène choisi, ou ``None`` pour le thème automatique selon le deck joué.
    decor: str | None
    animations_possibles: list[str]
    tailles_possibles: list[str]
    #: Les décors proposés, **dans l'ordre d'affichage** (du plus neutre au plus marqué) — c'est
    #: pourquoi cette liste n'est pas triée alphabétiquement comme les deux précédentes.
    decors_possibles: list[str]
    facteur_temps_rallonge: float

    @classmethod
    def de(cls, reglages: ReglagesConfort) -> ConfortOut:
        """Construit la sortie depuis la vue pure des réglages."""
        return cls(
            animations=reglages.animations,
            taille_texte=reglages.taille_texte,
            temps_rallonge=reglages.temps_rallonge,
            decor=reglages.decor,
            animations_possibles=sorted(ANIMATIONS),
            tailles_possibles=sorted(TAILLES_TEXTE),
            decors_possibles=list(DECORS),
            facteur_temps_rallonge=FACTEUR_TEMPS_RALLONGE,
        )


class ConfortIn(BaseModel):
    """Modification **partielle** : seuls les champs fournis changent.

    C'est ce qui permet à l'écran de couper les animations sans renvoyer la taille du texte — donc
    sans écraser un réglage changé entre-temps dans un autre onglet.
    """

    animations: str | None = Field(
        default=None, description="« completes » ou « reduites » (aucune animation rendue)."
    )
    taille_texte: str | None = Field(
        default=None, description="« normale », « grande » ou « tres_grande »."
    )
    temps_rallonge: bool | None = Field(
        default=None,
        description="Double les horloges des parties lancées ensuite (DJ4). Jamais rétroactif.",
    )
    decor: str | None = Field(
        default=None,
        description=(
            "Clé du décor d'arène, ou `null` explicite pour revenir au thème automatique selon "
            "le deck. Champ absent = réglage inchangé."
        ),
    )


@router.get("/reglages", response_model=ConfortOut)
async def lire_reglages(
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_game_access),
) -> ConfortOut:
    """Mes réglages de confort — les défauts si je n'y ai jamais touché."""
    return ConfortOut.de(await service.charger_reglages(db, current_user.id))


@router.patch("/reglages", response_model=ConfortOut)
async def modifier_reglages(
    corps: ConfortIn,
    current_user: Annotated[User, Depends(require_game_access)],
    _csrf: Annotated[None, Depends(require_csrf)],
    db: AsyncSession = Depends(get_session),
) -> ConfortOut:
    """Modifie mes réglages (partiellement) et rend l'état complet qui en résulte.

    ``temps_rallonge`` ne touche **aucune partie en cours** : une partie fige ses horloges à sa
    création. Le changement vaut pour les parties lancées ensuite — l'écran le dit au joueur.
    """
    try:
        reglages = await service.enregistrer_reglages(
            db,
            current_user.id,
            animations=corps.animations,
            taille_texte=corps.taille_texte,
            temps_rallonge=corps.temps_rallonge,
            decor=corps.decor,
            # `null` veut dire « reviens au thème automatique » pour ce champ, et pas « ne touche
            # à rien » : seule la présence de la clé dans le corps distingue les deux.
            decor_fourni="decor" in corps.model_fields_set,
        )
    except service.ConfortValeurInvalide as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    await db.commit()
    return ConfortOut.de(reglages)
