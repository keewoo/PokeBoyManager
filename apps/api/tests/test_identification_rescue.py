"""Secours IA vision de l'identification (`pbm-hotfix-fallback-ia-confiance`, demande JF
20/09/2026) : sous 75 % de score combiné, la découpe est refaite par le LLM vision
(`pbm_api.identification.rescue.recrop_with_llm`) et l'identification rejouée sur le nouveau
recadrage — le meilleur des deux essais est conservé, le cache d'empreinte ne stocke ni ne
ressert jamais un résultat sous le seuil quand une clé IA permet de retenter mieux.

Avant ce correctif, `_identify_one` s'arrêtait au premier essai quel que soit le score :
chacun de ces tests échoue sur le service d'origine et passe avec le secours.
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
from pbm_api.identification.cache import store_cache
from pbm_api.identification.fingerprint import compute_phash
from pbm_api.identification.rescue import top_combined_score
from pbm_api.identification.schemas import CardExtraction
from pbm_api.identification.service import run_identification_for_upload
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
from pbm_api.models.identification import IdentificationCache
from pbm_api.s3 import ObjectStorage

AI_KEY = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789"


def _extraction_payload(confidence: float) -> dict:
    return {
        "name": "Sarmuraï",
        "name_confidence": confidence,
        "number": "1",
        "number_confidence": confidence,
        "total": None,
        "total_confidence": 0.0,
        "set_code": None,
        "set_code_confidence": 0.0,
        "language": "fr",
        "language_confidence": confidence,
        "hp": 60,
        "hp_confidence": 0.8,
        "card_type": "Pokémon",
        "card_type_confidence": 0.7,
        "variant": "normal",
        "variant_confidence": 0.6,
    }


LOW_PAYLOAD = _extraction_payload(0.4)  # combiné ≈ 0.4 : sous le seuil de 0.75
HIGH_PAYLOAD = _extraction_payload(0.95)  # combiné ≈ 0.95 : au-dessus du seuil
# Rien de lu : aucun palier de rapprochement possible, aucun candidat (score 0).
UNREADABLE_PAYLOAD = {
    **{key: None for key in _extraction_payload(0.0)},
    "name_confidence": 0.0,
    "number_confidence": 0.0,
    "total_confidence": 0.0,
    "set_code_confidence": 0.0,
    "language_confidence": 0.0,
    "hp_confidence": 0.0,
    "card_type_confidence": 0.0,
    "variant_confidence": 0.0,
}

BOX_PAYLOAD = {"box": {"x_min": 0.05, "y_min": 0.05, "x_max": 0.95, "y_max": 0.95}}


class _RescueAwareProvider(AIProvider):
    """Répond au schéma « boîte » du secours ET au schéma d'extraction : la liste
    `extraction_payloads` est servie dans l'ordre (le dernier élément est resservi si la liste
    s'épuise) — premier essai puis relecture du secours."""

    PROVIDER = AiProvider.anthropic
    DEFAULT_MODEL = "stub-vision"

    def __init__(self, extraction_payloads: list[dict], **_ignored) -> None:
        super().__init__(api_key="unused")
        self._extraction_payloads = list(extraction_payloads)
        self.extract_calls = 0
        self.box_calls = 0
        self.prompts: list[str] = []

    async def _call(
        self, images: list[ImageInput], schema: type[T], prompt: str, model: str, retry_hint
    ) -> tuple[str, ExtractionUsage]:
        self.prompts.append(prompt)
        usage = ExtractionUsage(
            provider=self.PROVIDER, model=model, input_tokens=40, output_tokens=20
        )
        if schema.__name__ == "SingleCardBox":
            self.box_calls += 1
            return json.dumps(BOX_PAYLOAD), usage
        self.extract_calls += 1
        payload = (
            self._extraction_payloads.pop(0)
            if len(self._extraction_payloads) > 1
            else self._extraction_payloads[0]
        )
        return json.dumps(payload), usage


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
        email=f"rescue-{uuid.uuid4()}@example.com",
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


async def _prepared_upload(db_session, storage, *, seed: int) -> tuple[Upload, User]:
    photo = make_single_card(seed=seed, index=0)
    upload, user = await _make_upload(db_session, storage, _encode(photo.image))
    await upsert_key(db_session, user, AiProvider.anthropic, AI_KEY)
    await run_detection_for_upload(db_session, storage, upload)
    return upload, user


async def test_low_confidence_triggers_rescue_and_keeps_better_result(
    db_session, storage, monkeypatch
):
    """Premier essai à ~0.4 : le secours redemande la boîte au LLM, relit le nouveau recadrage
    (~0.95) et c'est ce second résultat qui est écrit — méthode `ia_secours`, trois appels IA
    comptés et facturés."""
    card = await _seed_sarmurai(db_session)
    upload, user = await _prepared_upload(db_session, storage, seed=7)

    stub = _RescueAwareProvider([LOW_PAYLOAD, HIGH_PAYLOAD])
    monkeypatch.setattr(
        "pbm_api.identification.service.create_provider", lambda *args, **kwargs: stub
    )

    summary = await run_identification_for_upload(db_session, storage, upload)

    assert stub.extract_calls == 2
    assert stub.box_calls == 1
    assert summary.ai_calls == 3
    assert summary.rescued_count == 1
    assert summary.identified_count == 1

    detection = (
        await db_session.execute(select(Detection).where(Detection.upload_id == upload.id))
    ).scalar_one()
    assert detection.identification_method == "ia_secours"
    assert detection.candidates[0]["card_id"] == str(card.id)
    assert top_combined_score(detection.candidates) >= 0.75

    usage = (
        await db_session.execute(
            select(AiUsageMonthly).where(AiUsageMonthly.user_id == user.id)
        )
    ).scalar_one()
    assert usage.calls_count == 3


