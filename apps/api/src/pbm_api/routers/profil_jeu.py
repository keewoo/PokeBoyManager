"""Routes du **profil de joueur** (lot `j-profil-jeu`, jalon J4, DJ6).

Deux routes, et une seule écriture :

* ``GET /jeu/profil`` — la vitrine : pseudo et avatar repris du compte, carte fétiche, badges,
  décors ;
* ``PUT /jeu/profil/carte-fetiche`` — poser ou retirer sa carte fétiche.

Comme toute route du jeu, elles sont gardées par
:func:`~pbm_api.auth.dependencies.require_game_access` (D11) : un compte sans accès au jeu reçoit
**404** partout. L'écriture exige le jeton CSRF.

**Aucune route ne prend d'identité en paramètre**, et il n'y en aura pas : on ne lit que le profil
du compte de la session. « Voir le profil d'un autre joueur » n'existe donc pas — la seule chose
qu'un adversaire voit de moi, c'est ma carte fétiche au lancement, et elle lui est servie par la
vue du lancement (:mod:`pbm_api.routers.lancement`), pas par une route de profil qu'on pourrait
interroger sur n'importe qui. C'est la même prudence que le classement privé, qui est **éteint par
défaut** parce qu'il nomme les comptes invités.

Le routeur ne décide rien : la vitrine est assemblée par :mod:`pbm_api.jeu.profil_service`, les
badges déclarés dans :mod:`pbm_api.jeu.badges`, le rendu de la carte par :mod:`pbm_api.jeu.rendu`
(DJ5).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.auth.dependencies import require_csrf, require_game_access
from pbm_api.db import get_session
from pbm_api.jeu import profil_service as service
from pbm_api.jeu.badges import MESURES, PALIER_PARTIES
from pbm_api.models import User
from pbm_api.storage import StorageBackend, build_storage

router = APIRouter(prefix="/jeu/profil", tags=["jeu-profil"])

# Un seul client de stockage pour le processus, comme les autres routeurs qui touchent aux images
# (`routers/jeu_rendu.py`, `routers/profile.py`).
_storage = build_storage()


def get_storage() -> StorageBackend:
    """Le client de stockage objet du processus (surchargeable en test)."""
    return _storage


class RenduOut(BaseModel):
    """Le rendu d'une carte, tel que l'écran l'affiche — la forme déjà connue du plateau."""

    origine: str
    url: str
    url_zoom: str
    credit: str | None = None
    raison: str | None = None
    url_repli: str | None = None


class CarteFeticheOut(BaseModel):
    """La carte fétiche : son identité catalogue, et son rendu."""

    card_id: uuid.UUID
    nom: str
    rendu: RenduOut

    @classmethod
    def de(cls, vue: service.CarteFeticheVue) -> CarteFeticheOut:
        """Construit la sortie HTTP depuis la vue du service."""
        return cls(
            card_id=vue.card_id,
            nom=vue.nom,
            rendu=RenduOut(
                origine=vue.rendu.origine,
                url=vue.rendu.url,
                url_zoom=vue.rendu.url_zoom,
                credit=vue.rendu.credit,
                raison=vue.rendu.raison,
                url_repli=vue.rendu.url_repli,
            ),
        )


class BadgeOut(BaseModel):
    """Un badge de la vitrine, obtenu ou non.

    ``mesure`` dit **ce que le badge récompense** (``issue``, ``exploit``, ``volume``,
    ``construction``). L'écran s'en sert pour les regrouper, et le champ existe surtout pour que la
    promesse « aucun badge ne récompense le temps passé » soit **lisible depuis l'extérieur** : il
    n'y a pas de mesure de temps dans le vocabulaire, et la sortie HTTP le montre.
    """

    code: str
    nom: str
    description: str
    mesure: str
    obtenu: bool
    obtenu_a: datetime | None
    game_id: uuid.UUID | None


class VitrineOut(BaseModel):
    """La vitrine du profil de joueur.

    ``mesures_possibles`` et ``palier_parties`` sont publiés par le serveur pour que l'écran ne code
    aucune de ces valeurs en dur — même règle que ``seuil_significativite`` de « Mes parties » et
    ``rendus_possibles`` du rendu : le vocabulaire vient de celui qui calcule.

    ``badges`` est **vide** quand ``badges_actifs`` est faux (DJ6 : « activables par JF ») ; l'écran
    affiche alors une phrase, pas une grille vide.
    """

    pseudo: str | None
    a_un_avatar: bool
    carte_fetiche: CarteFeticheOut | None
    badges_actifs: bool
    badges: list[BadgeOut]
    mesures_possibles: list[str]
    palier_parties: int
    decors: list[str]
    decor_choisi: str | None

    @classmethod
    def de(cls, vitrine: service.Vitrine) -> VitrineOut:
        """Construit la sortie HTTP depuis la vitrine du service."""
        return cls(
            pseudo=vitrine.pseudo,
            a_un_avatar=vitrine.a_un_avatar,
            carte_fetiche=(
                CarteFeticheOut.de(vitrine.carte_fetiche)
                if vitrine.carte_fetiche is not None
                else None
            ),
            badges_actifs=vitrine.badges_actifs,
            badges=[
                BadgeOut(
                    code=b.code,
                    nom=b.nom,
                    description=b.description,
                    mesure=b.mesure,
                    obtenu=b.obtenu,
                    obtenu_a=b.obtenu_a,
                    game_id=b.game_id,
                )
                for b in vitrine.badges
            ],
            mesures_possibles=sorted(MESURES),
            palier_parties=PALIER_PARTIES,
            decors=list(vitrine.decors),
            decor_choisi=vitrine.decor_choisi,
        )


class CarteFeticheIn(BaseModel):
    """La carte fétiche choisie — ``null`` pour la retirer.

    Un seul champ, et il est explicitement nullable : « je n'en veux plus » doit être exprimable,
    sinon un choix fait une fois serait définitif.
    """

    card_id: uuid.UUID | None = None


@router.get("", response_model=VitrineOut)
async def lire_profil(
    current_user: Annotated[User, Depends(require_game_access)],
    db: AsyncSession = Depends(get_session),
) -> VitrineOut:
    """Ma vitrine de joueur — celle du compte de la session, et d'aucun autre."""
    return VitrineOut.de(await service.composer_vitrine(db, current_user))


@router.put("/carte-fetiche", response_model=VitrineOut)
async def poser_carte_fetiche(
    corps: CarteFeticheIn,
    current_user: Annotated[User, Depends(require_game_access)],
    _csrf: Annotated[None, Depends(require_csrf)],
    db: AsyncSession = Depends(get_session),
    storage: StorageBackend = Depends(get_storage),
) -> VitrineOut:
    """Pose ou retire ma carte fétiche, et rend la vitrine qui en résulte.

    **422 en nommant la raison** quand la carte est inconnue du catalogue ou absente de ma
    collection : un refus muet laisserait croire à une panne, alors que le joueur n'a qu'un clic à
    changer (c'est la règle du dépôt — un refus se dit, D9).
    """
    try:
        await service.choisir_carte_fetiche(
            db, storage, user=current_user, card_id=corps.card_id
        )
    except service.CarteInconnue as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except service.CarteNonPossedee as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    await db.commit()
    await db.refresh(current_user)
    return VitrineOut.de(await service.composer_vitrine(db, current_user))
