"""Vérification et normalisation d'une photo envoyée (mission `v3-upload` point 2, élargie par
le correctif `pbm-hotfix-formats-image`).

`Image.open(...).load()` force le décodage réel des octets : un fichier renommé en `.jpg`
qui n'est pas une image lève `UnidentifiedImageError`/`OSError` ici — c'est le contrôle
« type réel (magic bytes) », pas une confiance dans l'en-tête `Content-Type` envoyé par le
client.

Formats acceptés — ce que les téléphones envoient réellement :
- JPEG : réencodé en JPEG (perd `image.info["exif"]` au passage) ;
- MPO : JPEG multi-images produit par les modes portrait/HDR d'iPhone et d'Android — Pillow le
  rapporte comme `MPO` ; on garde la première image (la photo pleine résolution) et on réencode
  en JPEG. C'était le défaut de production : un MPO parfaitement lisible était rejeté ;
- PNG : conservé en PNG ;
- HEIC/HEIF : décodé par `pillow_heif`, réencodé en JPEG ;
- WEBP : réencodé en JPEG.

L'orientation EXIF est appliquée avant réencodage (`ImageOps.exif_transpose`) : une carte
photographiée en paysage ne doit pas arriver couchée dans la détection. `exif_transpose` retire
au passage le tag d'orientation, et aucun `exif=` n'est réinjecté au `save` — les métadonnées
(position GPS incluse) ne sont donc jamais réécrites. Le GIF (animé compris) et tout autre
format restent refusés, avec un message clair citant les formats acceptés.
"""

import io
from dataclasses import dataclass

import pillow_heif
from PIL import Image, ImageOps, UnidentifiedImageError

pillow_heif.register_heif_opener()

# Ce que Pillow rapporte comme `image.format` pour ce que les gens envoient vraiment. HEIC et
# HEIF sont tous deux rapportés `HEIF` par `pillow_heif`.
ALLOWED_SOURCE_FORMATS = {"JPEG", "MPO", "PNG", "HEIF", "WEBP"}

# Libellés lisibles pour le message de refus : jamais un code Pillow brut isolé à l'écran.
ACCEPTED_FORMATS_LABEL = "JPEG, PNG, HEIC, WEBP"

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
        raise UnsupportedImageError(
            f"fichier vide (formats acceptés : {ACCEPTED_FORMATS_LABEL})"
        )

    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise UnsupportedImageError(
            f"le fichier n'est pas reconnu comme une image ({ACCEPTED_FORMATS_LABEL})"
        ) from exc

    source_format = image.format
    if source_format not in ALLOWED_SOURCE_FORMATS:
        raise UnsupportedImageError(
            f"format d'image « {source_format} » non pris en charge "
            f"(formats acceptés : {ACCEPTED_FORMATS_LABEL})"
        )

    # MPO = JPEG multi-images (portrait/HDR) : la première image est la photo pleine résolution.
    # `Image.open` s'y positionne déjà ; `seek(0)` le garantit sans supposer l'état du curseur.
    if source_format == "MPO":
        image.seek(0)

    # Applique l'orientation EXIF (une carte prise en paysage ne doit pas arriver couchée) et
    # retire le tag d'orientation au passage — sans effet si l'image n'en porte pas.
    image = ImageOps.exif_transpose(image)

    output = io.BytesIO()
    if source_format == "PNG":
        image.save(output, format="PNG")
        target_format = "PNG"
    else:
        # JPEG/MPO/HEIC/WEBP → JPEG : uniformise le pipeline de détection et laisse tomber
        # `image.info["exif"]` (aucun `exif=` réinjecté).
        image.convert("RGB").save(output, format="JPEG", quality=92)
        target_format = "JPEG"

    return ProcessedImage(
        data=output.getvalue(),
        content_type=CONTENT_TYPE_BY_FORMAT[target_format],
        format=target_format,
    )
