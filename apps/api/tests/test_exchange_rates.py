"""Taux de change BCE (`pbm_api.pricing.exchange_rates`) — flux XML remplacé par une doublure,
comme les autres clients tiers de ce dépôt : aucun test ne dépend du réseau.

`test_store_daily_rates_then_get_rate_to_eur_returns_the_stored_rate` échoue sans ce lot (le
module `pbm_api.pricing.exchange_rates` n'existe pas) et passe avec.
"""

from datetime import date
from decimal import Decimal

import httpx
import pytest

from pbm_api.pricing.exchange_rates import (
    EcbClient,
    EcbUnavailableError,
    convert_from_eur,
    convert_to_eur,
    get_rate_to_eur,
    store_daily_rates,
)

ECB_XML_SAMPLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01"
                  xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
    <gesmes:subject>Reference rates</gesmes:subject>
    <Cube>
        <Cube time='2026-09-18'>
            <Cube currency='USD' rate='1.1460'/>
            <Cube currency='GBP' rate='0.85880'/>
        </Cube>
    </Cube>
</gesmes:Envelope>
"""

DAY = date(2026, 9, 18)
EARLIER_DAY = date(2026, 9, 10)
LATER_DAY = date(2026, 9, 19)


async def test_store_daily_rates_then_get_rate_to_eur_returns_the_stored_rate(db_session):
    await store_daily_rates(db_session, DAY, {"USD": Decimal("1.1460"), "GBP": Decimal("0.8588")})

    rate = await get_rate_to_eur(db_session, "USD", DAY)

    assert rate == Decimal("1.1460")


async def test_store_daily_rates_is_idempotent(db_session):
    await store_daily_rates(db_session, DAY, {"USD": Decimal("1.1000")})
    await store_daily_rates(db_session, DAY, {"USD": Decimal("1.2000")})

    rate = await get_rate_to_eur(db_session, "USD", DAY)

    assert rate == Decimal("1.2000")


async def test_get_rate_to_eur_falls_back_to_most_recent_prior_day(db_session):
    await store_daily_rates(db_session, EARLIER_DAY, {"USD": Decimal("1.1000")})

    # Aucun taux publié le week-end : on demande un jour plus tard, on retombe sur le dernier
    # taux connu avant ou à cette date, jamais une extrapolation.
    rate = await get_rate_to_eur(db_session, "USD", LATER_DAY)

    assert rate == Decimal("1.1000")


async def test_get_rate_to_eur_returns_none_when_no_rate_known_yet(db_session):
    rate = await get_rate_to_eur(db_session, "USD", EARLIER_DAY)

    assert rate is None


async def test_get_rate_to_eur_eur_is_always_one(db_session):
    assert await get_rate_to_eur(db_session, "EUR", DAY) == Decimal("1")


async def test_ecb_client_parses_the_daily_xml_feed():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=ECB_XML_SAMPLE))
    client = EcbClient(http_client=httpx.AsyncClient(transport=transport))

    published_day, rates = await client.fetch_daily_rates()

    assert published_day == date(2026, 9, 18)
    assert rates == {"USD": Decimal("1.1460"), "GBP": Decimal("0.85880")}


async def test_ecb_client_raises_on_http_error():
    transport = httpx.MockTransport(lambda request: httpx.Response(503))
    client = EcbClient(http_client=httpx.AsyncClient(transport=transport))

    with pytest.raises(EcbUnavailableError):
        await client.fetch_daily_rates()


async def test_ecb_client_raises_on_unparseable_body():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"not xml"))
    client = EcbClient(http_client=httpx.AsyncClient(transport=transport))

    with pytest.raises(EcbUnavailableError):
        await client.fetch_daily_rates()


def test_convert_round_trip():
    rate = Decimal("1.1460")
    amount_eur = Decimal("10.00")

    converted = convert_from_eur(amount_eur, rate)
    back = convert_to_eur(converted, rate)

    assert converted == Decimal("11.460")
    assert round(back, 2) == amount_eur
