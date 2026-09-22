"""Export d'un deck en texte et en PDF (mission `v7-decks-import-export`, point 2).

Le texte est re-lisible par l'analyseur d'import (round-trip : exporter puis ré-importer redonne
le même deck). Le PDF montre les vignettes (une image en stockage est bien embarquée) et retombe
sur un cadre nommé quand la vignette manque — jamais un 500.
"""

import io
import re
import uuid

import httpx
from PIL import Image

from pbm_api.config import settings
from pbm_api.models import Card, CardName, Set
from pbm_api.models.collection import CollectionItem
from pbm_api.routers.decks import get_storage
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


async def _make_card(db_session, *, name, en_name=None, number, supertype="Pokémon",
                     energy_type=None, stage=None, set_code) -> Card:
    set_row = Set(code=set_code, name="Set export", series="Série test")
    db_session.add(set_row)
    await db_session.flush()
    card = Card(
        set_id=set_row.id, number=number, name=name, supertype=supertype,
        energy_type=energy_type, stage=stage, legal_standard=True, legal_expanded=True,
    )
    db_session.add(card)
    await db_session.flush()
    db_session.add(CardName(card_id=card.id, language="fr", name=name))
    db_session.add(CardName(card_id=card.id, language="en", name=en_name or name))
    await db_session.flush()
    return card


async def _own(db_session, user_id, card, count) -> None:
    for _ in range(count):
        db_session.add(CollectionItem(user_id=uuid.UUID(user_id), card_id=card.id))
    await db_session.flush()


async def _deck_with_cards(api_client, db_session, csrf, user_id):
    draca = await _make_card(
        db_session, name="Dracaufeu ex", en_name="Charizard ex", number="234",
        stage="Étape 2", set_code=f"ex-{uuid.uuid4().hex[:6]}",
    )
    feu = await _make_card(
        db_session, name="Énergie Feu", number="1", supertype="Énergie",
        energy_type="Normal", set_code=f"en-{uuid.uuid4().hex[:6]}",
    )
    await _own(db_session, user_id, draca, 3)
    created = await api_client.post(
        "/me/decks",
        json={
            "name": "Deck export",
            "cards": [
                {"card_id": str(draca.id), "quantity": 3},
                {"card_id": str(feu.id), "quantity": 10},
            ],
        },
        headers=_csrf(csrf),
    )
    assert created.status_code == 201, created.text
    return created.json()["id"], draca


class _FakeStorage:
    def __init__(self, blobs: dict[str, bytes]) -> None:
        self._blobs = blobs

    async def get(self, key: str) -> bytes | None:
        return self._blobs.get(key)


def _webp_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (63, 88), (200, 60, 60)).save(buf, "WEBP")
    return buf.getvalue()


# --------------------------------------------------------------------------------- texte
async def test_export_text_round_trips(api_client, db_session):
    user_id, csrf = await _register_verify_login(api_client, _unique_email("exp-txt"))
    deck_id, draca = await _deck_with_cards(api_client, db_session, csrf, user_id)

    resp = await api_client.get(f"/me/decks/{deck_id}/export?fmt=text")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    text = resp.text
    assert "# Deck export" in text
    assert "3 Dracaufeu ex" in text
    assert "10 Énergie Feu" in text

    # Round-trip : ré-importer ce texte redonne le même deck.
    reimport = await api_client.post(
        "/me/decks/import", json={"text": text, "name": "Réimport"}, headers=_csrf(csrf)
    )
    assert reimport.status_code == 200, reimport.text
    report = reimport.json()["report"]
    assert report["distinct_cards"] == 2
    assert report["cards_added"] == 13
    names = {ln["card"]["name"] for ln in report["lines"] if ln.get("card")}
    assert names == {"Dracaufeu ex", "Énergie Feu"}


# --------------------------------------------------------------------------------- pdf
async def test_export_pdf_placeholder_when_no_thumbnail(api_client, db_session):
    from pbm_api.main import app

    user_id, csrf = await _register_verify_login(api_client, _unique_email("exp-pdf"))
    deck_id, _draca = await _deck_with_cards(api_client, db_session, csrf, user_id)

    app.dependency_overrides[get_storage] = lambda: _FakeStorage({})
    resp = await api_client.get(f"/me/decks/{deck_id}/export?fmt=pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:5] == b"%PDF-"
    assert len(resp.content) > 800  # un vrai document, pas un stub


async def test_export_pdf_embeds_thumbnail(api_client, db_session):
    """Preuve que la vignette est embarquée : le PDF avec image en stockage est nettement plus
    lourd que le même deck rendu sans vignette (cadres nommés)."""
    from pbm_api.main import app

    user_id, csrf = await _register_verify_login(api_client, _unique_email("exp-pdf2"))
    deck_id, draca = await _deck_with_cards(api_client, db_session, csrf, user_id)

    app.dependency_overrides[get_storage] = lambda: _FakeStorage({})
    without = await api_client.get(f"/me/decks/{deck_id}/export?fmt=pdf")

    blobs = {f"cards/{draca.id}/low.webp": _webp_bytes()}
    app.dependency_overrides[get_storage] = lambda: _FakeStorage(blobs)
    with_img = await api_client.get(f"/me/decks/{deck_id}/export?fmt=pdf")

    assert without.status_code == with_img.status_code == 200
    assert with_img.content[:5] == b"%PDF-"
    assert len(with_img.content) > len(without.content)


async def test_export_unknown_deck_is_404(api_client, db_session):
    _uid, csrf = await _register_verify_login(api_client, _unique_email("exp-404"))
    missing = uuid.uuid4()
    assert (await api_client.get(f"/me/decks/{missing}/export?fmt=text")).status_code == 404
