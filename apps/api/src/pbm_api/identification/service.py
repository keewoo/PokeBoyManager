"""Orchestration DB/stockage de l'identification (mission `v3-identification`, étendue par
`v3-identification-visuelle`, puis par le secours IA vision `pbm-hotfix-fallback-ia-confiance`),
appelée par le worker juste après la détection (`pbm_api.worker.detect_cards_task`) — même job,
pas un second aller-retour par la file : les deux étapes du pipeline de reconnaissance partagent
le fournisseur IA de l'utilisateur déjà déchiffré pour la photo.

Pour chaque détection en attente, dans cet ordre (mission `v3-identification-visuelle` point 3) :
empreinte perceptuelle du recadrage (photo déjà vue, mission `v3-identification` point 4) —
touchée, le cache partagé répond directement, sans même relire l'index visuel ; sinon
comparaison à l'index visuel des images officielles (`pbm_api.identification.visual_index`) — une
correspondance confiante identifie la carte sans aucun appel IA (D4 : possible même sans clé) ;
sinon, si ambiguë (groupe « même illustration ») ou sans correspondance, un appel
`AIProvider.extract` (assisté des candidats visuels s'il y en a) puis rapprochement catalogue
(mission `v3-identification` point 2).

Secours IA vision (`pbm-hotfix-fallback-ia-confiance`, demande JF 20/09/2026) : si le meilleur
score combiné reste sous `RESCUE_CONFIDENCE_THRESHOLD` (75 %) et qu'une clé IA est disponible,
la découpe est refaite par le LLM vision (`pbm_api.identification.rescue.recrop_with_llm` — un
mauvais recadrage OpenCV passé pour plausible est la première cause de lecture ratée) puis
l'identification est rejouée sur le nouveau recadrage ; le meilleur des deux résultats est
conservé, et le recadrage en stockage est remplacé quand le secours fait mieux. Ce chemin
assume jusqu'à deux appels IA de plus par carte peu sûre — dérogation explicite au principe
« un seul appel IA par carte » de `docs/ARCHITECTURE.md`, arbitrée par JF : un résultat faux à
45 % coûte plus cher en corrections manuelles que deux appels de rattrapage.

Le cache d'empreinte suit le même seuil : une entrée sous le seuil n'est ni réutilisée (quand
une clé permet de retenter mieux) ni écrite — sans quoi la première lecture ratée d'une photo
empoisonnerait toutes les suivantes.
"""

import logging
from dataclasses import dataclass

import cv2
import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from pbm_api.ai.base import AIProvider, ExtractionUsage, ImageInput
from pbm_api.ai.errors import AIProviderError
from pbm_api.ai.factory import create_provider
from pbm_api.ai.service import get_default_credential, record_usage
from pbm_api.identification.cache import find_cached, store_cache
from pbm_api.identification.extraction import (
    extract_card,
    merge_bottom_reading,
    needs_bottom_pass,
    read_card_bottom,
)
from pbm_api.identification.fingerprint import compute_phash
from pbm_api.identification.reconciliation import CANDIDATES_LIMIT, reconcile
from pbm_api.identification.rescue import (
    RESCUE_CONFIDENCE_THRESHOLD,
    recrop_with_llm,
    top_combined_score,
)
from pbm_api.identification.schemas import CardExtraction
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

logger = logging.getLogger(__name__)

_CROP_MEDIA_TYPE = "image/jpeg"  # tous les recadrages sont encodés en JPEG (detection/annotate.py)


@dataclass(frozen=True)
class IdentificationRunSummary:
    identified_count: int
    cache_hits: int
    ai_calls: int
    # Cartes reconnues par la seule comparaison visuelle, sans appel IA (mission
    # `v3-identification-visuelle` point 4 : « part reconnue sans IA »).
    visual_matches: int = 0
    # Cartes passées par le secours IA vision (< 75 % de score combiné au premier essai,
    # redécoupe + relecture par le LLM — `pbm-hotfix-fallback-ia-confiance`).
    rescued_count: int = 0


@dataclass(frozen=True)
class _AiIdentification:
    """Résultat d'un essai d'identification IA sur un recadrage donné (premier essai ou
    secours) — tout ce qu'il faut pour comparer deux essais et écrire le meilleur."""

    extraction: CardExtraction
    candidates_payload: list[dict]
    tier: str
    usages: list[ExtractionUsage]
    phash: int


