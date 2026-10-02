"""Droit d'accès au jeu — « compte invité » (D11), lot `j-file-attente`.

Deux faces d'une même règle :

* **la commande d'administration** `set-game-access <email> on|off` pose et retire le droit
  (`test_set_game_access_pose_et_retire`, `test_set_game_access_compte_absent`) ;
* **les routes de parties** (`/games`, posées par `j-partie-service`) répondent **404** à un compte
  sans ce droit, comme pour un objet d'autrui (`test_games_404_sans_acces`). Les routes de la file
  (`/matchmaking`) sont gardées de la même façon et testées dans `test_matchmaking_routes`.

L'inscription est libre (D8) : un compte neuf n'a **aucun** accès au jeu (`game_access` à `false`
par défaut), ce que ces tests prennent comme point de départ.
"""

import re
import uuid
from datetime import date, datetime

import httpx
import pytest

from pbm_api.admin import SetGameAccessError, _build_parser, set_game_access
from pbm_api.games.service import creer_partie
from pbm_api.models import Card, Deck, DeckCard, Set, User

PASSWORD = "correct horse battery staple"

_IDENTITY = {
    "last_name": "Dresseur",
    "birth_date": date(2000, 1, 1),
    "terms_version": "test",
    "terms_accepted_at": datetime(2000, 1, 1),
}


def _email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@example.com"


# --- Commande d'administration ----------------------------------------------


async def test_set_game_access_pose_et_retire(db_session):
    email = _email("ga")
    user = User(email=email, password_hash="x", game_access=False, **_IDENTITY)
    db_session.add(user)
    await db_session.flush()

    # Pose le droit.
    rendu = await set_game_access(db_session, email=email.upper(), enabled=True)
    assert rendu == email  # normalisé (minuscules)
    refreshed = await db_session.get(User, user.id)
    assert refreshed.game_access is True

    # Le retire.
    await set_game_access(db_session, email=email, enabled=False)
    refreshed2 = await db_session.get(User, user.id)
    assert refreshed2.game_access is False


async def test_set_game_access_compte_absent(db_session):
    with pytest.raises(SetGameAccessError):
        await set_game_access(db_session, email=_email("inconnu"), enabled=True)


def test_parser_refuse_un_etat_invalide():
    """`on`/`off` seulement : argparse rejette tout autre état (sortie non nulle)."""
    with pytest.raises(SystemExit):
        _build_parser().parse_args(["set-game-access", "a@b.fr", "peut-etre"])


# --- Gating des routes de parties -------------------------------------------


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


async def _make_deck_jouable(db, user_id: uuid.UUID) -> uuid.UUID:
    set_row = Set(code=f"ga-{uuid.uuid4().hex[:8]}", name="Set jeu", series="Série test")
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


async def test_games_404_sans_acces(api_client, db_session):
    """Les routes de parties répondent 404 sans droit d'accès, 200 une fois le droit accordé."""
    email_a, email_b = _email("joueur"), _email("adv")
    a_id = await _register_verify_login(api_client, email_a)
    deck_a = await _make_deck_jouable(db_session, a_id)
    # Adversaire pour pouvoir créer une partie réelle.
    b_id = await _register_verify_login(api_client, email_b)
    deck_b = await _make_deck_jouable(db_session, b_id)
    game = await creer_partie(db_session, joueur_a=(a_id, deck_a), joueur_b=(b_id, deck_b))

    # On est connecté comme B (dernier login). B participe, mais n'a PAS le droit d'accès au jeu.
    assert (await api_client.get("/games")).status_code == 404
    assert (await api_client.get(f"/games/{game.id}")).status_code == 404
    assert (await api_client.get(f"/games/{game.id}/state")).status_code == 404

    # On accorde le droit à B : les mêmes routes répondent maintenant.
    await set_game_access(db_session, email=email_b, enabled=True)
    r_liste = await api_client.get("/games")
    assert r_liste.status_code == 200, r_liste.text
    assert any(g["id"] == str(game.id) for g in r_liste.json())
    assert (await api_client.get(f"/games/{game.id}")).status_code == 200
