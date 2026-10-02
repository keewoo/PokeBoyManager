"""Moteur SQLAlchemy async et fabrique de sessions, partagés par l'API et le worker."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from pbm_api.config import settings

engine = create_async_engine(settings.database_url, pool_pre_ping=True)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncSession:
    """Dépendance FastAPI : ouvre une session par requête, fermée (commit/rollback) à la sortie."""
    async with async_session_factory() as session:
        yield session
