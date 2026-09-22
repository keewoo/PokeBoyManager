"""`pbm_api.state.service.run_state_estimation_for_upload` (mission `v3-etat`) : orchestration
DB/stockage, chaînée après l'identification dans le même job — logique indépendante d'arq,
testable directement comme `run_identification_for_upload`/`run_detection_for_upload`.

Avant ce lot, `pbm_api.state.service` n'existe pas : chacun de ces tests échoue à la collection
et passe une fois le fichier ajouté.
"""

import uuid
from datetime import date, datetime

import cv2
import pytest
from sqlalchemy import select

from pbm_api.models import Card, Detection, DetectionStatus, Set, Upload, UploadStatus, User
from pbm_api.pricing.valuation import CONDITION_MULTIPLIERS
from pbm_api.s3 import ObjectStorage
from pbm_api.state.service import run_state_estimation_for_upload
from pbm_api.state.synthetic import generate_dataset


def _encode(image) -> bytes:
    ok, buffer = cv2.imencode(".jpg", image)
    assert ok
    return buffer.tobytes()


@pytest.fixture
async def storage():
    object_storage = ObjectStorage()
    await object_storage.ensure_bucket()
    return object_storage


async def _make_upload(db_session) -> Upload:
    user = User(
        email=f"etat-{uuid.uuid4()}@example.com",
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
        content_type="image/jpeg",
        size_bytes=1,
        status=UploadStatus.processed,
    )
    db_session.add(upload)
    await db_session.flush()
    return upload


async def _make_detection(
    db_session, storage, upload, crop_image, *, extraction=None, candidates=None
) -> Detection:
    crop_key = f"uploads/{upload.user_id}/{upload.id}/detections/{uuid.uuid4()}.jpg"
    await storage.put(crop_key, _encode(crop_image), "image/jpeg")
    detection = Detection(
        upload_id=upload.id,
        bbox={"reading_order": 0},
        crop_s3_key=crop_key,
        status=DetectionStatus.pending,
        extraction=extraction,
        candidates=candidates,
    )
    db_session.add(detection)
    await db_session.flush()
    return detection


async def _make_card(
    db_session,
    *,
    rarity: str,
    variants: dict | None = None,
    set_total_cards: int | None = None,
) -> Card:
    set_row = Set(code=f"etat-{uuid.uuid4().hex[:8]}", name="Set état", total_cards=set_total_cards)
    db_session.add(set_row)
    await db_session.flush()
    card = Card(set_id=set_row.id, number="1", name="Carte état", rarity=rarity, variants=variants)
    db_session.add(card)
    await db_session.flush()
    return card


_EXTRACTION_BASE = {
    "name": "Dracaufeu",
    "name_confidence": 0.9,
    "number": "6",
    "number_confidence": 0.9,
    "total": None,
    "total_confidence": 0.0,
    "set_code": None,
    "set_code_confidence": 0.0,
    "language": "fr",
    "language_confidence": 0.9,
    "hp": None,
    "hp_confidence": 0.0,
    "card_type": None,
    "card_type_confidence": 0.0,
    "variant": "normal",
    "variant_confidence": 0.9,
    "corner_wear": "excellent",
    "corner_wear_confidence": 0.8,
    "corner_wear_note": "légère usure sur un coin",
    "edge_wear": "near_mint",
    "edge_wear_confidence": 0.7,
    "edge_wear_note": "bords nets",
    "surface_wear": "good",
    "surface_wear_confidence": 0.5,
    "surface_wear_note": "quelques micro-rayures",
    "counterfeit_suspected": False,
    "counterfeit_confidence": 0.0,
    "counterfeit_reason": None,
}


def _crop(crop_id: str):
    return next(c for c in generate_dataset() if c.id == crop_id).image


async def test_run_state_estimation_combines_centering_and_extraction(db_session, storage):
    upload = await _make_upload(db_session)
    await _make_detection(
        db_session, storage, upload, _crop("centre_parfait"), extraction=_EXTRACTION_BASE
    )

    summary = await run_state_estimation_for_upload(db_session, storage, upload)

    assert summary.assessed_count == 1
    assert summary.counterfeit_flagged_count == 0

    detection = (
        await db_session.execute(select(Detection).where(Detection.upload_id == upload.id))
    ).scalar_one()
    condition = detection.condition_assessment
    assert condition["centering"]["grade"] == "mint"
    assert condition["corners"] == {
        "grade": "excellent", "confidence": 0.8, "note": "légère usure sur un coin"
    }
    assert condition["edges"]["grade"] == "near_mint"
    assert condition["surface"]["grade"] == "good"
    # Le plus sévère des quatre paliers (mint, excellent, near_mint, good) l'emporte.
    assert condition["overall_grade"] == "good"
    assert condition["overall_grade_label"] == "GD"
    assert condition["score_10"] == round(float(CONDITION_MULTIPLIERS["good"]) * 10, 1)
    assert condition["counterfeit_suspected"] is False
    assert condition["counterfeit_reasons"] == []
    assert "indicative" in condition["disclaimer"]


async def test_run_state_estimation_without_extraction_only_measures_centering(
    db_session, storage
):
    """D4 (sans clé IA) : l'extraction est absente, le centrage reste mesurable — jamais une
    exception, juste des champs coins/bords/surface à `None`."""
    upload = await _make_upload(db_session)
    await _make_detection(db_session, storage, upload, _crop("marque_deux_axes"), extraction=None)

    summary = await run_state_estimation_for_upload(db_session, storage, upload)

    assert summary.assessed_count == 1
    detection = (
        await db_session.execute(select(Detection).where(Detection.upload_id == upload.id))
    ).scalar_one()
    condition = detection.condition_assessment
    assert condition["corners"] is None
    assert condition["edges"] is None
    assert condition["surface"] is None
    assert condition["overall_grade"] == condition["centering"]["grade"] == "poor"


