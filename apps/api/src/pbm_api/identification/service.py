"""Orchestration DB/stockage de l'identification (mission `v3-identification`, étendue par
`v3-identification-visuelle`), appelée par le worker juste après la détection
(`pbm_api.worker.detect_cards_task`) — même job, pas un second aller-retour par la file : les
deux étapes du pipeline de reconnaissance partagent le fournisseur IA de l'utilisateur déjà
déchiffré pour la photo, et « un seul appel IA par carte, dès le premier tir » (principe cadre)
veut dire un appel par carte détectée, pas un job de plus.

Pour chaque détection en attente, dans cet ordre (mission `v3-identification-visuelle` point 3) :
empreinte perceptuelle du recadrage (photo déjà vue, mission `v3-identification` point 4) —
touchée, le cache partagé répond directement, sans même relire l'index visuel ; sinon
comparaison à l'index visuel des images officielles (`pbm_api.identification.visual_index`) — une
correspondance confiante identifie la carte sans aucun appel IA (D4 : possible même sans clé) ;
sinon, si ambiguë (groupe « même illustration ») ou sans correspondance, un appel
`AIProvider.extract` (assisté des candidats visuels s'il y en a) puis rapprochement catalogue
(mission `v3-identification` point 2) — résultat écrit sur la `Detection` et mis en cache dans
tous les cas où quelque chose a été résolu.
"""

from dataclasses import dataclass

import cv2
import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.ai.base import AIProvider, ExtractionUsage, ImageInput
from pbm_api.ai.factory import create_provider
from pbm_api.ai.service import get_default_credential, record_usage
from pbm_api.identification.cache import find_cached, store_cache
from pbm_api.identification.extraction import extract_card
from pbm_api.identification.fingerprint import compute_phash
from pbm_api.identification.reconciliation import CANDIDATES_LIMIT, reconcile
from pbm_api.identification.visual_geometry import illustration_region
from pbm_api.identification.visual_index import VisualIndex
from pbm_api.identification.visual_index import resolve as resolve_visual
from pbm_api.identification.visual_resolve import (
    build_ambiguous_candidates,
    build_confident_extraction,
    visual_hint_lines,
)
from pbm_api.models import Detection, DetectionStatus, Upload, User
from pbm_api.storage import StorageBackend

_CROP_MEDIA_TYPE = "image/jpeg"  # tous les recadrages sont encodés en JPEG (detection/annotate.py)


@dataclass(frozen=True)
class IdentificationRunSummary:
    identified_count: int
    cache_hits: int
    ai_calls: int
    # Cartes reconnues par la seule comparaison visuelle, sans appel IA (mission
    # `v3-identification-visuelle` point 4 : « part reconnue sans IA »).
    visual_matches: int = 0


async def _identify_one(
    session: AsyncSession,
    storage: StorageBackend,
    detection: Detection,
    ai_provider: AIProvider | None,
    ai_model: str | None,
    visual_index: VisualIndex,
) -> tuple[ExtractionUsage | None, bool]:
    """Renvoie l'usage IA le cas échéant, et si la carte a été reconnue par la seule comparaison
    visuelle (pour `IdentificationRunSummary.visual_matches`)."""
    crop_bytes = await storage.get(detection.crop_s3_key)
    if crop_bytes is None:
        return None, False

    crop = cv2.imdecode(np.frombuffer(crop_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    phash = compute_phash(crop)

    cached = await find_cached(session, phash)
    if cached is not None:
        detection.extraction = cached.extraction
        detection.candidates = cached.candidates
        detection.identification_method = cached.method
        return None, False

    illustration_phash = compute_phash(illustration_region(crop))
    matches = visual_index.search(full_phash=phash, illustration_phash=illustration_phash)
    resolution = resolve_visual(matches)

    if resolution.confident_match is not None:
        built = await build_confident_extraction(session, resolution.confident_match)
        if built is not None:
            extraction, candidate = built
            candidates_payload = [candidate.model_dump(mode="json")]
            detection.extraction = extraction.model_dump(mode="json")
            detection.candidates = candidates_payload
            detection.identification_method = "visuel"
            await store_cache(
                session, phash, extraction, candidates_payload, "visuel", method="visuel"
            )
            return None, True

    visual_candidates = (
        await build_ambiguous_candidates(session, resolution.candidates[:CANDIDATES_LIMIT])
        if resolution.candidates
        else []
    )

    if ai_provider is None:
        if visual_candidates:
            detection.candidates = [c.model_dump(mode="json") for c in visual_candidates]
        detection.identification_method = "aucun"
        return None, False

    extraction, usage = await extract_card(
        ai_provider,
        ImageInput(data=crop_bytes, media_type=_CROP_MEDIA_TYPE),
        model=ai_model,
        visual_hints=visual_hint_lines(visual_candidates),
    )
    result = await reconcile(session, extraction)
    candidates_payload = [c.model_dump(mode="json") for c in result.candidates]

    detection.extraction = extraction.model_dump(mode="json")
    detection.candidates = candidates_payload
    detection.identification_method = "ia"
    await store_cache(session, phash, extraction, candidates_payload, result.tier, method="ia")
    return usage, False


async def run_identification_for_upload(
    db: AsyncSession, storage: StorageBackend, upload: Upload
) -> IdentificationRunSummary:
    result = await db.execute(
        select(Detection).where(
            Detection.upload_id == upload.id, Detection.status == DetectionStatus.pending
        )
    )
    detections = list(result.scalars().all())
    if not detections:
        return IdentificationRunSummary(identified_count=0, cache_hits=0, ai_calls=0)

    user = await db.get(User, upload.user_id)
    assert user is not None  # FK NOT NULL sur uploads.user_id : ne peut pas manquer ici

    ai_provider: AIProvider | None = None
    ai_model = user.ai_default_model
    credential = await get_default_credential(db, user)
    if credential is not None:
        provider_enum, api_key = credential
        ai_provider = create_provider(provider_enum, api_key)

    # Un chargement pour tout l'envoi (potentiellement plusieurs cartes), pas par carte : le coût
    # de lecture de `card_visual_index` (~20 000 × 2 lignes) est amorti sur toutes les détections
    # de cette photo (mission point 5 : recherche < 200 ms par carte une fois l'index en mémoire).
    visual_index = await VisualIndex.load(db)

    identified = 0
    cache_hits = 0
    ai_calls = 0
    visual_matches = 0
    try:
        for detection in detections:
            had_extraction_before = detection.extraction is not None
            usage, is_visual_match = await _identify_one(
                db, storage, detection, ai_provider, ai_model, visual_index
            )
            if detection.extraction is not None:
                identified += 1
                if usage is not None:
                    ai_calls += 1
                    await record_usage(db, user, usage)
                elif is_visual_match:
                    visual_matches += 1
                elif not had_extraction_before:
                    cache_hits += 1
            # Commit par détection, pas un seul à la fin de la boucle : le flux SSE de
            # progression (lot `v3-validation`) lit la même ligne au fil de l'eau, et un job
            # interrompu (clé épuisée, voir le risque du lot) garde les cartes déjà identifiées
            # au lieu de tout reperdre.
            await db.commit()
    finally:
        if ai_provider is not None:
            await ai_provider.aclose()

    return IdentificationRunSummary(
        identified_count=identified,
        cache_hits=cache_hits,
        ai_calls=ai_calls,
        visual_matches=visual_matches,
    )
