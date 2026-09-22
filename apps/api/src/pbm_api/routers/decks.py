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

from pbm_api.ai.errors import AIProviderError
from pbm_api.ai.factory import create_provider
from pbm_api.auth.dependencies import get_current_user, require_csrf
from pbm_api.db import get_session
from pbm_api.decks import ai_builder, card_search, import_service, replacements, service
from pbm_api.decks import export as export_mod
from pbm_api.decks.ai_builder import ProposalOptions, ProviderFactory
from pbm_api.decks.card_search import DeckCardSearchFilters, DeckCardSort
from pbm_api.decks.errors import (
    DeckCardNotFoundError,
    DeckNotFoundError,
    EmptyCollectionError,
    NoAiKeyForDeckError,
)
from pbm_api.decks.export import ExportCard
from pbm_api.decks.import_service import ImportResult
from pbm_api.decks.legality import DeckLegality
from pbm_api.decks.schemas import (
    CreateDeckRequest,
    DeckAlertOut,
    DeckAlertsResponse,
    DeckCardFacetSet,
    DeckCardOut,
    DeckCardSearchFacets,
    DeckCardSearchItem,
    DeckCardSearchResponse,
    DeckDetail,
    DeckHistoryResponse,
    DeckLegalityOut,
    DeckListResponse,
    DeckProposalCorrectionOut,
    DeckProposalExplanationOut,
    DeckProposalResponse,
    DeckReplacementItem,
    DeckReplacementsResponse,
    DeckStatBucketOut,
    DeckStatsOut,
    DeckSummary,
    DeckValueOut,
    ImportCandidateOut,
    ImportDeckRequest,
    ImportDeckResponse,
    ImportLineOut,
    ImportReportOut,
    LegalityIssueOut,
    MarkAlertsReadRequest,
    ProposeDeckRequest,
    SetDeckCardRequest,
    UpdateDeckRequest,
)
from pbm_api.decks.service import DeckAlert, LoadedDeckCard
from pbm_api.decks.stats import DeckStats
from pbm_api.models import DeckEvent, User
from pbm_api.storage import StorageBackend, build_storage
from pbm_api.validation.errors import CardNotFoundError

router = APIRouter(prefix="/me/decks", tags=["decks"])

# `build_storage()` (comme les routeurs `images`/`uploads`), jamais `ObjectStorage()` en dur : le
# backend est choisi par `STORAGE_BACKEND` (local en PROD, s3 en dev/CI). Sert de source aux
# vignettes du PDF (`cards/{id}/low.webp`, même clé que le proxy d'images du catalogue).
_storage = build_storage()


def get_storage() -> StorageBackend:
    return _storage


def get_deck_ai_provider_factory() -> ProviderFactory:
    """Fabrique de fournisseur IA, injectée par dépendance (comme `card_insights`) : la suite
    automatisée la remplace par un double déterministe — aucune clé IA réelle sur chimera."""
    return create_provider


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


# ---- alertes de synchronisation collection→deck (mission `v7-decks-collection-sync`) -------
# Route littérale `/alerts` déclarée AVANT `/{deck_id}` (même précaution que `/cards`).
def _alert_out(deck_id: uuid.UUID, deck_name: str, event: DeckEvent) -> DeckAlertOut:
    detail = event.detail or {}
    return DeckAlertOut(
        id=event.id,
        deck_id=deck_id,
        deck_name=deck_name,
        event_type=event.event_type,
        reason=event.reason,
        card_id=event.card_id,
        card_name=event.card_name,
        required=int(detail.get("required", 0)),
        owned=int(detail.get("owned", 0)),
        missing=int(detail.get("missing", 0)),
        read=event.read_at is not None,
        created_at=event.created_at,
    )


