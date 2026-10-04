"""`/me/demandes-cartes` — la file de demandes « je voudrais jouer cette carte » (lot
`j-effets-couverture-outil`).

Tests fonctionnels sur base (la CI fait foi). Chacun échoue sans le lot (la route n'existait pas)
et passe avec. Couvre : création idempotente, progression (jouabilité recalculée contre le
registre), carte inconnue refusée, suppression, et **accès croisé** (un joueur ne voit jamais les
demandes d'un autre — section 7 du lot)."""

import uuid

import httpx

from pbm_api.config import settings
from pbm_api.models import Card, Set
from pbm_api.security.csrf import CSRF_HEADER_NAME

PASSWORD = "correct horse battery staple"


def _unique_email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@example.com"


async def _register_verify_login(client: httpx.AsyncClient, email: str) -> tuple[str, str]:
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
    return login.json()["id"], client.cookies.get(settings.csrf_cookie_name)


def _csrf(token: str) -> dict[str, str]:
    return {CSRF_HEADER_NAME: token}


async def _make_card(db_session, *, effet: str | None = None, name: str = "Carte test") -> Card:
    set_row = Set(code=f"dem-{uuid.uuid4().hex[:8]}", name="Set demandes", series="Série test")
    db_session.add(set_row)
    await db_session.flush()
    attacks = [{"name": "Éclair", "effect": effet}] if effet else None
    card = Card(
        set_id=set_row.id,
        number=str(uuid.uuid4().int % 100000),
        name=name,
        supertype="Pokémon",
        stage="Base",
        attacks=attacks,
    )
    db_session.add(card)
    await db_session.flush()
    return card


async def test_create_and_list_request(api_client, db_session):
    card = await _make_card(db_session, effet="Un effet non scripté.", name="Pikachu rêveur")
    _, csrf = await _register_verify_login(api_client, _unique_email("a"))

    created = await api_client.post(
        "/me/demandes-cartes",
        json={"card_id": str(card.id), "note": "je veux jouer ce talent"},
        headers=_csrf(csrf),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["card_id"] == str(card.id)
    assert body["card_name"] == "Pikachu rêveur"
    assert body["statut"] == "en_attente"
    assert body["note"] == "je veux jouer ce talent"
    # Aucun script : la carte n'est pas encore jouable (progression = en attente réelle).
    assert body["jouable_maintenant"] is False

    listed = await api_client.get("/me/demandes-cartes")
    assert listed.status_code == 200
    reqs = listed.json()["requests"]
    assert len(reqs) == 1
    assert reqs[0]["card_id"] == str(card.id)


async def test_request_for_cardless_effect_is_already_playable(api_client, db_session):
    # Une carte sans effet n'exige aucun script : sa demande est « déjà jouable » dès la création.
    card = await _make_card(db_session, effet=None, name="Pokémon à dégâts secs")
    _, csrf = await _register_verify_login(api_client, _unique_email("b"))
    created = await api_client.post(
        "/me/demandes-cartes", json={"card_id": str(card.id)}, headers=_csrf(csrf)
    )
    assert created.status_code == 201, created.text
    assert created.json()["jouable_maintenant"] is True


async def test_create_is_idempotent_per_user_card(api_client, db_session):
    card = await _make_card(db_session, effet="Effet.", name="Ronflex")
    _, csrf = await _register_verify_login(api_client, _unique_email("c"))
    for note in ("première", "deuxième"):
        r = await api_client.post(
            "/me/demandes-cartes",
            json={"card_id": str(card.id), "note": note},
            headers=_csrf(csrf),
        )
        assert r.status_code == 201, r.text
    listed = await api_client.get("/me/demandes-cartes")
    reqs = listed.json()["requests"]
    assert len(reqs) == 1  # pas de doublon
    assert reqs[0]["note"] == "deuxième"  # la seconde demande a mis à jour la note


async def test_request_unknown_card_is_404(api_client, db_session):
    _, csrf = await _register_verify_login(api_client, _unique_email("d"))
    r = await api_client.post(
        "/me/demandes-cartes", json={"card_id": str(uuid.uuid4())}, headers=_csrf(csrf)
    )
    assert r.status_code == 404, r.text


async def test_delete_request(api_client, db_session):
    card = await _make_card(db_session, effet="Effet.", name="Évoli")
    _, csrf = await _register_verify_login(api_client, _unique_email("e"))
    await api_client.post(
        "/me/demandes-cartes", json={"card_id": str(card.id)}, headers=_csrf(csrf)
    )
    deleted = await api_client.delete(f"/me/demandes-cartes/{card.id}", headers=_csrf(csrf))
    assert deleted.status_code == 204, deleted.text
    listed = await api_client.get("/me/demandes-cartes")
    assert listed.json()["requests"] == []
    # Supprimer une demande inexistante : 404, jamais un succès silencieux.
    again = await api_client.delete(f"/me/demandes-cartes/{card.id}", headers=_csrf(csrf))
    assert again.status_code == 404


async def test_cross_user_isolation(api_client, db_session):
    # A crée une demande ; B, connecté ensuite, ne la voit pas (isolation par user_id).
    card = await _make_card(db_session, effet="Effet.", name="Carte de A")
    _, csrf_a = await _register_verify_login(api_client, _unique_email("owner"))
    await api_client.post(
        "/me/demandes-cartes", json={"card_id": str(card.id)}, headers=_csrf(csrf_a)
    )
    assert len((await api_client.get("/me/demandes-cartes")).json()["requests"]) == 1

    # B se connecte (le cookie de session change) : sa file est vide.
    await _register_verify_login(api_client, _unique_email("other"))
    b_list = await api_client.get("/me/demandes-cartes")
    assert b_list.status_code == 200
    assert b_list.json()["requests"] == []
