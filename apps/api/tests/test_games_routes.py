"""Routes de lecture des parties (`/games`) — lot `j-partie-service`.

Vérifie l'accès **borné au participant** (section « test d'accès croisé » du processus) : un
utilisateur qui ne joue pas la partie reçoit 404 (jamais 403 — pas de fuite d'existence), et sa
liste de parties ne la contient pas. La création d'une partie se fait ici par le service (le lot
`j-lancement-partie` posera la route de création) ; l'app et le test partagent la même session, donc
la partie créée est visible des requêtes HTTP.
"""

import re
import uuid

import httpx

from pbm_api.games.service import creer_partie
from pbm_api.models import Card, Deck, DeckCard, Set, User

PASSWORD = "correct horse battery staple"


def _email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@example.com"


async def _register_verify_login(client: httpx.AsyncClient, email: str) -> str:
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


async def _login(client: httpx.AsyncClient, email: str) -> None:
    login = await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text


async def _make_deck_jouable(db, user_id: uuid.UUID) -> uuid.UUID:
    set_row = Set(code=f"gr-{uuid.uuid4().hex[:8]}", name="Set jeu", series="Série test")
    db.add(set_row)
    await db.flush()
    card = Card(
        set_id=set_row.id,
        number="1",
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


async def test_acces_croise_et_liste_bornee_au_participant(api_client, db_session):
    email_a, email_b, email_c = _email("a"), _email("b"), _email("c")
    a_id = uuid.UUID(await _register_verify_login(api_client, email_a))
    deck_a = await _make_deck_jouable(db_session, a_id)
    b_id = uuid.UUID(await _register_verify_login(api_client, email_b))
    deck_b = await _make_deck_jouable(db_session, b_id)

    game = await creer_partie(
        db_session, joueur_a=(a_id, deck_a), joueur_b=(b_id, deck_b)
    )

    # Les trois comptes reçoivent le droit d'accès au jeu (D11) : ce test porte sur l'isolation
    # entre participants, pas sur la garde d'accès (testée dans `test_game_access`).
    c_id = uuid.UUID(await _register_verify_login(api_client, email_c))
    for uid in (a_id, b_id, c_id):
        u = await db_session.get(User, uid)
        u.game_access = True
    await db_session.flush()

    # L'intrus C ne participe pas : 404 sur la partie, et liste vide.
    r_intrus = await api_client.get(f"/games/{game.id}")
    assert r_intrus.status_code == 404, r_intrus.text
    r_liste_c = await api_client.get("/games")
    assert r_liste_c.status_code == 200
    assert r_liste_c.json() == []

    # Le participant A voit la partie, et sa liste la contient.
    await _login(api_client, email_a)
    r_a = await api_client.get(f"/games/{game.id}")
    assert r_a.status_code == 200, r_a.text
    detail = r_a.json()
    assert detail["id"] == str(game.id)
    assert detail["status"] == "en_cours"
    assert {p["seat"] for p in detail["players"]} == {0, 1}
    # Le secret d'aléatoire n'est jamais exposé ; seul l'engagement l'est.
    assert "graine" not in detail
    assert detail["engagement"] == game.engagement

    r_liste_a = await api_client.get("/games")
    assert r_liste_a.status_code == 200
    assert str(game.id) in {g["id"] for g in r_liste_a.json()}


async def test_partie_inexistante_rend_404(api_client, db_session):
    email = _email("solo")
    solo_id = uuid.UUID(await _register_verify_login(api_client, email))
    u = await db_session.get(User, solo_id)
    u.game_access = True
    await db_session.flush()
    r = await api_client.get(f"/games/{uuid.uuid4()}")
    assert r.status_code == 404, r.text
