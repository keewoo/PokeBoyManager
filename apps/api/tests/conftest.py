import os

import httpx
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from pbm_api.config import settings
from pbm_api.db import get_session
from pbm_api.email import EmailSender, get_email_sender
from pbm_api.main import app
from pbm_api.security.compromised import CompromisedPasswordChecker, get_compromised_checker
from pbm_api.security.rate_limit import get_redis

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v1_auth_test",
)


@pytest_asyncio.fixture
async def db_session():
    """Une session par test, dans une transaction annulée en fin de test (rien n'est persisté)."""
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        # `expire_on_commit=False` comme `pbm_api.db.async_session_factory` : sans ça, accéder
        # à un attribut après un `commit()` (le routeur auth en fait) déclenche un rechargement
        # implicite hors du pont greenlet de SQLAlchemy async (`MissingGreenlet`).
        session = AsyncSession(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()
    await engine.dispose()


class RecordingEmailSender(EmailSender):
    """Capture les e-mails au lieu de les envoyer — la suite pytest ne dépend d'aucun SMTP
    (CI n'a pas de Mailpit). La preuve « e-mails reçus dans Mailpit » se fait manuellement,
    documentée dans le compte rendu du lot."""

    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    async def send(self, to: str, subject: str, body: str) -> None:
        self.sent.append({"to": to, "subject": subject, "body": body})


class FakeCompromisedChecker(CompromisedPasswordChecker):
    """Substitut déterministe de l'appel réseau HIBP — pas de dépendance à un service tiers
    dans la suite automatisée."""

    def __init__(self, compromised: frozenset[str] = frozenset()) -> None:
        self._compromised = compromised

    async def is_compromised(self, password: str) -> bool:
        return password in self._compromised


@pytest_asyncio.fixture(autouse=True)
async def _clean_rate_limit_state():
    """Les tests HTTP partagent la même IP source (TestClient) : sans ce nettoyage, les
    compteurs de limitation se propageraient d'un test à l'autre."""
    redis = get_redis()
    pattern = f"{settings.redis_prefix}ratelimit:*"

    async def _flush() -> None:
        async for key in redis.scan_iter(pattern):
            await redis.delete(key)

    await _flush()
    yield
    await _flush()


@pytest_asyncio.fixture
async def api_client(db_session):
    """Client HTTP contre l'app réelle, base de données de test, e-mails/HIBP simulés.

    `httpx.AsyncClient` + `ASGITransport` (pas `fastapi.testclient.TestClient`) : le client
    synchrone exécute l'app dans un thread/boucle asyncio séparés, incompatible avec le
    partage d'une session SQLAlchemy async créée dans la boucle du test (« attached to a
    different loop »). `ASGITransport` exécute l'app dans la même boucle que le test.

    `base_url` en `https://` : les cookies de session/CSRF sont posés `Secure`, un client
    `http://` ne les renverrait pas sur la requête suivante.
    """

    async def _get_session_override():
        yield db_session

    email_sender = RecordingEmailSender()
    compromised_checker = FakeCompromisedChecker()

    app.dependency_overrides[get_session] = _get_session_override
    app.dependency_overrides[get_email_sender] = lambda: email_sender
    app.dependency_overrides[get_compromised_checker] = lambda: compromised_checker

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client:
        client.email_sender = email_sender  # type: ignore[attr-defined]
        client.compromised_checker = compromised_checker  # type: ignore[attr-defined]
        yield client

    app.dependency_overrides.clear()
