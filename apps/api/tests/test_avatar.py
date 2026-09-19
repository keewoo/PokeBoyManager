"""Traitement de l'avatar (`pbm_api.profile.avatar`) : recadrage centré en carré et
ré-encodage, indépendamment de toute route HTTP."""

import io

import pytest
from PIL import Image

from pbm_api.ai.errors import UnsupportedImageFormatError
from pbm_api.profile.avatar import AVATAR_SIZE, MAX_UPLOAD_BYTES, process_avatar
from pbm_api.profile.errors import AvatarTooLargeError


def _jpeg_bytes(width: int, height: int, color=(200, 30, 30)) -> bytes:
    image = Image.new("RGB", (width, height), color=color)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def test_process_avatar_crops_a_wide_photo_to_a_centered_square() -> None:
    processed = process_avatar(_jpeg_bytes(800, 400))

    with Image.open(io.BytesIO(processed)) as image:
        assert image.size == (AVATAR_SIZE, AVATAR_SIZE)
        assert image.format == "JPEG"


def test_process_avatar_crops_a_tall_photo_to_a_centered_square() -> None:
    processed = process_avatar(_jpeg_bytes(300, 900))

    with Image.open(io.BytesIO(processed)) as image:
        assert image.size == (AVATAR_SIZE, AVATAR_SIZE)


def test_process_avatar_rejects_data_that_is_not_an_image() -> None:
    with pytest.raises(UnsupportedImageFormatError):
        process_avatar(b"pas une image")


def test_process_avatar_rejects_a_file_above_the_size_limit() -> None:
    with pytest.raises(AvatarTooLargeError):
        process_avatar(b"x" * (MAX_UPLOAD_BYTES + 1))
