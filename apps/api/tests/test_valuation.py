"""Service `valuation` (`pbm_api.pricing.valuation`) : décote par état, référence de prix,
valeur d'un exemplaire et d'une collection.

`test_item_value_applies_condition_decote` échoue sans ce lot (le module
`pbm_api.pricing.valuation` n'existe pas) et passe avec.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pbm_api.models import Card, CardPriceDaily, PriceSource, PriceVariant, Set, User
from pbm_api.models.collection import CollectionItem
from pbm_api.pricing.exchange_rates import store_daily_rates
from pbm_api.pricing.valuation import (
    CONDITION_MULTIPLIERS,
    collection_value,
    condition_multiplier,
    item_value,
    reference_price_eur,
)

DAY = date(2026, 9, 19)


def test_condition_multiplier_known_grade():
    assert condition_multiplier("excellent") == CONDITION_MULTIPLIERS["excellent"]


def test_condition_multiplier_unknown_or_missing_defaults_to_near_mint():
    assert condition_multiplier(None) == CONDITION_MULTIPLIERS["near_mint"]
    assert condition_multiplier("not-a-real-grade") == CONDITION_MULTIPLIERS["near_mint"]


async def _make_card(db_session) -> Card:
    set_row = Set(code=f"val-{uuid.uuid4().hex[:8]}", name="Set de valorisation")
    db_session.add(set_row)
    await db_session.flush()
    card = Card(set_id=set_row.id, number="1", name="Carte de valorisation")
    db_session.add(card)
    await db_session.flush()
    return card


async def _make_user(db_session) -> User:
    user = User(
        email=f"user-{uuid.uuid4()}@example.com",
        password_hash="x",
        last_name="Test",
        birth_date=date(2000, 1, 1),
        terms_version="test",
        terms_accepted_at=datetime(2000, 1, 1),
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _add_price(
    db_session,
    card,
    *,
    source,
    variant=PriceVariant.normal,
    currency="EUR",
    low=None,
    mid=None,
    trend=None,
    day=DAY,
):
    db_session.add(
        CardPriceDaily(
            card_id=card.id,
            source=source,
            variant=variant,
            day=day,
            currency=currency,
            price_low=low,
            price_mid=mid,
            price_trend=trend,
        )
    )
    await db_session.flush()


async def test_reference_price_prefers_cardmarket_trend_over_tcgplayer(db_session):
    card = await _make_card(db_session)
    await _add_price(
        db_session, card, source=PriceSource.cardmarket, low=4, mid=8, trend=Decimal("8.74")
    )
    await _add_price(
        db_session,
        card,
        source=PriceSource.tcgplayer,
        currency="USD",
        low=4,
        mid=9,
        trend=Decimal("9"),
    )

    reference = await reference_price_eur(db_session, card.id, PriceVariant.normal, DAY)

    assert reference == Decimal("8.74")


async def test_reference_price_falls_back_to_converted_tcgplayer(db_session):
    card = await _make_card(db_session)
    await _add_price(
        db_session,
        card,
        source=PriceSource.tcgplayer,
        currency="USD",
        low=4,
        mid=9,
        trend=Decimal("10"),
    )
    await store_daily_rates(db_session, DAY, {"USD": Decimal("1.1460")})

    reference = await reference_price_eur(db_session, card.id, PriceVariant.normal, DAY)

    assert reference == Decimal("10") / Decimal("1.1460")


async def test_reference_price_missing_when_no_source_available(db_session):
    card = await _make_card(db_session)

    reference = await reference_price_eur(db_session, card.id, PriceVariant.normal, DAY)

    assert reference is None


async def test_reference_price_missing_when_tcgplayer_has_no_exchange_rate(db_session):
    card = await _make_card(db_session)
    await _add_price(
        db_session,
        card,
        source=PriceSource.tcgplayer,
        currency="USD",
        low=4,
        mid=9,
        trend=Decimal("10"),
    )
    # Aucun store_daily_rates ici : le job de taux de change n'a pas encore tourné ce jour-là.

    reference = await reference_price_eur(db_session, card.id, PriceVariant.normal, DAY)

    assert reference is None


async def test_reference_price_clamps_an_outlier_trend(db_session):
    card = await _make_card(db_session)
    # Tendance à 100 pour un prix moyen de 5 : marché fin, un seul vendeur — bornée à 3x le
    # prix moyen (risque documenté du lot : « ne doit pas faire exploser la valeur »).
    await _add_price(
        db_session,
        card,
        source=PriceSource.cardmarket,
        low=4,
        mid=Decimal("5"),
        trend=Decimal("100"),
    )

    reference = await reference_price_eur(db_session, card.id, PriceVariant.normal, DAY)

    assert reference == Decimal("15")  # 5 * OUTLIER_TREND_MULTIPLE (3)


async def test_item_value_applies_condition_decote(db_session):
    card = await _make_card(db_session)
    await _add_price(
        db_session, card, source=PriceSource.cardmarket, low=8, mid=10, trend=Decimal("10")
    )
    user = await _make_user(db_session)
    item = CollectionItem(
        user_id=user.id,
        card_id=card.id,
        language="fr",
        variant=PriceVariant.normal,
        condition_grade="excellent",
    )
    db_session.add(item)
    await db_session.flush()

    value = await item_value(db_session, item, as_of=DAY)

    assert value == Decimal("10") * CONDITION_MULTIPLIERS["excellent"]


async def test_item_value_neutralized_to_zero_for_suspected_counterfeit(db_session):
    """Mission `v3-etat` point 3 : une carte signalée contrefaçon probable n'est jamais
    valorisée comme l'originale, même avec un prix de référence et un état mint."""
    card = await _make_card(db_session)
    await _add_price(
        db_session, card, source=PriceSource.cardmarket, low=8, mid=10, trend=Decimal("10")
    )
    user = await _make_user(db_session)
    item = CollectionItem(
        user_id=user.id,
        card_id=card.id,
        language="fr",
        variant=PriceVariant.normal,
        condition_grade="mint",
        counterfeit_suspected=True,
    )
    db_session.add(item)
    await db_session.flush()

    assert await item_value(db_session, item, as_of=DAY) == Decimal("0")
    assert await item_value(db_session, item, as_of=DAY, currency="USD") == Decimal("0")


