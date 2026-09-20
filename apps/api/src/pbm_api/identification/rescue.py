"""Secours IA vision de l'identification (correctif `pbm-hotfix-fallback-ia-confiance`,
demande JF 20/09/2026) : quand le meilleur score combiné d'une détection reste sous
`RESCUE_CONFIDENCE_THRESHOLD`, la découpe elle-même est suspecte — un quadrilatère OpenCV
géométriquement plausible peut couper la carte (miniatures tronquées observées en production
sur pokeboy.acx-connect.com), et un recadrage faux fait chuter toutes les confiances de
lecture. Le LLM vision refait alors les deux : la boîte de la carte est redemandée sur la zone
concernée de la photo d'origine (jamais la photo entière : il ne doit localiser QUE la carte de
cette détection), affinée par le même OpenCV que le repli de détection, redressée en 630×880,
puis l'extraction est relancée sur ce nouveau recadrage.

Ce module ne porte que le score, la géométrie et l'appel « boîte » ; l'orchestration
(comparaison avant/après, cache, stockage) reste dans `pbm_api.identification.service`.
"""

from dataclasses import dataclass

import numpy as np
from pydantic import BaseModel

from pbm_api.ai.base import AIProvider, ExtractionUsage, ImageInput
from pbm_api.detection.annotate import encode_jpeg
from pbm_api.detection.geometry import warp_card
from pbm_api.detection.llm_fallback import NormalizedBox
from pbm_api.detection.pipeline import refine_box_with_opencv

# Seuil demandé par JF (20/09/2026) : sous 75 % de score combiné, la découpe et la lecture sont
# systématiquement refaites par le LLM vision — quand une clé IA est disponible (D4 : sans clé,
# rien ne change, la validation humaine reste le filet).
RESCUE_CONFIDENCE_THRESHOLD = 0.75

# Marge autour de la boîte englobante du quadrilatère d'origine avant de redemander la boîte au
# LLM : si la première découpe a coupé la carte, le morceau manquant est par construction juste
# à côté — 35 % de chaque côté suffit à faire entrer la carte entière dans la sous-image sans
# montrer les cartes voisines entières d'un classeur.
RESCUE_MARGIN_FRACTION = 0.35

RESCUE_PROMPT = (
    "This image is a region of a larger photo and contains exactly one Pokémon trading card "
    "(possibly in a plastic sleeve or toploader, possibly with fragments of neighbouring cards "
    "visible near the edges). Return the bounding box of that single card — the full card, "
    "edge to edge, never the sleeve, never a fragment of a neighbouring card. Coordinates are "
    "fractions of the image width/height (0.0 to 1.0), origin at the top-left corner."
)


class SingleCardBox(BaseModel):
    box: NormalizedBox


def top_combined_score(candidates: list | None) -> float:
    """Meilleur `combined_score` d'une liste de candidats (payload JSON) — 0.0 sans candidat :
    « aucun candidat » est le cas le moins sûr de tous, le secours doit s'y déclencher aussi."""
    if not candidates:
        return 0.0
    return max(float(candidate.get("combined_score") or 0.0) for candidate in candidates)


@dataclass(frozen=True)
class RescuedCrop:
    quad: np.ndarray  # coordonnées pixels dans la photo d'origine, ordre (hg, hd, bd, bg)
    crop: np.ndarray  # BGR, 630×880 (même format que `pbm_api.detection.geometry.warp_card`)
    crop_jpeg: bytes
    usage: ExtractionUsage


def region_around_quad(
    image: np.ndarray, quad_points: list, *, margin_fraction: float = RESCUE_MARGIN_FRACTION
) -> tuple[int, int, int, int]:
    """Boîte englobante du quadrilatère d'origine élargie de `margin_fraction`, bornée à
    l'image — la fenêtre montrée au LLM pour qu'il retrouve la carte entière."""
    height, width = image.shape[:2]
    points = np.asarray(quad_points, dtype=np.float32).reshape(-1, 2)
    x_min = float(points[:, 0].min())
    y_min = float(points[:, 1].min())
    x_max = float(points[:, 0].max())
    y_max = float(points[:, 1].max())
    margin_x = (x_max - x_min) * margin_fraction
    margin_y = (y_max - y_min) * margin_fraction
    x0 = max(0, int(round(x_min - margin_x)))
    y0 = max(0, int(round(y_min - margin_y)))
    x1 = min(width, int(round(x_max + margin_x)))
    y1 = min(height, int(round(y_max + margin_y)))
    # Fenêtre dégénérée (bbox corrompue) : toute l'image, plutôt qu'un crop vide qui planterait
    # l'encodage JPEG — le LLM localisera quand même la carte, juste avec plus de contexte.
    if x1 - x0 < 8 or y1 - y0 < 8:
        return 0, 0, width, height
    return x0, y0, x1, y1


async def recrop_with_llm(
    original: np.ndarray,
    quad_points: list,
    provider: AIProvider,
    *,
    model: str | None,
) -> RescuedCrop:
    """Redécoupe une carte par le LLM vision : boîte demandée au modèle sur la fenêtre autour du
    quadrilatère d'origine, affinée par OpenCV (`refine_box_with_opencv`, le même que le repli
    de détection), redressée en 630×880. Les erreurs fournisseur remontent telles quelles —
    c'est l'appelant (`pbm_api.identification.service`) qui décide quoi garder."""
    x0, y0, x1, y1 = region_around_quad(original, quad_points)
    sub_image = original[y0:y1, x0:x1]

    result, usage = await provider.extract(
        [ImageInput(data=encode_jpeg(sub_image), media_type="image/jpeg")],
        SingleCardBox,
        RESCUE_PROMPT,
        model=model,
    )

    # Boîte dégénérée renvoyée par le modèle (largeur/hauteur quasi nulles) : on retombe sur la
    # fenêtre entière plutôt que de découper un ruban — `denormalize_box` garantit déjà au moins
    # 1 px, le contrôle ici écarte les boîtes < 5 % de la fenêtre.
    box = result.box
    if (box.x_max - box.x_min) < 0.05 or (box.y_max - box.y_min) < 0.05:
        box = NormalizedBox(x_min=0.0, y_min=0.0, x_max=1.0, y_max=1.0)

    local_quad = refine_box_with_opencv(sub_image, box)
    quad = local_quad + np.array([x0, y0], dtype=np.float32)
    crop = warp_card(original, quad)
    return RescuedCrop(quad=quad, crop=crop, crop_jpeg=encode_jpeg(crop), usage=usage)
