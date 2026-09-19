"""Construction d'une entrée d'index visuel (mission `v3-identification-visuelle` point 1) à
partir de l'image officielle basse définition d'une carte : deux empreintes (illustration, carte
entière) après la même normalisation géométrique que le recadrage utilisateur
(`pbm_api.identification.visual_geometry`) — sans quoi une simple différence d'échelle ferait
diverger deux hachages qui devraient être proches.
"""

import re
import uuid

import cv2
import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.identification.fingerprint import compute_phash
from pbm_api.identification.visual_geometry import illustration_region, normalize_to_card_canvas
from pbm_api.models.identification import CardVisualIndex

# `Card.image_url` est fixé à la langue primaire de l'import (`fr`, voir
# `catalog.import_service`) — jamais recalculé par langue. Le chemin TCGdex a toujours la forme
# `.../<lang>/<serie>/<extension>/<numero-local>` (vérifié sur des dizaines d'extensions,
# 2026-09-20) : substituer le segment de langue donne l'URL de l'autre langue sans second appel
# API. Documenté comme une déduction d'URL, pas un contrat publié par TCGdex — si le format
# change un jour, `build_visual_index.py` le signalera par des échecs de téléchargement en
# nombre, jamais silencieusement.
_LANG_SEGMENT_RE = re.compile(r"^(https://[^/]+)/[a-z]{2}(/.*)$")


class UndecodableImageError(Exception):
    """L'image officielle n'a pas pu être décodée (téléchargement tronqué, format inattendu) —
    jamais avalé en silence : `scripts/build_visual_index.py` la compte en échec."""


def image_url_for_language(base_image_url: str, language: str) -> str:
    match = _LANG_SEGMENT_RE.match(base_image_url)
    if match is None:
        raise ValueError(f"URL d'image officielle inattendue : {base_image_url}")
    return f"{match.group(1)}/{language}{match.group(2)}"


def compute_visual_hashes(image_bytes: bytes) -> tuple[int, int]:
    """`(full_phash, illustration_phash)` à partir des octets d'une image officielle (webp/jpeg/
    png, peu importe le format d'origine — décodée par OpenCV)."""
    decoded = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if decoded is None:
        raise UndecodableImageError("image officielle illisible")
    canvas = normalize_to_card_canvas(decoded)
    return compute_phash(canvas), compute_phash(illustration_region(canvas))


async def upsert_visual_index_entry(
    session: AsyncSession,
    card_id: uuid.UUID,
    language: str,
    image_bytes: bytes,
    source_image_key: str | None = None,
) -> CardVisualIndex:
    full_phash, illustration_phash = compute_visual_hashes(image_bytes)

    result = await session.execute(
        select(CardVisualIndex).where(
            CardVisualIndex.card_id == card_id, CardVisualIndex.language == language
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = CardVisualIndex(card_id=card_id, language=language)
        session.add(row)
    row.full_phash = full_phash
    row.illustration_phash = illustration_phash
    row.source_image_key = source_image_key
    return row
