"""Import d'une liste de deck (mission `v7-decks-import-export`, point 1 & risque).

Couvre les trois jeux exigés (mission point 3) : liste de tournoi réelle (en-têtes de section,
codes d'extension qui ne sont pas les nôtres), liste avec fautes de frappe, liste avec cartes non
possédées — plus le risque du lot (une liste importée ne crée JAMAIS de cartes en collection) et
l'accès croisé (B reçoit 404 sur le deck importé de A).

`match_candidates` s'appuie sur `pg_trgm`/`unaccent` (extensions de la migration initiale,
présentes dans la base de test — les tests de `v2-recherche` en dépendent déjà).
"""

import re
import uuid

import httpx
from sqlalchemy import func, select

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


async def _make_card(
    db_session,
    *,
    name: str,
    en_name: str | None = None,
    number: str = "1",
    supertype: str = "Pokémon",
    energy_type: str | None = None,
    stage: str | None = None,
    set_code: str | None = None,
    set_name: str = "Set import",
    legal_standard: bool | None = True,
    legal_expanded: bool | None = True,
) -> Card:
    set_row = Set(
        code=set_code or f"imp-{uuid.uuid4().hex[:8]}", name=set_name, series="Série test"
    )
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
    db_session.add(CardName(card_id=card.id, language="fr", name=name))
    db_session.add(CardName(card_id=card.id, language="en", name=en_name or name))
    await db_session.flush()
    return card


async def _own(db_session, user_id: str, card: Card, count: int) -> None:
    for _ in range(count):
        db_session.add(CollectionItem(user_id=uuid.UUID(user_id), card_id=card.id))
    await db_session.flush()


async def _collection_count(db_session, user_id: str) -> int:
    result = await db_session.execute(
        select(func.count()).select_from(CollectionItem).where(
            CollectionItem.user_id == uuid.UUID(user_id)
        )
    )
    return result.scalar_one()


# --------------------------------------------------------------------------------- auth / csrf
async def test_import_requires_authentication(api_client):
    assert (await api_client.post("/me/decks/import", json={"text": "1 Pika"})).status_code == 401


async def test_import_requires_csrf(api_client, db_session):
    await _register_verify_login(api_client, _unique_email("imp-csrf"))
    assert (await api_client.post("/me/decks/import", json={"text": "1 Pika"})).status_code == 403


