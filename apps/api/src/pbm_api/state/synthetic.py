"""Recadrages synthétiques pour la mise au point et les tests de `pbm_api.state.centering`
(mission point 4, même contrainte que `pbm_api.detection.synthetic` : aucun appareil photo ni
carte physique sur chimera). Un recadrage synthétique dessine une bordure de couleur unie
(630×880 px, comme `pbm_api.detection.geometry`) autour d'un cadre intérieur décalé de marges
connues — ce que `pbm_api.detection.synthetic` ne modélise pas (son contour n'est qu'un simple
trait, pas un vrai cadre imprimé), donc un jeu dédié plutôt qu'une réutilisation.
"""

from dataclasses import dataclass

import cv2
import numpy as np

from pbm_api.detection.geometry import CARD_HEIGHT_PX, CARD_WIDTH_PX


@dataclass(frozen=True)
class SyntheticCrop:
    id: str
    image: np.ndarray  # BGR, comme cv2.imdecode
    left_px: int
    right_px: int
    top_px: int
    bottom_px: int


def make_bordered_crop(
    seed: int,
    crop_id: str,
    *,
    left: int,
    top: int,
    right: int,
    bottom: int,
    border_color: tuple[int, int, int] = (30, 200, 220),  # jaune-orangé, bordure classique
    inner_color: tuple[int, int, int] = (150, 130, 90),
) -> SyntheticCrop:
    """Un recadrage 630×880 : bordure unie, cadre intérieur décalé des marges données (px)."""
    rng = np.random.default_rng(seed)
    width, height = CARD_WIDTH_PX, CARD_HEIGHT_PX

    canvas = np.full((height, width, 3), border_color, dtype=np.uint8)
    inner_w = width - left - right
    inner_h = height - top - bottom
    assert inner_w > 0 and inner_h > 0

    cv2.rectangle(canvas, (left, top), (left + inner_w, top + inner_h), inner_color, thickness=-1)
    # Illustration grossière à l'intérieur du cadre : casse l'uniformité comme une vraie carte
    # (texte + artwork), sans jamais s'approcher de la couleur de bordure.
    cv2.circle(
        canvas,
        (left + inner_w // 2, top + inner_h // 3),
        min(inner_w, inner_h) // 6,
        tuple(int(c * 0.6) for c in inner_color),
        -1,
    )
    noise = rng.normal(0, 4, canvas.shape)
    canvas = np.clip(canvas.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    return SyntheticCrop(
        id=crop_id, image=canvas, left_px=left, right_px=right, top_px=top, bottom_px=bottom
    )


def generate_dataset(seed: int = 20260919) -> list[SyntheticCrop]:
    """Un jeu couvrant un centrage quasi parfait jusqu'à très marqué, sur les deux axes
    indépendamment, plus un cas sans bordure distincte (carte pleine page, non mesurable)."""
    crops = [
        make_bordered_crop(seed, "centre_parfait", left=40, right=40, top=55, bottom=55),
        make_bordered_crop(seed + 1, "leger_horizontal", left=35, right=45, top=55, bottom=55),
        make_bordered_crop(seed + 2, "modere_horizontal", left=25, right=55, top=55, bottom=55),
        make_bordered_crop(seed + 3, "marque_horizontal", left=12, right=68, top=55, bottom=55),
        make_bordered_crop(seed + 4, "leger_vertical", left=40, right=40, top=48, bottom=62),
        make_bordered_crop(seed + 5, "modere_vertical", left=40, right=40, top=35, bottom=75),
        make_bordered_crop(seed + 6, "marque_deux_axes", left=15, right=65, top=20, bottom=90),
    ]
    return crops


def make_full_bleed_crop(seed: int = 1) -> SyntheticCrop:
    """Carte sans bordure imprimée distincte (full art) : un seul dégradé de couleur proche sur
    toute la surface — le centrage ne doit jamais s'y inventer une mesure."""
    rng = np.random.default_rng(seed)
    width, height = CARD_WIDTH_PX, CARD_HEIGHT_PX
    base = np.array([120, 140, 160], dtype=np.int16)
    gradient = np.linspace(-15, 15, width).reshape(1, width, 1)
    canvas = np.clip(base + gradient, 0, 255).astype(np.uint8)
    canvas = np.repeat(canvas, height, axis=0)
    noise = rng.normal(0, 5, canvas.shape)
    canvas = np.clip(canvas.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    return SyntheticCrop(
        id="full_bleed", image=canvas, left_px=0, right_px=0, top_px=0, bottom_px=0
    )
