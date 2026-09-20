"""`GET /cards/featured` (mission `pbm-front-accueil`, point 1) : neuf vraies cartes pour la
démonstration de l'accueil visiteur — publique (pas de session, contrairement aux autres routes
de `pbm_api.routers.cards`), une par extension, la plus valorisée, jamais une carte sans image
officielle ni sans prix connu.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from pbm_api.models import Card, CardPriceDaily, PriceSource, PriceVariant, Set
from pbm_api.ranking.service import refresh_card_value_rank

TODAY = datetime.now(UTC).date()


async def _make_set(db_session, *, name: str) -> Set:
    set_row = Set(code=f"featured-{uuid.uuid4().hex[:8]}", name=name, series=name)
    db_session.add(set_row)
    await db_session.flush()
    return set_row


async def _make_card(
    db_session,
    set_row: Set,
    *,
    name: str,
    number: str = "1",
    image_url: str | None = "https://example.com/cards/1",
) -> Card:
    card = Card(set_id=set_row.id, number=number, name=name, image_url=image_url)
    db_session.add(card)
    await db_session.flush()
    return card


async def _add_price(db_session, card: Card, *, trend: Decimal) -> None:
    db_session.add(
        CardPriceDaily(
            card_id=card.id,
            source=PriceSource.cardmarket,
            variant=PriceVariant.normal,
            day=TODAY,
            currency="EUR",
            price_low=trend,
            price_mid=trend,
            price_trend=trend,
        )
    )
    await db_session.flush()


async def test_get_featured_cards_requires_no_session(api_client):
    response = await api_client.get("/cards/featured")

    assert response.status_code == 200


async def test_get_featured_cards_returns_empty_list_without_data(api_client):
    response = await api_client.get("/cards/featured")

    assert response.status_code == 200
    assert response.json() == []


async def test_get_featured_cards_picks_the_priciest_card_per_set(api_client, db_session):
    set_a = await _make_set(db_session, name="Écarlate et Violet")
    cheap_in_a = await _make_card(db_session, set_a, name="Racaillou", number="1")
    pricey_in_a = await _make_card(db_session, set_a, name="Dracaufeu-EX", number="2")
    await _add_price(db_session, cheap_in_a, trend=Decimal("2"))
    await _add_price(db_session, pricey_in_a, trend=Decimal("199.90"))

    set_b = await _make_set(db_session, name="Voltage Éclatant")
    only_in_b = await _make_card(db_session, set_b, name="Pikachu VMAX", number="1")
    await _add_price(db_session, only_in_b, trend=Decimal("42"))

    await refresh_card_value_rank(db_session)

    response = await api_client.get("/cards/featured")

    assert response.status_code == 200
    body = response.json()
    ids = {c["id"] for c in body}
    assert str(pricey_in_a.id) in ids
    assert str(cheap_in_a.id) not in ids
    assert str(only_in_b.id) in ids
    # Triée par valeur décroissante : l'extension la plus chère d'abord.
    assert body[0]["id"] == str(pricey_in_a.id)


async def test_get_featured_cards_excludes_cards_without_image_or_price(api_client, db_session):
    set_row = await _make_set(db_session, name="Écarlate et Violet 151")
    no_image = await _make_card(db_session, set_row, name="Mew", number="1", image_url=None)
    await _add_price(db_session, no_image, trend=Decimal("500"))

    no_price = await _make_card(db_session, set_row, name="Mewtwo", number="2")

    await refresh_card_value_rank(db_session)

    response = await api_client.get("/cards/featured")

    assert response.status_code == 200
    ids = {c["id"] for c in response.json()}
    assert str(no_image.id) not in ids
    assert str(no_price.id) not in ids


async def test_get_featured_cards_caps_at_nine(api_client, db_session):
    for i in range(12):
        set_row = await _make_set(db_session, name=f"Extension {i}")
        card = await _make_card(db_session, set_row, name=f"Carte {i}", number="1")
        await _add_price(db_session, card, trend=Decimal(str(10 + i)))

    await refresh_card_value_rank(db_session)

    response = await api_client.get("/cards/featured")

    assert response.status_code == 200
    assert len(response.json()) == 9
