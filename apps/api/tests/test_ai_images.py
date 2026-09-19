"""Détection du type MIME d'une photo à partir de ses octets (`pbm_api.ai.images`) — jamais
supposé, une carte pouvant être envoyée en JPEG, PNG ou WebP selon l'origine de l'upload."""

import pytest

from pbm_api.ai.errors import UnsupportedImageFormatError
from pbm_api.ai.images import detect_media_type

_PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
    "53de0000000c4944415408d763f8ffff3f0005fe02fea739666500000000"
    "49454e44ae426082"
)
_JPEG_HEADER = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 20
_WEBP_HEADER = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 20


def test_detect_media_type_recognizes_png() -> None:
    assert detect_media_type(_PNG_1X1) == "image/png"


def test_detect_media_type_recognizes_jpeg() -> None:
    assert detect_media_type(_JPEG_HEADER) == "image/jpeg"


def test_detect_media_type_recognizes_webp() -> None:
    assert detect_media_type(_WEBP_HEADER) == "image/webp"


def test_detect_media_type_rejects_unknown_format() -> None:
    with pytest.raises(UnsupportedImageFormatError):
        detect_media_type(b"not an image")
