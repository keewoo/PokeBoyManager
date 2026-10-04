"""`/me/demandes-cartes` — la file de demandes « je voudrais jouer cette carte » (lot
`j-effets-couverture-outil`).

Un joueur dont un deck refuse une carte (effet non scripté, D9) peut la signaler ; chaque demande
nourrit la priorisation du chantier de scriptage. Toute route est bornée au propriétaire via
`get_current_user` (jamais un identifiant reçu du client) : un joueur ne voit et ne touche **que**
ses propres demandes. L'agrégation (combien de joueurs veulent telle carte) est une donnée
d'exploitation lue hors ligne (`pbm_api.jeu.scripts.couverture`), jamais exposée ici."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.auth.dependencies import get_current_user, require_csrf
from pbm_api.db import get_session
from pbm_api.jeu.scripts import demandes
from pbm_api.jeu.scripts.schemas import (
    CardPlayRequestCreate,
    CardPlayRequestOut,
    CardPlayRequestsResponse,
)
from pbm_api.models import Card, User

router = APIRouter(prefix="/me/demandes-cartes", tags=["demandes-cartes"])


def _to_out(item: demandes.DemandeJoueur) -> CardPlayRequestOut:
    """Sérialise une demande du joueur, statut stocké + jouabilité courante recalculée."""
    d = item.demande
    return CardPlayRequestOut(
        id=d.id,
        card_id=d.card_id,
        card_name=item.card_name,
        statut=d.statut,
        note=d.note,
        jouable_maintenant=item.jouable_maintenant,
        created_at=d.created_at,
        updated_at=d.updated_at,
    )


@router.get("", response_model=CardPlayRequestsResponse)
async def list_requests(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> CardPlayRequestsResponse:
    """Les demandes du joueur courant, chacune avec sa progression (statut + jouabilité)."""
    items = await demandes.demandes_du_joueur(db, user.id)
    return CardPlayRequestsResponse(requests=[_to_out(i) for i in items])


@router.post("", response_model=CardPlayRequestOut, status_code=status.HTTP_201_CREATED)
async def create_request(
    payload: CardPlayRequestCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    _: None = Depends(require_csrf),
) -> CardPlayRequestOut:
    """Signale (ou ré-ouvre) une demande du joueur pour une carte. Idempotent par (joueur, carte) :
    re-signaler ne crée pas de doublon. Une carte inconnue du catalogue est refusée (404)."""
    exists = (
        await db.execute(select(Card.id).where(Card.id == payload.card_id))
    ).scalar_one_or_none()
    if exists is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Carte introuvable.")
    await demandes.creer_ou_maj_demande(
        db, user_id=user.id, card_id=payload.card_id, note=payload.note
    )
    # La liste du joueur est courte : on la relit pour renvoyer la demande avec sa jouabilité.
    items = await demandes.demandes_du_joueur(db, user.id)
    cree = next(i for i in items if i.demande.card_id == payload.card_id)
    return _to_out(cree)


# Exposé pour un éventuel test d'accès croisé explicite : la suppression d'une demande.
@router.delete("/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_request(
    card_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    _: None = Depends(require_csrf),
) -> None:
    """Retire la demande du joueur pour une carte. 404 si le joueur n'a pas de demande pour elle
    (une demande d'un autre joueur est, pour celui-ci, inexistante — jamais 403)."""
    from pbm_api.models.card_play_requests import CardPlayRequest

    ligne = (
        await db.execute(
            select(CardPlayRequest).where(
                CardPlayRequest.user_id == user.id, CardPlayRequest.card_id == card_id
            )
        )
    ).scalar_one_or_none()
    if ligne is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aucune demande pour cette carte.")
    await db.delete(ligne)
    await db.commit()
