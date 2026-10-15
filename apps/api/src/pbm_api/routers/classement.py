"""Route du **classement privé** (``GET /jeu/classement``) — lot `j-classement-prive`, DJ6.

Une seule route, en lecture. Comme toute route du jeu, elle est gardée par
:func:`~pbm_api.auth.dependencies.require_game_access` (D11) : un compte sans accès au jeu reçoit un
**404**, pas un 403 — on ne confirme pas l'existence de ce qu'il n'a pas le droit de voir.

Le routeur ne décide rien : la formule vit dans :mod:`pbm_api.jeu.classement` (pur), la lecture dans
:mod:`pbm_api.jeu.classement_service`, et l'interrupteur dans :mod:`pbm_api.jeu.reglages` — posé
par JF en ligne de commande sur le serveur, jamais par HTTP.

**Il n'y a pas de route d'écriture, et c'est le cœur du lot.** Activer, désactiver ou changer le
barème se fait par ``python -m pbm_api.admin set-reglage-jeu …`` : une commande, aucun redémarrage,
aucun build. Exposer ces réglages en HTTP aurait demandé une notion d'administrateur que ce produit
n'a pas (il n'existe aucun compte privilégié côté web), donc une surface d'attaque pour un réglage
que deux personnes changeront trois fois.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.auth.dependencies import require_game_access
from pbm_api.db import get_session
from pbm_api.jeu.classement import LigneClassement
from pbm_api.jeu.classement_service import (
    FENETRE_RECENTE_JOURS_DEFAUT,
    FENETRE_RECENTE_JOURS_MAX,
    FENETRE_RECENTE_JOURS_MIN,
    VueClassement,
    charger_classement,
)
from pbm_api.models import User

router = APIRouter(prefix="/jeu", tags=["jeu-classement"])


class BaremeOut(BaseModel):
    """La formule appliquée, rendue avec le tableau : un total sans son barème ne se lit pas."""

    nom: str
    libelle: str
    points_victoire: int
    points_egalite: int
    points_defaite: int


class LigneClassementOut(BaseModel):
    """Une ligne du tableau. **Sans identifiant de compte** : l'écran n'en a pas besoin.

    Le pseudo suffit à nommer un joueur, et ``moi`` suffit à surligner sa propre ligne. Publier
    l'UUID des autres comptes invités serait une donnée de plus à chaque requête, sans usage — donc
    une fuite gratuite.

    Les quatre compteurs permettent de **recompter** les points avec le barème rendu à côté : c'est
    ce qui rend un classement contestable sans être suspect.
    """

    rang: int
    pseudo: str | None
    #: Vrai pour la ligne du compte qui interroge — l'écran surligne, le serveur n'a pas à deviner.
    moi: bool
    points: int
    parties: int
    victoires: int
    defaites: int
    egalites: int
    #: Points gagnés dans la fenêtre récente (``fenetre_jours``) : l'« évolution dans le temps ».
    points_recents: int
    derniere_partie_a: datetime | None


class ClassementOut(BaseModel):
    """Le tableau complet, ou son absence assumée.

    ``actif=False`` est l'état **par défaut** du produit (DJ6 : « en option, activable par JF ») et
    se rend en 200 avec zéro ligne, pas en 404 : l'écran doit pouvoir distinguer « JF n'a pas
    activé le classement » d'une route cassée. Quand il est éteint, l'historique n'est même pas lu.
    """

    actif: bool
    bareme: BaremeOut
    fenetre_jours: int
    lignes: list[LigneClassementOut]

    @classmethod
    def de(cls, vue: VueClassement, *, moi: uuid.UUID) -> ClassementOut:
        """Traduit la vue du service en sortie HTTP (``moi`` est l'identifiant du demandeur)."""
        formule = vue.classement.bareme
        return cls(
            actif=vue.actif,
            bareme=BaremeOut(
                nom=formule.nom,
                libelle=formule.libelle,
                points_victoire=formule.victoire,
                points_egalite=formule.egalite,
                points_defaite=formule.defaite,
            ),
            fenetre_jours=vue.fenetre_jours,
            lignes=[_ligne_out(ligne, moi=moi) for ligne in vue.classement.lignes],
        )


def _ligne_out(ligne: LigneClassement, *, moi: uuid.UUID) -> LigneClassementOut:
    """Une ligne de sortie, sans l'identifiant de compte (voir :class:`LigneClassementOut`)."""
    return LigneClassementOut(
        rang=ligne.rang,
        pseudo=ligne.pseudo,
        moi=ligne.user_id == moi,
        points=ligne.points,
        parties=ligne.parties,
        victoires=ligne.victoires,
        defaites=ligne.defaites,
        egalites=ligne.egalites,
        points_recents=ligne.points_recents,
        derniere_partie_a=ligne.derniere_partie_a,
    )


@router.get("/classement", response_model=ClassementOut)
async def lire_classement(
    current_user: Annotated[User, Depends(require_game_access)],
    db: Annotated[AsyncSession, Depends(get_session)],
    fenetre_jours: Annotated[
        int,
        Query(
            ge=FENETRE_RECENTE_JOURS_MIN,
            le=FENETRE_RECENTE_JOURS_MAX,
            description="Largeur de la fenêtre « points récents », en jours.",
        ),
    ] = FENETRE_RECENTE_JOURS_DEFAUT,
) -> ClassementOut:
    """Le classement privé des comptes invités, recalculé à chaque appel depuis l'historique.

    Rien n'est stocké : c'est ce qui garantit qu'une erreur de formule ne devient jamais définitive
    (risque nommé du lot). Le demandeur figure toujours au tableau, même sans partie comptée.
    """
    vue = await charger_classement(db, demandeur_id=current_user.id, fenetre_jours=fenetre_jours)
    return ClassementOut.de(vue, moi=current_user.id)


__all__ = ["router"]
