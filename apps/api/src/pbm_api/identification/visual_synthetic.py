"""Jeu synthétique pour la comparaison visuelle (mission `v3-identification-visuelle` point 4) —
même contrainte que `pbm_api.identification.synthetic`/`pbm_api.detection.synthetic` : aucune
vraie photo ni carte physique sur chimera (voir leurs avertissements).

Chaque carte a une image officielle procédurale (basse définition, comme TCGdex "low",
245×337 px) et une photo utilisateur bruitée dérivée du même motif mais rendue directement à la
taille d'un recadrage (630×880 px, `pbm_api.detection.geometry`) — jamais un agrandissement de
l'image officielle, qui rendrait la comparaison triviale (bytes quasi identiques après
redimensionnement). Un sous-ensemble de cartes partage délibérément le même motif qu'une autre
(mission « risques & pièges », groupe « même illustration » — réimpression/reverse/promo) : la
comparaison visuelle doit refuser de les départager seule.
"""

from dataclasses import dataclass

import cv2
import numpy as np

from pbm_api.detection.geometry import CARD_HEIGHT_PX, CARD_WIDTH_PX

OFFICIAL_W, OFFICIAL_H = 245, 337  # dimensions réelles d'une image TCGdex "low"


def _draw_card(canvas: np.ndarray, base_color: tuple[int, int, int], shape_seed: int) -> None:
    """`compute_phash` (mission `v3-identification`) travaille en niveaux de gris : une variation
    de seule teinte (`base_color`) ne suffit pas à discriminer deux cartes (constaté en écrivant
    ce module — une roue de couleurs bien séparées produisait quand même 0 % de reconnaissance,
    la conversion en gris les rendait presque identiques). La discrimination vient donc d'une
    disposition de formes à niveaux de gris variés, tirée par un RNG dérivé de `shape_seed` —
    déterministe, donc deux cartes du même `shape_seed` (mission « risques & pièges ») produisent
    toujours exactement le même motif."""
    height, width = canvas.shape[:2]
    canvas[:] = base_color
    # Bandeau de nom (mission `visual_geometry.ILLUSTRATION_TOP_RATIO`).
    cv2.rectangle(canvas, (0, 0), (width, int(height * 0.11)), (30, 30, 30), -1)

    illustration_top, illustration_bottom = int(height * 0.11), int(height * 0.58)
    illustration_left, illustration_right = int(width * 0.08), int(width * 0.92)
    local_rng = np.random.default_rng(shape_seed)
    for _ in range(8):
        cx = local_rng.integers(illustration_left, illustration_right)
        cy = local_rng.integers(illustration_top, illustration_bottom)
        radius = int(local_rng.integers(int(width * 0.05), int(width * 0.16)))
        gray = int(local_rng.integers(15, 235))
        cv2.circle(canvas, (int(cx), int(cy)), radius, (gray, gray, gray), -1)

    cv2.rectangle(
        canvas,
        (illustration_left, illustration_top),
        (illustration_right, illustration_bottom),
        (20, 20, 20),
        max(1, height // 200),
    )
    # Zone de texte/attaques en bas — du bruit géométrique, jamais lu, juste pour ne pas laisser
    # une zone unie qui biaiserait le hachage entier vers zéro variance.
    for i in range(3):
        y = int(height * 0.66) + i * int(height * 0.08)
        cv2.line(canvas, (int(width * 0.1), y), (int(width * 0.9), y), (70, 70, 70), 1)


def render_official_image(base_color: tuple[int, int, int], shape_seed: int) -> np.ndarray:
    canvas = np.zeros((OFFICIAL_H, OFFICIAL_W, 3), dtype=np.uint8)
    _draw_card(canvas, base_color, shape_seed)
    return canvas


def render_user_crop(
    rng: np.random.Generator, base_color: tuple[int, int, int], shape_seed: int
) -> np.ndarray:
    """Rendu direct à la taille d'un recadrage (jamais un agrandissement de l'image officielle) +
    dégradations réalistes d'une vraie prise de vue : bruit, flou léger, luminosité, JPEG."""
    canvas = np.zeros((CARD_HEIGHT_PX, CARD_WIDTH_PX, 3), dtype=np.uint8)
    _draw_card(canvas, base_color, shape_seed)

    brightness = rng.uniform(-15, 15)
    noisy = np.clip(canvas.astype(np.int16) + brightness, 0, 255).astype(np.uint8)
    noise = rng.normal(0, 5, noisy.shape)
    noisy = np.clip(noisy.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    noisy = cv2.GaussianBlur(noisy, (3, 3), 0)

    ok, buffer = cv2.imencode(".jpg", noisy, [cv2.IMWRITE_JPEG_QUALITY, 80])
    assert ok
    return cv2.imdecode(buffer, cv2.IMREAD_COLOR)


@dataclass(frozen=True)
class VisualSyntheticCard:
    id: str
    set_code: str
    number: str
    name: str
    base_color: tuple[int, int, int]
    shape_seed: int
    # `id` d'une autre carte du même motif (mission « risques & pièges ») — `None` si cette carte
    # est visuellement unique dans le jeu.
    confusable_with: str | None


def _color_for_index(index: int, total: int) -> tuple[int, int, int]:
    """Une teinte différente et bien séparée par carte (roue HSV) — au contraire d'une petite
    palette recyclée, qui ferait passer des cartes sans rapport pour visuellement proches et
    fausserait la mesure d'ambiguïté (constaté en écrivant ce script : `_PALETTE` à 8 couleurs
    pour 90 cartes en faisait des dizaines de "confusables" involontaires)."""
    hue = int((index / total) * 179)
    hsv = np.uint8([[[hue, 160, 210]]])
    bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)[0][0]
    return int(bgr[0]), int(bgr[1]), int(bgr[2])


def generate_dataset(
    *, base_count: int = 90, confusable_pairs: int = 10, seed: int = 20260920
) -> list[VisualSyntheticCard]:
    """`base_count` cartes visuellement uniques + `confusable_pairs` cartes supplémentaires qui
    reprennent délibérément le motif d'une carte de base (mission « risques & pièges ») — au
    total `base_count + confusable_pairs` cartes, réparties dans deux extensions synthétiques
    (`vsyn-a`/`vsyn-b`) pour que numéro + extension restent uniques par ligne."""
    rng = np.random.default_rng(seed)
    cards: list[VisualSyntheticCard] = []

    for i in range(base_count):
        color = _color_for_index(i, base_count)
        cards.append(
            VisualSyntheticCard(
                id=f"base_{i:03d}",
                set_code="vsyn-a",
                number=str(i + 1),
                name=f"Carte synthétique {i + 1}",
                base_color=color,
                shape_seed=i,
                confusable_with=None,
            )
        )

    confusable_targets = rng.choice(base_count, size=confusable_pairs, replace=False)
    for j, target in enumerate(confusable_targets):
        source = cards[int(target)]
        cards.append(
            VisualSyntheticCard(
                id=f"reprint_{j:03d}",
                set_code="vsyn-b",
                number=str(j + 1),
                name=f"{source.name} (réimpression)",
                base_color=source.base_color,
                shape_seed=source.shape_seed,
                confusable_with=source.id,
            )
        )
        # La relation est symétrique : la carte de base fait aussi partie du groupe ambigu.
        cards[int(target)] = VisualSyntheticCard(
            **{**source.__dict__, "confusable_with": f"reprint_{j:03d}"}
        )

    return cards
