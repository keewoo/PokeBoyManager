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


async def test_image_proxy_works_with_local_storage_backend(db_session, tmp_path):
    """Sur le PROD `STORAGE_BACKEND=local` (disque du serveur, aucun S3/MinIO) : le proxy doit
    cacher puis servir depuis le disque. Le proxy codait `ObjectStorage()` en dur et renvoyait 500
    pour TOUTES les cartes en PROD — l'accueil visiteur (`pbm-front-accueil`) retombait alors sur
    neuf « Image à venir ». Ce test aurait mordu (`pbm-hotfix-img-proxy-storage`)."""
    from pbm_api.storage.local import LocalObjectStorage

    local = LocalObjectStorage(root=str(tmp_path))
    await local.ensure_bucket()
    card = await _make_card(db_session, "local", "https://assets.tcgdex.net/fr/sv/sv03.5/007")
    fake_tcgdex = FakeImageTcgdexClient()
    async with await _client_for(db_session, local, fake_tcgdex) as client:
        first = await client.get(f"/img/cards/{card.id}", params={"size": "low"})
        second = await client.get(f"/img/cards/{card.id}", params={"size": "low"})

    assert first.status_code == 200
    assert first.content == b"fake-image-bytes"
    assert second.status_code == 200
    assert fake_tcgdex.fetch_calls == [
        ("https://assets.tcgdex.net/fr/sv/sv03.5/007", "low")
    ], "un seul appel réseau : le deuxième doit venir du cache disque local, pas d'un S3 supposé"


def test_image_proxy_uses_configured_storage_backend_not_hardcoded_s3():
    """Garde anti-régression directe : le proxy passe par `build_storage()` (respecte
    `STORAGE_BACKEND`), jamais un `ObjectStorage()` (client S3) codé en dur — celui-ci lève une
    erreur de connexion sur le PROD en stockage local et casse le proxy pour toutes les cartes."""
    import inspect

    from pbm_api.routers import images

    source = inspect.getsource(images)
    assert "build_storage()" in source, "le proxy doit construire son stockage via build_storage()"
    # Le marqueur du bug est l'import DIRECT du client S3 (immunisé contre une mention en
    # commentaire) : s'il réapparaît, quelqu'un a recodé le backend en dur.
    assert "from pbm_api.s3 import ObjectStorage" not in source, (
        "le proxy ne doit pas importer le client S3 directement : passer par build_storage() "
        "(respecte STORAGE_BACKEND), sinon 500 sur le PROD en stockage local"
    )
