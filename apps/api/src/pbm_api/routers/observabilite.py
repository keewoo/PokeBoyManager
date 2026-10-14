"""Route de **supervision du jeu** : les métriques, sans ouvrir de session SSH.

C'est le critère d'acceptation « les métriques sont visibles sans se connecter en SSH » du lot
``j-observabilite-jeu`` : un compte ayant l'accès au jeu ouvre ``/jeu/metriques`` dans son
navigateur (le cookie de session suffit) et lit le même relevé et le même verdict que ceux de
l'e-mail de la sonde — les deux appellent :func:`pbm_api.observabilite.regles.evaluer`, il n'y a
donc pas deux vérités.

**Pourquoi l'accès au jeu (D11) et pas un rôle d'administration :** il n'y a pas de rôle
d'administration dans ce produit, et le jeu est réservé à une poignée de comptes invités
nommément. Le relevé est **agrégé** : il ne dit pas qui a fait quoi. La ventilation par compte
existe en base (``jeu_incidents.user_id``) pour le diagnostic, et n'est délibérément pas servie
ici — ce serait une fuite entre joueurs.

Sans ce droit, la route répond **404** comme toute route du jeu : pour un compte non invité, le
jeu n'existe pas.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.auth.dependencies import require_game_access
from pbm_api.db import get_session
from pbm_api.models import User
from pbm_api.observabilite.metriques import FENETRE_DEFAUT_H, relever
from pbm_api.observabilite.regles import evaluer, verdict

router = APIRouter(prefix="/jeu", tags=["observabilite"])

#: Fenêtre maximale consultable : 30 jours. Au-delà, un relevé mélange trop d'époques pour
#: signaler quoi que ce soit, et la requête d'agrégat n'est plus bornée.
FENETRE_MAX_H = 24 * 30


class AlerteOut(BaseModel):
    """Une alerte telle qu'elle est publiée : code stable, gravité, message en français."""

    code: str
    gravite: str
    message: str


class MetriquesOut(BaseModel):
    """Le relevé, les alertes et le verdict — exactement ce que la sonde envoie par e-mail."""

    genere_le: datetime = Field(description="Instant du relevé (UTC).")
    fenetre_heures: int
    verdict: str = Field(description="OK, A_SURVEILLER ou PANNE.")
    releve: dict
    alertes: list[AlerteOut]


@router.get("/metriques", response_model=MetriquesOut)
async def metriques(
    fenetre_heures: int = Query(
        FENETRE_DEFAUT_H, ge=1, le=FENETRE_MAX_H, description="Fenêtre d'observation, en heures."
    ),
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_game_access),
) -> MetriquesOut:
    """Les métriques du jeu sur la fenêtre demandée, avec les alertes qu'elles déclenchent.

    Lecture seule et agrégée : aucune donnée nominative, aucun identifiant de partie d'autrui —
    rien ici n'est borné à l'utilisateur courant parce que rien ici ne parle d'un utilisateur.
    """
    maintenant = datetime.now(UTC)
    releve = await relever(db, maintenant=maintenant, fenetre_heures=fenetre_heures)
    alertes = evaluer(releve)
    return MetriquesOut(
        genere_le=maintenant,
        fenetre_heures=fenetre_heures,
        verdict=verdict(alertes),
        releve=releve.en_json(),
        alertes=[AlerteOut(code=a.code, gravite=a.gravite, message=a.message) for a in alertes],
    )
