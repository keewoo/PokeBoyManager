"""Routes du lancement (`/lancements`) — lot `j-lancement-partie`, de bout en bout en HTTP.

Vérifie les critères du lot sur l'API réelle :

* **D11 / accès au jeu** — un compte sans `game_access` reçoit **404** (`test_sans_acces_404`) ;
* **machine de lancement persistée** — A et B se préparent, le tirage part, le gagnant choisit, on
  bascule en partie (`test_bout_en_bout_tirage_et_bascule`) ; le tirage est vérifiable (engagement
  publié, graine jamais exposée en cours) ;
* **deck devenu injouable** — une carte vendue entre le tirage et le choix arrête le lancement en
  **422** nommant la carte, sans partie fantôme (`test_deck_vendu_422`) ;
* **isolation** — un tiers ne voit pas le lancement d'autrui (`test_tiers_404`).

Le client HTTP partage son cookie de session : pour agir tour à tour comme deux joueurs, on se
reconnecte. Decks, exemplaires possédés et invitation acceptée sont posés directement en base
(`db_session`, la même session que l'app), comme dans les tests des invitations et de la file.
"""

import uuid
from datetime import UTC, datetime, timedelta

import httpx

from pbm_api.config import settings
from pbm_api.models import Card, CollectionItem, Deck, DeckCard, GameInvitation, Set, User
from pbm_api.models.invitations import INVITATION_MODE_PSEUDO, INVITATION_STATUT_ACCEPTEE
from pbm_api.security.csrf import CSRF_HEADER_NAME

PASSWORD = "correct horse battery staple"


def _email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@example.com"


def _csrf(token: str) -> dict[str, str]:
    return {CSRF_HEADER_NAME: token}


async def _register_verify_login(client: httpx.AsyncClient, email: str) -> tuple[uuid.UUID, str]:
    import re

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


async def _preparer_compte(db, user_id: uuid.UUID, *, pseudo: str) -> None:
    user = await db.get(User, user_id)
    user.game_access = True
    user.pseudo = pseudo
    await db.flush()


