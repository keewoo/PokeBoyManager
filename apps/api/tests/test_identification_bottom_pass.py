"""Seconde passe ciblée sur le bas de la carte (lot `pbm-parcours-validation`, mission point 4).

Quand le premier appel IA n'a pas lu de numéro fiable, une bande AGRANDIE du bas du recadrage est
relue pour en extraire numéro / total / code d'extension — c'est ce qui fait passer une carte du
palier « nom seul » (jamais présélectionné) au palier « numéro + nom » (présélectionnable). Le
gain se mesure aussi sur une vraie clé (`scripts/measure_identification_rate.py`), hors de portée
de chimera : ici on vérifie le déclenchement, la fusion et l'orchestration de bout en bout avec un
fournisseur stub qui répond différemment selon le schéma demandé.
"""

import json
import uuid
from datetime import date, datetime

import cv2
import numpy as np
import pytest
from sqlalchemy import select

from pbm_api.ai.base import AIProvider, ExtractionUsage, ImageInput, T
from pbm_api.ai.service import upsert_key
from pbm_api.detection.service import run_detection_for_upload
from pbm_api.detection.synthetic import make_single_card
from pbm_api.identification.extraction import (
    bottom_strip,
    merge_bottom_reading,
    needs_bottom_pass,
)
from pbm_api.identification.schemas import CardBottomReading, CardExtraction
from pbm_api.identification.service import run_identification_for_upload
from pbm_api.models import AiProvider, Card, CardName, Detection, Set, Upload, UploadStatus, User
from pbm_api.s3 import ObjectStorage

AI_KEY = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789"


# --- Unités : déclenchement, découpe, fusion -------------------------------------------------


def test_needs_bottom_pass_only_when_number_is_empty():
    assert needs_bottom_pass(CardExtraction(name="Mew"))  # numéro absent
    assert needs_bottom_pass(CardExtraction(name="Mew", number=""))  # chaîne vide
    # Un numéro présent, même peu sûr, ne déclenche PAS : il est déjà utilisé par le rapprochement,
    # et une lecture globale douteuse est rattrapée par le secours vision. Ne pas empiler un appel
    # sur le chemin bas-confiance (sinon les tests de `test_identification_rescue` cassent).
    assert not needs_bottom_pass(
        CardExtraction(name="Mew", number="12", number_confidence=0.3)
    )
    assert not needs_bottom_pass(
        CardExtraction(name="Mew", number="12", number_confidence=0.9)
    )
    # Un code d'extension manquant ne suffit pas non plus (trop de cartes n'en impriment aucun).
    assert not needs_bottom_pass(
        CardExtraction(name="Mew", number="12", number_confidence=0.9, set_code=None)
    )


def test_bottom_strip_isolates_and_enlarges_the_bottom_band():
    crop = np.zeros((880, 630, 3), dtype=np.uint8)
    y0 = int(round(880 * (1 - 0.22)))
    strip = bottom_strip(crop)
    assert strip.shape[1] == 630 * 3
    assert strip.shape[0] == (880 - y0) * 3


def test_merge_bottom_reading_fills_missing_number_and_set_code():
    base = CardExtraction(name="Mew", name_confidence=0.9)
    bottom = CardBottomReading(
        number="151", number_confidence=0.8, set_code="MEW", set_code_confidence=0.7
    )
    merged = merge_bottom_reading(base, bottom)
    assert merged.number == "151"
    assert merged.number_confidence == 0.8
    assert merged.set_code == "MEW"
    assert merged.name == "Mew"  # champs du premier appel intacts


def test_merge_bottom_reading_never_overrides_a_more_confident_field():
    base = CardExtraction(name="X", number="1", number_confidence=0.95)
    bottom = CardBottomReading(number="999", number_confidence=0.3)
    merged = merge_bottom_reading(base, bottom)
    assert merged.number == "1"  # lecture sûre conservée, jamais écrasée par une lecture douteuse


# --- Bout en bout : le second appel améliore le rapprochement --------------------------------


