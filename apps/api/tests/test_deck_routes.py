"""`/me/decks` — CRUD, légalité (formats, sévérités), accès croisé, revalidation.

Missions `v7-decks-api` (CRUD, socle) + `v7-decks-legalite` (choix de format et cartes hors
format, sévérité des constats, Pokémon de base, exclusion des contrefaçons). Le test d'accès
croisé (section 6) et la revalidation après vente d'une carte (mission point 3) sont couverts ici.
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
    stage: str | None = None,
    legal_standard: bool | None = None,
    legal_expanded: bool | None = None,
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
        stage=stage,
        legal_standard=legal_standard,
        legal_expanded=legal_expanded,
    )
    db_session.add(card)
    await db_session.flush()
    return card


async def _basic_pokemon_card(db_session, name: str = "Pikachu") -> Card:
    """Un Pokémon de base — pour rendre un deck de test réellement jouable."""
    return await _make_card(db_session, name=name, supertype="Pokémon", stage="Base")


async def _own(
    db_session, user_id: str, card: Card, count: int, *, counterfeit: bool = False
) -> list[CollectionItem]:
    items = [
        CollectionItem(
            user_id=uuid.UUID(user_id), card_id=card.id, counterfeit_suspected=counterfeit
        )
        for _ in range(count)
    ]
    db_session.add_all(items)
    await db_session.flush()
    return items


# ----------------------------------------------------------------------------------- auth
async def test_decks_require_authentication(api_client):
    assert (await api_client.get("/me/decks")).status_code == 401


# ----------------------------------------------------------------------------------- CRUD
async def test_create_and_get_deck(api_client, db_session):
    user_id, csrf = await _register_verify_login(api_client, _unique_email("deck-crud"))
    card = await _basic_pokemon_card(db_session)
    await _own(db_session, user_id, card, 2)

    created = await api_client.post(
        "/me/decks",
        json={"name": "Mon deck", "cards": [{"card_id": str(card.id), "quantity": 2}]},
        headers=_csrf(csrf),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == "Mon deck"
    assert body["format"] == "standard"  # défaut
    assert body["legality"]["card_count"] == 2
    assert body["legality"]["legal"] is False  # 2 cartes, pas 60
    assert body["legality"]["format"] == "standard"
    entry = body["cards"][0]
    assert entry["quantity"] == 2
    assert entry["owned"] == 2
    assert entry["missing"] == 0
    assert entry["in_collection"] is True
    assert entry["is_basic_pokemon"] is True
    assert entry["in_format"] is True
    assert entry["counterfeit_excluded"] == 0

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
    """Deck de 60 cartes conforme : 1 Pokémon de base + 3 Énergies spéciales possédés
    + 56 Énergies de base (fournies, non possédées) → légal."""
    user_id, csrf = await _register_verify_login(api_client, _unique_email("deck-legal"))
    pokemon = await _basic_pokemon_card(db_session, name="Pikachu")
    special = await _make_card(
        db_session, name="Double Énergie", supertype="Énergie", energy_type="Special", number="2"
    )
    basic = await _make_card(
        db_session, name="Énergie Feu", supertype="Énergie", energy_type="Normal", number="3"
    )
    await _own(db_session, user_id, pokemon, 1)
    await _own(db_session, user_id, special, 3)  # aucune Énergie de base possédée : voulu

    created = await api_client.post(
        "/me/decks",
        json={
            "name": "Deck légal",
            "cards": [
                {"card_id": str(pokemon.id), "quantity": 1},
                {"card_id": str(special.id), "quantity": 3},
                {"card_id": str(basic.id), "quantity": 56},
            ],
        },
        headers=_csrf(csrf),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["legality"]["legal"] is True, body["legality"]["issues"]
    assert body["legality"]["card_count"] == 60
    assert body["legality"]["issues"] == []
    by_name = {c["card_name"]: c for c in body["cards"]}
    assert by_name["Énergie Feu"]["is_basic_energy"] is True
    assert by_name["Énergie Feu"]["missing"] == 0  # fournie, jamais manquante
    assert by_name["Double Énergie"]["is_special_energy"] is True
    assert by_name["Double Énergie"]["owned"] == 3
    assert by_name["Pikachu"]["is_basic_pokemon"] is True


async def test_deck_without_basic_pokemon_is_illegal(api_client, db_session):
    """PIÈGE : 60 Énergies de base, aucun Pokémon de base → injouable, avec l'explication."""
    _uid, csrf = await _register_verify_login(api_client, _unique_email("deck-nobasic"))
    basic = await _make_card(
        db_session, name="Énergie Eau", supertype="Énergie", energy_type="Normal"
    )
    created = await api_client.post(
        "/me/decks",
        json={"name": "Que des énergies", "cards": [{"card_id": str(basic.id), "quantity": 60}]},
        headers=_csrf(csrf),
    )
    body = created.json()
    assert body["legality"]["legal"] is False
    codes = [i["code"] for i in body["legality"]["issues"]]
    assert "no_basic_pokemon" in codes
    no_basic = next(i for i in body["legality"]["issues"] if i["code"] == "no_basic_pokemon")
    assert no_basic["severity"] == "bloquant"


