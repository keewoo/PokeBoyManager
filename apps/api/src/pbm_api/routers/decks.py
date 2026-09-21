"""`/me/decks` — création, légalité et sauvegarde des decks (mission `v7-decks-api`).

Toute route est bornée au propriétaire via `get_current_user` (jamais un identifiant reçu du
client) ; les écritures exigent `require_csrf`. Un deck d'un autre utilisateur renvoie 404 (pas
403 : pas de fuite d'existence). La légalité renvoyée est recalculée à chaque lecture sur la
collection du moment — aucune écriture n'est nécessaire pour qu'un deck devienne injouable après
la vente d'une carte (mission point 3).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.auth.dependencies import get_current_user, require_csrf
from pbm_api.db import get_session
from pbm_api.decks import card_search, service
from pbm_api.decks.card_search import DeckCardSearchFilters, DeckCardSort
from pbm_api.decks.errors import DeckCardNotFoundError, DeckNotFoundError
from pbm_api.decks.legality import DeckLegality
from pbm_api.decks.schemas import (
    CreateDeckRequest,
    DeckCardFacetSet,
    DeckCardOut,
    DeckCardSearchFacets,
    DeckCardSearchItem,
    DeckCardSearchResponse,
    DeckDetail,
    DeckLegalityOut,
    DeckListResponse,
    DeckSummary,
    LegalityIssueOut,
    RenameDeckRequest,
    SetDeckCardRequest,
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
        issues=[
            LegalityIssueOut(
                code=i.code,
                message=i.message,
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
            owned=per_card[c.card_id].owned,
            missing=per_card[c.card_id].missing,
            in_collection=per_card[c.card_id].in_collection,
        )
        for c in loaded
    ]
    return DeckDetail(
        id=deck.id,
        name=deck.name,
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
                card_count=report.card_count,
                legal=report.legal,
                created_at=deck.created_at,
                updated_at=deck.updated_at,
            )
            for deck, report in decks
        ]
    )


# ---- recherche de cartes du constructeur (mission `v7-decks-recherche`) --------------------
# Routes littérales `/cards` et `/cards/facets` déclarées AVANT `/{deck_id}` : FastAPI parserait
# sinon "cards" comme un UUID de deck et renverrait 422 (même précaution que `routers/collection`).
@router.get("/cards/facets", response_model=DeckCardSearchFacets)
async def deck_card_facets(
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> DeckCardSearchFacets:
    facets = await card_search.get_facets(session, current_user)
    return DeckCardSearchFacets(
        sets=[DeckCardFacetSet(set_id=s, name=n, code=c) for s, n, c in facets.sets],
        rarities=facets.rarities,
        card_types=facets.card_types,
        hp_min=facets.hp_min,
        hp_max=facets.hp_max,
        owned_card_count=facets.owned_card_count,
        duplicate_card_count=facets.duplicate_card_count,
    )


@router.get("/cards", response_model=DeckCardSearchResponse)
async def search_deck_cards(
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    q: Annotated[str | None, Query(max_length=255)] = None,
    set_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    rarity: Annotated[list[str] | None, Query()] = None,
    card_type: Annotated[list[str] | None, Query()] = None,
    hp_min: Annotated[int | None, Query(ge=0)] = None,
    hp_max: Annotated[int | None, Query(ge=0)] = None,
    owned: bool = False,
    duplicates: bool = False,
    deck_id: uuid.UUID | None = None,
    lang: Annotated[str | None, Query(min_length=2, max_length=8)] = None,
    sort: DeckCardSort = DeckCardSort.name_asc,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=card_search.MAX_LIMIT)] = card_search.DEFAULT_LIMIT,
) -> DeckCardSearchResponse:
    """Cherche dans le catalogue, chaque carte annotée du nombre possédé et déjà dans le deck
    (`deck_id`, s'il est fourni et appartient à l'utilisateur — sinon 404). Filtres cumulables,
    tri, pagination par curseur (voir `pbm_api.decks.card_search`)."""
    filters = DeckCardSearchFilters(
        q=q,
        set_ids=frozenset(set_id or []),
        rarities=frozenset(rarity or []),
        card_types=frozenset(card_type or []),
        hp_min=hp_min,
        hp_max=hp_max,
        owned_only=owned,
        duplicates_only=duplicates,
        lang=lang,
    )
    try:
        page = await card_search.search_deck_cards(
            session, current_user, filters, sort, deck_id, cursor, limit
        )
    except DeckNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, DECK_NOT_FOUND_MESSAGE) from None
    return DeckCardSearchResponse(
        items=[
            DeckCardSearchItem(
                card_id=r.card_id,
                set_id=r.set_id,
                number=r.number,
                name=r.name,
                set_name=r.set_name,
                set_code=r.set_code,
                series=r.series,
                rarity=r.rarity,
                supertype=r.supertype,
                hp=r.hp,
                image_url=r.image_url,
                energy_type=r.energy_type,
                is_basic_energy=r.is_basic_energy,
                is_special_energy=r.is_special_energy,
                value_eur=r.value_eur,
                owned_count=r.owned_count,
                in_deck_count=r.in_deck_count,
                is_duplicate=r.is_duplicate,
            )
            for r in page.results
        ],
        next_cursor=page.next_cursor,
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
async def rename_deck(
    deck_id: uuid.UUID,
    payload: RenameDeckRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> DeckDetail:
    try:
        await service.rename_deck(session, current_user, deck_id, payload.name)
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
