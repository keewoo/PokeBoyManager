"""Traitement de l'avatar : recadrage centré en carré, redimensionnement, ré-encodage JPEG.

Le recadrage est fait côté serveur (pas d'éditeur de recadrage côté front) : toute photo
JPEG/PNG envoyée est centrée sur son plus petit côté puis redimensionnée — reproductible,
sans dépendre d'un canvas navigateur.
"""

import io

from PIL import Image, ImageOps, UnidentifiedImageError

from pbm_api.ai.errors import UnsupportedImageFormatError
from pbm_api.profile.errors import AvatarTooLargeError

AVATAR_SIZE = 512
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_MEDIA_TYPES = {"image/jpeg", "image/png"}


def process_avatar(data: bytes) -> bytes:
    """Renvoie l'avatar recadré en carré, `AVATAR_SIZE`×`AVATAR_SIZE`, encodé en JPEG."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise AvatarTooLargeError

    try:
        with Image.open(io.BytesIO(data)) as source:
            image = ImageOps.exif_transpose(source) or source
            image = image.convert("RGB")
    except UnidentifiedImageError as exc:
        raise UnsupportedImageFormatError(
            "Format d'image non reconnu (JPEG ou PNG attendus)."
        ) from exc

    width, height = image.size
    side = min(width, height)
    left = (width - side) // 2
    top = (height - side) // 2
    image = image.crop((left, top, left + side, top + side))
    image = image.resize((AVATAR_SIZE, AVATAR_SIZE), Image.LANCZOS)

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=88)
    return buffer.getvalue()
