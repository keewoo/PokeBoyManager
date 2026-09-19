"""Image annotée de contrôle (mission point 4) : contours détectés + numéro d'ordre de
lecture, encodée en JPEG — c'est la preuve visuelle jointe à chaque photo traitée."""

import cv2
import numpy as np

_BOX_COLOR = (0, 200, 0)
_TEXT_COLOR = (0, 0, 255)


def draw_control_image(image: np.ndarray, quads: list[np.ndarray]) -> bytes:
    annotated = image.copy()
    for index, quad in enumerate(quads, start=1):
        pts = quad.reshape(-1, 1, 2).astype(np.int32)
        cv2.polylines(annotated, [pts], isClosed=True, color=_BOX_COLOR, thickness=3)
        origin = tuple(quad.reshape(4, 2).min(axis=0).astype(int))
        cv2.putText(
            annotated,
            str(index),
            (origin[0] + 6, origin[1] + 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            _TEXT_COLOR,
            2,
        )
    return encode_jpeg(annotated, quality=90)


def encode_jpeg(image: np.ndarray, *, quality: int = 92) -> bytes:
    ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("échec de l'encodage JPEG de l'image")
    return buffer.tobytes()