async def test_high_confidence_never_calls_rescue(db_session, storage, monkeypatch):
    """Au-dessus du seuil dès le premier essai : exactement un appel IA, comme avant le
    correctif — le secours ne coûte jamais rien quand tout va bien."""
    await _seed_sarmurai(db_session)
    upload, _user = await _prepared_upload(db_session, storage, seed=11)

    stub = _RescueAwareProvider([HIGH_PAYLOAD])
    monkeypatch.setattr(
        "pbm_api.identification.service.create_provider", lambda *args, **kwargs: stub
    )

    summary = await run_identification_for_upload(db_session, storage, upload)

    assert stub.extract_calls == 1
    assert stub.box_calls == 0
    assert summary.ai_calls == 1
    assert summary.rescued_count == 0

    detection = (
        await db_session.execute(select(Detection).where(Detection.upload_id == upload.id))
    ).scalar_one()
    assert detection.identification_method == "ia"


async def test_rescue_keeps_first_result_when_retry_is_worse(db_session, storage, monkeypatch):
    """La relecture du secours ne lit rien du tout (score 0 < 0.4) : le premier essai reste le
    résultat écrit, méthode `ia` — le secours ne remplace jamais un résultat par un pire."""
    card = await _seed_sarmurai(db_session)
    upload, _user = await _prepared_upload(db_session, storage, seed=13)

    stub = _RescueAwareProvider([LOW_PAYLOAD, UNREADABLE_PAYLOAD])
    monkeypatch.setattr(
        "pbm_api.identification.service.create_provider", lambda *args, **kwargs: stub
    )

    summary = await run_identification_for_upload(db_session, storage, upload)

    assert stub.extract_calls == 2
    assert stub.box_calls == 1
    assert summary.rescued_count == 1

    detection = (
        await db_session.execute(select(Detection).where(Detection.upload_id == upload.id))
    ).scalar_one()
    assert detection.identification_method == "ia"
    assert detection.candidates[0]["card_id"] == str(card.id)
    assert 0.0 < top_combined_score(detection.candidates) < 0.75


async def test_no_cache_entry_below_threshold(db_session, storage, monkeypatch):
    """Un résultat final sous le seuil n'est jamais mis en cache : la même photo renvoyée
    demain repassera par le pipeline complet au lieu d'hériter d'une lecture ratée."""
    await _seed_sarmurai(db_session)
    upload, _user = await _prepared_upload(db_session, storage, seed=17)

    stub = _RescueAwareProvider([LOW_PAYLOAD, UNREADABLE_PAYLOAD])
    monkeypatch.setattr(
        "pbm_api.identification.service.create_provider", lambda *args, **kwargs: stub
    )

    await run_identification_for_upload(db_session, storage, upload)

    cache_rows = (
        (await db_session.execute(select(IdentificationCache))).scalars().all()
    )
    assert cache_rows == []


async def test_cached_low_confidence_entry_is_bypassed_when_key_available(
    db_session, storage, monkeypatch
):
    """Une entrée de cache sous le seuil (posée avant le correctif, ou par un envoi sans clé)
    n'empoisonne plus les envois suivants : avec une clé, le pipeline complet est rejoué."""
    await _seed_sarmurai(db_session)
    upload, _user = await _prepared_upload(db_session, storage, seed=19)

    detection = (
        await db_session.execute(select(Detection).where(Detection.upload_id == upload.id))
    ).scalar_one()
    crop_bytes = await storage.get(detection.crop_s3_key)
    crop = cv2.imdecode(np.frombuffer(crop_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    await store_cache(
        db_session,
        compute_phash(crop),
        CardExtraction(**LOW_PAYLOAD),
        [{"combined_score": 0.4}],
        "numero_nom",
        method="ia",
    )

    stub = _RescueAwareProvider([HIGH_PAYLOAD])
    monkeypatch.setattr(
        "pbm_api.identification.service.create_provider", lambda *args, **kwargs: stub
    )

    summary = await run_identification_for_upload(db_session, storage, upload)

    assert summary.cache_hits == 0
    assert stub.extract_calls == 1  # HIGH dès le premier essai : pas de secours derrière

    await db_session.refresh(detection)
    assert top_combined_score(detection.candidates) >= 0.75


async def test_cached_low_confidence_entry_still_serves_users_without_key(db_session, storage):
    """D4 : sans clé IA, une entrée de cache sous le seuil reste mieux que rien — servie telle
    quelle, comme avant le correctif."""
    await _seed_sarmurai(db_session)
    photo = make_single_card(seed=23, index=0)
    upload, _user = await _make_upload(db_session, storage, _encode(photo.image))
    await run_detection_for_upload(db_session, storage, upload)

    detection = (
        await db_session.execute(select(Detection).where(Detection.upload_id == upload.id))
    ).scalar_one()
    crop_bytes = await storage.get(detection.crop_s3_key)
    crop = cv2.imdecode(np.frombuffer(crop_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    await store_cache(
        db_session,
        compute_phash(crop),
        CardExtraction(**LOW_PAYLOAD),
        [{"combined_score": 0.4}],
        "numero_nom",
        method="ia",
    )

    summary = await run_identification_for_upload(db_session, storage, upload)

    assert summary.cache_hits == 1
    assert summary.ai_calls == 0

    await db_session.refresh(detection)
    assert detection.candidates == [{"combined_score": 0.4}]
