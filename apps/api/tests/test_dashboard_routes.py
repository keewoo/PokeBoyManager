"""`GET /me/dashboard` (mission `v4-dashboard`) : valeur totale et courbe 90 j, meilleures
variations 30 j, cinq derniers ajouts. Avant ce lot, la route n'existait pas (404) : chacun de
ces tests échoue sans elle et passe avec.
"""

import re
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx

from pbm_api.config import settings
from pbm_api.models import Card, CardPriceDaily, PriceSource, PriceVariant, Set
from pbm_api.models.collection import CollectionItem

PASSWORD = "correct horse battery staple"
TODAY = datetime.now(UTC).date()


def _unique_email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@example.com"


async def _register_verify_login(client: httpx.AsyncClient, email: str) -> str:
    response = await client.post(
        "/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "last_name": "Dresseur",
            "birth_date": "2000-01-01",
            "accept_terms": True,
        },
    )
    assert response.status_code == 202, response.text
    sent = client.email_sender.sent  # type: ignore[attr-defined]
    match = re.search(r"token=(\S+)", sent[-1]["body"])
    assert match
    await client.post("/auth/verify-email", json={"token": match.group(1)})
    login = await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    return login.json()["id"]


async def _make_card(db_session, *, name: str = "Dracaufeu", number: str = "1") -> Card:
    set_row = Set(code=f"dash-{uuid.uuid4().hex[:8]}", name="Set dashboard", series="Série test")
    db_session.add(set_row)
    await db_session.flush()
    card = Card(set_id=set_row.id, number=number, name=name, rarity="rare", supertype="Pokémon")
    db_session.add(card)
    await db_session.flush()
    return card


async def _add_price(
    db_session,
    card: Card,
    *,
    trend: Decimal,
    day: date = TODAY,
    variant: PriceVariant = PriceVariant.normal,
) -> None:
    db_session.add(
        CardPriceDaily(
            card_id=card.id,
            source=PriceSource.cardmarket,
            variant=variant,
            day=day,
            currency="EUR",
            price_low=trend,
            price_mid=trend,
            price_trend=trend,
        )
    )
    await db_session.flush()


async def _add_item(
    db_session,
    user_id: uuid.UUID,
    card: Card,
    *,
    variant: PriceVariant = PriceVariant.normal,
    condition_grade: str = "mint",
    created_at: datetime | None = None,
) -> CollectionItem:
    item = CollectionItem(
        user_id=user_id, card_id=card.id, variant=variant, condition_grade=condition_grade
    )
    db_session.add(item)
    await db_session.flush()
    if created_at is not None:
        item.created_at = created_at
        await db_session.flush()
    return item


async def test_dashboard_requires_authentication(api_client):
    response = await api_client.get("/me/dashboard")

    assert response.status_code == 401


async def test_dashboard_reports_total_value_and_history(api_client, db_session):
    user_id = await _register_verify_login(api_client, _unique_email("dash-total"))
    card = await _make_card(db_session, name="Pikachu")
    await _add_price(db_session, card, trend=Decimal("10"), day=TODAY - timedelta(days=90))
    await _add_price(db_session, card, trend=Decimal("15"))
    await _add_item(db_session, uuid.UUID(user_id), card)

    response = await api_client.get("/me/dashboard")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["items_total"] == 1
    assert body["items_priced"] == 1
    assert body["total_value_eur"] == "15.0000"
    history = body["value_history"]
    assert history[-1]["as_of"] == TODAY.isoformat()
    assert history[-1]["total_value_eur"] == "15.0000"
    assert history[0]["as_of"] == (TODAY - timedelta(days=90)).isoformat()
    assert history[0]["total_value_eur"] == "10.0000"


