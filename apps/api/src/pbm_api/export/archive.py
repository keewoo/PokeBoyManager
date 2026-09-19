"""Construction de l'archive ZIP d'export (mission point 1) — pure, sans dépendance à FastAPI,
SQLAlchemy ni au stockage : reçoit des données déjà lues, renvoie des octets. Testable sans
base de données ni backend de stockage.
"""

import csv
import io
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from pbm_api.ai.errors import UnsupportedImageFormatError
from pbm_api.ai.images import detect_media_type

_EXTENSION_BY_MEDIA_TYPE = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
_FALLBACK_EXTENSION = ".bin"

COLLECTION_JSON_NAME = "collection.json"
COLLECTION_CSV_NAME = "collection.csv"
PROFILE_JSON_NAME = "profil.json"
PHOTOS_DIR = "photos"

CSV_FIELDS = [
    "item_id",
    "carte",
    "extension",
    "numero",
    "rarete",
    "langue",
    "variante",
    "etat",
    "prix_achat",
    "devise_achat",
    "acquis_le",
    "valeur_estimee_eur",
    "photo",
]


@dataclass
class ExportCollectionRow:
    item_id: uuid.UUID
    card_name: str
    set_name: str
    set_code: str
    card_number: str
    rarity: str | None
    language: str
    variant: str
    condition_grade: str | None
    purchase_price: Decimal | None
    purchase_currency: str | None
    acquired_at: date | None
    value_eur: Decimal | None
    photo_s3_key: str | None
    created_at: datetime


def _photo_extension(data: bytes) -> str:
    try:
        return _EXTENSION_BY_MEDIA_TYPE[detect_media_type(data)]
    except UnsupportedImageFormatError:
        return _FALLBACK_EXTENSION


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    raise TypeError(f"non sérialisable : {value!r}")


def _row_to_dict(row: ExportCollectionRow) -> dict[str, Any]:
    data = asdict(row)
    data.pop("photo_s3_key")
    data["has_photo"] = row.photo_s3_key is not None
    return data


def _row_to_csv_line(row: ExportCollectionRow, photo_filename: str | None) -> dict[str, str]:
    return {
        "item_id": str(row.item_id),
        "carte": row.card_name,
        "extension": f"{row.set_name} ({row.set_code})",
        "numero": row.card_number,
        "rarete": row.rarity or "",
        "langue": row.language,
        "variante": row.variant,
        "etat": row.condition_grade or "",
        "prix_achat": str(row.purchase_price) if row.purchase_price is not None else "",
        "devise_achat": row.purchase_currency or "",
        "acquis_le": row.acquired_at.isoformat() if row.acquired_at else "",
        "valeur_estimee_eur": str(row.value_eur) if row.value_eur is not None else "",
        "photo": photo_filename or "",
    }


def build_archive(
    profile: dict[str, Any],
    rows: list[ExportCollectionRow],
    photos: dict[uuid.UUID, bytes],
    generated_at: datetime,
) -> bytes:
    """`photos` associe l'id d'un exemplaire aux octets déjà lus depuis le stockage — un
    exemplaire absent du dict n'a simplement pas de photo dans l'archive (ni dans `collection.csv`,
    colonne `photo` vide)."""
    photo_filenames: dict[uuid.UUID, str] = {}
    for item_id, data in photos.items():
        photo_filenames[item_id] = f"{PHOTOS_DIR}/{item_id}{_photo_extension(data)}"

    collection_json = {
        "genere_le": generated_at.isoformat(),
        "cartes": [_row_to_dict(row) for row in rows],
    }

    csv_buffer = io.StringIO()
    writer = csv.DictWriter(csv_buffer, fieldnames=CSV_FIELDS)
    writer.writeheader()
    for row in rows:
        writer.writerow(_row_to_csv_line(row, photo_filenames.get(row.item_id)))

    buffer = io.BytesIO()
    with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED) as zip_file:
        profile_payload = {**profile, "genere_le": generated_at.isoformat()}
        zip_file.writestr(
            PROFILE_JSON_NAME, json.dumps(profile_payload, indent=2, ensure_ascii=False)
        )
        zip_file.writestr(
            COLLECTION_JSON_NAME,
            json.dumps(collection_json, indent=2, ensure_ascii=False, default=_json_default),
        )
        zip_file.writestr(COLLECTION_CSV_NAME, csv_buffer.getvalue())
        for item_id, data in photos.items():
            zip_file.writestr(photo_filenames[item_id], data)

    return buffer.getvalue()
