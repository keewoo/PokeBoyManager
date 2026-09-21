"""`/me/decks` — CRUD, légalité, accès croisé, revalidation (mission `v7-decks-api`).

Aucune de ces routes n'existait avant le lot (404/405) : chacun de ces tests échoue sans lui et
passe avec. Le test d'accès croisé (section 6 du processus) et la revalidation après vente d'une
carte (mission point 3) sont couverts ici.
"""

import re
import uuid

import httpx

from pbm_api.config import settings
from pbm_api.models import Card, Set
from pbm_api.models.collection import CollectionItem
from pbm_api.security.csrf import CSRF_HEADER_NAME

PASSWORD = "correct horse battery staple"


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


async def _make_card(
    db_session,
    *,
    name: str,
    supertype: str = "Pokémon",
    energy_type: str | None = None,
    number: str = "1",
) -> Card:
    set_row = Set(code=f"deck-{uuid.uuid4().hex[:8]}", name="Set deck", series="Série test")
    db_session.add(set_row)
    await db_session.flush()
    card = Card(
        set_id=set_row.id,
        number=number,
        name=name,
        supertype=supertype,
        energy_type=energy_type,
    )
    db_session.add(card)
    await db_session.flush()
    return card


async def _own(db_session, user_id: str, card: Card, count: int) -> list[CollectionItem]:
    items = [CollectionItem(user_id=uuid.UUID(user_id), card_id=card.id) for _ in range(count)]
    db_session.add_all(items)
    await db_session.flush()
    return items


# ----------------------------------------------------------------------------------- auth
async def test_decks_require_authentication(api_client):
    assert (await api_client.get("/me/decks")).status_code == 401


