"""Cache d'identification par empreinte perceptuelle (mission point 4) : une carte déjà
identifiée dont l'empreinte est suffisamment proche (distance de Hamming <= `HAMMING_THRESHOLD`)
ne rappelle jamais l'IA. Partagé entre tous les utilisateurs, comme `card_insights`
(`pbm_api.models.catalog`) : le résultat d'une identification (extraction + candidats) ne dépend
que de l'image photographiée, jamais de qui l'a envoyée.

Recherche par XOR + `bit_count` (Postgres 14+, donc compatible PG16 dev et PG18 cible
production) plutôt qu'un index spécialisé : le volume (une ligne par carte réellement
photographiée un jour, pas par le catalogue entier) reste modeste, à revoir si la latence
devient sensible — même caveat que `pbm_api.catalog.search` pour son coût en requêtes.
"""

from sqlalchemy import cast, func, select
from sqlalchemy.dialects.postgresql import BIT
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.identification.schemas import CardExtraction
from pbm_api.models.identification import IdentificationCache

# Mesuré sur le jeu synthétique (`scripts/measure_identification_rate.py`, voir le compte
# rendu) : tolère de petites variations de prise de vue sans confondre deux cartes voisines
# dans un même set (même illustration de dos, numéros consécutifs).
HAMMING_THRESHOLD = 6


async def find_cached(session: AsyncSession, phash: int) -> IdentificationCache | None:
    # `bit_count` n'a de variante Postgres que pour `bytea`/`bit` (depuis PG14), pas pour un
    # entier — le XOR (bigint) est calculé d'abord, casté en `bit(64)` ensuite.
    distance = func.bit_count(cast(IdentificationCache.phash.op("#")(phash), BIT(64)))
    stmt = (
        select(IdentificationCache)
        .where(distance <= HAMMING_THRESHOLD)
        .order_by(distance)
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def store_cache(
    session: AsyncSession,
    phash: int,
    extraction: CardExtraction,
    candidates: list[dict],
    tier: str,
    *,
    method: str,
) -> IdentificationCache:
    row = IdentificationCache(
        phash=phash,
        extraction=extraction.model_dump(mode="json"),
        candidates=candidates,
        tier=tier,
        method=method,
    )
    session.add(row)
    await session.flush()
    return row
