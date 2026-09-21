"""Import CSV (mission `v6-import-export`) : un job comme la reconnaissance photo
(`pbm_api.detection`/`identification`), qui réutilise le MÊME écran de validation — `Upload` et
`Detection` génériques, la seule différence est l'origine (un fichier CSV plutôt qu'une photo, pas
de recadrage) et le rapprochement, fait directement sur les valeurs saisies plutôt que sur une
extraction IA.

Le rapprochement catalogue est EXACTEMENT le moteur de l'identification
(`pbm_api.identification.reconciliation.reconcile`, mission « risques & pièges » : « même moteur
que l'identification, avec validation ») : chaque ligne devient une `CardExtraction` dont les
champs renseignés portent une confiance de 1,0 (donnée saisie par l'utilisateur, pas lue par une
IA sur une photo) — le même calibrage de présélection s'applique donc, sans code dupliqué.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.config import settings
from pbm_api.identification.reconciliation import reconcile
from pbm_api.identification.schemas import CardExtraction, CardVariantGuess
from pbm_api.imports.errors import ImportFileTooLargeError
from pbm_api.imports.parser import ParsedImportRow, parse_csv
from pbm_api.models import Detection, DetectionStatus, Job, JobStatus, Upload, UploadStatus, User
from pbm_api.storage import StorageBackend
from pbm_api.uploads.errors import UploadNotFoundError
from pbm_api.uploads.service import get_owned_upload

# Types déclarés acceptés à l'envoi : le navigateur n'envoie pas toujours `text/csv` pour un CSV
# (Excel produit parfois `application/vnd.ms-excel`, certains navigateurs `application/octet-
# stream`) — même logique défensive que `pbm_api.uploads.service.ALLOWED_CONTENT_TYPES`, le
# contenu réel (décodage + un en-tête reconnu) fait foi, pas le type déclaré.
ALLOWED_CONTENT_TYPES = frozenset(
    {"text/csv", "application/vnd.ms-excel", "application/octet-stream", "text/plain"}
)

JOB_TYPE = "import_csv"
IMPORT_CONTENT_TYPE = "text/csv"


def _extraction_from_row(row: ParsedImportRow) -> CardExtraction:
    """Confiance à 1,0 sur chaque champ renseigné : une valeur saisie par l'utilisateur dans un
    CSV n'est pas lue avec incertitude comme une photo — c'est ce qui laisse
    `pbm_api.identification.reconciliation` présélectionner un candidat exact sans jamais avoir
    été calibré pour l'import (même seuils que la reconnaissance photo). `variant` réutilise
    directement `CardVariantGuess` (valeurs communes à `PriceVariant` pour les quatre variantes du
    CSV) plutôt qu'un champ à part — jamais un second schéma pour la même idée."""
    variant = row.variant if row.variant in set(CardVariantGuess) else None
    return CardExtraction(
        name=row.name,
        name_confidence=1.0 if row.name else 0.0,
        number=row.number,
        number_confidence=1.0 if row.number else 0.0,
        set_code=row.set_code,
        set_code_confidence=1.0 if row.set_code else 0.0,
        language=row.language,
        language_confidence=1.0 if row.language else 0.0,
        variant=variant,
        variant_confidence=1.0 if variant else 0.0,
    )


def _import_defaults(row: ParsedImportRow) -> dict:
    """Ce que le CSV portait et qu'aucun champ de `CardExtraction` ne représente (quantité, état
    en un mot, prix et date d'achat) : jamais perdu en silence — conservé à côté de l'extraction
    pour préremplir le formulaire de validation (`apps/web`, `detection-card.tsx`)."""
    return {
        "quantity": row.quantity,
        "condition_grade": row.condition_grade,
        "purchase_price": str(row.purchase_price) if row.purchase_price is not None else None,
        "acquired_at": row.acquired_at.isoformat() if row.acquired_at else None,
    }


@dataclass(frozen=True)
class ImportSummary:
    rows_parsed: int
    rows_ignored: int
    ignored_reasons: list[str]
    detections_count: int


async def create_import(
    db: AsyncSession, user: User, storage: StorageBackend, filename: str, data: bytes
) -> tuple[Upload, Job]:
    if len(data) > settings.import_csv_max_size_bytes:
        raise ImportFileTooLargeError

    await storage.ensure_bucket()
    upload_id = uuid.uuid4()
    s3_key = f"imports/{user.id}/{upload_id}.csv"
    upload = Upload(
        id=upload_id,
        user_id=user.id,
        s3_key=s3_key,
        original_filename=filename,
        content_type=IMPORT_CONTENT_TYPE,
        size_bytes=len(data),
        status=UploadStatus.processing,
    )
    db.add(upload)
    await storage.put(s3_key, data, IMPORT_CONTENT_TYPE)

    job = Job(
        type=JOB_TYPE,
        status=JobStatus.queued,
        user_id=user.id,
        payload={"upload_id": str(upload.id)},
    )
    db.add(job)
    await db.commit()
    await db.refresh(upload)
    await db.refresh(job)
    return upload, job


async def get_owned_import(db: AsyncSession, user: User, upload_id: uuid.UUID) -> Upload:
    upload = await get_owned_upload(db, user, upload_id)
    if upload.content_type != IMPORT_CONTENT_TYPE:
        # Un `upload_id` de photo présenté à une route d'import (ou l'inverse) : jamais traité
        # comme le mauvais type d'envoi, une 404 comme n'importe quel id qui ne correspond pas.
        raise UploadNotFoundError
    return upload


async def run_import_for_upload(
    db: AsyncSession, storage: StorageBackend, upload: Upload
) -> ImportSummary:
    existing = (
        await db.execute(
            select(func.count()).select_from(Detection).where(Detection.upload_id == upload.id)
        )
    ).scalar_one()
    if existing:
        # Reprise (même principe que `pbm_api.worker._detect_identify_state`) : un passage
        # précédent a déjà créé les détections (job repris après un blocage) — on ne les recrée
        # jamais, ça les dupliquerait.
        upload.status = UploadStatus.processed
        await db.commit()
        return ImportSummary(
            rows_parsed=existing, rows_ignored=0, ignored_reasons=[], detections_count=existing
        )

    data = await storage.get(upload.s3_key)
    if data is None:
        raise UploadNotFoundError

    result = parse_csv(data, max_rows=settings.import_csv_max_rows)

    detections_count = 0
    for index, row in enumerate(result.rows):
        extraction = _extraction_from_row(row)
        reconciliation = await reconcile(db, extraction)
        extraction_payload = extraction.model_dump(mode="json")
        extraction_payload["import_defaults"] = _import_defaults(row)
        db.add(
            Detection(
                upload_id=upload.id,
                bbox={"reading_order": index, "source_line": row.line_number},
                crop_s3_key=None,
                extraction=extraction_payload,
                candidates=[c.model_dump() for c in reconciliation.candidates],
                identification_method="import",
                status=DetectionStatus.pending,
            )
        )
        detections_count += 1
        await db.commit()

    upload.status = UploadStatus.processed
    await db.commit()

    return ImportSummary(
        rows_parsed=len(result.rows),
        rows_ignored=len(result.ignored),
        ignored_reasons=[f"ligne {line}: {reason}" for line, reason in result.ignored[:20]],
        detections_count=detections_count,
    )