async def test_dashboard_reports_30d_value_change(api_client, db_session):
    user_id = await _register_verify_login(api_client, _unique_email("dash-30d"))
    card = await _make_card(db_session, name="Mewtwo")
    await _add_price(db_session, card, trend=Decimal("20"), day=TODAY - timedelta(days=30))
    await _add_price(db_session, card, trend=Decimal("30"))
    await _add_item(db_session, uuid.UUID(user_id), card)

    response = await api_client.get("/me/dashboard")

    assert response.status_code == 200, response.text
    assert response.json()["value_change_30d_eur"] == "10.0000"


async def test_dashboard_top_movers_sorted_by_absolute_30d_change(api_client, db_session):
    user_id = await _register_verify_login(api_client, _unique_email("dash-movers"))
    big_riser = await _make_card(db_session, name="Dracaufeu", number="1")
    await _add_price(db_session, big_riser, trend=Decimal("10"), day=TODAY - timedelta(days=30))
    await _add_price(db_session, big_riser, trend=Decimal("50"))
    small_faller = await _make_card(db_session, name="Roucool", number="2")
    await _add_price(db_session, small_faller, trend=Decimal("12"), day=TODAY - timedelta(days=30))
    await _add_price(db_session, small_faller, trend=Decimal("10"))
    await _add_item(db_session, uuid.UUID(user_id), big_riser)
    await _add_item(db_session, uuid.UUID(user_id), small_faller)

    response = await api_client.get("/me/dashboard")

    assert response.status_code == 200, response.text
    movers = response.json()["top_movers"]
    assert len(movers) == 2
    assert movers[0]["card_name"] == "Dracaufeu"
    assert movers[0]["value_change_30d_eur"] == "40.0000"
    # (50 - 10) / 10 * 100 = 400 % : jamais un pourcentage inventé quand la base est connue.
    assert Decimal(movers[0]["value_change_30d_pct"]) == Decimal("400")
    assert movers[1]["card_name"] == "Roucool"


async def test_dashboard_recent_additions_limited_to_five_most_recent(api_client, db_session):
    user_id = await _register_verify_login(api_client, _unique_email("dash-recent"))
    now = datetime.now(UTC)
    for i in range(7):
        card = await _make_card(db_session, name=f"Carte {i}", number=str(i))
        await _add_item(
            db_session, uuid.UUID(user_id), card, created_at=now - timedelta(minutes=i)
        )

    response = await api_client.get("/me/dashboard")

    assert response.status_code == 200, response.text
    recent = response.json()["recent_additions"]
    assert len(recent) == 5
    assert [r["card_name"] for r in recent] == [
        "Carte 0",
        "Carte 1",
        "Carte 2",
        "Carte 3",
        "Carte 4",
    ]


async def test_dashboard_is_isolated_by_user(api_client, db_session):
    """Test d'accès croisé exigé par le processus (section 6) : la collection de B n'apparaît
    jamais dans le tableau de bord de A."""
    user_a_id = await _register_verify_login(api_client, _unique_email("dash-iso-a"))
    card = await _make_card(db_session)
    await _add_price(db_session, card, trend=Decimal("5"))
    await _add_item(db_session, uuid.UUID(user_a_id), card)

    user_b_id = await _register_verify_login(api_client, _unique_email("dash-iso-b"))
    await _add_item(db_session, uuid.UUID(user_b_id), card)
    await _add_item(db_session, uuid.UUID(user_b_id), card)

    response = await api_client.get("/me/dashboard")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["items_total"] == 2
    assert settings.session_cookie_name in api_client.cookies


async def test_dashboard_counts_items_missing_price(api_client, db_session):
    user_id = await _register_verify_login(api_client, _unique_email("dash-missing"))
    card = await _make_card(db_session)
    await _add_item(db_session, uuid.UUID(user_id), card)

    response = await api_client.get("/me/dashboard")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["items_total"] == 1
    assert body["items_priced"] == 0
    assert body["items_missing_price"] == 1
    assert body["total_value_eur"] == "0"
    assert body["top_movers"] == []
