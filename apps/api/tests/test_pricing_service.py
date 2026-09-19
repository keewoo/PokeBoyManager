"""Relevé quotidien de prix (`pbm_api.pricing.service.collect_daily_prices`).

TCGdex et Pokémon TCG API sont remplacés par des doublures, comme `test_import_service.py` — ces
tests ne dépendent d'aucun réseau. `test_collect_daily_prices_writes_cardmarket_and_tcgplayer_rows`
échoue sans ce lot (le module `pbm_api.pricing.service` n'existe pas) et passe avec.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from pbm_api.catalog.ptcg_client import PtcgUnavailableError
from pbm_api.models import Card, CardPriceDaily, PriceSource, PriceVariant, Set
from pbm_api.pricing.service import EmptyPriceRunError, collect_daily_prices

DAY = date(2026, 9, 19)

TCGDEX_CARD_DETAIL = {
    "id": "sv03.5-006",
    "pricing": {
        "cardmarket": {"low": 4, "avg": 8.74, "trend": 8.74, "trend-holo": 0},
    },
}

PTCG_CARD = {
    "id": "sv3pt5-6",
    "tcgplayer": {"prices": {"holofoil": {"low": 4.49, "mid": 9.25, "market": 8.36}}},
}


class FakeTcgdexClient:
    def __init__(self, details: dict[str, dict] | None = None, failing: set[str] = frozenset()):
        self._details = details if details is not None else {"sv03.5-006": TCGDEX_CARD_DETAIL}
        self._failing = failing
        self.calls: list[str] = []

    async def get_card(self, lang: str, card_id: str) -> dict:
        self.calls.append(card_id)
        if card_id in self._failing:
            raise RuntimeError("panne simulée TCGdex")
        return self._details[card_id]


class FakePtcgClient:
    def __init__(self, cards_by_set: dict[str, list[dict]] | None = None):
        self._cards_by_set = cards_by_set if cards_by_set is not None else {"sv3pt5": [PTCG_CARD]}

    async def list_cards_in_set(self, ptcg_set_id: str) -> list[dict]:
        return self._cards_by_set.get(ptcg_set_id, [])


class UnavailablePtcgClient:
    async def list_cards_in_set(self, ptcg_set_id: str) -> list[dict]:
        raise PtcgUnavailableError("Pokémon TCG API indisponible après 3 tentatives (500)")


async def _make_card(db_session, *, tcgdex_id: str | None, ptcg_id: str | None) -> Card:
    set_row = Set(code=f"set-{tcgdex_id or ptcg_id}", name="Set de test")
    db_session.add(set_row)
    await db_session.flush()
    card = Card(
        set_id=set_row.id, number="6", name="Carte de test", tcgdex_id=tcgdex_id, ptcg_id=ptcg_id
    )
    db_session.add(card)
    await db_session.flush()
    return card


async def test_collect_daily_prices_writes_cardmarket_and_tcgplayer_rows(db_session):
    card = await _make_card(db_session, tcgdex_id="sv03.5-006", ptcg_id="sv3pt5-6")

    report = await collect_daily_prices(db_session, FakeTcgdexClient(), FakePtcgClient(), day=DAY)

    assert report["prices_written_cardmarket"] == 1
    assert report["prices_written_tcgplayer"] == 1
    assert report["errors"] == []

    rows = (
        (await db_session.execute(select(CardPriceDaily).where(CardPriceDaily.card_id == card.id)))
        .scalars()
        .all()
    )
    by_source_variant = {(r.source, r.variant): r for r in rows}

    cardmarket_row = by_source_variant[(PriceSource.cardmarket, PriceVariant.normal)]
    assert cardmarket_row.currency == "EUR"
    assert cardmarket_row.price_trend == Decimal("8.74")
    assert cardmarket_row.day == DAY

    tcgplayer_row = by_source_variant[(PriceSource.tcgplayer, PriceVariant.holo)]
    assert tcgplayer_row.currency == "USD"
    assert tcgplayer_row.price_trend == Decimal("8.36")

    # Pas de version holo côté Cardmarket pour cette carte (trend-holo == 0 dans la doublure).
    assert (PriceSource.cardmarket, PriceVariant.holo) not in by_source_variant


async def test_collect_daily_prices_is_idempotent(db_session):
    await _make_card(db_session, tcgdex_id="sv03.5-006", ptcg_id="sv3pt5-6")

    await collect_daily_prices(db_session, FakeTcgdexClient(), FakePtcgClient(), day=DAY)
    await collect_daily_prices(db_session, FakeTcgdexClient(), FakePtcgClient(), day=DAY)

    rows = (await db_session.execute(select(CardPriceDaily))).scalars().all()
    assert len(rows) == 2  # une ligne cardmarket + une ligne tcgplayer, pas de doublon


async def test_collect_daily_prices_continues_after_a_card_failure(db_session):
    ok_card = await _make_card(db_session, tcgdex_id="sv03.5-006", ptcg_id=None)
    failing_card = await _make_card(db_session, tcgdex_id="sv03.5-025", ptcg_id=None)

    tcgdex = FakeTcgdexClient(
        details={"sv03.5-006": TCGDEX_CARD_DETAIL, "sv03.5-025": TCGDEX_CARD_DETAIL},
        failing={"sv03.5-025"},
    )

    report = await collect_daily_prices(db_session, tcgdex, None, day=DAY)

    assert report["prices_written_cardmarket"] == 1
    assert len(report["errors"]) == 1
    assert "sv03.5-025" in report["errors"][0]

    ok_rows = (
        (
            await db_session.execute(
                select(CardPriceDaily).where(CardPriceDaily.card_id == ok_card.id)
            )
        )
        .scalars()
        .all()
    )
    failing_rows = (
        (
            await db_session.execute(
                select(CardPriceDaily).where(CardPriceDaily.card_id == failing_card.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(ok_rows) == 1
    assert failing_rows == []


async def test_collect_daily_prices_degrades_when_ptcg_unavailable(db_session):
    await _make_card(db_session, tcgdex_id="sv03.5-006", ptcg_id="sv3pt5-6")

    report = await collect_daily_prices(
        db_session, FakeTcgdexClient(), UnavailablePtcgClient(), day=DAY
    )

    assert report["prices_written_cardmarket"] == 1
    assert report["prices_written_tcgplayer"] == 0
    assert "indisponible" in report["errors"][0]


async def test_collect_daily_prices_raises_when_nothing_written(db_session):
    await _make_card(db_session, tcgdex_id="sv03.5-999", ptcg_id=None)
    tcgdex = FakeTcgdexClient(details={"sv03.5-999": {"id": "sv03.5-999", "pricing": {}}})

    with pytest.raises(EmptyPriceRunError):
        await collect_daily_prices(db_session, tcgdex, None, day=DAY)


async def test_collect_daily_prices_no_cards_does_not_raise(db_session):
    report = await collect_daily_prices(db_session, FakeTcgdexClient(details={}), None, day=DAY)

    assert report["cards_total"] == 0
