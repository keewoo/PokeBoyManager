"""Routes du **rendu des cartes en jeu** (``/jeu/rendu``) — lot ``j-rendu-carte``.

Trois choses, et rien d'autre :

* ``GET|PATCH /jeu/rendu/reglages`` — mon rendu par défaut et mon veto « ne jamais montrer mes
  photos » (DJ5) ;
* ``GET /jeu/rendu/decks/{deck_id}`` — ce que **chaque carte de mon deck** montrera en jeu, et la
  raison quand ce sera l'image officielle. C'est ce que le constructeur de deck affiche au joueur,
  et c'est aussi le moment où les variantes de jeu manquantes sont produites (« à l'avance ») ;
* ``GET /jeu/rendu/parties/{game_id}/photos/{item_id}`` — la variante de jeu d'une photo, servie
  **dans le cadre d'une partie** aux deux joueurs de cette partie, si son propriétaire l'autorise.

Comme toute route du jeu, elles sont gardées par
:func:`~pbm_api.auth.dependencies.require_game_access` (D11). Et comme partout, un refus est un
**404** : « cette photo n'existe pas pour toi » plutôt que « elle existe, mais tu n'y as pas
droit » — sur une photo personnelle, l'existence est déjà une information.

Le routeur ne décide rien : la décision DJ5 vit dans :mod:`pbm_api.jeu.rendu` (pure) et les
lectures dans :mod:`pbm_api.jeu.rendu_service`.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.auth.dependencies import require_csrf, require_game_access
from pbm_api.db import get_session
from pbm_api.jeu import rendu_service as service
from pbm_api.jeu.rendu import (
    RENDU_PHOTO,
    RENDUS_REGLABLES,
    ReglagesRendu,
    preference_effective,
)
from pbm_api.jeu.rendu_image import HAUTEUR_JEU, LARGEUR_JEU
from pbm_api.models import Deck, User
from pbm_api.storage import StorageBackend, build_storage

router = APIRouter(prefix="/jeu/rendu", tags=["jeu-rendu"])

NOT_FOUND_MESSAGE = "Ressource introuvable."

# Un seul client de stockage pour le processus, comme les autres routeurs qui servent des images
# (`routers/images.py`, `routers/profile.py`) : `build_storage()` et jamais `ObjectStorage()` en
# dur, pour que le backend local des tests et de la recette soit respecté.
_storage = build_storage()


def get_storage() -> StorageBackend:
    """Le client de stockage objet du processus (surchargeable en test)."""
    return _storage


class ReglagesOut(BaseModel):
    """Mes réglages de rendu, plus ce que le produit **impose** (le vocabulaire et la taille).

    ``rendus_possibles`` donne le vocabulaire complet, pour que l'écran liste les choix sans les
    coder en dur ; ``largeur_jeu``/``hauteur_jeu`` disent la taille réelle de la variante servie —
    un joueur qui se demande si « sa » carte sera nette mérite de lire le chiffre.
    """

    rendus_possibles: list[str]
    rendu_defaut: str
    jamais_montrer_mes_photos: bool
    largeur_jeu: int
    hauteur_jeu: int

    @classmethod
    def de(cls, reglages: ReglagesRendu) -> ReglagesOut:
        """Construit la sortie depuis la vue pure des réglages."""
        return cls(
            rendus_possibles=sorted(RENDUS_REGLABLES),
            rendu_defaut=reglages.rendu_defaut,
            jamais_montrer_mes_photos=reglages.jamais_montrer_mes_photos,
            largeur_jeu=LARGEUR_JEU,
            hauteur_jeu=HAUTEUR_JEU,
        )


class ReglagesIn(BaseModel):
    """Modification **partielle** : seuls les champs fournis changent.

    C'est ce qui permet à l'écran de basculer le veto sans renvoyer le rendu par défaut — donc sans
    écraser un réglage changé entre-temps dans un autre onglet.
    """

    rendu_defaut: str | None = Field(
        default=None, description="« photo » (mes cartes photographiées) ou « officielle »."
    )
    jamais_montrer_mes_photos: bool | None = None

    @field_validator("rendu_defaut")
    @classmethod
    def _rendu_connu(cls, valeur: str | None) -> str | None:
        """Refuse un rendu hors vocabulaire : un réglage qui ne règle rien est un mensonge."""
        if valeur is None:
            return None
        if valeur not in RENDUS_REGLABLES:
            raise ValueError(f"rendu inconnu (attendus : {sorted(RENDUS_REGLABLES)})")
        return valeur


class ApercuCarteOut(BaseModel):
    """Ce qu'une carte du deck montrera en jeu, et pourquoi — une ligne du constructeur de deck."""

    card_id: uuid.UUID
    nom: str
    origine: str
    raison: str | None


