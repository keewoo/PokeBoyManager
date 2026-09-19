"""`GET/POST /me/collection`, `GET /me/collection/facets`, `PATCH/DELETE /me/collection/{item}`
(mission `v4-collection`) : grille filtrable/triable/paginée avec agrégats de valeur, ajout
manuel, correction et suppression d'un exemplaire. Avant ce lot, aucune de ces routes n'existait
(404/405) : chacun de ces tests échoue sans elles et passe avec.
"""

import re
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx

from pbm_api.config import settings
from pbm_api.models import Card, CardName, CardPriceDaily, PriceSource, PriceVariant, Set
from pbm_api.models.collection import CollectionItem
from pbm_api.security.csrf import CSRF_HEADER_NAME

PASSWORD = "correct horse battery staple"
TODAY = datetime.now(UTC).date()


def _unique_email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@example.com"


async def _register_verify_login(client: httpx.AsyncClient, email: str) -> tuple[str, str]:
    """Inscrit, vérifie et connecte un utilisateur ; renvoie `(user_id, jeton_csrf)`."""
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
    return login.json()["id"], client.cookies.get(settings.csrf_cookie_name)


async def _make_card(
    db_session,
    *,
    number: str = "1",
    name: str = "Dracaufeu",
    rarity: str | None = "rare",
    supertype: str | None = "Pokémon",
    series: str | None = "Série test",
) -> Card:
    set_row = Set(code=f"coll-{uuid.uuid4().hex[:8]}", name="Set collection", series=series)
    db_session.add(set_row)
    await db_session.flush()
    card = Card(set_id=set_row.id, number=number, name=name, rarity=rarity, supertype=supertype)
    db_session.add(card)
    await db_session.flush()
    return card


async def _add_price(
    db_session,
    card: Card,
    *,
    trend: Decimal,
    variant: PriceVariant = PriceVariant.normal,
    day: date = TODAY,
    source: PriceSource = PriceSource.cardmarket,
) -> None:
    db_session.add(
        CardPriceDaily(
            card_id=card.id,
            source=source,
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
    language: str = "fr",
    variant: PriceVariant = PriceVariant.normal,
    condition_grade: str | None = None,
    acquired_at: date | None = None,
    counterfeit_suspected: bool = False,
) -> CollectionItem:
    item = CollectionItem(
        user_id=user_id,
        card_id=card.id,
        language=language,
        variant=variant,
        condition_grade=condition_grade,
        acquired_at=acquired_at,
        counterfeit_suspected=counterfeit_suspected,
    )
    db_session.add(item)
    await db_session.flush()
    return item


async def test_list_collection_requires_authentication(api_client):
    response = await api_client.get("/me/collection")

    assert response.status_code == 401


async def test_list_collection_returns_items_with_value_and_aggregates(api_client, db_session):
    user_id, _csrf = await _register_verify_login(api_client, _unique_email("coll-list"))
    card = await _make_card(db_session, name="Pikachu")
    await _add_price(db_session, card, trend=Decimal("10"))
    item = await _add_item(db_session, uuid.UUID(user_id), card, condition_grade="mint")

    response = await api_client.get("/me/collection")

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["items"]) == 1
    row = body["items"][0]
    assert row["id"] == str(item.id)
    assert row["card_name"] == "Pikachu"
    assert row["value_eur"] == "10.0000"
    assert body["aggregates"]["items_total"] == 1
    assert body["aggregates"]["items_priced"] == 1
    assert body["aggregates"]["total_value_eur"] == "10.0000"
    assert body["next_cursor"] is None


async def test_list_collection_item_reports_30d_value_change(api_client, db_session):
    user_id, _csrf = await _register_verify_login(api_client, _unique_email("coll-30d"))
    card = await _make_card(db_session, name="Mewtwo")
    await _add_price(db_session, card, trend=Decimal("20"), day=TODAY - timedelta(days=30))
    await _add_price(db_session, card, trend=Decimal("30"), day=TODAY)
    await _add_item(db_session, uuid.UUID(user_id), card, condition_grade="mint")

    response = await api_client.get("/me/collection")

    assert response.status_code == 200, response.text
    row = response.json()["items"][0]
    assert row["value_eur"] == "30.0000"
    assert row["value_change_30d_eur"] == "10.0000"
    # (30 - 20) / 20 * 100 = 50 % : jamais un pourcentage inventé quand la base est connue.
    assert Decimal(row["value_change_30d_pct"]) == Decimal("50")


async def test_list_collection_is_isolated_by_user(api_client, db_session):
    """Test d'accès croisé exigé par le processus (section 6) : la collection de B n'apparaît
    jamais dans la liste de A, même à contenu identique (même carte)."""
    user_a_id, _csrf_a = await _register_verify_login(api_client, _unique_email("coll-list-a"))
    card = await _make_card(db_session)
    await _add_price(db_session, card, trend=Decimal("5"))
    await _add_item(db_session, uuid.UUID(user_a_id), card)

    user_b_id, _csrf_b = await _register_verify_login(api_client, _unique_email("coll-list-b"))
    await _add_item(db_session, uuid.UUID(user_b_id), card)
    await _add_item(db_session, uuid.UUID(user_b_id), card)

    response = await api_client.get("/me/collection")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["aggregates"]["items_total"] == 2
    assert settings.session_cookie_name in api_client.cookies


