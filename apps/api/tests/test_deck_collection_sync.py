"""Synchronisation collection → decks (mission `v7-decks-collection-sync`).

Une carte qui quitte la collection ne doit pas laisser un deck faussement jouable, et le joueur
doit être prévenu — sans qu'aucune carte ne soit retirée du deck en silence. Ces tests couvrent
les scénarios exigés par la mission (vente d'une carte utilisée dans deux decks, doublon retiré
mais exemplaire restant, contenu du deck jamais modifié), plus l'isolation par utilisateur, les
suggestions de remplacement, la lecture des alertes et l'historique.
"""

import re
import uuid

import httpx

from pbm_api.config import settings
from pbm_api.models import Card, Set
from pbm_api.models.collection import CollectionItem
from pbm_api.security.csrf import CSRF_HEADER_NAME

PASSWORD = "correct horse battery staple"


def _unique_email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@example.com"


async def _login(client: httpx.AsyncClient, email: str) -> str:
    login = await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    return client.cookies.get(settings.csrf_cookie_name)


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
    supertype: str = "Pokémon",
    element_type: str | None = None,
    stage: str | None = None,
    attacks: list | None = None,
    hp: int | None = 60,
    number: str = "1",
) -> Card:
    set_row = Set(code=f"sync-{uuid.uuid4().hex[:8]}", name="Set sync", series="Série test")
    db_session.add(set_row)
    await db_session.flush()
    card = Card(
        set_id=set_row.id,
        number=number,
        name=name,
        supertype=supertype,
        element_type=element_type,
        stage=stage,
        attacks=attacks,
        hp=hp,
    )
    db_session.add(card)
    await db_session.flush()
    return card


async def _own(
    db_session, user_id: str, card: Card, count: int, *, counterfeit: bool = False
) -> list[CollectionItem]:
    items = [
        CollectionItem(
            user_id=uuid.UUID(user_id), card_id=card.id, counterfeit_suspected=counterfeit
        )
        for _ in range(count)
    ]
    db_session.add_all(items)
    await db_session.flush()
    return items


async def _create_deck(client, csrf, name, cards: list[tuple[Card, int]]) -> dict:
    payload = {
        "name": name,
        "cards": [{"card_id": str(c.id), "quantity": q} for c, q in cards],
    }
    response = await client.post("/me/decks", json=payload, headers=_csrf(csrf))
    assert response.status_code == 201, response.text
    return response.json()


# ------------------------------------------------------ scénario : vente touchant deux decks
async def test_selling_last_copy_alerts_every_deck_using_it(api_client, db_session):
    """Vente d'une carte utilisée dans DEUX decks → une alerte par deck, aucune modification."""
    user_id, csrf = await _register_verify_login(api_client, _unique_email("sync-two"))
    card = await _make_card(db_session, name="Dracaufeu", stage="Niveau 2")
    (item,) = await _own(db_session, user_id, card, 1)
    deck_a = await _create_deck(api_client, csrf, "Deck A", [(card, 1)])
    deck_b = await _create_deck(api_client, csrf, "Deck B", [(card, 1)])

    # Avant la vente : aucune alerte.
    alerts = (await api_client.get("/me/decks/alerts")).json()
    assert alerts["unread_count"] == 0

    deleted = await api_client.delete(f"/me/collection/{item.id}", headers=_csrf(csrf))
    assert deleted.status_code == 204, deleted.text

    alerts = (await api_client.get("/me/decks/alerts")).json()
    assert alerts["unread_count"] == 2
    alerted_decks = {a["deck_id"] for a in alerts["alerts"]}
    assert alerted_decks == {deck_a["id"], deck_b["id"]}
    one = alerts["alerts"][0]
    assert one["card_name"] == "Dracaufeu"
    assert one["reason"] == "removed"
    assert one["required"] == 1 and one["owned"] == 0 and one["missing"] == 1
    assert one["read"] is False


