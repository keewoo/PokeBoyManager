"""`/me/wishlist` — liste de souhaits (mission `v6-import-export`) : cartes que l'utilisateur veut
acheter, avec un prix cible facultatif comparé au prix courant de marché. Aucune de ces routes
n'existait avant ce lot (404/405) : chacun de ces tests échoue sans elles et passe avec.
"""

import re
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx

from pbm_api.config import settings
from pbm_api.main import app as fastapi_app
from pbm_api.models import Card, CardPriceDaily, PriceSource, PriceVariant, Set
from pbm_api.security.csrf import CSRF_HEADER_NAME

PASSWORD = "correct horse battery staple"
TODAY = datetime.now(UTC).date()


def _unique_email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@example.com"


async def _register_verify_login(client: httpx.AsyncClient, email: str) -> tuple[str, str]:
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


def _csrf(token: str) -> dict[str, str]:
    return {CSRF_HEADER_NAME: token}


async def _make_card(db_session, *, name: str = "Dracaufeu", number: str = "6") -> Card:
    set_row = Set(code=f"wl-{uuid.uuid4().hex[:8]}", name="Set vœux")
    db_session.add(set_row)
    await db_session.flush()
    card = Card(set_id=set_row.id, number=number, name=name, rarity="rare")
    db_session.add(card)
    await db_session.flush()
    return card


async def _add_price(db_session, card: Card, *, trend: Decimal, day: date = TODAY) -> None:
    db_session.add(
        CardPriceDaily(
            card_id=card.id,
            source=PriceSource.cardmarket,
            variant=PriceVariant.normal,
            day=day,
            currency="EUR",
            price_low=trend,
            price_mid=trend,
            price_trend=trend,
        )
    )
    await db_session.flush()


# ----------------------------------------------------------------------------------- auth
async def test_wishlist_requires_authentication(api_client):
    assert (await api_client.get("/me/wishlist")).status_code == 401


async def test_create_wishlist_item_requires_csrf(api_client, db_session):
    await _register_verify_login(api_client, _unique_email("wl-nocsrf"))
    card = await _make_card(db_session)
    response = await api_client.post("/me/wishlist", json={"card_id": str(card.id)})
    assert response.status_code == 403


# ----------------------------------------------------------------------------------- CRUD
async def test_create_and_list_wishlist_item(api_client, db_session):
    _uid, csrf = await _register_verify_login(api_client, _unique_email("wl-crud"))
    card = await _make_card(db_session, name="Pikachu", number="25")

    created = await api_client.post(
        "/me/wishlist",
        json={"card_id": str(card.id), "target_price_eur": "10.00", "note": "pour le deck"},
        headers=_csrf(csrf),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["card_name"] == "Pikachu"
    assert body["target_price_eur"] == "10.00"
    assert body["note"] == "pour le deck"
    assert body["current_price_eur"] is None
    # Aucun prix courant connu : la question « objectif atteint » n'a pas de réponse, jamais
    # une fausse alerte (`None`, pas `False`).
    assert body["target_reached"] is None

    listing = await api_client.get("/me/wishlist")
    assert listing.status_code == 200
    assert len(listing.json()["items"]) == 1
    assert listing.json()["items"][0]["id"] == body["id"]


async def test_wishlist_target_reached_compares_current_price(api_client, db_session):
    _uid, csrf = await _register_verify_login(api_client, _unique_email("wl-reached"))
    card = await _make_card(db_session, name="Bulbizarre", number="1")
    await _add_price(db_session, card, trend=Decimal("8.00"))

    created = await api_client.post(
        "/me/wishlist",
        json={"card_id": str(card.id), "target_price_eur": "10.00"},
        headers=_csrf(csrf),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["current_price_eur"] == "8.00"
    assert body["target_reached"] is True

    # Un prix cible plus bas que le marché n'est pas encore atteint.
    item_id = body["id"]
    lowered = await api_client.patch(
        f"/me/wishlist/{item_id}", json={"target_price_eur": "1.00"}, headers=_csrf(csrf)
    )
    assert lowered.status_code == 200
    assert lowered.json()["target_reached"] is False


async def test_create_wishlist_item_for_unknown_card_is_404(api_client, db_session):
    _uid, csrf = await _register_verify_login(api_client, _unique_email("wl-unknown-card"))
    response = await api_client.post(
        "/me/wishlist", json={"card_id": str(uuid.uuid4())}, headers=_csrf(csrf)
    )
    assert response.status_code == 404


async def test_create_wishlist_item_twice_for_same_card_conflicts(api_client, db_session):
    _uid, csrf = await _register_verify_login(api_client, _unique_email("wl-dup"))
    card = await _make_card(db_session)
    first = await api_client.post(
        "/me/wishlist", json={"card_id": str(card.id)}, headers=_csrf(csrf)
    )
    assert first.status_code == 201, first.text
    second = await api_client.post(
        "/me/wishlist", json={"card_id": str(card.id)}, headers=_csrf(csrf)
    )
    assert second.status_code == 409


async def test_update_unknown_wishlist_item_is_404(api_client):
    _uid, csrf = await _register_verify_login(api_client, _unique_email("wl-update-404"))
    response = await api_client.patch(
        f"/me/wishlist/{uuid.uuid4()}", json={"note": "x"}, headers=_csrf(csrf)
    )
    assert response.status_code == 404


async def test_delete_wishlist_item(api_client, db_session):
    _uid, csrf = await _register_verify_login(api_client, _unique_email("wl-delete"))
    card = await _make_card(db_session)
    created = await api_client.post(
        "/me/wishlist", json={"card_id": str(card.id)}, headers=_csrf(csrf)
    )
    item_id = created.json()["id"]

    deleted = await api_client.delete(f"/me/wishlist/{item_id}", headers=_csrf(csrf))
    assert deleted.status_code == 204

    listing = await api_client.get("/me/wishlist")
    assert listing.json()["items"] == []


# ----------------------------------------------------------------------- accès croisé (B/A)
async def test_wishlist_items_are_isolated_by_user(api_client, db_session):
    """B ne voit ni ne peut modifier/supprimer un vœu de A — jamais un 403 (pas de fuite
    d'existence), même règle que `test_decks_are_isolated_by_user`."""
    _uid_a, csrf_a = await _register_verify_login(api_client, _unique_email("wl-iso-a"))
    card = await _make_card(db_session)
    created = await api_client.post(
        "/me/wishlist", json={"card_id": str(card.id)}, headers=_csrf(csrf_a)
    )
    item_a_id = created.json()["id"]

    transport = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client_b:
        client_b.email_sender = api_client.email_sender  # type: ignore[attr-defined]
        _uid_b, csrf_b = await _register_verify_login(client_b, _unique_email("wl-iso-b"))

        listing_b = await client_b.get("/me/wishlist")
        assert listing_b.json()["items"] == []

        patched = await client_b.patch(
            f"/me/wishlist/{item_a_id}", json={"note": "vol"}, headers=_csrf(csrf_b)
        )
        assert patched.status_code == 404

        deleted = await client_b.delete(f"/me/wishlist/{item_a_id}", headers=_csrf(csrf_b))
        assert deleted.status_code == 404
