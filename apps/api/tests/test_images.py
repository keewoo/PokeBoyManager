"""Proxy `/img/cards/{id}` — MinIO/S3 réel (bucket du lot, `S3_BUCKET`), TCGdex remplacé par une
doublure qui compte ses appels : le test prouve la mise en cache au premier accès sans dépendre
du réseau externe.
"""

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from pbm_api.db import get_session
from pbm_api.main import app
from pbm_api.models import Card, Set
from pbm_api.routers.images import get_storage, get_tcgdex_client
from pbm_api.s3 import ObjectStorage


class FakeImageTcgdexClient:
    def __init__(self):
        self.fetch_calls: list[tuple[str, str]] = []

    async def fetch_image_bytes(self, image_base_url: str, size: str) -> bytes:
        self.fetch_calls.append((image_base_url, size))
        return b"fake-image-bytes"


class FailingImageTcgdexClient:
    async def fetch_image_bytes(self, image_base_url: str, size: str) -> bytes:
        raise httpx.ConnectError("panne simulée")


async def _make_card(session, suffix: str, image_url: str | None) -> Card:
    set_row = Set(code=f"img-{suffix}", name="Set")
    session.add(set_row)
    await session.flush()
    card = Card(set_id=set_row.id, number="1", name="Card", image_url=image_url)
    session.add(card)
    await session.flush()
    return card


@pytest.fixture
async def storage():
    object_storage = ObjectStorage()
    await object_storage.ensure_bucket()
    return object_storage


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


async def _client_for(db_session, storage_override, tcgdex_override):
    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_storage] = lambda: storage_override
    app.dependency_overrides[get_tcgdex_client] = lambda: tcgdex_override
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_image_proxy_fetches_once_then_serves_from_cache(db_session, storage):
    card = await _make_card(
        db_session, "cache", "https://assets.tcgdex.net/fr/sv/sv03.5/006"
    )
    fake_tcgdex = FakeImageTcgdexClient()
    async with await _client_for(db_session, storage, fake_tcgdex) as client:
        first = await client.get(f"/img/cards/{card.id}", params={"size": "high"})
        second = await client.get(f"/img/cards/{card.id}", params={"size": "high"})

    assert first.status_code == 200
    assert first.content == b"fake-image-bytes"
    assert second.status_code == 200
    assert second.content == b"fake-image-bytes"
    assert fake_tcgdex.fetch_calls == [
        ("https://assets.tcgdex.net/fr/sv/sv03.5/006", "high")
    ], "un seul appel réseau attendu : le deuxième doit venir du cache S3"


async def test_image_proxy_404_when_card_has_no_image(db_session, storage):
    card = await _make_card(db_session, "noimage", None)
    fake_tcgdex = FakeImageTcgdexClient()
    async with await _client_for(db_session, storage, fake_tcgdex) as client:
        response = await client.get(f"/img/cards/{card.id}")

    assert response.status_code == 404
    assert fake_tcgdex.fetch_calls == []


async def test_image_proxy_502_when_official_source_unreachable(db_session, storage):
    card = await _make_card(
        db_session, "unreachable", "https://assets.tcgdex.net/fr/sv/sv03.5/999"
    )
    async with await _client_for(db_session, storage, FailingImageTcgdexClient()) as client:
        response = await client.get(f"/img/cards/{card.id}")

    assert response.status_code == 502
