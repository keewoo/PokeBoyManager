"""Logique métier de l'export RGPD (mission `v5-rgpd` point 1), indépendante de FastAPI.

`create_export` pose la ligne `DataExport` (`queued`) ; `run_export` fait le travail réel
(archive, envoi, jeton) et est appelée depuis `pbm_api.worker.export_user_data_task`, mis en
file par `POST /me/export` — même schéma que `detect_cards_task` (mission `v3-detection`,
`pbm_api.queue.get_arq_pool`, premier job du dépôt enfilé depuis une route HTTP). Le worker
arq n'étant pas démarré en tests (comme pour `detect_cards_task`), les tests appellent
`run_export` directement pour simuler ce que ferait le worker.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.config import settings
from pbm_api.email import EmailSender
from pbm_api.export.archive import ExportCollectionRow, build_archive
from pbm_api.export.errors import (
    ExportArchiveMissingError,
    ExportNotFoundError,
    ExportTokenInvalidError,
)
from pbm_api.models import Card, CollectionItem, DataExport, JobStatus, Set, User
from pbm_api.pricing.valuation import item_value
from pbm_api.security.tokens import generate_opaque_token, hash_token
from pbm_api.storage import StorageBackend

EXPORT_TOKEN_TTL_HOURS = 24
EXPORT_READY_SUBJECT = "Ton export PokeBoyManager est prêt"


def _utc_now_naive() -> datetime:
    """Comme `pbm_api.auth.service._utc_now_naive` : `data_exports.expires_at` est en
    `TIMESTAMP WITHOUT TIME ZONE`, toujours en UTC, jamais "aware"."""
    return datetime.now(UTC).replace(tzinfo=None)


async def _collection_rows(session: AsyncSession, user_id: uuid.UUID) -> list[ExportCollectionRow]:
    result = await session.execute(
        select(CollectionItem, Card, Set)
        .join(Card, Card.id == CollectionItem.card_id)
        .join(Set, Set.id == Card.set_id)
        .where(CollectionItem.user_id == user_id)
        .order_by(CollectionItem.created_at)
    )
    rows: list[ExportCollectionRow] = []
    for item, card, card_set in result.all():
        value_eur = await item_value(session, item, currency="EUR")
        rows.append(
            ExportCollectionRow(
                item_id=item.id,
                card_name=card.name,
                set_name=card_set.name,
                set_code=card_set.code,
                card_number=card.number,
                rarity=card.rarity,
                language=item.language,
                variant=item.variant.value,
                condition_grade=item.condition_grade,
                purchase_price=item.purchase_price,
                purchase_currency=item.purchase_currency,
                acquired_at=item.acquired_at,
                value_eur=value_eur,
                photo_s3_key=item.photo_s3_key,
                created_at=item.created_at,
            )
        )
    return rows


async def create_export(db: AsyncSession, user: User) -> DataExport:
    export = DataExport(user_id=user.id, status=JobStatus.queued)
    db.add(export)
    await db.commit()
    await db.refresh(export)
    return export


async def run_export(
    db: AsyncSession,
    storage: StorageBackend,
    email_sender: EmailSender,
    user: User,
    export: DataExport,
) -> DataExport:
    """Exécute l'export : jamais d'échec silencieux — un statut `failed` porte toujours un
    message dans `error`, jamais un succès rendu alors que l'archive n'a pas été écrite."""
    export.status = JobStatus.running
    await db.commit()

    try:
        rows = await _collection_rows(db, user.id)
        photos: dict[uuid.UUID, bytes] = {}
        for row in rows:
            if row.photo_s3_key is None:
                continue
            data = await storage.get(row.photo_s3_key)
            if data is not None:
                photos[row.item_id] = data

        generated_at = datetime.now(UTC)
        profile = {
            "email": user.email,
            "pseudo": user.pseudo,
            "prenom": user.first_name,
            "nom": user.last_name,
            "date_de_naissance": user.birth_date.isoformat(),
            "compte_cree_le": user.created_at.isoformat(),
        }
        archive_bytes = build_archive(profile, rows, photos, generated_at)

        storage_key = f"exports/{user.id}/{export.id}.zip"
        await storage.ensure_bucket()
        await storage.put(storage_key, archive_bytes, "application/zip")

        raw_token = generate_opaque_token()
        export.storage_key = storage_key
        export.token_hash = hash_token(raw_token)
        export.expires_at = _utc_now_naive() + timedelta(hours=EXPORT_TOKEN_TTL_HOURS)
        export.status = JobStatus.succeeded
        export.completed_at = _utc_now_naive()
        await db.commit()

        link = f"{settings.api_public_url}/export/download?token={raw_token}"
        await email_sender.send(
            user.email,
            EXPORT_READY_SUBJECT,
            "Ton export PokeBoyManager (collection + photos) est prêt.\n\n"
            f"Télécharge-le ici : {link}\n"
            f"Ce lien expire dans {EXPORT_TOKEN_TTL_HOURS} heures.",
        )
    except Exception as exc:
        # Comme `pbm_api.worker._run_import` : un échec devient un `DataExport` en `failed`,
        # jamais une exception qui remonte au client (pas de 500 pour une panne déjà consignée).
        export.status = JobStatus.failed
        export.error = str(exc)
        export.completed_at = _utc_now_naive()
        await db.commit()

    return export


async def get_owned_export(db: AsyncSession, user: User, export_id: uuid.UUID) -> DataExport:
    result = await db.execute(
        select(DataExport).where(DataExport.id == export_id, DataExport.user_id == user.id)
    )
    export = result.scalar_one_or_none()
    if export is None:
        raise ExportNotFoundError
    return export


async def download_by_token(
    db: AsyncSession, storage: StorageBackend, token: str
) -> tuple[DataExport, bytes]:
    result = await db.execute(select(DataExport).where(DataExport.token_hash == hash_token(token)))
    export = result.scalar_one_or_none()
    if (
        export is None
        or export.status != JobStatus.succeeded
        or export.expires_at is None
        or export.expires_at < _utc_now_naive()
    ):
        raise ExportTokenInvalidError

    data = await storage.get(export.storage_key) if export.storage_key else None
    if data is None:
        raise ExportArchiveMissingError
    return export, data
