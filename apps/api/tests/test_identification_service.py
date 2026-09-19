"""`pbm_api.identification.service.run_identification_for_upload` (mission `v3-identification`,
étendue par `v3-identification-visuelle` — comparaison à l'index visuel avant tout appel IA) :
orchestration DB/stockage appelée par le worker juste après la détection
(`pbm_api.worker.detect_cards_task`) — logique indépendante d'arq, testable directement, comme
`pbm_api.detection.service.run_detection_for_upload`.

Avant ce lot, `pbm_api.identification.service` n'existait pas : chacun de ces tests échoue à la
collection et passe une fois le fichier ajouté.
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
from pbm_api.identification.fingerprint import compute_phash
from pbm_api.identification.service import run_identification_for_upload
from pbm_api.identification.visual_geometry import illustration_region
from pbm_api.models import (
    AiProvider,
    AiUsageMonthly,
    Card,
    CardName,
    Detection,
    Set,
    Upload,
    UploadStatus,
    User,
)
from pbm_api.models.identification import CardVisualIndex
from pbm_api.s3 import ObjectStorage

AI_KEY = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789"

STUB_PAYLOAD = {
    "name": "Sarmuraï",
    "name_confidence": 0.9,
    "number": "1",
    "number_confidence": 0.9,
    "total": None,
    "total_confidence": 0.0,
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


class _StubCardExtractionProvider(AIProvider):
    PROVIDER = AiProvider.anthropic
    DEFAULT_MODEL = "stub-vision"

    def __init__(self, payload: dict, **_ignored) -> None:
        super().__init__(api_key="unused")
        self._payload = payload
        self.calls = 0
        self.last_prompt: str | None = None

    async def _call(
        self, images: list[ImageInput], schema: type[T], prompt: str, model: str, retry_hint
    ) -> tuple[str, ExtractionUsage]:
        self.calls += 1
        self.last_prompt = prompt
        return (
            json.dumps(self._payload),
            ExtractionUsage(provider=self.PROVIDER, model=model, input_tokens=40, output_tokens=20),
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


async def _make_upload(db_session, storage, image_bytes: bytes) -> tuple[Upload, User]:
    user = User(
        email=f"ident-{uuid.uuid4()}@example.com",
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


async def _seed_sarmurai(db_session) -> Card:
    suffix = uuid.uuid4().hex[:8]
    set_row = Set(code=f"sv01-{suffix}", name="Écarlate et Violet", total_cards=198)
    db_session.add(set_row)
    await db_session.flush()
    card = Card(set_id=set_row.id, number="1", name="Sarmuraï")
    db_session.add(card)
    await db_session.flush()
    db_session.add_all(
        [
            CardName(card_id=card.id, language="fr", name="Sarmuraï"),
            CardName(card_id=card.id, language="en", name="Sprigatito"),
        ]
    )
    await db_session.flush()
    return card


async def test_run_identification_for_upload_calls_ai_and_stores_result(
    db_session, storage, monkeypatch
):
    card = await _seed_sarmurai(db_session)
    photo = make_single_card(seed=7, index=0)
    upload, user = await _make_upload(db_session, storage, _encode(photo.image))
    await upsert_key(db_session, user, AiProvider.anthropic, AI_KEY)
    await run_detection_for_upload(db_session, storage, upload)

    stub = _StubCardExtractionProvider(STUB_PAYLOAD)
    monkeypatch.setattr(
        "pbm_api.identification.service.create_provider", lambda *args, **kwargs: stub
    )

    summary = await run_identification_for_upload(db_session, storage, upload)

    assert summary.identified_count == 1
    assert summary.ai_calls == 1
    assert summary.cache_hits == 0
    assert stub.calls == 1

    result = await db_session.execute(select(Detection).where(Detection.upload_id == upload.id))
    detection = result.scalar_one()
    assert detection.extraction["name"] == "Sarmuraï"
    assert detection.candidates
    assert detection.candidates[0]["card_id"] == str(card.id)

    usage_result = await db_session.execute(
        select(AiUsageMonthly).where(AiUsageMonthly.user_id == user.id)
    )
    usage = usage_result.scalar_one()
    assert usage.calls_count == 1
    assert usage.tokens_count == 60


async def test_run_identification_for_upload_reuses_cache_for_same_crop(
    db_session, storage, monkeypatch
):
    """Mission point 4 : la même carte rephotographiée (empreinte identique du recadrage) ne
    rappelle jamais l'IA, même pour un envoi et un utilisateur différents (cache partagé, comme
    `card_insights`)."""
    await _seed_sarmurai(db_session)
    photo = make_single_card(seed=11, index=0)
    image_bytes = _encode(photo.image)

    stub = _StubCardExtractionProvider(STUB_PAYLOAD)
    monkeypatch.setattr(
        "pbm_api.identification.service.create_provider", lambda *args, **kwargs: stub
    )

    upload_1, user_1 = await _make_upload(db_session, storage, image_bytes)
    await upsert_key(db_session, user_1, AiProvider.anthropic, AI_KEY)
    await run_detection_for_upload(db_session, storage, upload_1)
    summary_1 = await run_identification_for_upload(db_session, storage, upload_1)
    assert summary_1.ai_calls == 1

    upload_2, user_2 = await _make_upload(db_session, storage, image_bytes)
    await upsert_key(db_session, user_2, AiProvider.anthropic, AI_KEY)
    await run_detection_for_upload(db_session, storage, upload_2)
    summary_2 = await run_identification_for_upload(db_session, storage, upload_2)

    assert summary_2.ai_calls == 0
    assert summary_2.cache_hits == 1
    assert stub.calls == 1  # un seul appel IA au total pour les deux envois

    result = await db_session.execute(select(Detection).where(Detection.upload_id == upload_2.id))
    detection_2 = result.scalar_one()
    assert detection_2.extraction["name"] == "Sarmuraï"


async def test_run_identification_for_upload_without_ai_key_leaves_detection_unidentified(
    db_session, storage
):
    """D4 : sans clé IA, la reconnaissance reste désactivée — `detect_cards` n'est jamais mis en
    file dans ce cas (`pbm_api.uploads.service.complete_upload`), mais si ce service était tout
    de même appelé (ex: clé retirée entre la détection et l'identification), il ne doit jamais
    lever, juste ne rien identifier."""
    photo = make_single_card(seed=13, index=0)
    upload, _user = await _make_upload(db_session, storage, _encode(photo.image))
    await run_detection_for_upload(db_session, storage, upload)

    summary = await run_identification_for_upload(db_session, storage, upload)

    assert summary == type(summary)(identified_count=0, cache_hits=0, ai_calls=0)
    result = await db_session.execute(select(Detection).where(Detection.upload_id == upload.id))
    detection = result.scalar_one()
    assert detection.extraction is None
    assert detection.candidates is None


async def _visual_hashes_for_detection(storage, detection: Detection) -> tuple[int, int]:
    crop_bytes = await storage.get(detection.crop_s3_key)
    crop = cv2.imdecode(np.frombuffer(crop_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    return compute_phash(crop), compute_phash(illustration_region(crop))


async def test_run_identification_for_upload_resolves_via_visual_index_without_ai_call(
    db_session, storage, monkeypatch
):
    """Mission `v3-identification-visuelle` point 2-4 : une correspondance visuelle confiante
    identifie la carte sans jamais appeler l'IA — même quand une clé est configurée (elle ne
    doit tout simplement pas servir)."""
    card = await _seed_sarmurai(db_session)
    photo = make_single_card(seed=21, index=0)
    upload, user = await _make_upload(db_session, storage, _encode(photo.image))
    await upsert_key(db_session, user, AiProvider.anthropic, AI_KEY)
    await run_detection_for_upload(db_session, storage, upload)

    detection = (
        await db_session.execute(select(Detection).where(Detection.upload_id == upload.id))
    ).scalar_one()
    full_phash, illustration_phash = await _visual_hashes_for_detection(storage, detection)
    db_session.add(
        CardVisualIndex(
            card_id=card.id,
            language="fr",
            full_phash=full_phash,
            illustration_phash=illustration_phash,
        )
    )
    await db_session.flush()

    stub = _StubCardExtractionProvider(STUB_PAYLOAD)
    monkeypatch.setattr(
        "pbm_api.identification.service.create_provider", lambda *args, **kwargs: stub
    )

    summary = await run_identification_for_upload(db_session, storage, upload)

    assert summary.ai_calls == 0
    assert summary.visual_matches == 1
    assert summary.identified_count == 1
    assert stub.calls == 0  # jamais appelée : la comparaison visuelle a suffi

    await db_session.refresh(detection)
    assert detection.identification_method == "visuel"
    assert detection.extraction["name"] == "Sarmuraï"
    assert detection.candidates[0]["card_id"] == str(card.id)
    assert detection.candidates[0]["preselected"] is True


async def test_run_identification_for_upload_falls_back_to_ai_when_visual_match_is_ambiguous(
    db_session, storage, monkeypatch
):
    """Groupe « même illustration » (mission « risques & pièges ») : deux cartes distinctes
    indexées avec la même empreinte que la photo — la comparaison visuelle ne tranche jamais
    seule, l'IA est appelée avec les deux candidats en indice (mission point 3)."""
    card = await _seed_sarmurai(db_session)
    other_set = Set(code=f"other-{uuid.uuid4().hex[:8]}", name="Autre extension", total_cards=50)
    db_session.add(other_set)
    await db_session.flush()
    other_card = Card(set_id=other_set.id, number="2", name="Autre carte")
    db_session.add(other_card)
    await db_session.flush()

    photo = make_single_card(seed=23, index=0)
    upload, user = await _make_upload(db_session, storage, _encode(photo.image))
    await upsert_key(db_session, user, AiProvider.anthropic, AI_KEY)
    await run_detection_for_upload(db_session, storage, upload)

    detection = (
        await db_session.execute(select(Detection).where(Detection.upload_id == upload.id))
    ).scalar_one()
    full_phash, illustration_phash = await _visual_hashes_for_detection(storage, detection)
    db_session.add_all(
        [
            CardVisualIndex(
                card_id=card.id,
                language="fr",
                full_phash=full_phash,
                illustration_phash=illustration_phash,
            ),
            CardVisualIndex(
                card_id=other_card.id,
                language="fr",
                full_phash=full_phash,
                illustration_phash=illustration_phash,
            ),
        ]
    )
    await db_session.flush()

    stub = _StubCardExtractionProvider(STUB_PAYLOAD)
    monkeypatch.setattr(
        "pbm_api.identification.service.create_provider", lambda *args, **kwargs: stub
    )

    summary = await run_identification_for_upload(db_session, storage, upload)

    assert summary.ai_calls == 1
    assert summary.visual_matches == 0
    assert stub.calls == 1
    assert stub.last_prompt is not None
    assert "Sarmuraï" in stub.last_prompt
    assert "Autre carte" in stub.last_prompt

    await db_session.refresh(detection)
    assert detection.identification_method == "ia"


