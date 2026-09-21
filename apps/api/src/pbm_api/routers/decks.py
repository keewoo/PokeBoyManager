"""`/me/decks` — création, légalité (formats, sévérités) et sauvegarde des decks.

Missions `v7-decks-api` (CRUD, socle de légalité) puis `v7-decks-legalite` (sévérité des
constats, légalité par format choisi par le joueur, Pokémon de base, contrefaçons exclues).

Toute route est bornée au propriétaire via `get_current_user` (jamais un identifiant reçu du
client) ; les écritures exigent `require_csrf`. Un deck d'un autre utilisateur renvoie 404 (pas
403 : pas de fuite d'existence). La légalité renvoyée est recalculée à chaque lecture sur la
collection du moment — aucune écriture n'est nécessaire pour qu'un deck devienne injouable après
la vente ou le signalement contrefaçon d'une carte (mission point 3).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.auth.dependencies import get_current_user, require_csrf
from pbm_api.db import get_session
from pbm_api.decks import service
from pbm_api.decks.errors import DeckCardNotFoundError, DeckNotFoundError
from pbm_api.decks.legality import DeckLegality
from pbm_api.decks.schemas import (
    CreateDeckRequest,
    DeckCardOut,
    DeckDetail,
    DeckLegalityOut,
    DeckListResponse,
    DeckSummary,
    LegalityIssueOut,
    SetDeckCardRequest,
    UpdateDeckRequest,
)
from pbm_api.decks.service import LoadedDeckCard
from pbm_api.models import User
from pbm_api.validation.errors import CardNotFoundError

router = APIRouter(prefix="/me/decks", tags=["decks"])

DECK_NOT_FOUND_MESSAGE = "deck introuvable"
CARD_NOT_FOUND_MESSAGE = "carte introuvable au catalogue"
DECK_CARD_NOT_FOUND_MESSAGE = "cette carte n'est pas dans le deck"


def _legality_out(report: DeckLegality) -> DeckLegalityOut:
    return DeckLegalityOut(
        legal=report.legal,
        card_count=report.card_count,
        size_ok=report.size_ok,
        format=report.format,
        format_label=report.format_label,
        issues=[
            LegalityIssueOut(
                code=i.code,
                message=i.message,
                severity=i.severity,
                card_id=i.card_id,
                card_name=i.card_name,
                detail=i.detail,
            )
            for i in report.issues
        ],
    )


def _detail_response(
    deck, loaded: list[LoadedDeckCard], report: DeckLegality
) -> DeckDetail:
    per_card = {c.card_id: c for c in report.cards}
    cards = [
        DeckCardOut(
            card_id=c.card_id,
            card_name=c.card_name,
            card_number=c.card_number,
            set_id=c.set_id,
            set_name=c.set_name,
            set_code=c.set_code,
            image_url=c.image_url,
            supertype=c.supertype,
            rarity=c.rarity,
            quantity=c.quantity,
            is_basic_energy=per_card[c.card_id].is_basic_energy,
            is_special_energy=per_card[c.card_id].is_special_energy,
            is_basic_pokemon=per_card[c.card_id].is_basic_pokemon,
            owned=per_card[c.card_id].owned,
            missing=per_card[c.card_id].missing,
            in_collection=per_card[c.card_id].in_collection,
            in_format=per_card[c.card_id].in_format,
            counterfeit_excluded=per_card[c.card_id].counterfeit_excluded,
        )
        for c in loaded
    ]
    return DeckDetail(
        id=deck.id,
        name=deck.name,
        format=deck.format,
        created_at=deck.created_at,
        updated_at=deck.updated_at,
        cards=cards,
        legality=_legality_out(report),
    )


@router.post("", response_model=DeckDetail, status_code=status.HTTP_201_CREATED)
async def create_deck(
    payload: CreateDeckRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> DeckDetail:
    try:
        deck = await service.create_deck(session, current_user, payload)
    except CardNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, CARD_NOT_FOUND_MESSAGE) from None
    deck, loaded, report = await service.deck_detail(session, current_user, deck.id)
    return _detail_response(deck, loaded, report)


@router.get("", response_model=DeckListResponse)
async def list_decks(
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> DeckListResponse:
    decks = await service.list_decks(session, current_user)
    return DeckListResponse(
        decks=[
            DeckSummary(
                id=deck.id,
                name=deck.name,
                format=deck.format,
                card_count=report.card_count,
                legal=report.legal,
                created_at=deck.created_at,
                updated_at=deck.updated_at,
            )
            for deck, report in decks
        ]
    )


@router.get("/{deck_id}", response_model=DeckDetail)
async def get_deck(
    deck_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> DeckDetail:
    try:
        deck, loaded, report = await service.deck_detail(session, current_user, deck_id)
    except DeckNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, DECK_NOT_FOUND_MESSAGE) from None
    return _detail_response(deck, loaded, report)


@router.patch("/{deck_id}", response_model=DeckDetail)
async def update_deck(
    deck_id: uuid.UUID,
    payload: UpdateDeckRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> DeckDetail:
    try:
        await service.update_deck(
            session, current_user, deck_id, name=payload.name, deck_format=payload.format
        )
        deck, loaded, report = await service.deck_detail(session, current_user, deck_id)
    except DeckNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, DECK_NOT_FOUND_MESSAGE) from None
    return _detail_response(deck, loaded, report)


@router.delete("/{deck_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_deck(
    deck_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> None:
    try:
        await service.delete_deck(session, current_user, deck_id)
    except DeckNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, DECK_NOT_FOUND_MESSAGE) from None


@router.post("/{deck_id}/duplicate", response_model=DeckDetail, status_code=status.HTTP_201_CREATED)
async def duplicate_deck(
    deck_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> DeckDetail:
    try:
        copy = await service.duplicate_deck(session, current_user, deck_id)
    except DeckNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, DECK_NOT_FOUND_MESSAGE) from None
    deck, loaded, report = await service.deck_detail(session, current_user, copy.id)
    return _detail_response(deck, loaded, report)


@router.put("/{deck_id}/cards/{card_id}", response_model=DeckDetail)
async def set_deck_card(
    deck_id: uuid.UUID,
    card_id: uuid.UUID,
    payload: SetDeckCardRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> DeckDetail:
    try:
        await service.set_deck_card(session, current_user, deck_id, card_id, payload.quantity)
    except DeckNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, DECK_NOT_FOUND_MESSAGE) from None
    except CardNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, CARD_NOT_FOUND_MESSAGE) from None
    deck, loaded, report = await service.deck_detail(session, current_user, deck_id)
    return _detail_response(deck, loaded, report)


@router.delete("/{deck_id}/cards/{card_id}", response_model=DeckDetail)
async def remove_deck_card(
    deck_id: uuid.UUID,
    card_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> DeckDetail:
    try:
        await service.remove_deck_card(session, current_user, deck_id, card_id)
    except DeckNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, DECK_NOT_FOUND_MESSAGE) from None
    except DeckCardNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, DECK_CARD_NOT_FOUND_MESSAGE) from None
    deck, loaded, report = await service.deck_detail(session, current_user, deck_id)
    return _detail_response(deck, loaded, report)
