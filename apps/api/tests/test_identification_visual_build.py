"""`pbm_api.identification.visual_build` (mission `v3-identification-visuelle` point 1) :
déduction de l'URL de l'image officielle par langue, calcul des empreintes, upsert dans
`card_visual_index` — et `VisualIndex.load` qui les relit (`pbm_api.identification.visual_index`).

Avant ce lot, ce module n'existait pas : chacun de ces tests échoue à la collection et passe une
fois le module ajouté.
"""

import uuid

import cv2
import numpy as np
import pytest
from sqlalchemy import select

from pbm_api.identification.fingerprint import compute_phash
from pbm_api.identification.visual_build import (
    UndecodableImageError,
    compute_visual_hashes,
    image_url_for_language,
    upsert_visual_index_entry,
)
from pbm_api.identification.visual_geometry import illustration_region, normalize_to_card_canvas
from pbm_api.identification.visual_index import VisualIndex
from pbm_api.models import Card, Set
from pbm_api.models.identification import CardVisualIndex


def _official_image_bytes(color: tuple[int, int, int]) -> bytes:
    canvas = np.full((337, 245, 3), color, dtype=np.uint8)
    cv2.rectangle(canvas, (10, 30), (235, 200), (10, 10, 10), 4)
    ok, buffer = cv2.imencode(".png", canvas)
    assert ok
    return buffer.tobytes()


def test_image_url_for_language_swaps_the_language_segment():
    url = "https://assets.tcgdex.net/fr/sv/sv01/1"
    assert image_url_for_language(url, "en") == "https://assets.tcgdex.net/en/sv/sv01/1"


def test_image_url_for_language_rejects_unexpected_shape():
    with pytest.raises(ValueError):
        image_url_for_language("https://assets.tcgdex.net/not-a-card-path", "en")


def test_compute_visual_hashes_matches_manual_computation():
    image_bytes = _official_image_bytes((180, 160, 140))
    full_phash, illustration_phash = compute_visual_hashes(image_bytes)

    decoded = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    canvas = normalize_to_card_canvas(decoded)
    assert full_phash == compute_phash(canvas)
    assert illustration_phash == compute_phash(illustration_region(canvas))


def test_compute_visual_hashes_rejects_undecodable_bytes():
    with pytest.raises(UndecodableImageError):
        compute_visual_hashes(b"not an image")


async def _seed_card(db_session) -> Card:
    suffix = uuid.uuid4().hex[:8]
    set_row = Set(code=f"vb-{suffix}", name="Visual build", total_cards=10)
    db_session.add(set_row)
    await db_session.flush()
    card = Card(set_id=set_row.id, number="1", name="Carte de test")
    db_session.add(card)
    await db_session.flush()
    return card


async def test_upsert_visual_index_entry_creates_then_updates(db_session):
    card = await _seed_card(db_session)
    first_bytes = _official_image_bytes((200, 200, 200))

    await upsert_visual_index_entry(db_session, card.id, "fr", first_bytes, "cards/x/fr/low.webp")
    await db_session.flush()

    result = await db_session.execute(
        select(CardVisualIndex).where(CardVisualIndex.card_id == card.id)
    )
    rows = result.scalars().all()
    assert len(rows) == 1
    first_full_phash = rows[0].full_phash

    second_bytes = _official_image_bytes((10, 10, 10))
    await upsert_visual_index_entry(db_session, card.id, "fr", second_bytes, "cards/x/fr/low.webp")
    await db_session.flush()

    result = await db_session.execute(
        select(CardVisualIndex).where(CardVisualIndex.card_id == card.id)
    )
    rows = result.scalars().all()
    assert len(rows) == 1  # mis à jour, pas dupliqué (contrainte unique card_id+language)
    assert rows[0].full_phash != first_full_phash


async def test_visual_index_load_reads_every_language_row(db_session):
    card = await _seed_card(db_session)
    await upsert_visual_index_entry(
        db_session, card.id, "fr", _official_image_bytes((50, 60, 70)), None
    )
    await upsert_visual_index_entry(
        db_session, card.id, "en", _official_image_bytes((90, 80, 70)), None
    )
    await db_session.flush()

    index = await VisualIndex.load(db_session)
    assert len(index) == 2
