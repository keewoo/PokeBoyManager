"""Sème un envoi déjà « identifié » pour l'écran de validation (lot `v3-validation`), sans
worker arq ni clé IA réelle — jamais exécuté par la suite pytest.

L'e2e Playwright (`apps/web/e2e/validation.spec.ts`) fait la partie compte + connexion en vrai
(comme `auth.spec.ts`), mais ne peut pas faire tourner le pipeline réel de reconnaissance
(aucune clé IA réelle disponible sur chimera, voir `docs/ARCHITECTURE.md`) : ce script sème
directement en base — même forme que `_simulate_worker` de `tests/test_validation_routes.py` —
un envoi avec une détection déjà extraite et rapprochée, pour que le navigateur exerce l'écran
de validation lui-même (candidats, confiance, valider/rejeter), pas la détection.

Usage :
    DATABASE_URL=postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v3_validation_e2e \
        uv run python scripts/seed_validation_e2e.py <email>

Affiche l'`upload_id` créé sur stdout (rien d'autre) pour être capturé par le test.
"""

import asyncio
import sys
import uuid

import numpy as np
from sqlalchemy import select

from pbm_api.db import async_session_factory
from pbm_api.detection.annotate import encode_jpeg
from pbm_api.identification.reconciliation import PRESELECTION_THRESHOLD
from pbm_api.models import (
    Card,
    CardName,
    Detection,
    DetectionStatus,
    Set,
    Upload,
    UploadStatus,
    User,
)
from pbm_api.storage import build_storage


def _crop_bytes() -> bytes:
    image = np.zeros((880, 630, 3), dtype=np.uint8)
    image[:] = (60, 90, 180)
    return encode_jpeg(image)


async def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(1)
    email = sys.argv[1]

    async with async_session_factory() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one()

        suffix = uuid.uuid4().hex[:8]
        set_row = Set(code=f"e2e-{suffix}", name="Écarlate et Violet", total_cards=198)
        session.add(set_row)
        await session.flush()
        card = Card(set_id=set_row.id, number="1", name="Sarmuraï")
        session.add(card)
        await session.flush()
        session.add_all(
            [
                CardName(card_id=card.id, language="fr", name="Sarmuraï"),
                CardName(card_id=card.id, language="en", name="Sprigatito"),
            ]
        )

        upload = Upload(
            user_id=user.id,
            s3_key=f"uploads/{user.id}/{uuid.uuid4()}/original",
            original_filename="classeur-page-1.jpg",
            content_type="image/jpeg",
            size_bytes=1024,
            status=UploadStatus.processed,
        )
        session.add(upload)
        await session.flush()

        storage = build_storage()
        await storage.ensure_bucket()
        crop_key = f"uploads/{user.id}/{upload.id}/detections/0.jpg"
        await storage.put(crop_key, _crop_bytes(), "image/jpeg")

        extraction = {
            "name": "Sarmuraï",
            "name_confidence": 0.95,
            "number": "1",
            "number_confidence": 0.95,
            "total": 198,
            "total_confidence": 0.9,
            "set_code": None,
            "set_code_confidence": 0.0,
            "language": "fr",
            "language_confidence": 0.9,
            "hp": 60,
            "hp_confidence": 0.8,
            "card_type": "Pokémon",
            "card_type_confidence": 0.7,
            "variant": "normal",
            "variant_confidence": 0.6,
        }
        candidates = [
            {
                "card_id": str(card.id),
                "set_id": str(set_row.id),
                "name": card.name,
                "number": card.number,
                "set_name": set_row.name,
                "set_code": set_row.code,
                "catalog_score": 1.0,
                "combined_score": PRESELECTION_THRESHOLD + 0.01,
                "preselected": True,
            }
        ]
        session.add(
            Detection(
                upload_id=upload.id,
                bbox={"reading_order": 0, "points": []},
                crop_s3_key=crop_key,
                extraction=extraction,
                candidates=candidates,
                identification_method="ia",
                status=DetectionStatus.pending,
            )
        )
        await session.commit()
        print(str(upload.id))


if __name__ == "__main__":
    asyncio.run(main())
