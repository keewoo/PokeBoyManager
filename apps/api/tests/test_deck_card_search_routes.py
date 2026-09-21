"""`GET /me/decks/cards` et `/me/decks/cards/facets` — recherche de cartes du constructeur
(mission `v7-decks-recherche`).

Aucune de ces routes n'existait avant le lot : chaque test fonctionnel ci-dessous échoue sans lui
(la recherche ne renvoie rien / 404) et passe avec. Accès croisé (section 6, mission point 4) :
un utilisateur B ne voit jamais la possession de A ni le contenu d'un deck de A.

`card_value_rank` (vue matérialisée, lot `v4-ranking`) n'est pas rafraîchie sur les cartes semées
en test (transaction annulée) : `value_eur` y est donc toujours `None` et le tri par valeur
retombe sur `card_id` — l'ORDRE par valeur réel est vérifié par le script de mesure
(`scripts/measure_deck_card_search_performance.py`), qui rafraîchit la vue. Ici on couvre le
filtrage, les comptes de possession, l'accès croisé et la pagination par curseur.
"""

import re
import uuid
from datetime import date

import httpx

from pbm_api.config import settings
from pbm_api.models import Card, CardName, Set
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


async def _make_set(db_session, *, name: str, code: str | None = None) -> Set:
    set_row = Set(code=code or f"dcs-{uuid.uuid4().hex[:8]}", name=name, series="Série test")
    db_session.add(set_row)
    await db_session.flush()
    return set_row


async def _make_card(
    db_session,
    *,
    set_row: Set,
    name: str,
    number: str = "1",
    supertype: str = "Pokémon",
    rarity: str | None = None,
    hp: int | None = None,
    energy_type: str | None = None,
    localized_fr: str | None = None,
) -> Card:
    card = Card(
        set_id=set_row.id,
        number=number,
        name=name,
        supertype=supertype,
        rarity=rarity,
        hp=hp,
        energy_type=energy_type,
    )
    db_session.add(card)
    await db_session.flush()
    if localized_fr is not None:
        db_session.add(CardName(card_id=card.id, language="fr", name=localized_fr))
        await db_session.flush()
    return card


async def _own(db_session, user_id: str, card: Card, count: int, acquired: date | None = None):
    items = [
        CollectionItem(user_id=uuid.UUID(user_id), card_id=card.id, acquired_at=acquired)
        for _ in range(count)
    ]
    db_session.add_all(items)
    await db_session.flush()
    return items


# --------------------------------------------------------------------------------------- auth
async def test_deck_cards_require_authentication(api_client):
    assert (await api_client.get("/me/decks/cards")).status_code == 401
    assert (await api_client.get("/me/decks/cards/facets")).status_code == 401


# --------------------------------------------------------------------- recherche nom / numéro
async def test_search_by_name_is_accent_insensitive(api_client, db_session):
    await _register_verify_login(api_client, _unique_email("dcs-name"))
    set_row = await _make_set(db_session, name="Écarlate")
    # Nom canonique anglais + nom localisé français accentué : la recherche sans accent doit
    # trouver les deux, et l'affichage montre le nom localisé.
    await _make_card(
        db_session, set_row=set_row, name="Charizard", number="4", localized_fr="Dracaufeu"
    )
    await _make_card(db_session, set_row=set_row, name="Pikachu", number="25")

    found = await api_client.get("/me/decks/cards", params={"q": "dracaufeu"})
    assert found.status_code == 200, found.text
    items = found.json()["items"]
    assert [i["name"] for i in items] == ["Dracaufeu"]  # nom localisé affiché

    # Aucun accent tapé, aucun accent stocké côté canonique : toujours trouvé.
    assert len((await api_client.get("/me/decks/cards", params={"q": "pika"})).json()["items"]) == 1
    assert (await api_client.get("/me/decks/cards", params={"q": "zzz"})).json()["items"] == []


async def test_search_by_number_normalizes_leading_zeros(api_client, db_session):
    await _register_verify_login(api_client, _unique_email("dcs-num"))
    set_row = await _make_set(db_session, name="Set num")
    await _make_card(db_session, set_row=set_row, name="Roucool", number="025")

    for query in ("25", "025", "236/217"):
        res = await api_client.get("/me/decks/cards", params={"q": query})
        assert res.status_code == 200
    matched = await api_client.get("/me/decks/cards", params={"q": "25"})
    assert [i["number"] for i in matched.json()["items"]] == ["025"]


