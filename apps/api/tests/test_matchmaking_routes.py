"""Routes de la recherche d'adversaire (`/matchmaking`) — lot `j-file-attente`.

Vérifie :

* **le droit d'accès au jeu (D11)** — un compte sans `game_access` reçoit **404** sur chacune des
  routes du jeu (`test_sans_acces_404_partout`) ;
* **l'entrée en file et l'appariement** de bout en bout en HTTP (`test_entree_et_appariement`) ;
* **le refus d'un deck à l'entrée** nommant les cartes (`test_deck_refuse_nomme_les_cartes`) ;
* **un deck d'autrui** → 404, pas de fuite (`test_deck_dun_autre_404`) ;
* **la présence** et ses options de repli quand personne n'est disponible (`test_presence_seul`).

Le client HTTP partage son cookie de session : pour agir tour à tour comme deux joueurs, on se
reconnecte entre les deux. L'état Redis `mm:*` est purgé entre les tests par le conftest.
"""

import re
import uuid

import httpx

from pbm_api.config import settings
from pbm_api.models import Card, Deck, DeckCard, Set, User
from pbm_api.security.csrf import CSRF_HEADER_NAME

PASSWORD = "correct horse battery staple"


def _email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@example.com"


def _csrf(token: str) -> dict[str, str]:
    return {CSRF_HEADER_NAME: token}


async def _register_verify_login(client: httpx.AsyncClient, email: str) -> tuple[uuid.UUID, str]:
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
    return uuid.UUID(login.json()["id"]), client.cookies.get(settings.csrf_cookie_name)


async def _login(client: httpx.AsyncClient, email: str) -> str:
    login = await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    return client.cookies.get(settings.csrf_cookie_name)


async def _accorder_acces_jeu(db, user_id: uuid.UUID) -> None:
    user = await db.get(User, user_id)
    user.game_access = True
    await db.flush()


async def _make_deck_jouable(db, user_id: uuid.UUID, *, nom="Carapuce") -> uuid.UUID:
    set_row = Set(code=f"mr-{uuid.uuid4().hex[:8]}", name="Set jeu", series="Série test")
    db.add(set_row)
    await db.flush()
    card = Card(
        set_id=set_row.id,
        number=str(uuid.uuid4().int % 1000),
        name=nom,
        supertype="Pokémon",
        energy_type="water",
        element_type="water",
        hp=60,
        stage="Base",
        retreat_cost=1,
        prize_marker="ordinaire",
    )
    db.add(card)
    await db.flush()
    deck = Deck(user_id=user_id, name="Deck jouable")
    db.add(deck)
    await db.flush()
    db.add(DeckCard(deck_id=deck.id, card_id=card.id, quantity=8))
    await db.flush()
    return deck.id


async def _make_deck_casse(db, user_id: uuid.UUID) -> uuid.UUID:
    set_row = Set(code=f"mb-{uuid.uuid4().hex[:8]}", name="Set jeu", series="Série test")
    db.add(set_row)
    await db.flush()
    card = Card(
        set_id=set_row.id,
        number=str(uuid.uuid4().int % 1000),
        name="Insolourdo",
        supertype="Pokémon",
        energy_type="water",
        element_type="water",
        hp=60,
        stage="Base",
        retreat_cost=1,
        prize_marker=None,  # non jouable : l'adaptateur le refuse (D9)
    )
    db.add(card)
    await db.flush()
    deck = Deck(user_id=user_id, name="Deck cassé")
    db.add(deck)
    await db.flush()
    db.add(DeckCard(deck_id=deck.id, card_id=card.id, quantity=8))
    await db.flush()
    return deck.id