# ------------------------------------------------ scénario : doublon retiré, deck encore jouable
async def test_removing_a_duplicate_that_leaves_enough_raises_no_alert(api_client, db_session):
    """Un doublon vendu dont il reste un exemplaire suffisant : deck jouable, pas d'alerte."""
    user_id, csrf = await _register_verify_login(api_client, _unique_email("sync-dup"))
    card = await _make_card(db_session, name="Pikachu", stage="Base")
    items = await _own(db_session, user_id, card, 2)  # deux exemplaires
    await _create_deck(api_client, csrf, "Deck doublon", [(card, 1)])  # n'en exige qu'un

    deleted = await api_client.delete(f"/me/collection/{items[0].id}", headers=_csrf(csrf))
    assert deleted.status_code == 204

    alerts = (await api_client.get("/me/decks/alerts")).json()
    assert alerts["unread_count"] == 0
    assert alerts["alerts"] == []


# --------------------------------- scénario : le contenu du deck n'est JAMAIS modifié en silence
async def test_sync_never_modifies_deck_content(api_client, db_session):
    """Une vente rend le deck « à compléter » mais ne retire aucune carte : son contenu est intact
    (une partie figée au démarrage ne serait donc pas affectée)."""
    user_id, csrf = await _register_verify_login(api_client, _unique_email("sync-frozen"))
    card = await _make_card(db_session, name="Ronflex", stage="Base")
    items = await _own(db_session, user_id, card, 2)
    deck = await _create_deck(api_client, csrf, "Deck figé", [(card, 2)])

    await api_client.delete(f"/me/collection/{items[0].id}", headers=_csrf(csrf))

    refreshed = (await api_client.get(f"/me/decks/{deck['id']}")).json()
    entry = refreshed["cards"][0]
    assert entry["card_id"] == str(card.id)
    assert entry["quantity"] == 2  # le contenu du deck est INCHANGÉ
    assert entry["owned"] == 1 and entry["missing"] == 1  # mais la légalité, elle, a suivi
    assert refreshed["legality"]["legal"] is False
    # …et une alerte a bien été inscrite pour prévenir le joueur.
    alerts = (await api_client.get("/me/decks/alerts")).json()
    assert alerts["unread_count"] == 1


# ------------------------------------------------------ scénario : signalement contrefaçon
async def test_counterfeit_flag_triggers_alert(api_client, db_session):
    """Signaler un exemplaire contrefaçon le sort du décompte : même effet qu'une vente."""
    user_id, csrf = await _register_verify_login(api_client, _unique_email("sync-fake"))
    card = await _make_card(db_session, name="Ectoplasma", stage="Niveau 2")
    (item,) = await _own(db_session, user_id, card, 1)
    await _create_deck(api_client, csrf, "Deck contrefait", [(card, 1)])

    patched = await api_client.patch(
        f"/me/collection/{item.id}",
        json={"counterfeit_suspected": True},
        headers=_csrf(csrf),
    )
    assert patched.status_code == 200, patched.text

    alerts = (await api_client.get("/me/decks/alerts")).json()
    assert alerts["unread_count"] == 1
    assert alerts["alerts"][0]["reason"] == "counterfeit"


# ------------------------------------------------------ suggestions de remplacement
async def test_replacements_are_owned_ranked_and_reasoned(api_client, db_session):
    """Suggestions prises dans la collection, classées par proximité, avec raison — sans IA."""
    user_id, csrf = await _register_verify_login(api_client, _unique_email("sync-repl"))
    lightning_atk = [{"name": "Éclair", "cost": ["Lightning"]}]
    missing = await _make_card(
        db_session, name="Pikachu", element_type="Lightning", stage="Base", attacks=lightning_atk
    )
    good = await _make_card(
        db_session, name="Voltali", element_type="Lightning", stage="Base",
        attacks=lightning_atk, number="2",
    )
    other = await _make_card(
        db_session, name="Salamèche", element_type="Fire", stage="Base",
        attacks=lightning_atk, number="3",
    )
    await _own(db_session, user_id, good, 2)
    await _own(db_session, user_id, other, 1)
    deck = await _create_deck(api_client, csrf, "Deck remplacement", [(missing, 1)])

    resp = await api_client.get(f"/me/decks/{deck['id']}/cards/{missing.id}/replacements")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    names = [r["name"] for r in body["replacements"]]
    assert names == ["Voltali", "Salamèche"]  # même type d'abord
    top = body["replacements"][0]
    assert top["owned_count"] == 2  # pris dans la collection
    assert "Lightning".lower() in top["reason"].lower()
    assert top["card_id"] == str(good.id)


