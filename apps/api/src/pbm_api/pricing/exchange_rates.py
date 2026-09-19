"""Taux de change quotidiens BCE (https://www.ecb.europa.eu/stats/eurofxref) — mission point 2.

Flux public, sans clé, un point par jour ouvré (la BCE ne publie pas le week-end ni les jours
fériés TARGET) : `get_rate_to_eur` cherche le taux le plus récent à la date demandée ou avant,
jamais une extrapolation.
"""

import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.models import ExchangeRateDaily

ECB_DAILY_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
_NS = {"ecb": "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"}


class EcbUnavailableError(RuntimeError):
    """Le flux BCE n'a pas répondu ou son contenu est illisible."""


class EcbClient:
    """Enveloppe fine autour du flux XML quotidien de la BCE."""

    def __init__(
        self, http_client: httpx.AsyncClient | None = None, url: str = ECB_DAILY_URL
    ) -> None:
        self._client = http_client or httpx.AsyncClient(timeout=20.0)
        self._url = url
        self._owns_client = http_client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def fetch_daily_rates(self) -> tuple[date, dict[str, Decimal]]:
        """Retourne `(jour_publie, {devise: taux})` — taux = unités de devise pour 1 EUR."""
        try:
            response = await self._client.get(self._url)
            response.raise_for_status()
            root = ET.fromstring(response.content)
        except (httpx.HTTPStatusError, httpx.TransportError, ET.ParseError) as exc:
            raise EcbUnavailableError(f"flux BCE indisponible ou illisible : {exc}") from exc

        day_cube = root.find(".//ecb:Cube/ecb:Cube[@time]", _NS)
        if day_cube is None:
            raise EcbUnavailableError("flux BCE : aucune date publiée dans la réponse")
        published_day = date.fromisoformat(day_cube.attrib["time"])

        rates = {
            cube.attrib["currency"]: Decimal(cube.attrib["rate"])
            for cube in day_cube.findall("ecb:Cube", _NS)
            if cube.get("currency") and cube.get("rate")
        }
        if not rates:
            raise EcbUnavailableError("flux BCE : réponse sans aucun taux")
        return published_day, rates


async def store_daily_rates(
    session: AsyncSession, day: date, rates: dict[str, Decimal]
) -> int:
    """Enregistre les taux du jour, idempotent (met à jour si déjà présents)."""
    written = 0
    for currency, rate in rates.items():
        stmt = pg_insert(ExchangeRateDaily).values(day=day, currency=currency, rate=rate)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_exchange_rates_daily_day_currency", set_={"rate": stmt.excluded.rate}
        )
        await session.execute(stmt)
        written += 1
    await session.commit()
    return written


async def get_rate_to_eur(
    session: AsyncSession, currency: str, as_of: date
) -> Decimal | None:
    """Taux le plus récent connu à `as_of` ou avant. `None` si aucun relevé (jamais inventé)."""
    if currency == "EUR":
        return Decimal("1")
    result = await session.execute(
        select(ExchangeRateDaily.rate)
        .where(ExchangeRateDaily.currency == currency, ExchangeRateDaily.day <= as_of)
        .order_by(ExchangeRateDaily.day.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def convert_from_eur(amount_eur: Decimal, rate_to_eur: Decimal) -> Decimal:
    return amount_eur * rate_to_eur


def convert_to_eur(amount: Decimal, rate_to_eur: Decimal) -> Decimal:
    return amount / rate_to_eur
