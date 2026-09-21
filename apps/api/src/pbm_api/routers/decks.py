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

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.auth.dependencies import get_current_user, require_csrf
from pbm_api.db import get_session
from pbm_api.decks import card_search, import_service, service
from pbm_api.decks import export as export_mod
from pbm_api.decks.card_search import DeckCardSearchFilters, DeckCardSort
from pbm_api.decks.errors import DeckCardNotFoundError, DeckNotFoundError
from pbm_api.decks.export import ExportCard
from pbm_api.decks.import_service import ImportResult
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
    ImportCandidateOut,
    ImportDeckRequest,
    ImportDeckResponse,
    ImportLineOut,
    ImportReportOut,
    LegalityIssueOut,
    SetDeckCardRequest,
    UpdateDeckRequest,
)
from pbm_api.decks.service import LoadedDeckCard
from pbm_api.models import User
from pbm_api.storage import StorageBackend, build_storage
from pbm_api.validation.errors import CardNotFoundError

router = APIRouter(prefix="/me/decks", tags=["decks"])

# `build_storage()` (comme les routeurs `images`/`uploads`), jamais `ObjectStorage()` en dur : le
# backend est choisi par `STORAGE_BACKEND` (local en PROD, s3 en dev/CI). Sert de source aux
# vignettes du PDF (`cards/{id}/low.webp`, même clé que le proxy d'images du catalogue).
_storage = build_storage()


def get_storage() -> StorageBackend:
    return _storage


# Taille de vignette servie au PDF — la basse définition suffit et pèse peu.
_THUMBNAIL_KEY = "cards/{card_id}/low.webp"

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


# ------------------------------------------------------------------------- import / export


def _candidate_out(c) -> ImportCandidateOut:
    return ImportCandidateOut(
        card_id=c.card_id,
        name=c.name,
        set_code=c.set_code,
        set_name=c.set_name,
        number=c.number,
        score=c.score,
    )


def _report_out(result: ImportResult) -> ImportReportOut:
    return ImportReportOut(
        matched=result.matched,
        ambiguous=result.ambiguous,
        not_found=result.not_found,
        sections_ignored=result.sections_ignored,
        cards_added=result.cards_added,
        distinct_cards=result.distinct_cards,
        truncated=result.truncated,
        warnings=result.warnings,
        lines=[
            ImportLineOut(
                line_no=line.line_no,
                raw=line.raw,
                status=line.status,
                quantity=line.quantity,
                parsed_name=line.parsed_name,
                parsed_set=line.parsed_set,
                parsed_number=line.parsed_number,
                notes=line.notes,
                card=_candidate_out(line.card) if line.card else None,
                alternatives=[_candidate_out(c) for c in line.alternatives],
                owned=line.owned,
                missing=line.missing,
            )
            for line in result.lines
        ],
    )


@router.post("/import", response_model=ImportDeckResponse)
async def import_deck(
    payload: ImportDeckRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> ImportDeckResponse:
    """Importe une liste de deck collée : rapproche chaque ligne au catalogue et crée un deck
    « à compléter ». N'écrit JAMAIS dans la collection (risque du lot). `dry_run` renvoie le seul
    rapport, sans rien créer."""
    result = await import_service.import_deck(
        session,
        current_user,
        text=payload.text,
        name=payload.name,
        deck_format=payload.format,
        dry_run=payload.dry_run,
    )
    deck_out: DeckDetail | None = None
    if result.deck_id is not None:
        deck, loaded, report = await service.deck_detail(session, current_user, result.deck_id)
        deck_out = _detail_response(deck, loaded, report)
    return ImportDeckResponse(report=_report_out(result), deck=deck_out)


@router.get("/{deck_id}/export")
async def export_deck(
    deck_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    storage: Annotated[StorageBackend, Depends(get_storage)],
    fmt: str = Query("text", pattern="^(text|pdf)$"),
) -> Response:
    """Exporte un deck en texte standard (`fmt=text`) ou en PDF avec vignettes (`fmt=pdf`).
    Borné au propriétaire : un deck d'un autre utilisateur renvoie 404."""
    try:
        deck, loaded, report = await service.deck_detail(session, current_user, deck_id)
    except DeckNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, DECK_NOT_FOUND_MESSAGE) from None

    cards = [
        ExportCard(
            card_id=c.card_id,
            quantity=c.quantity,
            name=c.card_name,
            set_code=c.set_code,
            number=c.card_number,
            supertype=c.supertype,
        )
        for c in loaded
    ]
    safe_name = deck.name.replace('"', "").replace("\n", " ").strip() or "deck"

    if fmt == "text":
        body = export_mod.render_text(
            deck_name=deck.name,
            format_label=report.format_label,
            card_count=report.card_count,
            legal=report.legal,
            cards=cards,
        )
        return Response(
            content=body,
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}.txt"'},
        )

    # fmt == "pdf" : on précharge les vignettes (I/O async) puis on rend (fpdf2 est synchrone).
    images: dict[uuid.UUID, bytes | None] = {}
    for c in loaded:
        try:
            images[c.card_id] = await storage.get(_THUMBNAIL_KEY.format(card_id=c.card_id))
        except Exception:  # noqa: BLE001 — stockage indisponible : cadre nommé, jamais un 500.
            images[c.card_id] = None
    pdf_bytes = export_mod.render_pdf(
        deck_name=deck.name,
        format_label=report.format_label,
        card_count=report.card_count,
        legal=report.legal,
        cards=cards,
        image_loader=images.get,
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.pdf"'},
    )