# ----------------------------------------------------------------------------------- CRUD
async def test_create_and_get_deck(api_client, db_session):
    user_id, csrf = await _register_verify_login(api_client, _unique_email("deck-crud"))
    card = await _make_card(db_session, name="Pikachu")
    await _own(db_session, user_id, card, 2)

    created = await api_client.post(
        "/me/decks",
        json={"name": "Mon deck", "cards": [{"card_id": str(card.id), "quantity": 2}]},
        headers=_csrf(csrf),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == "Mon deck"
    assert body["legality"]["card_count"] == 2
    assert body["legality"]["legal"] is False  # 2 cartes, pas 60
    entry = body["cards"][0]
    assert entry["quantity"] == 2
    assert entry["owned"] == 2
    assert entry["missing"] == 0
    assert entry["in_collection"] is True

    fetched = await api_client.get(f"/me/decks/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["cards"][0]["card_name"] == "Pikachu"


async def test_create_deck_with_unknown_card_is_404(api_client, db_session):
    _uid, csrf = await _register_verify_login(api_client, _unique_email("deck-unknown"))
    response = await api_client.post(
        "/me/decks",
        json={"name": "X", "cards": [{"card_id": str(uuid.uuid4()), "quantity": 1}]},
        headers=_csrf(csrf),
    )
    assert response.status_code == 404


async def test_full_legal_deck_end_to_end(api_client, db_session):
    """Deck de 60 cartes conforme à D10 : 4 Énergies spéciales possédées + 56 Énergies de base
    (fournies, non possédées) → légal."""
    user_id, csrf = await _register_verify_login(api_client, _unique_email("deck-legal"))
    special = await _make_card(
        db_session, name="Double Énergie", supertype="Énergie", energy_type="Special"
    )
    basic = await _make_card(
        db_session, name="Énergie Feu", supertype="Énergie", energy_type="Normal", number="2"
    )
    await _own(db_session, user_id, special, 4)  # aucune Énergie de base possédée : voulu

    created = await api_client.post(
        "/me/decks",
        json={
            "name": "Deck légal",
            "cards": [
                {"card_id": str(special.id), "quantity": 4},
                {"card_id": str(basic.id), "quantity": 56},
            ],
        },
        headers=_csrf(csrf),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["legality"]["legal"] is True
    assert body["legality"]["card_count"] == 60
    assert body["legality"]["issues"] == []
    by_name = {c["card_name"]: c for c in body["cards"]}
    assert by_name["Énergie Feu"]["is_basic_energy"] is True
    assert by_name["Énergie Feu"]["missing"] == 0  # fournie, jamais manquante
    assert by_name["Double Énergie"]["is_special_energy"] is True
    assert by_name["Double Énergie"]["owned"] == 4


async def test_rename_deck(api_client, db_session):
    _uid, csrf = await _register_verify_login(api_client, _unique_email("deck-rename"))
    created = await api_client.post("/me/decks", json={"name": "Avant"}, headers=_csrf(csrf))
    deck_id = created.json()["id"]
    renamed = await api_client.patch(
        f"/me/decks/{deck_id}", json={"name": "Après"}, headers=_csrf(csrf)
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Après"


async def test_duplicate_deck_copies_cards(api_client, db_session):
    user_id, csrf = await _register_verify_login(api_client, _unique_email("deck-dup"))
    card = await _make_card(db_session, name="Roucool")
    await _own(db_session, user_id, card, 3)
    created = await api_client.post(
        "/me/decks",
        json={"name": "Original", "cards": [{"card_id": str(card.id), "quantity": 3}]},
        headers=_csrf(csrf),
    )
    deck_id = created.json()["id"]
    dup = await api_client.post(f"/me/decks/{deck_id}/duplicate", headers=_csrf(csrf))
    assert dup.status_code == 201, dup.text
    body = dup.json()
    assert body["id"] != deck_id
    assert body["name"] == "Original (copie)"
    assert body["cards"][0]["quantity"] == 3

    listing = await api_client.get("/me/decks")
    assert len(listing.json()["decks"]) == 2


async def test_delete_deck(api_client, db_session):
    _uid, csrf = await _register_verify_login(api_client, _unique_email("deck-del"))
    created = await api_client.post("/me/decks", json={"name": "À supprimer"}, headers=_csrf(csrf))
    deck_id = created.json()["id"]
    deleted = await api_client.request(
        "DELETE", f"/me/decks/{deck_id}", headers=_csrf(csrf)
    )
    assert deleted.status_code == 204
    assert (await api_client.get(f"/me/decks/{deck_id}")).status_code == 404


async def test_set_and_remove_card(api_client, db_session):
    user_id, csrf = await _register_verify_login(api_client, _unique_email("deck-cards"))
    card = await _make_card(db_session, name="Salamèche")
    await _own(db_session, user_id, card, 4)
    deck_id = (
        await api_client.post("/me/decks", json={"name": "D"}, headers=_csrf(csrf))
    ).json()["id"]

    put = await api_client.put(
        f"/me/decks/{deck_id}/cards/{card.id}", json={"quantity": 3}, headers=_csrf(csrf)
    )
    assert put.status_code == 200, put.text
    assert put.json()["cards"][0]["quantity"] == 3

    # idempotent : rejouer met à jour la quantité, jamais un doublon.
    put2 = await api_client.put(
        f"/me/decks/{deck_id}/cards/{card.id}", json={"quantity": 2}, headers=_csrf(csrf)
    )
    assert len(put2.json()["cards"]) == 1
    assert put2.json()["cards"][0]["quantity"] == 2

    removed = await api_client.request(
        "DELETE", f"/me/decks/{deck_id}/cards/{card.id}", headers=_csrf(csrf)
    )
    assert removed.status_code == 200
    assert removed.json()["cards"] == []


# ------------------------------------------------------------------------- accès croisé
async def test_decks_are_isolated_by_user(api_client, db_session):
    """Accès croisé (section 6) : B ne voit pas le deck de A et reçoit 404 sur toutes ses
    routes (jamais 403 : pas de fuite d'existence)."""
    user_a, csrf_a = await _register_verify_login(api_client, _unique_email("deck-a"))
    card = await _make_card(db_session, name="Mew")
    await _own(db_session, user_a, card, 1)
    a_deck = (
        await api_client.post(
            "/me/decks",
            json={"name": "Deck de A", "cards": [{"card_id": str(card.id), "quantity": 1}]},
            headers=_csrf(csrf_a),
        )
    ).json()["id"]

    _user_b, csrf_b = await _register_verify_login(api_client, _unique_email("deck-b"))
    listing = await api_client.get("/me/decks")
    assert listing.json()["decks"] == []  # B ne voit rien de A

    assert (await api_client.get(f"/me/decks/{a_deck}")).status_code == 404
    assert (
        await api_client.patch(
            f"/me/decks/{a_deck}", json={"name": "vol"}, headers=_csrf(csrf_b)
        )
    ).status_code == 404
    assert (
        await api_client.request("DELETE", f"/me/decks/{a_deck}", headers=_csrf(csrf_b))
    ).status_code == 404
    assert (
        await api_client.post(f"/me/decks/{a_deck}/duplicate", headers=_csrf(csrf_b))
    ).status_code == 404
    assert (
        await api_client.put(
            f"/me/decks/{a_deck}/cards/{card.id}", json={"quantity": 1}, headers=_csrf(csrf_b)
        )
    ).status_code == 404


# ------------------------------------------------------------------- revalidation collection
async def test_deck_revalidates_when_a_card_is_sold(api_client, db_session):
    """Vendre (supprimer) un exemplaire rend le deck injouable, sans aucune écriture sur le deck
    (mission point 3, risque du lot : le deck reste lisible, la raison est affichée)."""
    user_id, csrf = await _register_verify_login(api_client, _unique_email("deck-reval"))
    card = await _make_card(db_session, name="Dracaufeu")
    items = await _own(db_session, user_id, card, 2)
    deck_id = (
        await api_client.post(
            "/me/decks",
            json={"name": "Reval", "cards": [{"card_id": str(card.id), "quantity": 2}]},
            headers=_csrf(csrf),
        )
    ).json()["id"]

    before = await api_client.get(f"/me/decks/{deck_id}")
    assert before.json()["cards"][0]["owned"] == 2
    assert before.json()["cards"][0]["missing"] == 0
    assert not any(i["code"] == "not_owned" for i in before.json()["legality"]["issues"])

    # Vente d'un exemplaire : suppression d'un CollectionItem, sans toucher au deck.
    await db_session.delete(items[0])
    await db_session.flush()

    after = await api_client.get(f"/me/decks/{deck_id}")
    entry = after.json()["cards"][0]
    assert entry["owned"] == 1
    assert entry["missing"] == 1
    not_owned = [i for i in after.json()["legality"]["issues"] if i["code"] == "not_owned"]
    assert len(not_owned) == 1
    assert not_owned[0]["detail"] == {"required": 2, "owned": 1, "missing": 1}


# --------------------------------------------------------------------------------- CSRF
async def test_create_deck_requires_csrf(api_client, db_session):
    await _register_verify_login(api_client, _unique_email("deck-csrf"))
    # Aucun en-tête CSRF : la route d'écriture refuse.
    response = await api_client.post("/me/decks", json={"name": "Sans CSRF"})
    assert response.status_code == 403