async def _deck_possede(db, user_id: uuid.UUID, *, name="Carapuce", quantity=20) -> Deck:
    set_row = Set(code=f"lr-{uuid.uuid4().hex[:8]}", name="Set jeu", series="Série test")
    db.add(set_row)
    await db.flush()
    card = Card(
        set_id=set_row.id,
        number=str(uuid.uuid4().int % 100000),
        name=name,
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
    deck = Deck(user_id=user_id, name=f"Deck {name}")
    db.add(deck)
    await db.flush()
    db.add(DeckCard(deck_id=deck.id, card_id=card.id, quantity=quantity))
    for _ in range(quantity):
        db.add(CollectionItem(user_id=user_id, card_id=card.id))
    await db.flush()
    return deck


async def _invitation_acceptee(db, a_id, b_id, deck_a, deck_b) -> GameInvitation:
    inv = GameInvitation(
        mode=INVITATION_MODE_PSEUDO,
        statut=INVITATION_STATUT_ACCEPTEE,
        inviter_user_id=a_id,
        invitee_user_id=b_id,
        inviter_deck_id=deck_a.id,
        invitee_deck_id=deck_b.id,
        expires_at=datetime.now(UTC) + timedelta(days=7),
        resolved_at=datetime.now(UTC),
    )
    db.add(inv)
    await db.flush()
    return inv


async def test_sans_acces_404(api_client, db_session):
    """Un compte sans droit d'accès au jeu reçoit 404 sur la route de lancement (D11)."""
    await _register_verify_login(api_client, _email("noaccess"))
    r = await api_client.get(f"/lancements/{uuid.uuid4()}")
    assert r.status_code == 404, r.text


async def test_bout_en_bout_tirage_et_bascule(api_client, db_session):
    """A et B se préparent, le tirage part, le gagnant choisit, on bascule en partie."""
    a_id, _ = await _register_verify_login(api_client, (a_email := _email("alice")))
    await _preparer_compte(db_session, a_id, pseudo="alice")
    b_id, _ = await _register_verify_login(api_client, (b_email := _email("bob")))
    await _preparer_compte(db_session, b_id, pseudo="bob")

    deck_a = await _deck_possede(db_session, a_id, name="Carapuce")
    deck_b = await _deck_possede(db_session, b_id, name="Salamèche")
    inv = await _invitation_acceptee(db_session, a_id, b_id, deck_a, deck_b)

    # A se prépare.
    csrf_a = await _login(api_client, a_email)
    r = await api_client.post(f"/lancements/{inv.id}/preparer", json={}, headers=_csrf(csrf_a))
    assert r.status_code == 200, r.text
    assert r.json()["statut"] == "preparation"

    # B se prépare → le tirage part.
    csrf_b = await _login(api_client, b_email)
    r = await api_client.post(f"/lancements/{inv.id}/preparer", json={}, headers=_csrf(csrf_b))
    assert r.status_code == 200, r.text
    corps = r.json()
    assert corps["statut"] == "tirage"
    assert corps["engagement"] and corps["tirage"] is not None
    assert corps["graine"] is None  # secret maintenu tant que la partie tourne
    gagnant = uuid.UUID(corps["tirage_gagnant_user_id"])

    # Le gagnant choisit de commencer → bascule en partie.
    gagnant_email = a_email if gagnant == a_id else b_email
    csrf_g = await _login(api_client, gagnant_email)
    r = await api_client.post(
        f"/lancements/{inv.id}/choisir", json={"commencer": True}, headers=_csrf(csrf_g)
    )
    assert r.status_code == 200, r.text
    final = r.json()
    assert final["statut"] == "lance"
    assert final["premier_joueur_user_id"] == str(gagnant)
    assert final["game_id"] is not None


async def test_deck_vendu_422(api_client, db_session):
    """Une carte vendue entre le tirage et le choix : le lancement s'arrête en 422, carte nommée."""
    a_id, _ = await _register_verify_login(api_client, (a_email := _email("alice")))
    await _preparer_compte(db_session, a_id, pseudo="alice")
    b_id, _ = await _register_verify_login(api_client, (b_email := _email("bob")))
    await _preparer_compte(db_session, b_id, pseudo="bob")

    deck_a = await _deck_possede(db_session, a_id, name="Carapuce")
    deck_b = await _deck_possede(db_session, b_id, name="Salamèche")
    inv = await _invitation_acceptee(db_session, a_id, b_id, deck_a, deck_b)

    csrf_a = await _login(api_client, a_email)
    await api_client.post(f"/lancements/{inv.id}/preparer", json={}, headers=_csrf(csrf_a))
    csrf_b = await _login(api_client, b_email)
    corps = (
        await api_client.post(f"/lancements/{inv.id}/preparer", json={}, headers=_csrf(csrf_b))
    ).json()
    gagnant = uuid.UUID(corps["tirage_gagnant_user_id"])

    # « Vente » du deck de A : on retire ses exemplaires.
    da_cards = [
        row.card_id
        for row in (
            await db_session.execute(
                DeckCard.__table__.select().where(DeckCard.deck_id == deck_a.id)
            )
        ).all()
    ]
    await db_session.execute(
        CollectionItem.__table__.delete().where(
            (CollectionItem.user_id == a_id) & (CollectionItem.card_id.in_(da_cards))
        )
    )
    await db_session.flush()

    gagnant_email = a_email if gagnant == a_id else b_email
    csrf_g = await _login(api_client, gagnant_email)
    r = await api_client.post(
        f"/lancements/{inv.id}/choisir", json={"commencer": True}, headers=_csrf(csrf_g)
    )
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert any("Carapuce" in refus["carte"] for refus in detail["refus"])


async def test_tiers_404(api_client, db_session):
    """Un tiers (ni émetteur ni invité) ne voit pas le lancement (→ 404, pas de fuite)."""
    a_id, _ = await _register_verify_login(api_client, _email("alice"))
    await _preparer_compte(db_session, a_id, pseudo="alice")
    b_id, _ = await _register_verify_login(api_client, _email("bob"))
    await _preparer_compte(db_session, b_id, pseudo="bob")
    deck_a = await _deck_possede(db_session, a_id)
    deck_b = await _deck_possede(db_session, b_id, name="Salamèche")
    inv = await _invitation_acceptee(db_session, a_id, b_id, deck_a, deck_b)

    # C est un troisième compte **avec** accès au jeu, mais sans rôle dans l'invitation : le 404
    # prouve l'isolation (le rôle), pas seulement la garde d'accès.
    c_id, _ = await _register_verify_login(api_client, _email("carol"))
    await _preparer_compte(db_session, c_id, pseudo="carol")
    await _login(api_client, (await db_session.get(User, c_id)).email)
    r = await api_client.get(f"/lancements/{inv.id}")
    assert r.status_code == 404, r.text