# ------------------------------------------------------------------- possession & deck courant
async def test_owned_and_in_deck_counts(api_client, db_session):
    user_id, csrf = await _register_verify_login(api_client, _unique_email("dcs-owned"))
    set_row = await _make_set(db_session, name="Set owned")
    owned_card = await _make_card(db_session, set_row=set_row, name="Salamèche", number="4")
    await _make_card(db_session, set_row=set_row, name="Carapuce", number="7")  # non possédée
    await _own(db_session, user_id, owned_card, 3)  # doublon (>= 2)

    deck = await api_client.post(
        "/me/decks",
        json={"name": "D", "cards": [{"card_id": str(owned_card.id), "quantity": 2}]},
        headers=_csrf(csrf),
    )
    deck_id = deck.json()["id"]

    res = await api_client.get("/me/decks/cards", params={"deck_id": deck_id, "sort": "name_asc"})
    assert res.status_code == 200, res.text
    by_name = {i["name"]: i for i in res.json()["items"]}
    assert by_name["Salamèche"]["owned_count"] == 3
    assert by_name["Salamèche"]["in_deck_count"] == 2
    assert by_name["Salamèche"]["is_duplicate"] is True
    assert by_name["Carapuce"]["owned_count"] == 0
    assert by_name["Carapuce"]["in_deck_count"] == 0
    assert by_name["Carapuce"]["is_duplicate"] is False


async def test_owned_only_and_duplicates_filters(api_client, db_session):
    user_id, _csrf_token = await _register_verify_login(api_client, _unique_email("dcs-filt"))
    set_row = await _make_set(db_session, name="Set filt")
    single = await _make_card(db_session, set_row=set_row, name="Bulbizarre", number="1")
    dup = await _make_card(db_session, set_row=set_row, name="Herbizarre", number="2")
    await _make_card(db_session, set_row=set_row, name="Florizarre", number="3")  # non possédée
    await _own(db_session, user_id, single, 1)
    await _own(db_session, user_id, dup, 2)

    owned = await api_client.get("/me/decks/cards", params={"owned": "true"})
    assert {i["name"] for i in owned.json()["items"]} == {"Bulbizarre", "Herbizarre"}

    dups = await api_client.get("/me/decks/cards", params={"duplicates": "true"})
    assert {i["name"] for i in dups.json()["items"]} == {"Herbizarre"}


async def test_filter_by_type_rarity_hp_and_set(api_client, db_session):
    await _register_verify_login(api_client, _unique_email("dcs-facet"))
    set_a = await _make_set(db_session, name="Set A")
    set_b = await _make_set(db_session, name="Set B")
    await _make_card(
        db_session, set_row=set_a, name="Dracaufeu", number="4", rarity="Rare", hp=120,
        supertype="Pokémon",
    )
    await _make_card(
        db_session, set_row=set_a, name="Potion", number="90", rarity="Commune", hp=None,
        supertype="Dresseur",
    )
    await _make_card(
        db_session, set_row=set_b, name="Mewtwo", number="10", rarity="Rare", hp=70,
        supertype="Pokémon",
    )

    only_pokemon = await api_client.get("/me/decks/cards", params={"card_type": "Pokémon"})
    assert {i["name"] for i in only_pokemon.json()["items"]} == {"Dracaufeu", "Mewtwo"}

    rare = await api_client.get("/me/decks/cards", params={"rarity": "Rare"})
    assert {i["name"] for i in rare.json()["items"]} == {"Dracaufeu", "Mewtwo"}

    hp_high = await api_client.get("/me/decks/cards", params={"hp_min": "100"})
    assert {i["name"] for i in hp_high.json()["items"]} == {"Dracaufeu"}

    in_set_b = await api_client.get("/me/decks/cards", params={"set_id": str(set_b.id)})
    assert {i["name"] for i in in_set_b.json()["items"]} == {"Mewtwo"}


# ------------------------------------------------------------------------------------ facettes
async def test_facets_are_catalog_wide_with_user_counts(api_client, db_session):
    user_id, _csrf_token = await _register_verify_login(api_client, _unique_email("dcs-facets"))
    set_row = await _make_set(db_session, name="Set facets")
    c1 = await _make_card(
        db_session, set_row=set_row, name="A", number="1", rarity="Rare", hp=60,
        supertype="Pokémon",
    )
    await _make_card(
        db_session, set_row=set_row, name="B", number="2", rarity="Commune", hp=180,
        supertype="Dresseur",
    )
    await _own(db_session, user_id, c1, 2)  # une carte possédée, en doublon

    facets = await api_client.get("/me/decks/cards/facets")
    assert facets.status_code == 200, facets.text
    body = facets.json()
    assert {"Commune", "Rare"} <= set(body["rarities"])
    assert {"Dresseur", "Pokémon"} <= set(body["card_types"])
    assert body["hp_min"] == 60
    assert body["hp_max"] == 180
    assert any(s["name"] == "Set facets" for s in body["sets"])
    assert body["owned_card_count"] == 1
    assert body["duplicate_card_count"] == 1


