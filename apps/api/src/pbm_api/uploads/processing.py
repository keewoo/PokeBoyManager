"""Vérification et normalisation d'une photo envoyée (mission `v3-upload` point 2).

`Image.open(...).load()` force le décodage réel des octets : un fichier renommé en `.jpg`
qui n'est pas une image lève `UnidentifiedImageError`/`OSError` ici — c'est le contrôle
« type réel (magic bytes) », pas une confiance dans l'en-tête `Content-Type` envoyé par le
client. Réenregistrer l'image sans repasser le paramètre `exif=` supprime les métadonnées
(position GPS incluse) : vérifié, `Image.save(...)` sans `exif=` explicite n'embarque pas
`image.info["exif"]` même s'il est présent après l'ouverture.
"""

import io
from dataclasses import dataclass

import pillow_heif
from PIL import Image, UnidentifiedImageError

pillow_heif.register_heif_opener()

ALLOWED_SOURCE_FORMATS = {"JPEG", "PNG", "HEIF"}
CONTENT_TYPE_BY_FORMAT = {"JPEG": "image/jpeg", "PNG": "image/png"}


class UnsupportedImageError(Exception):
    """Le fichier n'est pas une image reconnue, ou pas dans un format accepté."""


@dataclass(frozen=True)
class ProcessedImage:
    data: bytes
    content_type: str
    format: str


def process_uploaded_image(raw: bytes) -> ProcessedImage:
    if not raw:
        raise UnsupportedImageError("fichier vide")

    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise UnsupportedImageError(
            "le fichier n'est pas reconnu comme une image JPEG, PNG ou HEIC"
        ) from exc

    source_format = image.format
    if source_format not in ALLOWED_SOURCE_FORMATS:
        raise UnsupportedImageError(f"format d'image non accepté : {source_format}")

    output = io.BytesIO()
    if source_format == "PNG":
        image.save(output, format="PNG")
        target_format = "PNG"
    else:
        # HEIC → JPEG (mission point 2) ; un JPEG est réencodé en JPEG pour la même raison
        # que le PNG : perdre `image.info["exif"]` au passage.
        image.convert("RGB").save(output, format="JPEG", quality=92)
        target_format = "JPEG"

    return ProcessedImage(
        data=output.getvalue(),
        content_type=CONTENT_TYPE_BY_FORMAT[target_format],
        format=target_format,
    )
