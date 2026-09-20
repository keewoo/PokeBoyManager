"""Normalisation d'une photo envoyée (`pbm_api.uploads.processing`), correctif
`pbm-hotfix-formats-image`.

Un test par format réellement accepté (JPEG, MPO, PNG, HEIC, WEBP, JPEG à orientation EXIF 6) +
le refus propre d'un format non géré (GIF). Chaque fichier de test est fabriqué ici, pas lu depuis
le dépôt. `test_mpo_*` est le garde-fou du défaut de production : il échoue si le MPO redevient
refusé.
"""

import io

import pillow_heif
import pytest
from PIL import Image
from PIL.ExifTags import Base as ExifTag

from pbm_api.uploads.processing import (
    ACCEPTED_FORMATS_LABEL,
    UnsupportedImageError,
    process_uploaded_image,
)

pillow_heif.register_heif_opener()


def _jpeg_bytes(color: str = "red", size: tuple[int, int] = (48, 32)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG")
    return buf.getvalue()


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), "blue").save(buf, format="PNG")
    return buf.getvalue()


def _heic_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), "green").save(buf, format="HEIF")
    return buf.getvalue()


def _webp_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), (200, 100, 50)).save(buf, format="WEBP")
    return buf.getvalue()


def _mpo_bytes() -> bytes:
    """Un MPO = deux images JPEG dans un même conteneur (segments APP2 « MPF »), ce que produisent
    les modes portrait/HDR des téléphones. Pillow le rapporte comme `MPO`."""
    buf = io.BytesIO()
    Image.new("RGB", (48, 32), "red").save(
        buf, format="MPO", append_images=[Image.new("RGB", (48, 32), "blue")]
    )
    return buf.getvalue()


def _jpeg_orientation6_bytes() -> bytes:
    """Image paysage (large) marquée orientation EXIF 6 (« rotation 90° horaire à l'affichage ») :
    après application de l'orientation, elle doit devenir portrait (haute)."""
    image = Image.new("RGB", (64, 32), "red")  # paysage : plus large que haute
    exif = image.getexif()
    exif[ExifTag.Orientation.value] = 6
    buf = io.BytesIO()
    image.save(buf, format="JPEG", exif=exif.tobytes())
    return buf.getvalue()


def test_jpeg_accepted_and_reencoded_as_jpeg():
    result = process_uploaded_image(_jpeg_bytes())
    assert result.format == "JPEG"
    assert result.content_type == "image/jpeg"
    assert Image.open(io.BytesIO(result.data)).format == "JPEG"


def test_mpo_accepted_and_reduced_to_single_jpeg():
    """Le défaut de production : les photos portrait/HDR des téléphones sont des MPO, rejetées
    avant ce correctif. Ce test échoue si le MPO redevient refusé."""
    raw = _mpo_bytes()
    # Garde-fou : on teste bien un MPO (et non un JPEG que Pillow aurait écrit à la place).
    assert Image.open(io.BytesIO(raw)).format == "MPO"

    result = process_uploaded_image(raw)

    assert result.format == "JPEG"
    assert result.content_type == "image/jpeg"
    out = Image.open(io.BytesIO(result.data))
    assert out.format == "JPEG"  # ramené à une seule image JPEG, plus un conteneur MPO


def test_png_accepted_and_kept_as_png():
    result = process_uploaded_image(_png_bytes())
    assert result.format == "PNG"
    assert result.content_type == "image/png"
    assert Image.open(io.BytesIO(result.data)).format == "PNG"


def test_heic_accepted_and_reencoded_as_jpeg():
    result = process_uploaded_image(_heic_bytes())
    assert result.format == "JPEG"
    assert result.content_type == "image/jpeg"
    assert Image.open(io.BytesIO(result.data)).format == "JPEG"


def test_webp_accepted_and_reencoded_as_jpeg():
    raw = _webp_bytes()
    assert Image.open(io.BytesIO(raw)).format == "WEBP"

    result = process_uploaded_image(raw)

    assert result.format == "JPEG"
    assert result.content_type == "image/jpeg"
    assert Image.open(io.BytesIO(result.data)).format == "JPEG"


def test_exif_orientation_is_applied_before_reencoding():
    """Orientation 6 = l'image est stockée couchée. Une carte prise en paysage doit arriver
    portrait (haute) dans le pipeline de détection, et le tag d'orientation doit avoir disparu."""
    raw = _jpeg_orientation6_bytes()
    source = Image.open(io.BytesIO(raw))
    assert source.width > source.height  # paysage à l'entrée
    assert source.getexif().get(ExifTag.Orientation.value) == 6

    result = process_uploaded_image(raw)

    out = Image.open(io.BytesIO(result.data))
    assert out.height > out.width  # portrait après application de l'orientation
    # Plus aucune orientation « à corriger » : le tag a été appliqué puis retiré (aucun `exif=`
    # réinjecté au réencodage).
    assert out.getexif().get(ExifTag.Orientation.value) in (None, 1)


def test_gif_is_refused_with_a_clear_message():
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), "red").save(buf, format="GIF")

    with pytest.raises(UnsupportedImageError) as excinfo:
        process_uploaded_image(buf.getvalue())

    message = str(excinfo.value)
    assert "GIF" in message
    assert ACCEPTED_FORMATS_LABEL in message  # cite les formats acceptés


def test_non_image_bytes_are_refused():
    with pytest.raises(UnsupportedImageError):
        process_uploaded_image(b"ceci n'est pas une image, juste du texte" * 20)


def test_empty_bytes_are_refused():
    with pytest.raises(UnsupportedImageError):
        process_uploaded_image(b"")
