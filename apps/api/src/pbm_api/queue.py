"""Pool arq pour mettre un job en file depuis une route HTTP (mission `v3-detection`).

Jusqu'ici, tous les jobs arq du dépôt étaient déclenchés en cron ou en CLI direct
(`import_catalogue_task`, `daily_prices_task`, `pbm_api.worker`) : aucun point d'entrée
n'enfilait de job depuis l'API elle-même. `POST /uploads/{id}/complete` (mission `v3-upload`)
crée déjà la ligne `Job` mais ne la mettait pas en file — ce module comble ce manque pour le
job `detect_cards`.
"""

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from pbm_api.config import settings


async def get_arq_pool() -> ArqRedis:
    """Un pool par appel, comme `pbm_api.security.rate_limit.get_redis` : le volume (une mise
    en file par envoi de photos complété) ne justifie pas un pool partagé à l'échelle de l'app."""
    return await create_pool(
        RedisSettings.from_dsn(settings.redis_url),
        default_queue_name=f"{settings.redis_prefix}queue",
    )
