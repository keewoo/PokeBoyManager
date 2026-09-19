"""`pbm_api.identification.fingerprint` (mission point 4) : la même carte rephotographiée ne
doit jamais recoûter un appel IA — vérifié ici sur l'empreinte seule (distance de Hamming),
`test_identification_cache.py` vérifie le cache qui s'en sert.
"""

import cv2
import numpy as np

from pbm_api.identification.fingerprint import compute_phash, hamming_distance


def _solid_crop(color: tuple[int, int, int]) -> np.ndarray:
    canvas = np.full((880, 630, 3), color, dtype=np.uint8)
    cv2.rectangle(canvas, (60, 90), (570, 790), (30, 30, 30), 6)
    cv2.circle(canvas, (315, 440), 120, tuple(int(c * 0.6) for c in color), -1)
    return canvas


def test_identical_crops_produce_identical_hash():
    crop = _solid_crop((200, 180, 150))
    assert compute_phash(crop) == compute_phash(crop.copy())


def test_slightly_perturbed_crop_stays_close():
    """Un peu de bruit (comme une seconde prise de vue) ne doit pas faire diverger l'empreinte
    au-delà du seuil de tolérance utilisé par le cache (`HAMMING_THRESHOLD` = 6)."""
    rng = np.random.default_rng(42)
    crop = _solid_crop((200, 180, 150))
    noise = rng.normal(0, 4, crop.shape)
    perturbed = np.clip(crop.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    distance = hamming_distance(compute_phash(crop), compute_phash(perturbed))
    assert distance <= 6


def test_different_cards_produce_distant_hash():
    light_crop = _solid_crop((235, 235, 230))
    dark_crop = _solid_crop((40, 60, 90))

    distance = hamming_distance(compute_phash(light_crop), compute_phash(dark_crop))
    assert distance > 6


def test_hash_round_trips_as_signed_64_bit_integer():
    """`identification_cache.phash` est un `bigint` Postgres (signé) — l'empreinte doit rester
    dans cette plage quelle que soit la suite de 64 bits produite."""
    for color in [(0, 0, 0), (255, 255, 255), (255, 0, 0), (0, 255, 0), (0, 0, 255)]:
        value = compute_phash(_solid_crop(color))
        assert -(2**63) <= value <= 2**63 - 1