async def test_list_collection_filters_by_language_and_variant(api_client, db_session):
    user_id, _csrf = await _register_verify_login(api_client, _unique_email("coll-filter"))
    card = await _make_card(db_session)
    await _add_price(db_session, card, trend=Decimal("5"))
    await _add_price(db_session, card, trend=Decimal("20"), variant=PriceVariant.holo)
    await _add_item(
        db_session, uuid.UUID(user_id), card, language="fr", variant=PriceVariant.normal
    )
    await _add_item(db_session, uuid.UUID(user_id), card, language="en", variant=PriceVariant.holo)

    response = await api_client.get("/me/collection", params={"language": "en", "variant": "holo"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["language"] == "en"
    assert body["items"][0]["variant"] == "holo"


async def test_list_collection_filters_by_value_range(api_client, db_session):
    user_id, _csrf = await _register_verify_login(api_client, _unique_email("coll-value-range"))
    cheap = await _make_card(db_session, number="1", name="Roucool")
    expensive = await _make_card(db_session, number="2", name="Mewtwo")
    await _add_price(db_session, cheap, trend=Decimal("2"))
    await _add_price(db_session, expensive, trend=Decimal("200"))
    await _add_item(db_session, uuid.UUID(user_id), cheap)
    await _add_item(db_session, uuid.UUID(user_id), expensive)

    response = await api_client.get("/me/collection", params={"value_min": "50"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["card_name"] == "Mewtwo"


async def test_list_collection_search_matches_localized_name(api_client, db_session):
    user_id, _csrf = await _register_verify_login(api_client, _unique_email("coll-search"))
    card = await _make_card(db_session, name="Charizard")
    db_session.add(CardName(card_id=card.id, language="fr", name="Dracaufeu"))
    await db_session.flush()
    await _add_price(db_session, card, trend=Decimal("30"))
    await _add_item(db_session, uuid.UUID(user_id), card, language="fr")

    response = await api_client.get("/me/collection", params={"q": "dracaufeu"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["card_name"] == "Dracaufeu"


async def test_list_collection_sorts_by_value_desc_by_default(api_client, db_session):
    user_id, _csrf = await _register_verify_login(api_client, _unique_email("coll-sort"))
    low = await _make_card(db_session, number="1", name="Chenipan")
    high = await _make_card(db_session, number="2", name="Leviator")
    await _add_price(db_session, low, trend=Decimal("1"))
    await _add_price(db_session, high, trend=Decimal("500"))
    await _add_item(db_session, uuid.UUID(user_id), low)
    await _add_item(db_session, uuid.UUID(user_id), high)

    response = await api_client.get("/me/collection")

    assert response.status_code == 200, response.text
    names = [item["card_name"] for item in response.json()["items"]]
    assert names == ["Leviator", "Chenipan"]


async def test_list_collection_paginates_with_cursor(api_client, db_session):
    user_id, _csrf = await _register_verify_login(api_client, _unique_email("coll-cursor"))
    for i in range(3):
        card = await _make_card(db_session, number=str(i), name=f"Carte {i}")
        await _add_price(db_session, card, trend=Decimal(str(10 * (i + 1))))
        await _add_item(db_session, uuid.UUID(user_id), card)

    first_page = await api_client.get("/me/collection", params={"limit": 2})
    assert first_page.status_code == 200, first_page.text
    first_body = first_page.json()
    assert len(first_body["items"]) == 2
    assert first_body["next_cursor"] is not None

    second_page = await api_client.get(
        "/me/collection", params={"limit": 2, "cursor": first_body["next_cursor"]}
    )
    assert second_page.status_code == 200, second_page.text
    second_body = second_page.json()
    assert len(second_body["items"]) == 1
    assert second_body["next_cursor"] is None

    seen_ids = {item["id"] for item in first_body["items"] + second_body["items"]}
    assert len(seen_ids) == 3


async def test_list_collection_duplicates_filter(api_client, db_session):
    user_id, _csrf = await _register_verify_login(api_client, _unique_email("coll-dup"))
    duplicated = await _make_card(db_session, number="1", name="Doublon")
    unique = await _make_card(db_session, number="2", name="Unique")
    await _add_price(db_session, duplicated, trend=Decimal("5"))
    await _add_price(db_session, unique, trend=Decimal("5"))
    await _add_item(db_session, uuid.UUID(user_id), duplicated)
    await _add_item(db_session, uuid.UUID(user_id), duplicated)
    await _add_item(db_session, uuid.UUID(user_id), unique)

    response = await api_client.get("/me/collection", params={"duplicates": "true"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["items"]) == 2
    assert all(item["card_name"] == "Doublon" for item in body["items"])
    assert all(item["is_duplicate"] for item in body["items"])


async def test_list_collection_counterfeit_filter(api_client, db_session):
    user_id, _csrf = await _register_verify_login(api_client, _unique_email("coll-fake"))
    card = await _make_card(db_session)
    await _add_price(db_session, card, trend=Decimal("5"))
    await _add_item(db_session, uuid.UUID(user_id), card, counterfeit_suspected=True)
    await _add_item(db_session, uuid.UUID(user_id), card, counterfeit_suspected=False)

    response = await api_client.get("/me/collection", params={"counterfeit": "true"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["counterfeit_suspected"] is True
    assert body["items"][0]["value_eur"] == "0"


async def test_get_collection_facets_scoped_to_user(api_client, db_session):
    user_a_id, _csrf_a = await _register_verify_login(api_client, _unique_email("coll-facets-a"))
    card_a = await _make_card(db_session, rarity="rare", series="Série A")
    await _add_item(db_session, uuid.UUID(user_a_id), card_a, language="fr")

    user_b_id, _csrf_b = await _register_verify_login(api_client, _unique_email("coll-facets-b"))
    card_b = await _make_card(db_session, rarity="commune", series="Série B")
    await _add_item(db_session, uuid.UUID(user_b_id), card_b, language="en")

    response = await api_client.get("/me/collection/facets")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["rarities"] == ["commune"]
    assert body["series"] == ["Série B"]
    assert body["languages"] == ["en"]


async def test_create_manual_collection_item(api_client, db_session):
    _user_id, csrf = await _register_verify_login(api_client, _unique_email("coll-create"))
    card = await _make_card(db_session)

    response = await api_client.post(
        "/me/collection",
        json={"card_id": str(card.id), "language": "fr", "variant": "normal", "quantity": 2},
        headers={CSRF_HEADER_NAME: csrf},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert len(body["collection_item_ids"]) == 2

    listing = await api_client.get("/me/collection")
    assert listing.json()["aggregates"]["items_total"] == 2


async def test_create_manual_collection_item_requires_csrf(api_client, db_session):
    await _register_verify_login(api_client, _unique_email("coll-create-nocsrf"))
    card = await _make_card(db_session)

    response = await api_client.post("/me/collection", json={"card_id": str(card.id)})

    assert response.status_code == 403


async def test_create_manual_collection_item_returns_404_for_unknown_card(api_client):
    _user_id, csrf = await _register_verify_login(api_client, _unique_email("coll-create-404"))

    response = await api_client.post(
        "/me/collection",
        json={"card_id": str(uuid.uuid4())},
        headers={CSRF_HEADER_NAME: csrf},
    )

    assert response.status_code == 404


async def test_update_collection_item_changes_only_provided_fields(api_client, db_session):
    user_id, csrf = await _register_verify_login(api_client, _unique_email("coll-update"))
    card = await _make_card(db_session)
    await _add_price(db_session, card, trend=Decimal("10"))
    item = await _add_item(
        db_session, uuid.UUID(user_id), card, language="fr", condition_grade="mint"
    )

    response = await api_client.patch(
        f"/me/collection/{item.id}",
        json={"condition_grade": "excellent"},
        headers={CSRF_HEADER_NAME: csrf},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["condition_grade"] == "excellent"
    assert body["language"] == "fr"  # inchangé : non envoyé dans le PATCH


async def test_update_collection_item_returns_404_for_another_users_item(api_client, db_session):
    """Test d'accès croisé exigé par le processus (section 6)."""
    user_a_id, _csrf_a = await _register_verify_login(api_client, _unique_email("coll-upd-iso-a"))
    card = await _make_card(db_session)
    item_a = await _add_item(db_session, uuid.UUID(user_a_id), card)

    _user_b_id, csrf_b = await _register_verify_login(api_client, _unique_email("coll-upd-iso-b"))
    response = await api_client.patch(
        f"/me/collection/{item_a.id}",
        json={"condition_grade": "poor"},
        headers={CSRF_HEADER_NAME: csrf_b},
    )

    assert response.status_code == 404
    assert settings.session_cookie_name in api_client.cookies


async def test_delete_collection_item(api_client, db_session):
    user_id, csrf = await _register_verify_login(api_client, _unique_email("coll-delete"))
    card = await _make_card(db_session)
    item = await _add_item(db_session, uuid.UUID(user_id), card)

    response = await api_client.delete(
        f"/me/collection/{item.id}", headers={CSRF_HEADER_NAME: csrf}
    )
    assert response.status_code == 204

    listing = await api_client.get("/me/collection")
    assert listing.json()["aggregates"]["items_total"] == 0


async def test_delete_collection_item_returns_404_for_another_users_item(api_client, db_session):
    """Test d'accès croisé exigé par le processus (section 6)."""
    user_a_id, _csrf_a = await _register_verify_login(api_client, _unique_email("coll-del-iso-a"))
    card = await _make_card(db_session)
    item_a = await _add_item(db_session, uuid.UUID(user_a_id), card)

    _user_b_id, csrf_b = await _register_verify_login(api_client, _unique_email("coll-del-iso-b"))
    response = await api_client.delete(
        f"/me/collection/{item_a.id}", headers={CSRF_HEADER_NAME: csrf_b}
    )

    assert response.status_code == 404
