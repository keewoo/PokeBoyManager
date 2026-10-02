"""`GET /me` expose `game_access` (lot `j-salon-partie`).

Le front a besoin de savoir, côté serveur, si le compte a le droit d'accès au jeu (D11) pour
décider s'il affiche l'entrée « Jouer » (navigation, salon). Ce champ n'ouvre aucun accès — chaque
route du jeu reste gardée par `require_game_access` (404 sans le droit) — il évite seulement
d'afficher une porte qui mènerait à un 404.

Deux tests : par défaut le droit est **faux** (inscription libre, D8), et il devient **vrai** une
fois posé en base (ce que fait l'administration hors ligne via `pbm_api.admin set-game-access`).
"""

import re
import uuid

import httpx

from pbm_api.models import User

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


async def test_me_sans_acces_jeu_game_access_false(api_client):
    """Un compte ordinaire : `game_access` faux — le jeu ne lui est pas ouvert par défaut (D8)."""
    await _register_verify_login(api_client, _email("ordinaire"))
    r = await api_client.get("/me")
    assert r.status_code == 200, r.text
    assert r.json()["game_access"] is False


async def test_me_avec_acces_jeu_game_access_true(api_client, db_session):
    """Une fois le droit posé en base (administration), `GET /me` le reflète."""
    uid = await _register_verify_login(api_client, _email("invite"))
    user = await db_session.get(User, uid)
    user.game_access = True
    await db_session.flush()
    # Le cookie de session reste valide ; l'état lu vient de la base, désormais à jour.
    r = await api_client.get("/me")
    assert r.status_code == 200, r.text
    assert r.json()["game_access"] is True