async def test_item_value_none_when_no_price_available(db_session):
    card = await _make_card(db_session)
    user = await _make_user(db_session)
    item = CollectionItem(user_id=user.id, card_id=card.id, language="fr")
    db_session.add(item)
    await db_session.flush()

    assert await item_value(db_session, item, as_of=DAY) is None


async def test_collection_value_sums_priced_items_and_counts_missing(db_session):
    user = await _make_user(db_session)
    priced_card = await _make_card(db_session)
    unpriced_card = await _make_card(db_session)
    await _add_price(
        db_session, priced_card, source=PriceSource.cardmarket, low=8, mid=10, trend=Decimal("10")
    )

    db_session.add_all(
        [
            CollectionItem(
                user_id=user.id,
                card_id=priced_card.id,
                language="fr",
                variant=PriceVariant.normal,
                condition_grade="mint",
            ),
            CollectionItem(user_id=user.id, card_id=unpriced_card.id, language="fr"),
        ]
    )
    await db_session.flush()

    report = await collection_value(db_session, user.id, as_of=DAY)

    assert report["total"] == Decimal("10")
    assert report["items_total"] == 2
    assert report["items_priced"] == 1
    assert report["items_missing_price"] == 1
    assert report["currency"] == "EUR"


async def test_collection_value_converts_to_requested_currency(db_session):
    user = await _make_user(db_session)
    card = await _make_card(db_session)
    await _add_price(
        db_session, card, source=PriceSource.cardmarket, low=8, mid=10, trend=Decimal("10")
    )
    await store_daily_rates(db_session, DAY, {"USD": Decimal("1.1460")})
    db_session.add(
        CollectionItem(
            user_id=user.id,
            card_id=card.id,
            language="fr",
            variant=PriceVariant.normal,
            condition_grade="mint",
        )
    )
    await db_session.flush()

    report = await collection_value(db_session, user.id, as_of=DAY, currency="USD")

    assert report["currency"] == "USD"
    assert report["total"] == Decimal("10") * Decimal("1.1460")


async def test_collection_value_is_isolated_by_user(db_session):
    """Équivalent du test d'accès croisé (pas de route HTTP dans ce lot, voir
    `test_cross_user_isolation.py`) : la valorisation de A ne doit jamais compter les
    exemplaires de B, même identiques (même carte, même prix)."""
    user_a = await _make_user(db_session)
    user_b = await _make_user(db_session)
    card = await _make_card(db_session)
    await _add_price(
        db_session, card, source=PriceSource.cardmarket, low=8, mid=10, trend=Decimal("10")
    )

    db_session.add_all(
        [
            CollectionItem(
                user_id=user_a.id, card_id=card.id, language="fr", condition_grade="mint"
            ),
            CollectionItem(
                user_id=user_b.id, card_id=card.id, language="fr", condition_grade="mint"
            ),
            CollectionItem(
                user_id=user_b.id, card_id=card.id, language="fr", condition_grade="mint"
            ),
        ]
    )
    await db_session.flush()

    report_a = await collection_value(db_session, user_a.id, as_of=DAY)
    report_b = await collection_value(db_session, user_b.id, as_of=DAY)

    assert report_a["items_total"] == 1
    assert report_b["items_total"] == 2
    assert report_a["total"] == Decimal("10")
    assert report_b["total"] == Decimal("20")
