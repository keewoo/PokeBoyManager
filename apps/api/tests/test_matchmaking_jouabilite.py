"""Jouabilité d'un deck avant l'entrée en file — `GET /matchmaking/decks/{id}/jouabilite`.

Lot `j-salon-partie` : le salon affiche la jouabilité d'un deck **avant** de proposer d'entrer en
file. L'endpoint applique le contrôle exact de l'entrée (`pbm_api.games.entry.verifier_deck`), sans
rien modifier. On vérifie :

* un deck jouable → `jouable` vrai, aucun refus ;
* un deck dont une carte n'est pas scriptée → `jouable` faux, la carte **nommée** avec sa raison
  (D9 — jamais un refus muet) ;
* le deck d'un autre joueur → 404 (pas de fuite d'existence) ;
* un compte sans droit d'accès au jeu → 404 (D11, le jeu n'existe pas pour lui).
"""

import re
import uuid

import httpx

from pbm_api.models import Card, Deck, DeckCard, Set, User

PASSWORD = "correct horse battery staple"


def _email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@example.com"


async def _register_verify_login(client: httpx.AsyncClient, email: str) -> uuid.UUID:
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
    return uuid.UUID(login.json()["id"])


async def _login(client: httpx.AsyncClient, email: str) -> None:
    login = await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text


async def _accorder_acces_jeu(db, user_id: uuid.UUID) -> None:
    user = await db.get(User, user_id)
    user.game_access = True
    await db.flush()


async def _make_deck_jouable(db, user_id: uuid.UUID) -> uuid.UUID:
    set_row = Set(code=f"mj-{uuid.uuid4().hex[:8]}", name="Set jeu", series="Série test")
    db.add(set_row)
    await db.flush()
    card = Card(
        set_id=set_row.id,
        number=str(uuid.uuid4().int % 1000),
        name="Carapuce",
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
    set_row = Set(code=f"mc-{uuid.uuid4().hex[:8]}", name="Set jeu", series="Série test")
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


async def test_deck_jouable(api_client, db_session):
    uid = await _register_verify_login(api_client, _email("jou"))
    await _accorder_acces_jeu(db_session, uid)
    deck_id = await _make_deck_jouable(db_session, uid)

    r = await api_client.get(f"/matchmaking/decks/{deck_id}/jouabilite")
    assert r.status_code == 200, r.text
    corps = r.json()
    assert corps["jouable"] is True
    assert corps["refus"] == []
    assert corps["deck_id"] == str(deck_id)


async def test_deck_non_jouable_nomme_les_cartes(api_client, db_session):
    uid = await _register_verify_login(api_client, _email("cas"))
    await _accorder_acces_jeu(db_session, uid)
    deck_id = await _make_deck_casse(db_session, uid)

    r = await api_client.get(f"/matchmaking/decks/{deck_id}/jouabilite")
    assert r.status_code == 200, r.text
    corps = r.json()
    assert corps["jouable"] is False
    cartes = [item["carte"] for item in corps["refus"]]
    assert "Insolourdo" in cartes
    assert all(item["raison"] for item in corps["refus"])


async def test_deck_dun_autre_404(api_client, db_session):
    a_id = await _register_verify_login(api_client, _email("owner"))
    await _accorder_acces_jeu(db_session, a_id)
    deck_a = await _make_deck_jouable(db_session, a_id)

    b_email = _email("intrus")
    b_id = await _register_verify_login(api_client, b_email)
    await _accorder_acces_jeu(db_session, b_id)
    await _login(api_client, b_email)
    # B interroge la jouabilité du deck de A : 404, pas de fuite d'existence.
    r = await api_client.get(f"/matchmaking/decks/{deck_a}/jouabilite")
    assert r.status_code == 404, r.text


async def test_sans_acces_jeu_404(api_client, db_session):
    uid = await _register_verify_login(api_client, _email("noacc"))
    deck_id = await _make_deck_jouable(db_session, uid)  # un deck valide : ce n'est pas le motif
    r = await api_client.get(f"/matchmaking/decks/{deck_id}/jouabilite")
    assert r.status_code == 404, r.text
