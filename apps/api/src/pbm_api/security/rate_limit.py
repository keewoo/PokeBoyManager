"""Limitation de tentatives par fenêtre glissante, via Redis (compteur + expiration)."""

from redis.asyncio import Redis

from pbm_api.config import settings


class RateLimiter:
    def __init__(self, redis: Redis, max_attempts: int, window_seconds: int) -> None:
        self._redis = redis
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds

    def _key(self, scope: str, identifier: str) -> str:
        return f"{settings.redis_prefix}ratelimit:{scope}:{identifier}"

    async def hit(self, scope: str, identifier: str) -> bool:
        """Enregistre une tentative ; renvoie False si la limite est dépassée."""
        key = self._key(scope, identifier)
        count = await self._redis.incr(key)
        if count == 1:
            await self._redis.expire(key, self._window_seconds)
        return count <= self._max_attempts

    async def reset(self, scope: str, identifier: str) -> None:
        await self._redis.delete(self._key(scope, identifier))


def get_redis() -> Redis:
    """Un client par appel : `redis.asyncio.Redis` est lié à la boucle asyncio courante — un
    singleton de module survivrait à un changement de boucle (déjà vu en tests, une boucle
    par test). Le coût de construction est négligeable face à un aller-retour réseau."""
    return Redis.from_url(settings.redis_url, decode_responses=True)


def get_login_rate_limiter() -> RateLimiter:
    return RateLimiter(
        get_redis(),
        max_attempts=settings.login_rate_limit_max_attempts,
        window_seconds=settings.login_rate_limit_window_seconds,
    )