async def _identify_on_crop(
    session: AsyncSession,
    crop_bytes: bytes,
    crop: np.ndarray,
    ai_provider: AIProvider,
    ai_model: str | None,
    visual_index: VisualIndex,
) -> _AiIdentification:
    """Le chemin « index visuel puis IA » sur un recadrage, sans cache ni écriture : partagé
    entre le premier essai et le secours (`pbm-hotfix-fallback-ia-confiance`), qui doivent
    juger deux recadrages avec exactement la même logique pour être comparables."""
    phash = compute_phash(crop)
    illustration_phash = compute_phash(illustration_region(crop))
    matches = visual_index.search(full_phash=phash, illustration_phash=illustration_phash)
    resolution = resolve_visual(matches)

    if resolution.confident_match is not None:
        built = await build_confident_extraction(session, resolution.confident_match)
        if built is not None:
            extraction, candidate = built
            return _AiIdentification(
                extraction=extraction,
                candidates_payload=[candidate.model_dump(mode="json")],
                tier="visuel",
                usages=[],
                phash=phash,
            )

    visual_candidates = (
        await build_ambiguous_candidates(session, resolution.candidates[:CANDIDATES_LIMIT])
        if resolution.candidates
        else []
    )
    extraction, usage = await extract_card(
        ai_provider,
        ImageInput(data=crop_bytes, media_type=_CROP_MEDIA_TYPE),
        model=ai_model,
        visual_hints=visual_hint_lines(visual_candidates),
    )
    result = await reconcile(session, extraction)
    return _AiIdentification(
        extraction=extraction,
        candidates_payload=[c.model_dump(mode="json") for c in result.candidates],
        tier=result.tier,
        usages=[usage],
        phash=phash,
    )