async def test_sans_acces_404_partout(api_client, db_session):
    """Un compte sans droit d'accès au jeu reçoit 404 sur chacune des routes du jeu (D11)."""
    email = _email("noaccess")
    uid, csrf = await _register_verify_login(api_client, email)
    deck_id = await _make_deck_jouable(db_session, uid)  # un deck valide : ce n'est pas le motif

    # POST (entrer), GET (consulter), DELETE (annuler), GET présence — toutes 404, le jeu n'existe
    # pas pour ce compte.
    r_post = await api_client.post(
        "/matchmaking/queue", json={"deck_id": str(deck_id)}, headers=_csrf(csrf)
    )
    assert r_post.status_code == 404, r_post.text
    assert (await api_client.get("/matchmaking/queue")).status_code == 404
    assert (
        await api_client.request("DELETE", "/matchmaking/queue", headers=_csrf(csrf))
    ).status_code == 404
    assert (await api_client.get("/matchmaking/presence")).status_code == 404


async def test_entree_et_appariement(api_client, db_session):
    email_a, email_b = _email("a"), _email("b")
    a_id, _ = await _register_verify_login(api_client, email_a)
    await _accorder_acces_jeu(db_session, a_id)
    deck_a = await _make_deck_jouable(db_session, a_id)
    b_id, _ = await _register_verify_login(api_client, email_b)
    await _accorder_acces_jeu(db_session, b_id)
    deck_b = await _make_deck_jouable(db_session, b_id)

    # A entre : en attente.
    csrf_a = await _login(api_client, email_a)
    r_a = await api_client.post(
        "/matchmaking/queue", json={"deck_id": str(deck_a)}, headers=_csrf(csrf_a)
    )
    assert r_a.status_code == 200, r_a.text
    assert r_a.json()["status"] == "en_attente"
    assert r_a.json()["joueurs_en_file"] == 1

    # B entre : apparié, une partie est créée.
    csrf_b = await _login(api_client, email_b)
    r_b = await api_client.post(
        "/matchmaking/queue", json={"deck_id": str(deck_b)}, headers=_csrf(csrf_b)
    )
    assert r_b.status_code == 200, r_b.text
    corps_b = r_b.json()
    assert corps_b["status"] == "apparie"
    assert corps_b["game_id"]
    assert corps_b["adversaire_user_id"] == str(a_id)

    # A consulte : il voit qu'il est apparié sur la même partie.
    await _login(api_client, email_a)
    r_a2 = await api_client.get("/matchmaking/queue")
    assert r_a2.status_code == 200
    assert r_a2.json()["status"] == "apparie"
    assert r_a2.json()["game_id"] == corps_b["game_id"]


async def test_deck_refuse_nomme_les_cartes(api_client, db_session):
    email = _email("refus")
    uid, csrf = await _register_verify_login(api_client, email)
    await _accorder_acces_jeu(db_session, uid)
    deck_casse = await _make_deck_casse(db_session, uid)

    r = await api_client.post(
        "/matchmaking/queue", json={"deck_id": str(deck_casse)}, headers=_csrf(csrf)
    )
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    cartes = [item["carte"] for item in detail["refus"]]
    assert "Insolourdo" in cartes
    assert all(item["raison"] for item in detail["refus"])


async def test_deck_dun_autre_404(api_client, db_session):
    email_a, email_b = _email("owner"), _email("intrus")
    a_id, _ = await _register_verify_login(api_client, email_a)
    await _accorder_acces_jeu(db_session, a_id)
    deck_a = await _make_deck_jouable(db_session, a_id)

    b_id, csrf_b = await _register_verify_login(api_client, email_b)
    await _accorder_acces_jeu(db_session, b_id)
    # B tente d'entrer avec le deck de A : 404 (pas de fuite d'existence).
    r = await api_client.post(
        "/matchmaking/queue", json={"deck_id": str(deck_a)}, headers=_csrf(csrf_b)
    )
    assert r.status_code == 404, r.text


async def test_presence_seul(api_client, db_session):
    email = _email("seul")
    uid, _ = await _register_verify_login(api_client, email)
    await _accorder_acces_jeu(db_session, uid)
    r = await api_client.get("/matchmaking/presence")
    assert r.status_code == 200, r.text
    corps = r.json()
    assert corps["en_ligne"] >= 1
    assert corps["autres_disponibles"] == 0
    # Personne à affronter → options de repli proposées (invitation, entraînement bot).
    assert "invitation" in corps["options"]
    assert "entrainement_bot" in corps["options"]
