"""Orchestration DB/stockage de l'estimation d'état (mission `v3-etat`), chaînée dans le même
job `detect_cards` que la détection et l'identification (`pbm_api.worker.detect_cards_task`,
juste après `run_identification_for_upload`) — jamais un job de plus ni un appel IA de plus :
le centrage se mesure par OpenCV sur le recadrage déjà stocké (`pbm_api.state.centering`), coins/
bords/surface/contrefaçon viennent de l'extraction déjà obtenue par l'identification
(`Detection.extraction`, étendue par ce lot), qu'elle vienne d'un appel IA frais ou du cache
partagé (mission `v3-identification` point 4) — jamais un second aller-retour.
"""

import uuid
from dataclasses import dataclass

import cv2
import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.identification.schemas import CardExtraction
from pbm_api.models import Card, Detection, Set, Upload
from pbm_api.state.centering import measure_centering
from pbm_api.state.counterfeit import assess_counterfeit
from pbm_api.state.grades import CARDMARKET_LABELS, score_10, worst_grade
from pbm_api.storage import StorageBackend

DISCLAIMER = (
    "Estimation indicative générée automatiquement (centrage mesuré + lecture IA des coins, "
    "bords et surface) — ce n'est pas une gradation professionnelle."
)


@dataclass(frozen=True)
class StateEstimationRunSummary:
    assessed_count: int
    counterfeit_flagged_count: int


def _axis_payload(axis) -> dict | None:
    if axis is None:
        return None
    return {
        "near_px": axis.near_px,
        "far_px": axis.far_px,
        "ratio": axis.ratio_label,
        "grade": axis.grade.value,
    }


@dataclass(frozen=True)
class _MatchedCardSignals:
    rarity: str | None
    variants: dict | None
    set_total_cards: int | None
    has_matched_card: bool


_NO_MATCH = _MatchedCardSignals(
    rarity=None, variants=None, set_total_cards=None, has_matched_card=False
)


async def _matched_card_signals(db: AsyncSession, detection: Detection) -> _MatchedCardSignals:
    """Signaux de la carte retenue pour le contrôle de contrefaçon (mission `v3-etat` point 3,
    étendue par `v6-contrefacon` mission point 1 : variantes déclarées et total de série de
    l'extension) — `selected_card_id` (validation humaine déjà faite) prime sur le premier
    candidat proposé par le rapprochement catalogue, disponible plus tôt dans le parcours."""
    card_id = detection.selected_card_id
    if card_id is None and detection.candidates:
        raw_card_id = detection.candidates[0].get("card_id")
        card_id = uuid.UUID(raw_card_id) if raw_card_id else None
    if card_id is None:
        return _NO_MATCH

    card = await db.get(Card, card_id)
    if card is None:
        return _NO_MATCH

    set_row = await db.get(Set, card.set_id)
    return _MatchedCardSignals(
        rarity=card.rarity,
        variants=card.variants,
        set_total_cards=set_row.total_cards if set_row else None,
        has_matched_card=True,
    )


async def _estimate_one(db: AsyncSession, storage: StorageBackend, detection: Detection) -> bool:
    """Renvoie `True` si un signal de contrefaçon a été retenu."""
    crop_bytes = await storage.get(detection.crop_s3_key) if detection.crop_s3_key else None
    centering = None
    if crop_bytes is not None:
        crop = cv2.imdecode(np.frombuffer(crop_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        centering = measure_centering(crop)

    extraction = (
        CardExtraction.model_validate(detection.extraction) if detection.extraction else None
    )

    corner_grade = extraction.corner_wear if extraction else None
    edge_grade = extraction.edge_wear if extraction else None
    surface_grade = extraction.surface_wear if extraction else None
    overall_grade = worst_grade(
        [centering.grade if centering else None, corner_grade, edge_grade, surface_grade]
    )

    matched = await _matched_card_signals(db, detection)
    counterfeit = assess_counterfeit(
        ai_suspected=extraction.counterfeit_suspected if extraction else False,
        ai_reason=extraction.counterfeit_reason if extraction else None,
        variant_guess=extraction.variant.value if extraction and extraction.variant else None,
        matched_card_rarity=matched.rarity,
        has_matched_card=matched.has_matched_card,
        matched_card_variants=matched.variants,
        extraction_total=extraction.total if extraction else None,
        matched_set_total_cards=matched.set_total_cards,
    )

    detection.condition_assessment = {
        "centering": (
            {
                "left_px": centering.left_px,
                "right_px": centering.right_px,
                "top_px": centering.top_px,
                "bottom_px": centering.bottom_px,
                "horizontal": _axis_payload(centering.horizontal),
                "vertical": _axis_payload(centering.vertical),
                "grade": centering.grade.value if centering.grade else None,
            }
            if centering is not None
            else None
        ),
        "corners": (
            {
                "grade": corner_grade.value if corner_grade else None,
                "confidence": extraction.corner_wear_confidence,
                "note": extraction.corner_wear_note,
            }
            if extraction
            else None
        ),
        "edges": (
            {
                "grade": edge_grade.value if edge_grade else None,
                "confidence": extraction.edge_wear_confidence,
                "note": extraction.edge_wear_note,
            }
            if extraction
            else None
        ),
        "surface": (
            {
                "grade": surface_grade.value if surface_grade else None,
                "confidence": extraction.surface_wear_confidence,
                "note": extraction.surface_wear_note,
            }
            if extraction
            else None
        ),
        "overall_grade": overall_grade.value if overall_grade else None,
        "overall_grade_label": CARDMARKET_LABELS[overall_grade] if overall_grade else None,
        "score_10": score_10(overall_grade),
        "counterfeit_suspected": counterfeit.suspected,
        "counterfeit_reasons": counterfeit.reasons,
        "disclaimer": DISCLAIMER,
    }
    return counterfeit.suspected


async def run_state_estimation_for_upload(
    db: AsyncSession, storage: StorageBackend, upload: Upload
) -> StateEstimationRunSummary:
    result = await db.execute(
        select(Detection).where(
            Detection.upload_id == upload.id, Detection.condition_assessment.is_(None)
        )
    )
    detections = list(result.scalars().all())
    if not detections:
        return StateEstimationRunSummary(assessed_count=0, counterfeit_flagged_count=0)

    counterfeit_flagged = 0
    for detection in detections:
        if await _estimate_one(db, storage, detection):
            counterfeit_flagged += 1

    await db.commit()
    return StateEstimationRunSummary(
        assessed_count=len(detections), counterfeit_flagged_count=counterfeit_flagged
    )