async def _rescue_low_confidence(
    session: AsyncSession,
    storage: StorageBackend,
    upload: Upload,
    detection: Detection,
    ai_provider: AIProvider,
    ai_model: str | None,
    visual_index: VisualIndex,
) -> tuple[_AiIdentification, bytes, list] | None:
    """Redécoupe la carte par le LLM vision sur la photo d'origine puis rejoue l'identification
    sur le nouveau recadrage. Renvoie `(essai, recadrage JPEG, points du quad)` ou `None` si le
    secours n'a pas pu tourner (photo d'origine disparue, bbox corrompue, erreur fournisseur —
    journalisée, jamais avalée sans trace : le premier essai reste alors le résultat)."""
    original_bytes = await storage.get(upload.s3_key)
    if original_bytes is None:
        logger.warning(
            "secours identification: photo d'origine absente du stockage (upload=%s, clé=%s)",
            upload.id,
            upload.s3_key,
        )
        return None
    original = cv2.imdecode(np.frombuffer(original_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if original is None:
        logger.warning("secours identification: photo d'origine illisible (upload=%s)", upload.id)
        return None

    points = (detection.bbox or {}).get("points")
    if not points:
        logger.warning(
            "secours identification: bbox sans points (detection=%s)", detection.id
        )
        return None

    try:
        rescued = await recrop_with_llm(original, points, ai_provider, model=ai_model)
        attempt = await _identify_on_crop(
            session, rescued.crop_jpeg, rescued.crop, ai_provider, ai_model, visual_index
        )
    except AIProviderError as exc:
        # Le premier essai a déjà produit un résultat exploitable (juste peu sûr) : une panne du
        # fournisseur pendant le rattrapage ne doit pas faire perdre la détection entière. Pas un
        # repli silencieux : tracé, et visible dans le score resté bas à l'écran de validation.
        logger.warning(
            "secours identification: appel IA en échec (detection=%s): %s", detection.id, exc
        )
        return None

    usages = [rescued.usage, *attempt.usages]
    attempt = _AiIdentification(
        extraction=attempt.extraction,
        candidates_payload=attempt.candidates_payload,
        tier=attempt.tier,
        usages=usages,
        phash=attempt.phash,
    )
    return attempt, rescued.crop_jpeg, rescued.quad.tolist()


@dataclass(frozen=True)
class _IdentifyOutcome:
    usages: list[ExtractionUsage]
    is_visual_match: bool
    is_cache_hit: bool
    rescued: bool


async def _identify_one(
    session: AsyncSession,
    storage: StorageBackend,
    upload: Upload,
    detection: Detection,
    ai_provider: AIProvider | None,
    ai_model: str | None,
    visual_index: VisualIndex,
) -> _IdentifyOutcome:
    no_outcome = _IdentifyOutcome(
        usages=[], is_visual_match=False, is_cache_hit=False, rescued=False
    )
    crop_bytes = await storage.get(detection.crop_s3_key)
    if crop_bytes is None:
        return no_outcome

    crop = cv2.imdecode(np.frombuffer(crop_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    phash = compute_phash(crop)

    cached = await find_cached(session, phash)
    # Une entrée de cache sous le seuil de secours n'est réutilisée que sans clé IA (D4) : la
    # première lecture ratée d'une photo ne doit pas empoisonner toutes les suivantes alors
    # qu'un rattrapage est possible (`pbm-hotfix-fallback-ia-confiance`).
    if cached is not None and (
        ai_provider is None
        or top_combined_score(cached.candidates) >= RESCUE_CONFIDENCE_THRESHOLD
    ):
        detection.extraction = cached.extraction
        detection.candidates = cached.candidates
        detection.identification_method = cached.method
        return _IdentifyOutcome(usages=[], is_visual_match=False, is_cache_hit=True, rescued=False)

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
            return _IdentifyOutcome(
                usages=[], is_visual_match=True, is_cache_hit=False, rescued=False
            )

    visual_candidates = (
        await build_ambiguous_candidates(session, resolution.candidates[:CANDIDATES_LIMIT])
        if resolution.candidates
        else []
    )

    if ai_provider is None:
        if visual_candidates:
            detection.candidates = [c.model_dump(mode="json") for c in visual_candidates]
        detection.identification_method = "aucun"
        return no_outcome

    extraction, usage = await extract_card(
        ai_provider,
        ImageInput(data=crop_bytes, media_type=_CROP_MEDIA_TYPE),
        model=ai_model,
        visual_hints=visual_hint_lines(visual_candidates),
    )
    result = await reconcile(session, extraction)
    best = _AiIdentification(
        extraction=extraction,
        candidates_payload=[c.model_dump(mode="json") for c in result.candidates],
        tier=result.tier,
        usages=[usage],
        phash=phash,
    )
    usages: list[ExtractionUsage] = list(best.usages)
    method = "ia"
    rescued = False

    # Seconde passe ciblée sur le bas de la carte (mission point 4) quand le premier appel n'a pas
    # lu de numéro fiable : numéro/total/code d'extension y sont imprimés en petit, une bande
    # agrandie se lit mieux. Le résultat fusionné n'est retenu que s'il rapproche AU MOINS aussi
    # bien la carte du catalogue — jamais une régression. Une panne du fournisseur pendant cette
    # passe est tracée, jamais avalée : le premier essai reste le résultat.
    if needs_bottom_pass(best.extraction):
        try:
            bottom, bottom_usage = await read_card_bottom(ai_provider, crop, model=ai_model)
        except AIProviderError as exc:
            logger.warning(
                "seconde passe bas de carte en échec (detection=%s): %s", detection.id, exc
            )
        else:
            usages.append(bottom_usage)
            merged = merge_bottom_reading(best.extraction, bottom)
            if (
                merged.number != best.extraction.number
                or merged.set_code != best.extraction.set_code
            ):
                merged_result = await reconcile(session, merged)
                merged_candidates = [c.model_dump(mode="json") for c in merged_result.candidates]
                if top_combined_score(merged_candidates) >= top_combined_score(
                    best.candidates_payload
                ):
                    best = _AiIdentification(
                        extraction=merged,
                        candidates_payload=merged_candidates,
                        tier=merged_result.tier,
                        usages=best.usages,
                        phash=phash,
                    )

    if top_combined_score(best.candidates_payload) < RESCUE_CONFIDENCE_THRESHOLD:
        rescue_result = await _rescue_low_confidence(
            session, storage, upload, detection, ai_provider, ai_model, visual_index
        )
        if rescue_result is not None:
            attempt, crop_jpeg, quad_points = rescue_result
            usages = usages + attempt.usages
            rescued = True
            # Égalité comprise : à score égal (souvent 0 des deux côtés), le recadrage refait
            # par le LLM est plus digne de confiance que celui qui vient d'échouer — c'est lui
            # que l'utilisateur verra en miniature à l'écran de validation.
            if top_combined_score(attempt.candidates_payload) >= top_combined_score(
                best.candidates_payload
            ):
                best = attempt
                method = "ia_secours"
                await storage.put(detection.crop_s3_key, crop_jpeg, _CROP_MEDIA_TYPE)
                detection.bbox = {**(detection.bbox or {}), "points": quad_points}
                flag_modified(detection, "bbox")

    detection.extraction = best.extraction.model_dump(mode="json")
    detection.candidates = best.candidates_payload
    detection.identification_method = method
    # Jamais une entrée de cache sous le seuil (voir le module docstring) : la relecture d'une
    # photo identique repassera par le pipeline complet tant que rien de sûr n'a été trouvé.
    if top_combined_score(best.candidates_payload) >= RESCUE_CONFIDENCE_THRESHOLD:
        await store_cache(
            session, best.phash, best.extraction, best.candidates_payload, best.tier, method=method
        )
    return _IdentifyOutcome(
        usages=usages, is_visual_match=False, is_cache_hit=False, rescued=rescued
    )


async def run_identification_for_upload(
    db: AsyncSession, storage: StorageBackend, upload: Upload, *, force_ai: bool = False
) -> IdentificationRunSummary:
    """`force_ai` : seconde passe (lot `h1-seconde-passe-ia`). L'index visuel est mis de côté —
    JF demande que l'IA fasse ET la découpe ET la reconnaissance, et une correspondance visuelle
    confiante court-circuiterait l'appel IA."""
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
    visual_index = VisualIndex.empty() if force_ai else await VisualIndex.load(db)

    identified = 0
    cache_hits = 0
    ai_calls = 0
    visual_matches = 0
    rescued_count = 0
    try:
        for detection in detections:
            outcome = await _identify_one(
                db, storage, upload, detection, ai_provider, ai_model, visual_index
            )
            if detection.extraction is not None:
                identified += 1
                if outcome.usages:
                    ai_calls += len(outcome.usages)
                    for usage in outcome.usages:
                        await record_usage(db, user, usage)
                elif outcome.is_visual_match:
                    visual_matches += 1
                elif outcome.is_cache_hit:
                    cache_hits += 1
            if outcome.rescued:
                rescued_count += 1
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
        rescued_count=rescued_count,
    )
