"""Classements (mission `v4-ranking`, D6) : rang de rareté et percentile de valeur dans
l'extension (vue matérialisée `card_value_rank`), rang de valeur dans la collection (calculé à
la demande). `test_card_value_rank_orders_cards_by_reference_price_within_set` échoue sans ce
lot (le module `pbm_api.ranking.service` n'existe pas) et passe avec.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pbm_api.models import Card, CardPriceDaily, PriceSource, PriceVariant, Set, User
from pbm_api.models.collection import CollectionItem
from pbm_api.ranking.service import card_value_rank, collection_rank, refresh_card_value_rank

DAY = date(2026, 9, 19)


async def _make_set(db_session) -> Set:
    set_row = Set(code=f"rk-{uuid.uuid4().hex[:8]}", name="Set de classement")
    db_session.add(set_row)
    await db_session.flush()
    return set_row


async def _make_card(
    db_session, set_row: Set, *, number: str = "1", rarity: str | None = None
) -> Card:
    card = Card(set_id=set_row.id, number=number, name=f"Carte {number}", rarity=rarity)
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


async def _add_cardmarket_price(
    db_session, card: Card, trend: Decimal, *, mid: Decimal | None = None
) -> None:
    db_session.add(
        CardPriceDaily(
            card_id=card.id,
            source=PriceSource.cardmarket,
            variant=PriceVariant.normal,
            day=DAY,
            currency="EUR",
            price_low=trend,
            price_mid=mid if mid is not None else trend,
            price_trend=trend,
        )
    )
    await db_session.flush()


async def test_card_value_rank_orders_cards_by_reference_price_within_set(db_session):
    set_row = await _make_set(db_session)
    cheap = await _make_card(db_session, set_row, number="1")
    mid = await _make_card(db_session, set_row, number="2")
    expensive = await _make_card(db_session, set_row, number="3")
    await _add_cardmarket_price(db_session, cheap, Decimal("1"))
    await _add_cardmarket_price(db_session, mid, Decimal("10"))
    await _add_cardmarket_price(db_session, expensive, Decimal("100"))

    await refresh_card_value_rank(db_session)

    rank_cheap = await card_value_rank(db_session, cheap.id)
    rank_mid = await card_value_rank(db_session, mid.id)
    rank_expensive = await card_value_rank(db_session, expensive.id)

    assert rank_cheap.value_percentile == 0.0
    assert rank_expensive.value_percentile == 1.0
    assert rank_cheap.value_percentile < rank_mid.value_percentile < rank_expensive.value_percentile


async def test_card_value_rank_percentile_is_scoped_to_its_own_set(db_session):
    """Deux cartes à la même valeur (5€) doivent être perçues différemment selon l'extension où
    elles se trouvent — la même règle que le gain du lot (« de son extension »), pas un
    percentile global au catalogue."""
    set_a = await _make_set(db_session)
    set_b = await _make_set(db_session)
    card_a_low = await _make_card(db_session, set_a, number="1")
    card_a_top = await _make_card(db_session, set_a, number="2")
    card_b_low = await _make_card(db_session, set_b, number="1")
    card_b_mid = await _make_card(db_session, set_b, number="2")
    card_b_top = await _make_card(db_session, set_b, number="3")
    await _add_cardmarket_price(db_session, card_a_low, Decimal("1"))
    await _add_cardmarket_price(db_session, card_a_top, Decimal("5"))
    await _add_cardmarket_price(db_session, card_b_low, Decimal("1"))
    await _add_cardmarket_price(db_session, card_b_mid, Decimal("5"))
    await _add_cardmarket_price(db_session, card_b_top, Decimal("9"))

    await refresh_card_value_rank(db_session)

    rank_a_top = await card_value_rank(db_session, card_a_top.id)
    rank_b_mid = await card_value_rank(db_session, card_b_mid.id)

    # Même valeur (5€), percentile différent : `card_a_top` est en tête de ses 2 cartes
    # (percentile 1.0), `card_b_mid` n'est qu'au milieu des 3 siennes (percentile 0.5).
    assert rank_a_top.value_percentile == 1.0
    assert rank_b_mid.value_percentile == 0.5
    assert rank_a_top.set_id != rank_b_mid.set_id


async def test_card_value_rank_rarity_rank_favors_smaller_group(db_session):
    set_row = await _make_set(db_session)
    secret = await _make_card(db_session, set_row, number="1", rarity="secret")
    common_a = await _make_card(db_session, set_row, number="2", rarity="common")
    common_b = await _make_card(db_session, set_row, number="3", rarity="common")

    await refresh_card_value_rank(db_session)

    rank_secret = await card_value_rank(db_session, secret.id)
    rank_common = await card_value_rank(db_session, common_a.id)
    rank_common_b = await card_value_rank(db_session, common_b.id)

    assert rank_secret.rarity_group_size == 1
    assert rank_common.rarity_group_size == 2
    assert rank_secret.rarity_rank < rank_common.rarity_rank
    assert rank_common.rarity_rank == rank_common_b.rarity_rank


async def test_card_value_rank_clamps_outlier_trend_like_valuation(db_session):
    set_row = await _make_set(db_session)
    card = await _make_card(db_session, set_row, number="1")
    await _add_cardmarket_price(db_session, card, Decimal("100"), mid=Decimal("5"))

    await refresh_card_value_rank(db_session)

    rank = await card_value_rank(db_session, card.id)

    assert rank.reference_price_eur == Decimal("15")  # 5 * 3 (OUTLIER_TREND_MULTIPLE)


async def test_card_value_rank_none_for_unknown_card(db_session):
    await refresh_card_value_rank(db_session)

    assert await card_value_rank(db_session, uuid.uuid4()) is None


async def test_collection_rank_orders_by_value_and_ranks_ties(db_session):
    set_row = await _make_set(db_session)
    user = await _make_user(db_session)
    card_cheap = await _make_card(db_session, set_row, number="1")
    card_mid_a = await _make_card(db_session, set_row, number="2")
    card_mid_b = await _make_card(db_session, set_row, number="3")
    card_expensive = await _make_card(db_session, set_row, number="4")
    await _add_cardmarket_price(db_session, card_cheap, Decimal("1"))
    await _add_cardmarket_price(db_session, card_mid_a, Decimal("10"))
    await _add_cardmarket_price(db_session, card_mid_b, Decimal("10"))
    await _add_cardmarket_price(db_session, card_expensive, Decimal("100"))

    item_cheap = CollectionItem(
        user_id=user.id, card_id=card_cheap.id, language="fr", condition_grade="mint"
    )
    item_mid_a = CollectionItem(
        user_id=user.id, card_id=card_mid_a.id, language="fr", condition_grade="mint"
    )
    item_mid_b = CollectionItem(
        user_id=user.id, card_id=card_mid_b.id, language="fr", condition_grade="mint"
    )
    item_expensive = CollectionItem(
        user_id=user.id, card_id=card_expensive.id, language="fr", condition_grade="mint"
    )
    db_session.add_all([item_cheap, item_mid_a, item_mid_b, item_expensive])
    await db_session.flush()

    rank_expensive = await collection_rank(db_session, user.id, item_expensive, as_of=DAY)
    rank_mid_a = await collection_rank(db_session, user.id, item_mid_a, as_of=DAY)
    rank_mid_b = await collection_rank(db_session, user.id, item_mid_b, as_of=DAY)
    rank_cheap = await collection_rank(db_session, user.id, item_cheap, as_of=DAY)

    assert rank_expensive.position == 1
    assert rank_mid_a.position == 2
    assert rank_mid_b.position == 2  # égalité de valeur -> même rang
    assert rank_cheap.position == 4  # le rang saute après l'égalité (RANK, pas DENSE_RANK)
    assert rank_cheap.total_priced == 4
    assert rank_cheap.total_items == 4


async def test_collection_rank_excludes_unpriced_items(db_session):
    set_row = await _make_set(db_session)
    user = await _make_user(db_session)
    priced_card = await _make_card(db_session, set_row, number="1")
    unpriced_card = await _make_card(db_session, set_row, number="2")
    await _add_cardmarket_price(db_session, priced_card, Decimal("10"))

    priced_item = CollectionItem(
        user_id=user.id, card_id=priced_card.id, language="fr", condition_grade="mint"
    )
    unpriced_item = CollectionItem(user_id=user.id, card_id=unpriced_card.id, language="fr")
    db_session.add_all([priced_item, unpriced_item])
    await db_session.flush()

    rank_unpriced = await collection_rank(db_session, user.id, unpriced_item, as_of=DAY)
    rank_priced = await collection_rank(db_session, user.id, priced_item, as_of=DAY)

    assert rank_unpriced.position is None
    assert rank_unpriced.total_priced == 1
    assert rank_priced.position == 1
    assert rank_priced.total_items == 2


async def test_collection_rank_is_isolated_by_user(db_session):
    """Équivalent du test d'accès croisé au niveau données (voir `test_cross_user_isolation.py`,
    `test_valuation.py`) : le rang de B ne doit jamais compter les exemplaires de A."""
    set_row = await _make_set(db_session)
    user_a = await _make_user(db_session)
    user_b = await _make_user(db_session)
    card = await _make_card(db_session, set_row, number="1")
    await _add_cardmarket_price(db_session, card, Decimal("10"))

    item_a = CollectionItem(
        user_id=user_a.id, card_id=card.id, language="fr", condition_grade="mint"
    )
    item_b = CollectionItem(
        user_id=user_b.id, card_id=card.id, language="fr", condition_grade="mint"
    )
    db_session.add_all([item_a, item_b])
    await db_session.flush()

    rank_a = await collection_rank(db_session, user_a.id, item_a, as_of=DAY)
    rank_b = await collection_rank(db_session, user_b.id, item_b, as_of=DAY)

    assert rank_a.total_items == 1
    assert rank_b.total_items == 1
    assert rank_a.position == 1
    assert rank_b.position == 1