async def test_run_identification_for_upload_exposes_ambiguous_visual_candidates_without_ai_key(
    db_session, storage
):
    """D4 étendu par ce lot : sans clé IA, une comparaison visuelle ambiguë propose tout de même
    ses candidats à la validation humaine, plutôt que de ne rien montrer du tout."""
    card = await _seed_sarmurai(db_session)
    other_set = Set(code=f"other-{uuid.uuid4().hex[:8]}", name="Autre extension", total_cards=50)
    db_session.add(other_set)
    await db_session.flush()
    other_card = Card(set_id=other_set.id, number="2", name="Autre carte")
    db_session.add(other_card)
    await db_session.flush()

    photo = make_single_card(seed=29, index=0)
    upload, _user = await _make_upload(db_session, storage, _encode(photo.image))
    await run_detection_for_upload(db_session, storage, upload)

    detection = (
        await db_session.execute(select(Detection).where(Detection.upload_id == upload.id))
    ).scalar_one()
    full_phash, illustration_phash = await _visual_hashes_for_detection(storage, detection)
    db_session.add_all(
        [
            CardVisualIndex(
                card_id=card.id,
                language="fr",
                full_phash=full_phash,
                illustration_phash=illustration_phash,
            ),
            CardVisualIndex(
                card_id=other_card.id,
                language="fr",
                full_phash=full_phash,
                illustration_phash=illustration_phash,
            ),
        ]
    )
    await db_session.flush()

    summary = await run_identification_for_upload(db_session, storage, upload)

    assert summary.ai_calls == 0
    assert summary.identified_count == 0  # aucune extraction : rien n'a été "lu" avec certitude

    await db_session.refresh(detection)
    assert detection.identification_method == "aucun"
    assert detection.extraction is None
    assert {c["card_id"] for c in detection.candidates} == {str(card.id), str(other_card.id)}
    assert all(c["preselected"] is False for c in detection.candidates)
