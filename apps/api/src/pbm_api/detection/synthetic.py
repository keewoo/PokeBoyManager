"""Générateur de photos synthétiques (mission point 3) — en l'absence d'appareil photo et de
vraies photos de classeur sur chimera, ce module produit un jeu déterministe (graine fixe) qui
couvre les familles demandées : carte seule, classeur 3×3 en toploaders, classeur avec reflets,
cartes sur table, fond clair à faible contraste. Chaque photo connaît son nombre de cartes
attendu, ce qui permet de mesurer un taux de détection reproductible en CI.

⚠️ Ceci ne remplace pas une vraie campagne photo (aucun appareil sur chimera, aucune carte
physique) : l'écart est documenté dans le compte rendu du lot `v3-detection`. Le rôle de ce jeu
est de valider la logique du pipeline (contours, ratio, ordre de lecture, repli) sur des cas
synthétiques construits pour ressembler aux pièges connus, pas de mesurer la précision réelle
d'OpenCV ou d'un LLM sur une vraie photo.
"""

from dataclasses import dataclass

import cv2
import numpy as np

CARD_W, CARD_H = 180, 252  # ratio 63:88 à l'échelle d'un canevas de quelques centaines de px


@dataclass(frozen=True)
class SyntheticPhoto:
    id: str
    category: str
    image: np.ndarray  # BGR, comme `cv2.imdecode`
    expected_count: int
    ground_truth_quads: list[np.ndarray]  # ordre de lecture gauche->droite, haut->bas