class _SchemaAwareStub(AIProvider):
    """Répond selon le schéma demandé : pas de numéro sur `CardExtraction` (premier appel), un
    numéro sur `CardBottomReading` (seconde passe ciblée)."""

    PROVIDER = AiProvider.anthropic
    DEFAULT_MODEL = "stub-vision"

    def __init__(self, extraction_payload: dict, bottom_payload: dict, **_ignored) -> None:
        super().__init__(api_key="unused")
        self._extraction = extraction_payload
        self._bottom = bottom_payload
        self.calls = 0
        self.schemas: list[str] = []

    async def _call(
        self, images: list[ImageInput], schema: type[T], prompt: str, model: str, retry_hint
    ) -> tuple[str, ExtractionUsage]:
        self.calls += 1
        self.schemas.append(schema.__name__)
        payload = self._bottom if schema is CardBottomReading else self._extraction
        return (
            json.dumps(payload),
            ExtractionUsage(provider=self.PROVIDER, model=model, input_tokens=10, output_tokens=5),
        )


def _encode(image) -> bytes:
    ok, buffer = cv2.imencode(".jpg", image)
    assert ok
    return buffer.tobytes()


@pytest.fixture
async def storage():
    object_storage = ObjectStorage()
    await object_storage.ensure_bucket()
    return object_storage


async def _seed_raichu_026(db_session) -> Card:
    suffix = uuid.uuid4().hex[:8]
    set_row = Set(code=f"sv02-{suffix}", name="Évolutions à Paldea", total_cards=200)
    db_session.add(set_row)
    await db_session.flush()
    card = Card(set_id=set_row.id, number="026", name="Raichu")
    db_session.add(card)
    await db_session.flush()
    db_session.add_all(
        [
            CardName(card_id=card.id, language="fr", name="Raichu"),
            CardName(card_id=card.id, language="en", name="Raichu"),
        ]
    )
    await db_session.flush()
    return card


async def _make_upload(db_session, storage, image_bytes: bytes) -> tuple[Upload, User]:
    user = User(
        email=f"bottom-{uuid.uuid4()}@example.com",
        password_hash="x",
        last_name="Test",
        birth_date=date(2000, 1, 1),
        terms_version="test",
        terms_accepted_at=datetime(2000, 1, 1),
    )
    db_session.add(user)
    await db_session.flush()
    upload = Upload(
        user_id=user.id,
        s3_key=f"uploads/{user.id}/{uuid.uuid4()}/original",
        original_filename="photo.jpg",
        content_type="image/jpeg",
        size_bytes=len(image_bytes),
        status=UploadStatus.processed,
    )
    db_session.add(upload)
    await db_session.flush()
    await storage.put(upload.s3_key, image_bytes, "image/jpeg")
    return upload, user


async def test_bottom_pass_reads_number_and_upgrades_the_match(db_session, storage, monkeypatch):
    """Premier appel : nom lu (« Raichu »), numéro illisible → palier « nom seul », non
    présélectionné. Seconde passe : le numéro « 026 » est lu sur le bas agrandi → palier
    « numéro + nom », candidat unique, présélectionné. Deux appels IA au total."""
    card = await _seed_raichu_026(db_session)
    photo = make_single_card(seed=41, index=0)
    upload, user = await _make_upload(db_session, storage, _encode(photo.image))
    await upsert_key(db_session, user, AiProvider.anthropic, AI_KEY)
    await run_detection_for_upload(db_session, storage, upload)

    stub = _SchemaAwareStub(
        extraction_payload={
            "name": "Raichu",
            "name_confidence": 0.9,
            "number": None,
            "number_confidence": 0.0,
            "language": "fr",
            "language_confidence": 0.9,
        },
        bottom_payload={
            "number": "026",
            "number_confidence": 0.9,
            "set_code": None,
            "set_code_confidence": 0.0,
            "total": None,
            "total_confidence": 0.0,
        },
    )
    monkeypatch.setattr(
        "pbm_api.identification.service.create_provider", lambda *a, **k: stub
    )

    summary = await run_identification_for_upload(db_session, storage, upload)

    assert stub.calls == 2
    assert "CardBottomReading" in stub.schemas
    assert summary.ai_calls == 2

    detection = (
        await db_session.execute(select(Detection).where(Detection.upload_id == upload.id))
    ).scalar_one()
    assert detection.extraction["number"] == "026"
    assert detection.candidates[0]["card_id"] == str(card.id)
    assert detection.candidates[0]["preselected"] is True