async def test_choose_format_and_out_of_format_card(api_client, db_session):
    """Le joueur choisit un format ; une carte hors format est signalée (bloquant), et
    passer en Illimité lève le blocage."""
    user_id, csrf = await _register_verify_login(api_client, _unique_email("deck-format"))
    pokemon = await _basic_pokemon_card(db_session, name="Pikachu")
    old = await _make_card(
        db_session, name="Dresseur ancien", supertype="Dresseur",
        legal_standard=False, legal_expanded=True, number="2",
    )
    await _own(db_session, user_id, pokemon, 1)
    await _own(db_session, user_id, old, 1)
    basic = await _make_card(
        db_session, name="Énergie Feu", supertype="Énergie", energy_type="Normal", number="3"
    )

    created = await api_client.post(
        "/me/decks",
        json={
            "name": "Deck format",
            "format": "standard",
            "cards": [
                {"card_id": str(pokemon.id), "quantity": 1},
                {"card_id": str(old.id), "quantity": 1},
                {"card_id": str(basic.id), "quantity": 58},
            ],
        },
        headers=_csrf(csrf),
    )
    body = created.json()
    assert body["format"] == "standard"
    out = [i for i in body["legality"]["issues"] if i["code"] == "out_of_format"]
    assert len(out) == 1
    assert out[0]["card_name"] == "Dresseur ancien"
    assert out[0]["severity"] == "bloquant"
    old_card = next(c for c in body["cards"] if c["card_name"] == "Dresseur ancien")
    assert old_card["in_format"] is False

    # Passage en Illimité : plus aucune carte hors format.
    patched = await api_client.patch(
        f"/me/decks/{body['id']}", json={"format": "unlimited"}, headers=_csrf(csrf)
    )
    assert patched.status_code == 200
    assert patched.json()["format"] == "unlimited"
    assert not any(
        i["code"] == "out_of_format" for i in patched.json()["legality"]["issues"]
    )


async def test_counterfeit_copies_are_excluded_and_warned(api_client, db_session):
    """PIÈGE : carte contrefaite — l'exemplaire signalé contrefaçon ne compte pas dans la
    possession (avertissement), ce qui peut créer un manque (bloquant)."""
    user_id, csrf = await _register_verify_login(api_client, _unique_email("deck-cf"))
    pokemon = await _basic_pokemon_card(db_session, name="Dracaufeu")
    # 1 vraie + 1 contrefaçon : la contrefaçon est exclue → 1 possédée pour 2 demandées.
    await _own(db_session, user_id, pokemon, 1)
    await _own(db_session, user_id, pokemon, 1, counterfeit=True)
    basic = await _make_card(
        db_session, name="Énergie Feu", supertype="Énergie", energy_type="Normal", number="2"
    )
    created = await api_client.post(
        "/me/decks",
        json={
            "name": "Deck contrefaçon",
            "cards": [
                {"card_id": str(pokemon.id), "quantity": 2},
                {"card_id": str(basic.id), "quantity": 58},
            ],
        },
        headers=_csrf(csrf),
    )
    body = created.json()
    entry = next(c for c in body["cards"] if c["card_name"] == "Dracaufeu")
    assert entry["owned"] == 1  # la contrefaçon n'est pas comptée
    assert entry["counterfeit_excluded"] == 1
    assert entry["missing"] == 1
    codes = {i["code"]: i for i in body["legality"]["issues"]}
    assert codes["counterfeit_excluded"]["severity"] == "avertissement"
    assert codes["not_owned"]["severity"] == "bloquant"
    assert body["legality"]["legal"] is False


async def test_create_deck_rejects_invalid_format(api_client, db_session):
    _uid, csrf = await _register_verify_login(api_client, _unique_email("deck-badfmt"))
    response = await api_client.post(
        "/me/decks",
        json={"name": "Mauvais format", "format": "vintage"},
        headers=_csrf(csrf),
    )
    assert response.status_code == 422


async def test_rename_deck(api_client, db_session):
    _uid, csrf = await _register_verify_login(api_client, _unique_email("deck-rename"))
    created = await api_client.post("/me/decks", json={"name": "Avant"}, headers=_csrf(csrf))
    deck_id = created.json()["id"]
    renamed = await api_client.patch(
        f"/me/decks/{deck_id}", json={"name": "Après"}, headers=_csrf(csrf)
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Après"
    assert renamed.json()["format"] == "standard"  # non touché


async def test_duplicate_deck_copies_cards_and_format(api_client, db_session):
    user_id, csrf = await _register_verify_login(api_client, _unique_email("deck-dup"))
    card = await _basic_pokemon_card(db_session, name="Roucool")
    await _own(db_session, user_id, card, 3)
    created = await api_client.post(
        "/me/decks",
        json={
            "name": "Original",
            "format": "expanded",
            "cards": [{"card_id": str(card.id), "quantity": 3}],
        },
        headers=_csrf(csrf),
    )
    deck_id = created.json()["id"]
    dup = await api_client.post(f"/me/decks/{deck_id}/duplicate", headers=_csrf(csrf))
    assert dup.status_code == 201, dup.text
    body = dup.json()
    assert body["id"] != deck_id
    assert body["name"] == "Original (copie)"
    assert body["format"] == "expanded"  # le format suit la copie
    assert body["cards"][0]["quantity"] == 3

    listing = await api_client.get("/me/decks")
    assert len(listing.json()["decks"]) == 2
    assert {d["format"] for d in listing.json()["decks"]} == {"expanded"}


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
    card = await _basic_pokemon_card(db_session, name="Salamèche")
    await _own(db_session, user_id, card, 4)
    deck_id = (
        await api_client.post("/me/decks", json={"name": "D"}, headers=_csrf(csrf))
    ).json()["id"]

    put = await api_client.put(
        f"/me/decks/{deck_id}/cards/{card.id}", json={"quantity": 3}, headers=_csrf(csrf)
    )
    assert put.status_code == 200, put.text
    assert put.json()["cards"][0]["quantity"] == 3

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
    card = await _basic_pokemon_card(db_session, name="Mew")
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
    card = await _basic_pokemon_card(db_session, name="Dracaufeu")
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
    response = await api_client.post("/me/decks", json={"name": "Sans CSRF"})
    assert response.status_code == 403
