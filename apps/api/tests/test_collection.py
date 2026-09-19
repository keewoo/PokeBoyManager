"""`GET /me/collection/{item}` (mission `v4-ranking` point 2) : l'exemplaire d'un utilisateur
avec ses classements. Avant ce lot, cette route n'existait pas (404) : chacun de ces tests
échoue sans le routeur `collection` et passe avec.
"""

import re
import uuid
from datetime import date
from decimal import Decimal

import httpx

from pbm_api.config import settings
from pbm_api.models import Card, CardPriceDaily, PriceSource, PriceVariant, Set
from pbm_api.models.collection import CollectionItem
from pbm_api.ranking.service import refresh_card_value_rank

PASSWORD = "correct horse battery staple"
DAY = date(2026, 9, 19)


def _unique_email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@example.com"


async def _register_verify_login(client: httpx.AsyncClient, email: str) -> str:
    """Inscrit, vérifie et connecte un utilisateur ; renvoie son id (la session/le cookie CSRF
    sont déjà posés sur `client` par le login, comme `test_uploads._register_verify_login`)."""
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


async def _make_card_with_price(db_session, *, trend: Decimal = Decimal("10")) -> Card:
    set_row = Set(code=f"coll-{uuid.uuid4().hex[:8]}", name="Set collection")
    db_session.add(set_row)
    await db_session.flush()
    card = Card(set_id=set_row.id, number="1", name="Carte collection", rarity="rare")
    db_session.add(card)
    await db_session.flush()
    db_session.add(
        CardPriceDaily(
            card_id=card.id,
            source=PriceSource.cardmarket,
            variant=PriceVariant.normal,
            day=DAY,
            currency="EUR",
            price_low=trend,
            price_mid=trend,
            price_trend=trend,
        )
    )
    await db_session.flush()
    return card


async def test_get_collection_item_returns_ranking(api_client, db_session):
    user_id = await _register_verify_login(api_client, _unique_email("coll-get"))
    card = await _make_card_with_price(db_session)
    item = CollectionItem(
        user_id=uuid.UUID(user_id),
        card_id=card.id,
        language="fr",
        variant=PriceVariant.normal,
        condition_grade="mint",
    )
    db_session.add(item)
    await db_session.flush()

    await refresh_card_value_rank(db_session)

    response = await api_client.get(f"/me/collection/{item.id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == str(item.id)
    assert body["card_id"] == str(card.id)
    assert body["set_id"] == str(card.set_id)
    assert body["value_eur"] == "10.0000"
    assert body["ranking"]["rarity_rank"] == 1
    # Seule carte de son extension dans ce test : `PERCENT_RANK()` d'une partition à 1 ligne
    # vaut 0 (définition SQL standard), pas 1 — voir `test_ranking.py` pour le cas à plusieurs.
    assert body["ranking"]["value_percentile"] == 0.0
    assert body["ranking"]["collection_rank"] == 1
    assert body["ranking"]["collection_rank_total"] == 1


async def test_get_collection_item_requires_authentication(api_client):
    response = await api_client.get(f"/me/collection/{uuid.uuid4()}")

    assert response.status_code == 401


async def test_get_collection_item_returns_404_for_unknown_item(api_client):
    await _register_verify_login(api_client, _unique_email("coll-404"))

    response = await api_client.get(f"/me/collection/{uuid.uuid4()}")

    assert response.status_code == 404


async def test_get_collection_item_returns_404_for_another_users_item(api_client, db_session):
    """Test d'accès croisé exigé par le processus (section 6) : l'utilisateur B ne doit jamais
    voir l'exemplaire de l'utilisateur A, même par identifiant deviné."""
    user_a_id = await _register_verify_login(api_client, _unique_email("coll-iso-a"))
    card = await _make_card_with_price(db_session)
    item_a = CollectionItem(user_id=uuid.UUID(user_a_id), card_id=card.id, language="fr")
    db_session.add(item_a)
    await db_session.flush()

    await _register_verify_login(api_client, _unique_email("coll-iso-b"))
    response = await api_client.get(f"/me/collection/{item_a.id}")

    assert response.status_code == 404
    assert settings.session_cookie_name in api_client.cookies
