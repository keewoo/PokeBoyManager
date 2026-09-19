"""Coffre de clés IA. Chaque route dérive l'utilisateur du cookie de session
(`get_current_user`) — jamais d'un identifiant fourni par le client — et toute écriture
exige le jeton CSRF (`require_csrf`), y compris `/test` qui déclenche un appel réseau au
nom de l'utilisateur."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.ai import service
from pbm_api.ai.errors import DefaultProviderWithoutKeyError, ProviderKeyNotFoundError
from pbm_api.ai.providers import ProviderKeyTester, get_provider_key_tester
from pbm_api.ai.schemas import (
    AiKeyResponse,
    AiKeyTestRequest,
    AiKeyTestResponse,
    AiKeyUpsertRequest,
    AiSettingsResponse,
    AiSettingsUpdateRequest,
    AiUsageEntry,
)
from pbm_api.auth.dependencies import get_current_user, require_csrf
from pbm_api.db import get_session
from pbm_api.models import AiCredential, AiProvider, User

router = APIRouter(prefix="/me", tags=["ai-keys"])

PROVIDER_KEY_NOT_FOUND_MESSAGE = "Aucune clé enregistrée pour ce fournisseur."
DEFAULT_PROVIDER_WITHOUT_KEY_MESSAGE = "Enregistrez d'abord une clé pour ce fournisseur."


def _to_key_response(credential: AiCredential) -> AiKeyResponse:
    return AiKeyResponse(
        provider=credential.provider,
        key_mask=credential.key_mask,
        created_at=credential.created_at,
        updated_at=credential.updated_at,
    )


@router.get("/ai-keys", response_model=list[AiKeyResponse])
async def list_ai_keys(
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[AiKeyResponse]:
    credentials = await service.list_keys(db, current_user)
    return [_to_key_response(c) for c in credentials]


@router.put("/ai-keys/{provider}", response_model=AiKeyResponse)
async def upsert_ai_key(
    provider: AiProvider,
    payload: AiKeyUpsertRequest,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
    _csrf: None = Depends(require_csrf),
) -> AiKeyResponse:
    credential = await service.upsert_key(db, current_user, provider, payload.api_key)
    return _to_key_response(credential)


@router.delete("/ai-keys/{provider}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ai_key(
    provider: AiProvider,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
    _csrf: None = Depends(require_csrf),
) -> None:
    try:
        await service.delete_key(db, current_user, provider)
    except ProviderKeyNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, PROVIDER_KEY_NOT_FOUND_MESSAGE) from None


@router.post("/ai-keys/{provider}/test", response_model=AiKeyTestResponse)
async def test_ai_key(
    provider: AiProvider,
    payload: AiKeyTestRequest,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
    tester: ProviderKeyTester = Depends(get_provider_key_tester),
    _csrf: None = Depends(require_csrf),
) -> AiKeyTestResponse:
    try:
        valid, message = await service.test_key(db, current_user, provider, payload.api_key, tester)
    except ProviderKeyNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, PROVIDER_KEY_NOT_FOUND_MESSAGE) from None
    return AiKeyTestResponse(valid=valid, message=message)


@router.get("/ai-settings", response_model=AiSettingsResponse)
async def get_ai_settings(current_user: User = Depends(get_current_user)) -> AiSettingsResponse:
    return AiSettingsResponse(
        default_provider=current_user.ai_default_provider,
        default_model=current_user.ai_default_model,
    )


@router.patch("/ai-settings", response_model=AiSettingsResponse)
async def update_ai_settings(
    payload: AiSettingsUpdateRequest,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
    _csrf: None = Depends(require_csrf),
) -> AiSettingsResponse:
    fields_set = payload.model_fields_set
    try:
        user = await service.update_settings(
            db,
            current_user,
            default_provider=payload.default_provider,
            provider_set="default_provider" in fields_set,
            default_model=payload.default_model,
            model_set="default_model" in fields_set,
        )
    except DefaultProviderWithoutKeyError:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, DEFAULT_PROVIDER_WITHOUT_KEY_MESSAGE
        ) from None
    return AiSettingsResponse(
        default_provider=user.ai_default_provider, default_model=user.ai_default_model
    )


@router.get("/ai-usage", response_model=list[AiUsageEntry])
async def get_ai_usage(
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[AiUsageEntry]:
    rows = await service.list_usage(db, current_user)
    return [
        AiUsageEntry(
            provider=row.provider,
            period=row.period,
            calls_count=row.calls_count,
            tokens_count=row.tokens_count,
            estimated_cost_eur=row.estimated_cost_eur,
        )
        for row in rows
    ]
