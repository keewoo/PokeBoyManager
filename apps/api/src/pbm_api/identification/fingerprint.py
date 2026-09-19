"""Empreinte perceptuelle d'un recadrage (mission point 4) : la même carte rephotographiée ne
rappelle jamais l'IA — comparée par distance de Hamming (`pbm_api.identification.cache`),
tolérante aux petites variations de prise de vue (luminosité, flou léger) qu'une comparaison
des octets JPEG ne tolérerait pas.

Hachage moyen (aHash) 64 bits : le recadrage est déjà redressé à taille fixe (630×880 px,
`pbm_api.detection.geometry`), ce qui rend l'empreinte nettement plus stable d'une photo à
l'autre que sur une image quelconque.
"""

import cv2
import numpy as np

_HASH_SIZE = 8  # 8×8 = 64 bits
_UNSIGNED_64_MASK = 0xFFFFFFFFFFFFFFFF
_SIGN_BIT = 0x8000000000000000
_WRAP = 0x10000000000000000


def _to_signed64(value: int) -> int:
    """Même motif binaire, en entier signé 64 bits — la seule représentation qu'un `bigint`
    Postgres puisse stocker (le XOR utilisé par `pbm_api.identification.cache` reste correct
    quel que soit le signe, seule la suite de bits compte)."""
    value &= _UNSIGNED_64_MASK
    return value - _WRAP if value >= _SIGN_BIT else value


def compute_phash(crop_bgr: np.ndarray) -> int:
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, (_HASH_SIZE, _HASH_SIZE), interpolation=cv2.INTER_AREA)
    mean = float(small.mean())
    bits = (small > mean).flatten()
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return _to_signed64(value)


def hamming_distance(a: int, b: int) -> int:
    return bin((a & _UNSIGNED_64_MASK) ^ (b & _UNSIGNED_64_MASK)).count("1")