async def test_replacements_card_not_in_deck_is_404(api_client, db_session):
    user_id, csrf = await _register_verify_login(api_client, _unique_email("sync-repl404"))
    in_deck = await _make_card(db_session, name="Miaouss", stage="Base")
    absent = await _make_card(db_session, name="Persian", stage="Niveau 1", number="2")
    deck = await _create_deck(api_client, csrf, "Deck 404", [(in_deck, 1)])

    resp = await api_client.get(f"/me/decks/{deck['id']}/cards/{absent.id}/replacements")
    assert resp.status_code == 404


# ------------------------------------------------------ lecture des alertes + historique
async def test_mark_alerts_read_and_history(api_client, db_session):
    user_id, csrf = await _register_verify_login(api_client, _unique_email("sync-read"))
    card = await _make_card(db_session, name="Léviator", stage="Niveau 1")
    (item,) = await _own(db_session, user_id, card, 1)
    deck = await _create_deck(api_client, csrf, "Deck lu", [(card, 1)])
    await api_client.delete(f"/me/collection/{item.id}", headers=_csrf(csrf))

    marked = await api_client.post("/me/decks/alerts/read", json={}, headers=_csrf(csrf))
    assert marked.status_code == 200, marked.text
    assert marked.json()["unread_count"] == 0

    # L'alerte n'est plus « non lue »…
    unread = (await api_client.get("/me/decks/alerts")).json()
    assert unread["unread_count"] == 0
    # …mais l'historique du deck la conserve, marquée lue.
    history = (await api_client.get(f"/me/decks/{deck['id']}/history")).json()
    assert len(history["events"]) == 1
    assert history["events"][0]["read"] is True
    assert history["events"][0]["card_name"] == "Léviator"


# ------------------------------------------------------ isolation par utilisateur (accès croisé)
async def test_cross_user_isolation(api_client, db_session):
    """B ne voit jamais les alertes de A, et B reçoit 404 sur le deck de A."""
    email_a = _unique_email("sync-a")
    user_a, csrf_a = await _register_verify_login(api_client, email_a)
    card = await _make_card(db_session, name="Tortank", stage="Niveau 2")
    (item,) = await _own(db_session, user_a, card, 1)
    deck_a = await _create_deck(api_client, csrf_a, "Deck de A", [(card, 1)])
    await api_client.delete(f"/me/collection/{item.id}", headers=_csrf(csrf_a))

    a_alerts = (await api_client.get("/me/decks/alerts")).json()
    assert a_alerts["unread_count"] == 1

    # Bascule sur B (nouvelle session sur le même client).
    _user_b, csrf_b = await _register_verify_login(api_client, _unique_email("sync-b"))
    b_alerts = (await api_client.get("/me/decks/alerts")).json()
    assert b_alerts["unread_count"] == 0  # B ne voit rien des alertes de A

    # B ne peut ni lire l'historique, ni demander des remplacements sur le deck de A.
    assert (await api_client.get(f"/me/decks/{deck_a['id']}/history")).status_code == 404
    resp = await api_client.get(f"/me/decks/{deck_a['id']}/cards/{card.id}/replacements")
    assert resp.status_code == 404

    # …et marquer « lu » depuis B ne touche pas les alertes de A.
    await api_client.post("/me/decks/alerts/read", json={}, headers=_csrf(csrf_b))
    await _login(api_client, email_a)  # on se reconnecte en A
    a_again = (await api_client.get("/me/decks/alerts")).json()
    assert a_again["unread_count"] == 1  # l'alerte de A est intacte
