"""Routes des invitations (`/invitations`) — lot `j-invitations`, de bout en bout en HTTP.

Vérifie les critères d'acceptation du lot sur l'API réelle :

* **D11 / accès au jeu** — un compte sans `game_access` reçoit **404** partout, et un lien ne lui
  ouvre aucun accès (`test_sans_acces_404_partout`, `test_lien_nouvre_aucun_acces`) ;
* **invitation par pseudo** acceptée de bout en bout, les deux joueurs voyant le **même salon**
  (`test_pseudo_bout_en_bout_meme_salon`) ;
* **lien à usage unique** : accepté une fois, refusé la seconde (`test_lien_usage_unique`) ;
* **isolation** : un tiers ne voit pas le salon d'autrui (`test_salon_tiers_404`).

Le client HTTP partage son cookie de session : pour agir tour à tour comme deux joueurs, on se
reconnecte. Le pseudo et le droit d'accès au jeu sont posés directement en base (`db_session`, la
même session que l'app), comme dans les tests de la file d'attente.
"""

import re
import uuid

import httpx

from pbm_api.config import settings
from pbm_api.models import User
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


async def _preparer(db, user_id: uuid.UUID, *, pseudo: str, game_access=True) -> None:
    user = await db.get(User, user_id)
    user.game_access = game_access
    user.pseudo = pseudo
    await db.flush()


async def test_sans_acces_404_partout(api_client, db_session):
    """Un compte sans droit d'accès au jeu reçoit 404 sur les routes d'invitation (D11)."""
    uid, csrf = await _register_verify_login(api_client, _email("noaccess"))
    assert (await api_client.get("/invitations/recues")).status_code == 404
    r = await api_client.post(
        "/invitations/pseudo", json={"pseudo": "quelquun"}, headers=_csrf(csrf)
    )
    assert r.status_code == 404, r.text
    r2 = await api_client.post("/invitations/lien", json={}, headers=_csrf(csrf))
    assert r2.status_code == 404, r2.text


async def test_pseudo_bout_en_bout_meme_salon(api_client, db_session):
    """A invite B par pseudo ; B l'accepte ; les deux voient le même salon. E-mail parti vers B."""
    a_id, _ = await _register_verify_login(api_client, _email("alice"))
    await _preparer(db_session, a_id, pseudo="alice")
    b_email = _email("bob")
    b_id, _ = await _register_verify_login(api_client, b_email)
    await _preparer(db_session, b_id, pseudo="bob")

    # A invite B.
    csrf_a = await _login(api_client, (await db_session.get(User, a_id)).email)
    r = await api_client.post(
        "/invitations/pseudo", json={"pseudo": "bob"}, headers=_csrf(csrf_a)
    )
    assert r.status_code == 201, r.text
    invitation_id = r.json()["id"]
    assert r.json()["statut"] == "envoyee"
    assert "jeton" not in r.json()  # une invitation par pseudo n'a pas de jeton
    # Relais e-mail vers B.
    envois = api_client.email_sender.sent  # type: ignore[attr-defined]
    assert any(m["to"] == b_email for m in envois)

    # B la voit dans ses invitations reçues (notification dans l'application) et l'accepte.
    csrf_b = await _login(api_client, b_email)
    recues = await api_client.get("/invitations/recues")
    assert [i["id"] for i in recues.json()] == [invitation_id]
    acc = await api_client.post(
        f"/invitations/{invitation_id}/accepter", json={}, headers=_csrf(csrf_b)
    )
    assert acc.status_code == 200, acc.text
    salon_b = acc.json()
    assert salon_b["statut"] == "acceptee"

    # A consulte le salon : vue identique à celle de B.
    await _login(api_client, (await db_session.get(User, a_id)).email)
    salon_a = (await api_client.get(f"/invitations/{invitation_id}/salon")).json()
    assert salon_a == salon_b
    assert salon_a["inviter"]["user_id"] == str(a_id)
    assert salon_a["invitee"]["user_id"] == str(b_id)


async def test_lien_usage_unique(api_client, db_session):
    """Un lien sert une fois : B rejoint (200), un second usage par C est refusé (409)."""
    a_id, csrf_a = await _register_verify_login(api_client, _email("alice"))
    await _preparer(db_session, a_id, pseudo="alice")

    r = await api_client.post("/invitations/lien", json={}, headers=_csrf(csrf_a))
    assert r.status_code == 201, r.text
    jeton = r.json()["jeton"]
    assert jeton and r.json()["url"].endswith(jeton)

    b_email = _email("bob")
    b_id, csrf_b = await _register_verify_login(api_client, b_email)
    await _preparer(db_session, b_id, pseudo="bob")
    rejoint = await api_client.post(
        "/invitations/lien/accepter", json={"jeton": jeton}, headers=_csrf(csrf_b)
    )
    assert rejoint.status_code == 200, rejoint.text
    assert rejoint.json()["invitee"]["user_id"] == str(b_id)

    c_email = _email("carol")
    c_id, csrf_c = await _register_verify_login(api_client, c_email)
    await _preparer(db_session, c_id, pseudo="carol")
    encore = await api_client.post(
        "/invitations/lien/accepter", json={"jeton": jeton}, headers=_csrf(csrf_c)
    )
    assert encore.status_code == 409, encore.text


async def test_lien_nouvre_aucun_acces(api_client, db_session):
    """Un compte SANS accès au jeu qui suit un lien reçoit 404 : le lien n'ouvre rien (D11)."""
    a_id, csrf_a = await _register_verify_login(api_client, _email("alice"))
    await _preparer(db_session, a_id, pseudo="alice")
    jeton = (
        await api_client.post("/invitations/lien", json={}, headers=_csrf(csrf_a))
    ).json()["jeton"]

    # B n'est PAS invité au jeu : la garde require_game_access le refuse avant tout traitement.
    b_email = _email("bob")
    _, csrf_b = await _register_verify_login(api_client, b_email)
    r = await api_client.post(
        "/invitations/lien/accepter", json={"jeton": jeton}, headers=_csrf(csrf_b)
    )
    assert r.status_code == 404, r.text


async def test_salon_tiers_404(api_client, db_session):
    """Un tiers invité au jeu ne voit pas le salon d'une invitation où il n'a aucun rôle."""
    a_id, _ = await _register_verify_login(api_client, _email("alice"))
    await _preparer(db_session, a_id, pseudo="alice")
    b_id, _ = await _register_verify_login(api_client, _email("bob"))
    await _preparer(db_session, b_id, pseudo="bob")

    # Se reconnecter comme A rafraîchit le cookie CSRF : on reprend le jeton courant, pas l'ancien.
    csrf_a = await _login(api_client, (await db_session.get(User, a_id)).email)
    reponse = await api_client.post(
        "/invitations/pseudo", json={"pseudo": "bob"}, headers=_csrf(csrf_a)
    )
    assert reponse.status_code == 201, reponse.text
    invitation_id = reponse.json()["id"]

    # C, invité au jeu mais étranger à l'invitation, reçoit 404 sur le salon.
    c_id, _ = await _register_verify_login(api_client, _email("carol"))
    await _preparer(db_session, c_id, pseudo="carol")
    r = await api_client.get(f"/invitations/{invitation_id}/salon")
    assert r.status_code == 404, r.text