async def test_run_state_estimation_is_idempotent(db_session, storage):
    upload = await _make_upload(db_session)
    await _make_detection(
        db_session, storage, upload, _crop("centre_parfait"), extraction=_EXTRACTION_BASE
    )

    first = await run_state_estimation_for_upload(db_session, storage, upload)
    second = await run_state_estimation_for_upload(db_session, storage, upload)

    assert first.assessed_count == 1
    assert second.assessed_count == 0


async def test_run_state_estimation_flags_unconfirmed_gold_variant_as_counterfeit(
    db_session, storage
):
    upload = await _make_upload(db_session)
    card = await _make_card(db_session, rarity="Common")
    extraction = {**_EXTRACTION_BASE, "variant": "gold", "variant_confidence": 0.9}
    await _make_detection(
        db_session,
        storage,
        upload,
        _crop("centre_parfait"),
        extraction=extraction,
        candidates=[{"card_id": str(card.id), "combined_score": 0.95}],
    )

    summary = await run_state_estimation_for_upload(db_session, storage, upload)

    assert summary.counterfeit_flagged_count == 1
    detection = (
        await db_session.execute(select(Detection).where(Detection.upload_id == upload.id))
    ).scalar_one()
    assert detection.condition_assessment["counterfeit_suspected"] is True
    assert detection.condition_assessment["counterfeit_reasons"]


async def test_run_state_estimation_does_not_flag_gold_variant_confirmed_by_catalog(
    db_session, storage
):
    upload = await _make_upload(db_session)
    card = await _make_card(db_session, rarity="Rare Secret")
    extraction = {**_EXTRACTION_BASE, "variant": "gold", "variant_confidence": 0.9}
    await _make_detection(
        db_session,
        storage,
        upload,
        _crop("centre_parfait"),
        extraction=extraction,
        candidates=[{"card_id": str(card.id), "combined_score": 0.95}],
    )

    summary = await run_state_estimation_for_upload(db_session, storage, upload)

    assert summary.counterfeit_flagged_count == 0


async def test_run_state_estimation_flags_variant_absent_from_catalog(db_session, storage):
    """Mission `v6-contrefacon` point 1, « variante absente du catalogue » : reverse holo perçu
    alors que TCGdex (`Card.variants`) ne déclare aucun tirage reverse pour cette carte."""
    upload = await _make_upload(db_session)
    card = await _make_card(
        db_session,
        rarity="Common",
        variants={"normal": True, "holo": False, "reverse": False},
    )
    extraction = {**_EXTRACTION_BASE, "variant": "reverse_holo", "variant_confidence": 0.9}
    await _make_detection(
        db_session,
        storage,
        upload,
        _crop("centre_parfait"),
        extraction=extraction,
        candidates=[{"card_id": str(card.id), "combined_score": 0.95}],
    )

    summary = await run_state_estimation_for_upload(db_session, storage, upload)

    assert summary.counterfeit_flagged_count == 1
    detection = (
        await db_session.execute(select(Detection).where(Detection.upload_id == upload.id))
    ).scalar_one()
    assert detection.condition_assessment["counterfeit_suspected"] is True
    assert any(
        "reverse_holo" in reason for reason in detection.condition_assessment["counterfeit_reasons"]
    )


async def test_run_state_estimation_flags_total_inconsistent_with_matched_set(db_session, storage):
    """Mission `v6-contrefacon` point 1, « numéro impossible » : total de série imprimé (lu par
    l'IA dans `CardExtraction.total`) incohérent avec le total officiel de l'extension reconnue
    (`Set.total_cards`)."""
    upload = await _make_upload(db_session)
    card = await _make_card(
        db_session,
        rarity="Common",
        variants={"normal": True, "holo": False, "reverse": False},
        set_total_cards=102,
    )
    extraction = {**_EXTRACTION_BASE, "total": 999, "total_confidence": 0.9}
    await _make_detection(
        db_session,
        storage,
        upload,
        _crop("centre_parfait"),
        extraction=extraction,
        candidates=[{"card_id": str(card.id), "combined_score": 0.95}],
    )

    summary = await run_state_estimation_for_upload(db_session, storage, upload)

    assert summary.counterfeit_flagged_count == 1
    detection = (
        await db_session.execute(select(Detection).where(Detection.upload_id == upload.id))
    ).scalar_one()
    assert detection.condition_assessment["counterfeit_suspected"] is True
    assert any(
        "999" in reason and "102" in reason
        for reason in detection.condition_assessment["counterfeit_reasons"]
    )


async def test_run_state_estimation_does_not_flag_secret_rare_number_beyond_set_total(
    db_session, storage
):
    """Le total imprimé est cohérent (198) même si le numéro de la carte (mission `v3-etat`,
    hors périmètre ici) dépasse ce total — jamais un faux positif sur une rareté légitime."""
    upload = await _make_upload(db_session)
    card = await _make_card(
        db_session,
        rarity="Rare Secret",
        variants={"normal": True},
        set_total_cards=198,
    )
    extraction = {**_EXTRACTION_BASE, "number": "202", "total": 198, "total_confidence": 0.9}
    await _make_detection(
        db_session,
        storage,
        upload,
        _crop("centre_parfait"),
        extraction=extraction,
        candidates=[{"card_id": str(card.id), "combined_score": 0.95}],
    )

    summary = await run_state_estimation_for_upload(db_session, storage, upload)

    assert summary.counterfeit_flagged_count == 0
