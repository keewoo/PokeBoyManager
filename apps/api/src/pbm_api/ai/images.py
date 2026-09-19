"""Détection du type MIME d'une photo à partir de ses octets — jamais supposé : l'origine de
l'upload (front, import) peut fournir du JPEG, du PNG ou du WebP indifféremment."""

from pbm_api.ai.errors import UnsupportedImageFormatError

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"
_RIFF_MAGIC = b"RIFF"
_WEBP_MARKER = b"WEBP"


def detect_media_type(data: bytes) -> str:
    if data.startswith(_PNG_MAGIC):
        return "image/png"
    if data.startswith(_JPEG_MAGIC):
        return "image/jpeg"
    if data[:4] == _RIFF_MAGIC and data[8:12] == _WEBP_MARKER:
        return "image/webp"
    raise UnsupportedImageFormatError("Format d'image non reconnu (JPEG, PNG ou WebP attendus).")