@router.get("/alerts", response_model=DeckAlertsResponse)
async def list_deck_alerts(
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    unread_only: bool = True,
) -> DeckAlertsResponse:
    """Alertes « à compléter » du joueur (en-tête + liste). Par défaut, les non lues seulement ;
    `unread_only=false` renvoie tout l'historique. Le compte des non lues est toujours fourni."""
    alerts: list[DeckAlert]
    alerts, unread_count = await service.list_alerts(
        session, current_user, only_unread=unread_only
    )
    return DeckAlertsResponse(
        alerts=[_alert_out(a.event.deck_id, a.deck_name, a.event) for a in alerts],
        unread_count=unread_count,
    )


@router.post("/alerts/read", response_model=DeckAlertsResponse)
async def mark_deck_alerts_read(
    payload: MarkAlertsReadRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> DeckAlertsResponse:
    """Marque des alertes comme lues (toutes les non lues si `event_ids` est absent)."""
    await service.mark_alerts_read(session, current_user, payload.event_ids)
    alerts, unread_count = await service.list_alerts(session, current_user, only_unread=True)
    return DeckAlertsResponse(
        alerts=[_alert_out(a.event.deck_id, a.deck_name, a.event) for a in alerts],
        unread_count=unread_count,
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


DECK_NO_AI_KEY_MESSAGE = (
    "Aucune clé IA par défaut : choisis un fournisseur avec une clé dans ton profil pour "
    "utiliser l'assistant."
)
DECK_EMPTY_COLLECTION_MESSAGE = (
    "Ta collection ne contient aucune carte jouable dans ce format : ajoute des cartes avant de "
    "demander un deck à l'IA."
)
DECK_AI_PROVIDER_ERROR_MESSAGE = "La proposition de deck a échoué : {}"


@router.post("/{deck_id}/propose", response_model=DeckProposalResponse)
async def propose_deck(
    deck_id: uuid.UUID,
    payload: ProposeDeckRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(require_csrf)],
    provider_factory: Annotated[ProviderFactory, Depends(get_deck_ai_provider_factory)],
) -> DeckProposalResponse:
    """Assistant IA (mission `v7-deck-ia`) : un seul appel IA propose un deck légal PRIS DANS la
    collection du joueur, l'explique carte par carte, puis réécrit ce deck (existant). La
    proposition brute est corrigée (possession, 4 exemplaires, Pokémon de base, taille) avant
    d'être écrite — jamais montrée telle quelle — et sa légalité est recalculée côté serveur.
    Un deck d'un autre utilisateur renvoie 404 (jamais 403)."""
    options = ProposalOptions(
        types=[(t.type, t.share) for t in payload.types],
        energy_types=list(payload.energy_types),
        style=payload.style,
        must_include=list(payload.must_include),
        size=payload.size,
    )
    try:
        outcome = await ai_builder.propose_deck(
            session, current_user, deck_id, options, provider_factory
        )
    except DeckNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, DECK_NOT_FOUND_MESSAGE) from None
    except NoAiKeyForDeckError:
        raise HTTPException(status.HTTP_409_CONFLICT, DECK_NO_AI_KEY_MESSAGE) from None
    except EmptyCollectionError:
        raise HTTPException(status.HTTP_409_CONFLICT, DECK_EMPTY_COLLECTION_MESSAGE) from None
    except AIProviderError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, DECK_AI_PROVIDER_ERROR_MESSAGE.format(exc.user_message)
        ) from exc

    deck, loaded, report = await service.deck_detail(session, current_user, deck_id)
    return DeckProposalResponse(
        deck=_detail_response(deck, loaded, report),
        explanations=[
            DeckProposalExplanationOut(
                card_id=c.card_id, card_name=c.name, quantity=c.quantity, reason=c.reason
            )
            for c in outcome.result.cards
        ],
        corrections=[
            DeckProposalCorrectionOut(code=c.code, message=c.message)
            for c in outcome.result.corrections
        ],
        summary=outcome.summary,
        provider=outcome.provider,
        model=outcome.model,
        input_tokens=outcome.input_tokens,
        output_tokens=outcome.output_tokens,
    )


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