# ------------------------------------------------------------------------------ pagination curseur
async def test_cursor_pagination_covers_all_without_duplicates(api_client, db_session):
    await _register_verify_login(api_client, _unique_email("dcs-page"))
    set_row = await _make_set(db_session, name="Set page")
    names = ["Aa", "Bb", "Cc", "Dd", "Ee"]
    for index, name in enumerate(names):
        await _make_card(db_session, set_row=set_row, name=name, number=str(index + 1))

    collected: list[str] = []
    cursor: str | None = None
    for _ in range(10):  # borne de sécurité, largement au-dessus des 3 pages attendues
        params = {"sort": "name_asc", "limit": "2"}
        if cursor:
            params["cursor"] = cursor
        page = await api_client.get("/me/decks/cards", params=params)
        assert page.status_code == 200, page.text
        body = page.json()
        collected.extend(i["name"] for i in body["items"])
        cursor = body["next_cursor"]
        if cursor is None:
            break

    assert collected == names  # ordre stable, couverture complète, aucun doublon
    assert cursor is None


async def test_value_sort_paginates_when_all_values_missing(api_client, db_session):
    """Cartes semées => `card_value_rank` vide => `value_eur` NULL partout => tri par valeur
    retombe sur `card_id`. Le curseur doit rester correct dans la traîne des NULL (régression
    du keyset `null_rank`)."""
    await _register_verify_login(api_client, _unique_email("dcs-val"))
    set_row = await _make_set(db_session, name="Set val")
    for index in range(5):
        await _make_card(db_session, set_row=set_row, name=f"V{index}", number=str(index + 1))

    seen: set[str] = set()
    cursor: str | None = None
    for _ in range(10):
        params = {"sort": "value_desc", "limit": "2"}
        if cursor:
            params["cursor"] = cursor
        body = (await api_client.get("/me/decks/cards", params=params)).json()
        for item in body["items"]:
            assert item["card_id"] not in seen  # aucun doublon entre pages
            assert item["value_eur"] is None
            seen.add(item["card_id"])
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert len(seen) == 5


# ------------------------------------------------------------------------------- accès croisé
async def test_owned_counts_are_per_user(api_client, db_session):
    """B ne « voit » jamais la possession de A : la même carte du catalogue renvoie owned_count=0
    pour B même si A en possède."""
    user_a, _csrf_a = await _register_verify_login(api_client, _unique_email("dcs-a"))
    set_row = await _make_set(db_session, name="Set croisé")
    card = await _make_card(db_session, set_row=set_row, name="Mew", number="151")
    await _own(db_session, user_a, card, 4)

    a_view = await api_client.get("/me/decks/cards", params={"q": "mew"})
    assert a_view.json()["items"][0]["owned_count"] == 4

    await _register_verify_login(api_client, _unique_email("dcs-b"))
    b_view = await api_client.get("/me/decks/cards", params={"q": "mew"})
    assert b_view.json()["items"][0]["owned_count"] == 0


async def test_deck_id_of_another_user_is_404(api_client, db_session):
    user_a, csrf_a = await _register_verify_login(api_client, _unique_email("dcs-deck-a"))
    set_row = await _make_set(db_session, name="Set deck croisé")
    card = await _make_card(db_session, set_row=set_row, name="Ronflex", number="143")
    await _own(db_session, user_a, card, 1)
    a_deck = (
        await api_client.post(
            "/me/decks",
            json={"name": "Deck de A", "cards": [{"card_id": str(card.id), "quantity": 1}]},
            headers=_csrf(csrf_a),
        )
    ).json()["id"]

    await _register_verify_login(api_client, _unique_email("dcs-deck-b"))
    # B tente d'annoter la recherche avec le deck de A : 404, jamais 403 (pas de fuite).
    denied = await api_client.get("/me/decks/cards", params={"deck_id": a_deck})
    assert denied.status_code == 404
