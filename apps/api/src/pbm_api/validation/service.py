"""Logique métier de l'écran de validation (lot `v3-validation`), indépendante de FastAPI —
même style que `pbm_api.uploads.service` : `confirm`/`reject` ne trouvent jamais la détection
d'un autre utilisateur (jointure sur `Upload.user_id`, jamais un `detection_id` seul).

Chaque décision (mission point 3) écrit une ligne `IdentificationCorrection` : le premier
candidat proposé par `pbm_api.identification.reconciliation` (`None` si aucun) contre celui
réellement retenu (`None` = rejetée) — le jeu de régression de l'identification.
"""

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.identification.reconciliation import top_candidate_preselected
from pbm_api.models import Card, IdentificationCorrection, User
from pbm_api.models.catalog import PriceVariant
from pbm_api.models.collection import CollectionItem, Detection, DetectionStatus, Upload
from pbm_api.uploads.service import get_owned_upload
from pbm_api.validation.errors import (
    CardNotFoundError,
    DetectionAlreadyProcessedError,
    DetectionNotFoundError,
)
from pbm_api.validation.schemas import ConfirmDetectionRequest

# Défauts de `confirm-all` (mission point 2, bouton « Tout ajouter ») : un exemplaire normal en
# français, sans prix ni état — toujours corrigeable depuis la collection ensuite. N'agit que sur
# les détections dont le premier candidat est présélectionné (score > `PRESELECTION_THRESHOLD`,
# `pbm_api.identification.reconciliation`) : jamais d'ajout à la collection sans qu'un candidat
# se soit démarqué, même implicitement.
CONFIRM_ALL_LANGUAGE = "fr"
CONFIRM_ALL_VARIANT = PriceVariant.normal


@dataclass(frozen=True)
class ConfirmAllResult:
    confirmed: list[uuid.UUID]
    skipped: list[uuid.UUID]


def _top_candidate(detection: Detection) -> dict | None:
    return detection.candidates[0] if detection.candidates else None


def _counterfeit_suspected(detection: Detection) -> bool:
    """Reprend le drapeau de `Detection.condition_assessment` (mission `v3-etat` point 3,
    `pbm_api.state.service`) au moment où l'exemplaire est créé — jamais une contrefaçon
    probable valorisée comme l'originale (`pbm_api.pricing.valuation.item_value`)."""
    if not detection.condition_assessment:
        return False
    return bool(detection.condition_assessment.get("counterfeit_suspected", False))


async def _get_owned_detection(
    db: AsyncSession, user: User, detection_id: uuid.UUID
) -> Detection:
    result = await db.execute(
        select(Detection)
        .join(Upload, Upload.id == Detection.upload_id)
        .where(Detection.id == detection_id, Upload.user_id == user.id)
    )
    detection = result.scalar_one_or_none()
    if detection is None:
        raise DetectionNotFoundError
    return detection


async def confirm_detection(
    db: AsyncSession, user: User, detection_id: uuid.UUID, data: ConfirmDetectionRequest
) -> tuple[Detection, list[CollectionItem]]:
    detection = await _get_owned_detection(db, user, detection_id)
    if detection.status != DetectionStatus.pending:
        raise DetectionAlreadyProcessedError

    card = await db.get(Card, data.card_id)
    if card is None:
        raise CardNotFoundError

    top = _top_candidate(detection)
    proposed_card_id = uuid.UUID(top["card_id"]) if top else None
    acquired_at = data.acquired_at or date.today()
    counterfeit_suspected = _counterfeit_suspected(detection)

    items = [
        CollectionItem(
            user_id=user.id,
            card_id=card.id,
            detection_id=detection.id,
            language=data.language,
            variant=data.variant,
            condition_grade=data.condition_grade,
            counterfeit_suspected=counterfeit_suspected,
            purchase_price=data.purchase_price,
            purchase_currency=data.purchase_currency,
            photo_s3_key=detection.crop_s3_key,
            acquired_at=acquired_at,
        )
        for _ in range(data.quantity)
    ]
    db.add_all(items)

    detection.status = DetectionStatus.validated
    detection.selected_card_id = card.id
    db.add(
        IdentificationCorrection(
            detection_id=detection.id,
            user_id=user.id,
            proposed_card_id=proposed_card_id,
            chosen_card_id=card.id,
        )
    )
    await db.commit()
    for item in items:
        await db.refresh(item)
    return detection, items


async def reject_detection(db: AsyncSession, user: User, detection_id: uuid.UUID) -> Detection:
    detection = await _get_owned_detection(db, user, detection_id)
    if detection.status != DetectionStatus.pending:
        raise DetectionAlreadyProcessedError

    top = _top_candidate(detection)
    proposed_card_id = uuid.UUID(top["card_id"]) if top else None

    detection.status = DetectionStatus.rejected
    db.add(
        IdentificationCorrection(
            detection_id=detection.id,
            user_id=user.id,
            proposed_card_id=proposed_card_id,
            chosen_card_id=None,
        )
    )
    await db.commit()
    return detection


async def confirm_all(
    db: AsyncSession, user: User, upload_id: uuid.UUID
) -> ConfirmAllResult:
    upload = await get_owned_upload(db, user, upload_id)
    result = await db.execute(
        select(Detection).where(
            Detection.upload_id == upload.id, Detection.status == DetectionStatus.pending
        )
    )
    detections = list(result.scalars().all())

    confirmed: list[uuid.UUID] = []
    skipped: list[uuid.UUID] = []
    for detection in detections:
        # Présélection ré-appliquée aux scores stockés (politique courante), pas au drapeau figé à
        # l'écriture (lot `pbm-parcours-validation`) : sinon les 143 détections d'Aymeric,
        # identifiées sous l'ancien seuil de 0,9, ne seraient jamais ajoutées par « Tout ajouter ».
        if not top_candidate_preselected(detection.candidates):
            skipped.append(detection.id)
            continue

        top = max(detection.candidates, key=lambda c: float(c.get("combined_score") or 0.0))
        card_id = uuid.UUID(top["card_id"])
        db.add(
            CollectionItem(
                user_id=user.id,
                card_id=card_id,
                detection_id=detection.id,
                language=CONFIRM_ALL_LANGUAGE,
                variant=CONFIRM_ALL_VARIANT,
                counterfeit_suspected=_counterfeit_suspected(detection),
                photo_s3_key=detection.crop_s3_key,
                acquired_at=date.today(),
            )
        )
        detection.status = DetectionStatus.validated
        detection.selected_card_id = card_id
        db.add(
            IdentificationCorrection(
                detection_id=detection.id,
                user_id=user.id,
                proposed_card_id=card_id,
                chosen_card_id=card_id,
            )
        )
        confirmed.append(detection.id)

    await db.commit()
    return ConfirmAllResult(confirmed=confirmed, skipped=skipped)