@router.get(
    "/{deck_id}/cards/{card_id}/replacements", response_model=DeckReplacementsResponse
)
async def deck_card_replacements(
    deck_id: uuid.UUID,
    card_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> DeckReplacementsResponse:
    """Cartes possédées proposées pour remplacer `card_id` dans ce deck, classées par proximité
    (type, rôle, coût d'attaque) avec la raison — aucun appel IA. Un deck ou une carte d'un autre
    utilisateur (ou absente du deck) renvoie 404."""
    try:
        suggestions = await replacements.suggest_replacements(
            session, current_user, deck_id, card_id, limit
        )
    except DeckNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, DECK_NOT_FOUND_MESSAGE) from None
    except DeckCardNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, DECK_CARD_NOT_FOUND_MESSAGE) from None
    return DeckReplacementsResponse(
        card_id=card_id,
        replacements=[
            DeckReplacementItem(
                card_id=s.candidate.traits.card_id,
                number=s.candidate.number,
                name=s.candidate.traits.name,
                set_name=s.candidate.set_name,
                set_code=s.candidate.set_code,
                supertype=s.candidate.traits.supertype,
                hp=s.candidate.hp,
                image_url=s.candidate.image_url,
                owned_count=s.candidate.owned_count,
                reason=s.reason,
            )
            for s in suggestions
        ],
    )


@router.get("/{deck_id}/history", response_model=DeckHistoryResponse)
async def deck_history(
    deck_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> DeckHistoryResponse:
    """Historique des changements de collection ayant touché ce deck. Borné au propriétaire."""
    try:
        deck_name, events = await service.deck_history(session, current_user, deck_id)
    except DeckNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, DECK_NOT_FOUND_MESSAGE) from None
    return DeckHistoryResponse(
        deck_id=deck_id,
        events=[_alert_out(deck_id, deck_name, event) for event in events],
    )


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


def _stats_response(deck_id: uuid.UUID, s: DeckStats) -> DeckStatsOut:
    def buckets(items: list) -> list[DeckStatBucketOut]:
        return [DeckStatBucketOut(key=b.key, label=b.label, count=b.count) for b in items]

    return DeckStatsOut(
        deck_id=deck_id,
        card_count=s.card_count,
        distinct_cards=s.distinct_cards,
        by_supertype=buckets(s.by_supertype),
        by_role=buckets(s.by_role),
        type_distribution=buckets(s.type_distribution),
        untyped_pokemon=s.untyped_pokemon,
        attack_cost_curve=buckets(s.attack_cost_curve),
        attacks_counted=s.attacks_counted,
        average_hp=s.average_hp,
        pokemon_with_hp=s.pokemon_with_hp,
        stage_distribution=buckets(s.stage_distribution),
        has_basic_pokemon=s.has_basic_pokemon,
        evolution_copies_without_base=s.evolution_copies_without_base,
        special_cards=s.special_cards,
        duplicate_copies=s.duplicate_copies,
        duplicate_ratio=s.duplicate_ratio,
        value=DeckValueOut(
            total_eur=s.value.total_eur,
            priced_cards=s.value.priced_cards,
            missing_price_cards=s.value.missing_price_cards,
            priced_copies=s.value.priced_copies,
            counted_copies=s.value.counted_copies,
        ),
    )


@router.get("/{deck_id}/stats", response_model=DeckStatsOut)
async def get_deck_stats(
    deck_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> DeckStatsOut:
    """Agrégats chiffrés d'un deck (mission `v7-decks-stats`) : composition (type de carte, type
    élémentaire, rôle), courbe des coûts d'attaque, PV moyens, structure d'évolution, cartes
    spéciales, valeur marchande et part de doublons. Borné au propriétaire : un deck d'un autre
    utilisateur renvoie 404 (jamais 403). Tous les chiffres viennent du catalogue et de la
    valorisation existante, jamais d'une estimation du modèle (risque du lot)."""
    try:
        _deck, computed = await service.deck_stats(session, current_user, deck_id)
    except DeckNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, DECK_NOT_FOUND_MESSAGE) from None
    return _stats_response(deck_id, computed)