# ------------------------------------------------------------------- import crée un deck + rapport
async def test_import_creates_deck_and_reports_lines(api_client, db_session):
    user_id, csrf = await _register_verify_login(api_client, _unique_email("imp-ok"))
    draca = await _make_card(
        db_session, name="Dracaufeu ex", en_name="Charizard ex", number="234", stage="Étape 2"
    )
    await _own(db_session, user_id, draca, 3)

    resp = await api_client.post(
        "/me/decks/import",
        json={"text": "3 Dracaufeu ex 234", "name": "Import test"},
        headers=_csrf(csrf),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["deck"] is not None
    assert body["deck"]["name"] == "Import test"
    assert body["report"]["matched"] == 1
    assert body["report"]["cards_added"] == 3
    line = body["report"]["lines"][0]
    assert line["status"] == "matched"
    assert line["card"]["name"] == "Dracaufeu ex"
    assert line["owned"] == 3
    assert line["missing"] == 0
    # le deck contient bien la carte
    assert body["deck"]["cards"][0]["quantity"] == 3


# ------------------------------------------------------------------- RISQUE : jamais la collection
async def test_import_never_creates_collection_items(api_client, db_session):
    """Risque du lot : une liste importée crée un deck « à compléter », JAMAIS des cartes en
    collection. On importe des cartes NON possédées et on vérifie que la collection reste vide."""
    user_id, csrf = await _register_verify_login(api_client, _unique_email("imp-nocol"))
    await _make_card(db_session, name="Roucarnage ex", en_name="Pidgeot ex", number="164")
    await _make_card(db_session, name="Nidoran", number="55", stage="Base")

    before = await _collection_count(db_session, user_id)
    assert before == 0

    resp = await api_client.post(
        "/me/decks/import",
        json={"text": "2 Roucarnage ex 164\n1 Nidoran 55"},
        headers=_csrf(csrf),
    )
    assert resp.status_code == 200, resp.text
    after = await _collection_count(db_session, user_id)
    assert after == 0  # aucune carte n'a été ajoutée à la collection
    # ...mais le rapport signale bien qu'elles manquent
    lines = resp.json()["report"]["lines"]
    assert all(ln["missing"] == ln["quantity"] for ln in lines if ln["status"] == "matched")


# ------------------------------------------------------------------- liste de tournoi réelle
async def test_import_tournament_list_with_sections(api_client, db_session):
    """Liste façon Pokémon TCG Live : en-têtes de section ignorés, cartes rapprochées par le nom
    et le numéro même quand le code d'extension collé (PAF, PAL) n'est pas le nôtre — le repli
    est signalé, jamais silencieux."""
    user_id, csrf = await _register_verify_login(api_client, _unique_email("imp-tournoi"))
    draca = await _make_card(
        db_session, name="Dracaufeu ex", en_name="Charizard ex", number="234", stage="Étape 2"
    )
    iono = await _make_card(db_session, name="Iono", number="185", supertype="Dresseur")
    await _make_card(
        db_session, name="Énergie Feu", number="1", supertype="Énergie", energy_type="Normal"
    )
    await _own(db_session, user_id, draca, 3)
    await _own(db_session, user_id, iono, 2)

    text = (
        "Pokémon: 3\n"
        "3 Dracaufeu ex PAF 234\n"
        "\n"
        "Trainer: 2\n"
        "2 Iono PAL 185\n"
        "Energy: 10\n"
        "10 Énergie Feu\n"
        "Total Cards: 60\n"
    )
    resp = await api_client.post("/me/decks/import", json={"text": text}, headers=_csrf(csrf))
    assert resp.status_code == 200, resp.text
    report = resp.json()["report"]
    assert report["sections_ignored"] == 4
    assert report["matched"] == 3
    assert report["cards_added"] == 15
    def _line_for(name: str) -> dict:
        return next(
            ln for ln in report["lines"] if ln.get("card") and ln["card"]["name"] == name
        )

    # le code d'extension étranger a été lâché, avec une note explicite
    draca_line = _line_for("Dracaufeu ex")
    assert draca_line["parsed_set"] == "PAF"
    assert any("PAF" in n for n in draca_line["notes"])
    # l'Énergie de base n'est jamais « manquante » même sans être possédée
    feu_line = _line_for("Énergie Feu")
    assert feu_line["owned"] == 0
    assert feu_line["missing"] == 0


# ------------------------------------------------------------------- fautes de frappe
async def test_import_tolerates_typos(api_client, db_session):
    user_id, csrf = await _register_verify_login(api_client, _unique_email("imp-typo"))
    await _make_card(db_session, name="Dracaufeu ex", en_name="Charizard ex", number="234")

    resp = await api_client.post(
        "/me/decks/import", json={"text": "1 Dracaufe ex"}, headers=_csrf(csrf)
    )
    assert resp.status_code == 200, resp.text
    report = resp.json()["report"]
    matched = [ln for ln in report["lines"] if ln["status"] in ("matched", "ambiguous")]
    assert matched, report
    assert matched[0]["card"]["name"] == "Dracaufeu ex"


# ------------------------------------------------------------------- carte inexistante au catalogue
async def test_import_unknown_card_not_in_catalog(api_client, db_session):
    _uid, csrf = await _register_verify_login(api_client, _unique_email("imp-unknown"))
    await _make_card(db_session, name="Dracaufeu ex", en_name="Charizard ex")

    resp = await api_client.post(
        "/me/decks/import",
        json={"text": "1 Carte Totalement Inexistante Zzzqwx"},
        headers=_csrf(csrf),
    )
    assert resp.status_code == 200, resp.text
    report = resp.json()["report"]
    assert report["not_found"] == 1
    line = report["lines"][0]
    assert line["status"] == "not_found"
    assert line["card"] is None
    assert any("catalogue" in n for n in line["notes"])
    # non ajoutée : le deck (créé quand même) ne la contient pas
    assert report["cards_added"] == 0


# ------------------------------------------------------------------- dry-run ne crée rien
async def test_import_dry_run_creates_no_deck(api_client, db_session):
    _uid, csrf = await _register_verify_login(api_client, _unique_email("imp-dry"))
    await _make_card(db_session, name="Pikachu", number="25", stage="Base")

    resp = await api_client.post(
        "/me/decks/import",
        json={"text": "1 Pikachu 25", "dry_run": True},
        headers=_csrf(csrf),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["deck"] is None
    assert resp.json()["report"]["matched"] == 1
    listing = await api_client.get("/me/decks")
    assert listing.json()["decks"] == []  # rien n'a été créé


# ------------------------------------------------------------------- accès croisé
async def test_imported_deck_is_isolated_by_user(api_client, db_session):
    user_a, csrf_a = await _register_verify_login(api_client, _unique_email("imp-a"))
    card = await _make_card(db_session, name="Mew", number="11", stage="Base")
    await _own(db_session, user_a, card, 1)
    a_deck = (
        await api_client.post(
            "/me/decks/import", json={"text": "1 Mew 11"}, headers=_csrf(csrf_a)
        )
    ).json()["deck"]["id"]

    _user_b, csrf_b = await _register_verify_login(api_client, _unique_email("imp-b"))
    assert (await api_client.get("/me/decks")).json()["decks"] == []
    assert (await api_client.get(f"/me/decks/{a_deck}")).status_code == 404
    assert (await api_client.get(f"/me/decks/{a_deck}/export?fmt=text")).status_code == 404
    assert (await api_client.get(f"/me/decks/{a_deck}/export?fmt=pdf")).status_code == 404
