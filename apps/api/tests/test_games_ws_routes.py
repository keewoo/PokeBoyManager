"""Transport temps réel (`pbm_api.routers.games_ws`) — lot `j-temps-reel`.

Porte sur le **repli en interrogation HTTP** (`GET /games/{id}/sync`) et les gardes du canal
WebSocket testables sans socket réel :

* le repli sert la même charge que la resync et reste **borné au participant** (accès croisé → 404,
  pas de fuite d'existence), et permet de rejouer les coups manqués (« aucune perte sur coupure ») ;
* l'authentification du canal (`resoudre_utilisateur`) exige une session valide **et** le droit de
  jeu, sinon refuse ;
* la défense anti-CSWSH (`origine_autorisee`) n'accepte que l'origine du front.

Le pilotage complet du WebSocket (resync, diffusion, battement, rattrapage) est exercé sur un faux
canal dans `test_games_temps_reel.py` : ce fichier couvre les portes d'entrée, pas la boucle.
"""

import re
import uuid

import httpx

from pbm_api.config import settings
from pbm_api.games.service import appliquer_action, creer_partie
from pbm_api.models import Card, Deck, DeckCard, Set, User
from pbm_api.routers.games_ws import origine_autorisee, resoudre_utilisateur

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


async def _make_deck_jouable(db, user_id: uuid.UUID) -> uuid.UUID:
    set_row = Set(code=f"ws-{uuid.uuid4().hex[:8]}", name="Set jeu", series="Série test")
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


async def _accorder_jeu(db, *user_ids: uuid.UUID) -> None:
    for uid in user_ids:
        u = await db.get(User, uid)
        u.game_access = True
    await db.flush()


async def test_sync_sert_la_file_depuis_un_numero(api_client, db_session):
    a_id = uuid.UUID(await _register_verify_login(api_client, _email("a")))
    # B est enregistré en dernier : la session courante du client est donc celle de B, participant.
    b_id = uuid.UUID(await _register_verify_login(api_client, _email("b")))
    deck_a = await _make_deck_jouable(db_session, a_id)
    deck_b = await _make_deck_jouable(db_session, b_id)
    await _accorder_jeu(db_session, a_id, b_id)
    game = await creer_partie(db_session, joueur_a=(a_id, deck_a), joueur_b=(b_id, deck_b))
    for n in range(3):
        await appliquer_action(
            db_session, game_id=game.id, user_id=a_id, type="piocher", numero_attendu=n
        )

    # B interroge le repli après une « coupure » : il récupère la file manquée depuis le coup 1,
    # dans l'ordre et sans trou (« aucune perte sur coupure »).
    r = await api_client.get(f"/games/{game.id}/sync", params={"depuis": 1})
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["numero"] == 3
    assert [c["numero"] for c in payload["evenements"]] == [1, 2]
    assert payload["vue"]["joueurs"]
    assert "graine" not in r.text


async def test_sync_accces_croise_rend_404(api_client, db_session):
    a_id = uuid.UUID(await _register_verify_login(api_client, _email("a")))
    b_id = uuid.UUID(await _register_verify_login(api_client, _email("b")))
    deck_a = await _make_deck_jouable(db_session, a_id)
    deck_b = await _make_deck_jouable(db_session, b_id)
    game = await creer_partie(db_session, joueur_a=(a_id, deck_a), joueur_b=(b_id, deck_b))

    # L'intrus C a le droit de jeu mais ne participe pas : 404 (pas de fuite d'existence).
    c_id = uuid.UUID(await _register_verify_login(api_client, _email("c")))
    await _accorder_jeu(db_session, a_id, b_id, c_id)

    r = await api_client.get(f"/games/{game.id}/sync", params={"depuis": 0})
    assert r.status_code == 404, r.text


async def test_sync_sans_droit_de_jeu_rend_404(api_client, db_session):
    a_id = uuid.UUID(await _register_verify_login(api_client, _email("solo")))
    # Pas de `game_access` : la garde du jeu répond 404 (pour ce compte, le jeu n'existe pas).
    r = await api_client.get(f"/games/{uuid.uuid4()}/sync")
    assert r.status_code == 404, r.text
    assert a_id  # le compte existe bien, c'est le droit de jeu qui manque


# --- Gardes du canal WebSocket (unitaires) -----------------------------------


def test_origine_autorisee_rejette_une_origine_tierce():
    assert origine_autorisee(settings.app_public_url) is True
    assert origine_autorisee(settings.app_public_url + "/") is True  # slash final toléré
    assert origine_autorisee("https://attaquant.example") is False
    assert origine_autorisee(None) is False  # pas d'origine (non-navigateur) : refusé


async def test_resoudre_utilisateur_exige_session_et_droit_de_jeu(api_client, db_session):
    a_id = uuid.UUID(await _register_verify_login(api_client, _email("a")))
    token = api_client.cookies.get(settings.session_cookie_name)
    assert token

    # Sans droit de jeu : refusé (comme la garde HTTP).
    assert await resoudre_utilisateur(db_session, token) is None
    # Avec droit de jeu : l'utilisateur est résolu.
    await _accorder_jeu(db_session, a_id)
    user = await resoudre_utilisateur(db_session, token)
    assert user is not None and user.id == a_id
    # Jeton absent ou inconnu : refusé, jamais une erreur.
    assert await resoudre_utilisateur(db_session, None) is None
    assert await resoudre_utilisateur(db_session, "jeton-bidon") is None
