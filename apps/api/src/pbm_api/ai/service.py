"""Logique métier du coffre de clés IA — indépendante de FastAPI (testable directement).

Toute lecture/écriture part d'un `User` déjà authentifié par la dépendance de session :
aucune fonction ici n'accepte de `user_id` fourni par l'appelant pour un tiers.
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.ai.base import ExtractionUsage
from pbm_api.ai.errors import DefaultProviderWithoutKeyError, ProviderKeyNotFoundError
from pbm_api.ai.providers import ProviderKeyTester
from pbm_api.models import AiCredential, AiProvider, AiUsageMonthly, User
from pbm_api.security.crypto import decrypt_api_key, encrypt_api_key, mask_api_key


async def list_keys(db: AsyncSession, user: User) -> list[AiCredential]:
    result = await db.execute(select(AiCredential).where(AiCredential.user_id == user.id))
    return list(result.scalars().all())


async def _get_credential(
    db: AsyncSession, user: User, provider: AiProvider
) -> AiCredential | None:
    result = await db.execute(
        select(AiCredential).where(
            AiCredential.user_id == user.id, AiCredential.provider == provider
        )
    )
    return result.scalar_one_or_none()


async def upsert_key(
    db: AsyncSession, user: User, provider: AiProvider, api_key: str
) -> AiCredential:
    encrypted_key, nonce = encrypt_api_key(api_key, user.id)
    key_mask = mask_api_key(api_key)

    credential = await _get_credential(db, user, provider)
    if credential is None:
        credential = AiCredential(user_id=user.id, provider=provider)
        db.add(credential)
    credential.encrypted_key = encrypted_key
    credential.nonce = nonce
    credential.key_mask = key_mask
    await db.commit()
    await db.refresh(credential)
    return credential


async def delete_key(db: AsyncSession, user: User, provider: AiProvider) -> None:
    credential = await _get_credential(db, user, provider)
    if credential is None:
        raise ProviderKeyNotFoundError
    await db.delete(credential)
    await db.commit()


async def test_key(
    db: AsyncSession,
    user: User,
    provider: AiProvider,
    api_key: str | None,
    tester: ProviderKeyTester,
) -> tuple[bool, str]:
    """Teste `api_key` s'il est fourni (avant enregistrement), sinon la clé déjà stockée."""
    if api_key is not None:
        return await tester.test(provider, api_key)

    credential = await _get_credential(db, user, provider)
    if credential is None:
        raise ProviderKeyNotFoundError
    decrypted = decrypt_api_key(credential.encrypted_key, credential.nonce, user.id)
    return await tester.test(provider, decrypted)


async def update_settings(
    db: AsyncSession,
    user: User,
    *,
    default_provider: AiProvider | None,
    provider_set: bool,
    default_model: str | None,
    model_set: bool,
) -> User:
    if provider_set:
        if default_provider is not None:
            credential = await _get_credential(db, user, default_provider)
            if credential is None:
                raise DefaultProviderWithoutKeyError
        user.ai_default_provider = default_provider
    if model_set:
        user.ai_default_model = default_model
    await db.commit()
    await db.refresh(user)
    return user


async def get_default_credential(db: AsyncSession, user: User) -> tuple[AiProvider, str] | None:
    """Fournisseur + clé déchiffrée à utiliser pour un appel du worker (mission `v3-detection`,
    repli LLM) : le fournisseur par défaut de l'utilisateur s'il a une clé, sinon la première
    clé enregistrée (`AiCredential`, ordre non garanti — un seul fournisseur suffit ici, le
    choix explicite reste `ai_default_provider`, réglable via `PATCH /me/ai-settings`)."""
    if user.ai_default_provider is not None:
        credential = await _get_credential(db, user, user.ai_default_provider)
        if credential is not None:
            decrypted = decrypt_api_key(credential.encrypted_key, credential.nonce, user.id)
            return credential.provider, decrypted

    credentials = await list_keys(db, user)
    if not credentials:
        return None
    credential = credentials[0]
    decrypted = decrypt_api_key(credential.encrypted_key, credential.nonce, user.id)
    return credential.provider, decrypted


async def record_usage(db: AsyncSession, user: User, usage: ExtractionUsage) -> None:
    """Alimente `ai_usage_monthly` (mission `v2-prix`/`v1-byok` : table posée, lecture seule
    jusqu'ici) à chaque appel réel au fournisseur — premier appelant : le repli LLM de la
    détection (mission `v3-detection`). `estimated_cost_eur` reste à 0 : aucune table de
    tarification par modèle n'existe encore dans ce dépôt (reste à faire, hors périmètre de ce
    lot), seuls les compteurs d'appels et de jetons sont fiables aujourd'hui."""
    period = date.today().replace(day=1)
    result = await db.execute(
        select(AiUsageMonthly).where(
            AiUsageMonthly.user_id == user.id,
            AiUsageMonthly.provider == usage.provider,
            AiUsageMonthly.period == period,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        # `calls_count`/`tokens_count` par défaut (0) ne sont posés par SQLAlchemy qu'à l'insert
        # (`server_default`/`default` côté colonne) : les fixer ici évite un `None += 1` avant
        # tout flush.
        row = AiUsageMonthly(
            user_id=user.id, provider=usage.provider, period=period, calls_count=0, tokens_count=0
        )
        db.add(row)
    row.calls_count += 1
    row.tokens_count += usage.input_tokens + usage.output_tokens
    await db.commit()


async def list_usage(db: AsyncSession, user: User) -> list[AiUsageMonthly]:
    result = await db.execute(
        select(AiUsageMonthly)
        .where(AiUsageMonthly.user_id == user.id)
        .order_by(AiUsageMonthly.period.desc(), AiUsageMonthly.provider)
    )
    return list(result.scalars().all())