class ApercuDeckOut(BaseModel):
    """L'aperçu de rendu d'un deck : son réglage, et la liste des cartes qui se replieront.

    ``cartes`` ne porte **que** les cartes dont le rendu n'est pas celui qu'on croit — celles qui
    tomberont sur l'image officielle alors que le joueur a demandé ses photos. Lister les soixante
    cartes noierait l'information utile ; ``nb_photos`` et ``nb_officielles`` donnent le compte
    complet.
    """

    rendu_effectif: str
    rendu_deck: str | None
    nb_photos: int
    nb_officielles: int
    cartes: list[ApercuCarteOut]


@router.get("/reglages", response_model=ReglagesOut)
async def lire_reglages(
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_game_access),
) -> ReglagesOut:
    """Mes réglages de rendu — les défauts DJ5 si je n'y ai jamais touché."""
    return ReglagesOut.de(await service.charger_reglages(db, current_user.id))


@router.patch("/reglages", response_model=ReglagesOut)
async def modifier_reglages(
    corps: ReglagesIn,
    current_user: Annotated[User, Depends(require_game_access)],
    _csrf: Annotated[None, Depends(require_csrf)],
    db: AsyncSession = Depends(get_session),
) -> ReglagesOut:
    """Modifie mes réglages (partiellement) et rend l'état complet qui en résulte."""
    try:
        reglages = await service.enregistrer_reglages(
            db,
            current_user.id,
            rendu_defaut=corps.rendu_defaut,
            jamais_montrer_mes_photos=corps.jamais_montrer_mes_photos,
        )
    except service.RenduValeurInvalide as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    await db.commit()
    return ReglagesOut.de(reglages)


@router.get("/decks/{deck_id}", response_model=ApercuDeckOut)
async def apercu_deck(
    deck_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_game_access)],
    db: AsyncSession = Depends(get_session),
    storage: StorageBackend = Depends(get_storage),
) -> ApercuDeckOut:
    """Ce que les cartes de **mon** deck montreront en jeu — 404 pour le deck d'un autre.

    Prépare au passage les variantes de jeu manquantes : c'est le moment « à l'avance » du lot,
    borné aux cartes de ce deck.
    """
    deck = (
        await db.execute(
            select(Deck).where(Deck.id == deck_id, Deck.user_id == current_user.id)
        )
    ).scalar_one_or_none()
    if deck is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_MESSAGE)

    reglages = await service.charger_reglages(db, current_user.id)
    apercus = await service.apercu_deck(
        db, storage, user_id=current_user.id, deck_id=deck_id
    )
    photos = [a for a in apercus if a.origine == RENDU_PHOTO]
    officielles = [a for a in apercus if a.origine != RENDU_PHOTO]
    return ApercuDeckOut(
        rendu_effectif=preference_effective(reglages, deck.rendu_cartes),
        rendu_deck=deck.rendu_cartes,
        nb_photos=len(photos),
        nb_officielles=len(officielles),
        cartes=[
            ApercuCarteOut(card_id=a.card_id, nom=a.nom, origine=a.origine, raison=a.raison)
            for a in officielles
        ],
    )


@router.get("/parties/{game_id}/photos/{item_id}")
async def photo_de_partie(
    game_id: uuid.UUID,
    item_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_game_access)],
    db: AsyncSession = Depends(get_session),
    storage: StorageBackend = Depends(get_storage),
) -> Response:
    """La variante de jeu d'une photo, pour un joueur de cette partie — 404 partout ailleurs.

    Les refus (ne participe pas, exemplaire d'un tiers, veto de confidentialité, photo
    inexploitable) rendent **le même** 404 : un code distinct dirait à l'adversaire ce qu'il n'a pas
    à savoir. ``private`` dans ``Cache-Control`` : la photo d'un joueur n'a rien à faire dans un
    cache partagé.
    """
    try:
        donnees, type_mime = await service.servir_photo(
            db, storage, game_id=game_id, item_id=item_id, regardant_id=current_user.id
        )
    except service.PhotoIntrouvable as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_MESSAGE) from exc
    return Response(
        content=donnees,
        media_type=type_mime,
        headers={"Cache-Control": "private, max-age=3600"},
    )