def noisy_background(
    rng: np.random.Generator, size: tuple[int, int], base_color: tuple[int, int, int]
) -> np.ndarray:
    height, width = size
    canvas = np.full((height, width, 3), base_color, dtype=np.uint8)
    noise = rng.normal(0, 6, (height, width, 3))
    canvas = np.clip(canvas.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    return canvas


def card_quad(center: tuple[float, float], angle_deg: float, scale: float = 1.0) -> np.ndarray:
    box = cv2.boxPoints(((center[0], center[1]), (CARD_W * scale, CARD_H * scale), angle_deg))
    return box.astype(np.float32)


def draw_card(
    canvas: np.ndarray,
    quad: np.ndarray,
    *,
    fill: tuple[int, int, int],
    border: tuple[int, int, int],
    border_thickness: int = 4,
    glare: bool = False,
) -> None:
    pts = quad.astype(np.int32)
    cv2.fillConvexPoly(canvas, pts, fill)
    cv2.polylines(canvas, [pts], isClosed=True, color=border, thickness=border_thickness)
    # Illustration grossière pour casser l'uniformité (un contour vide se détecte trop
    # facilement, une vraie carte a un dessin à l'intérieur).
    center = tuple(pts.mean(axis=0).astype(int))
    cv2.circle(canvas, center, min(CARD_W, CARD_H) // 5, tuple(int(c * 0.7) for c in fill), -1)

    if glare:
        # Bande translucide claire en diagonale sur une partie de la carte, comme un reflet de
        # pochette plastique sous éclairage direct (mission « risques & pièges »).
        overlay = canvas.copy()
        band_pts = np.array(
            [
                quad[0],
                quad[1],
                quad[1] + (quad[2] - quad[1]) * 0.5,
                quad[0] + (quad[3] - quad[0]) * 0.5,
            ],
            dtype=np.int32,
        )
        cv2.fillConvexPoly(overlay, band_pts, (255, 255, 255))
        cv2.addWeighted(overlay, 0.55, canvas, 0.45, 0, dst=canvas)


def make_single_card(seed: int, index: int) -> SyntheticPhoto:
    rng = np.random.default_rng(seed)
    canvas = noisy_background(rng, (500, 400), (150, 170, 150))
    angle = float(rng.uniform(-15, 15))
    center = (200 + float(rng.uniform(-30, 30)), 250 + float(rng.uniform(-30, 30)))
    quad = card_quad(center, angle, scale=1.6)
    draw_card(canvas, quad, fill=(210, 200, 170), border=(40, 40, 40))
    return SyntheticPhoto(
        id=f"carte_seule_{index}", category="carte_seule", image=canvas,
        expected_count=1, ground_truth_quads=[quad],
    )


def make_binder_grid(seed: int, index: int, *, glare: bool) -> SyntheticPhoto:
    rng = np.random.default_rng(seed)
    canvas = noisy_background(rng, (1000, 800), (235, 235, 235))
    quads: list[np.ndarray] = []
    margin_x, margin_y = 130, 150
    step_x, step_y = 260, 290
    for row in range(3):
        for col in range(3):
            jitter_x = float(rng.uniform(-8, 8))
            jitter_y = float(rng.uniform(-8, 8))
            angle = float(rng.uniform(-4, 4))
            center = (
                margin_x + col * step_x + jitter_x,
                margin_y + row * step_y + jitter_y,
            )
            quad = card_quad(center, angle, scale=1.0)
            quads.append(quad)
            card_glare = glare and (row + col) % 2 == 0
            draw_card(canvas, quad, fill=(200, 190, 160), border=(30, 30, 30), glare=card_glare)
    category = "classeur_3x3_reflets" if glare else "classeur_3x3"
    return SyntheticPhoto(
        id=f"{category}_{index}", category=category, image=canvas,
        expected_count=9, ground_truth_quads=quads,
    )


def make_table_scatter(seed: int, index: int, count: int) -> SyntheticPhoto:
    rng = np.random.default_rng(seed)
    canvas = noisy_background(rng, (700, 900), (90, 120, 150))  # bois/table sombre
    quads: list[np.ndarray] = []
    positions = [
        (200 + i * 220 + float(rng.uniform(-40, 40)), 350 + float(rng.uniform(-60, 60)))
        for i in range(count)
    ]
    for center in positions:
        angle = float(rng.uniform(-25, 25))
        quad = card_quad(center, angle, scale=1.3)
        quads.append(quad)
        draw_card(canvas, quad, fill=(215, 205, 180), border=(20, 20, 20))
    quads.sort(key=lambda q: (q[:, 1].mean(), q[:, 0].mean()))
    return SyntheticPhoto(
        id=f"table_{index}", category="table", image=canvas,
        expected_count=count, ground_truth_quads=quads,
    )


def make_light_background(seed: int, index: int, grid: bool) -> SyntheticPhoto:
    """Fond clair (mission « risques & pièges ») : carte à peine plus contrastée que le fond —
    le cas où OpenCV seul est censé échouer et où le repli LLM doit prendre le relais."""
    rng = np.random.default_rng(seed)
    canvas = noisy_background(rng, (600, 500), (248, 248, 248))
    quads: list[np.ndarray] = []
    centers = [(250, 300)] if not grid else [(180, 200), (380, 200), (180, 420), (380, 420)]
    for center in centers:
        angle = float(rng.uniform(-3, 3))
        quad = card_quad(center, angle, scale=1.1)
        quads.append(quad)
        draw_card(canvas, quad, fill=(238, 238, 236), border=(225, 225, 220), border_thickness=2)
    category = "fond_clair"
    return SyntheticPhoto(
        id=f"{category}_{index}", category=category, image=canvas,
        expected_count=len(centers), ground_truth_quads=quads,
    )


def generate_dataset(seed: int = 20260919) -> list[SyntheticPhoto]:
    """30 photos synthétiques (mission point 3) : 8 carte seule, 6 classeur 3×3 propre, 6
    classeur 3×3 avec reflets, 6 table (2 à 5 cartes en vrac), 4 fond clair (1 ou 4 cartes)."""
    photos: list[SyntheticPhoto] = []
    for i in range(8):
        photos.append(make_single_card(seed + i, i))
    for i in range(6):
        photos.append(make_binder_grid(seed + 100 + i, i, glare=False))
    for i in range(6):
        photos.append(make_binder_grid(seed + 200 + i, i, glare=True))
    scatter_counts = [2, 3, 3, 4, 4, 5]
    for i, count in enumerate(scatter_counts):
        photos.append(make_table_scatter(seed + 300 + i, i, count))
    for i in range(4):
        photos.append(make_light_background(seed + 400 + i, i, grid=(i % 2 == 0)))
    return photos
