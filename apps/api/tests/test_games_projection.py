"""Autorité du serveur : vue projetée, coup validé, refus tracé — lot `j-autorite-vues`.

Trois critères d'acceptation du lot, au niveau HTTP (la CI fait foi) :

* le client reçoit **exclusivement** sa vue (`GET /games/{id}/state`) — jamais la main adverse, ni
  l'ordre d'une pioche, ni la graine ; et un intrus reçoit 404 (accès croisé) ;
* un coup **illégal** (`POST /games/{id}/actions`) reçoit un refus motivé (422) et **n'altère pas**
  l'état ; le serveur impose l'auteur depuis la session ;
* les refus sont **tracés**, et une **rafale** de coups illégaux lève une alerte (anti-triche).

Les propriétés fines des jetons opaques et la non-fuite sur 1 000 états sont prouvées côté moteur
(job `game` : `apps/game/tests/test_sortie_*`). Ici on vérifie le **câblage** API ↔ moteur.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import date, datetime

import httpx
import pytest

from pbm_api.games.errors import ActionRefusee
from pbm_api.games.service import (
    appliquer_action,
    creer_partie,
    reinitialiser_alerte_refus,
)
from pbm_api.models import Card, Deck, DeckCard, Game, Set, User

PASSWORD = "correct horse battery staple"

_IDENTITY = {
    "last_name": "Dresseur",
    "birth_date": date(2000, 1, 1),
    "terms_version": "test",
    "terms_accepted_at": datetime(2000, 1, 1),
}


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


async def _make_deck_jouable(db, user_id: uuid.UUID) -> uuid.UUID:
    set_row = Set(code=f"av-{uuid.uuid4().hex[:8]}", name="Set jeu", series="Série test")
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


async def _partie_a_vs_b(api_client, db_session) -> tuple[str, uuid.UUID, str, uuid.UUID, Game]:
    """Crée deux joueurs vérifiés (A, B) et une partie entre eux.

    Renvoie ``(email_a, a_id, email_b, b_id, game)`` ; à la fin, c'est **A** qui est connecté.
    """
    email_a, email_b = _email("av-a"), _email("av-b")
    a_id = await _register_verify_login(api_client, email_a)
    deck_a = await _make_deck_jouable(db_session, a_id)
    b_id = await _register_verify_login(api_client, email_b)
    deck_b = await _make_deck_jouable(db_session, b_id)
    game = await creer_partie(db_session, joueur_a=(a_id, deck_a), joueur_b=(b_id, deck_b))
    await _login(api_client, email_a)
    return email_a, a_id, email_b, b_id, game


async def test_state_ne_revele_ni_graine_ni_main_adverse(api_client, db_session):
    """A pioche, puis demande sa vue : il voit SA main, un NOMBRE pour celle de B, aucune graine."""
    email_a, a_id, email_b, b_id, game = await _partie_a_vs_b(api_client, db_session)

    # A joue un coup légal (pioche 1) via la route : le serveur fait autorité.
    r_coup = await api_client.post(
        f"/games/{game.id}/actions", json={"type": "piocher", "numero_attendu": 0}
    )
    assert r_coup.status_code == 200, r_coup.text

    r_state = await api_client.get(f"/games/{game.id}/state")
    assert r_state.status_code == 200, r_state.text
    vue = r_state.json()["vue"]
    moi = next(j for j in vue["joueurs"] if j["id"] == str(a_id))
    adverse = next(j for j in vue["joueurs"] if j["id"] == str(b_id))

    # A voit sa propre main (une carte piochée) et ses jetons de récompenses (opaques) ;
    # l'adversaire n'est connu que par des nombres.
    assert isinstance(moi.get("main"), list) and len(moi["main"]) == 1
    assert "recompenses_jetons" in moi
    assert "main" not in adverse and "main_nombre" in adverse
    assert "pioche" not in moi  # l'ordre de la pioche n'est jamais exposé, même à soi

    texte = json.dumps(r_state.json())
    assert game.graine not in texte  # le secret d'aléatoire ne fuit jamais


async def test_state_ne_fuit_pas_la_carte_piochee_a_l_adversaire(api_client, db_session):
    """La carte qu'A a piochée (dans sa main, cachée) n'apparaît pas dans la vue de B."""
    email_a, a_id, email_b, b_id, game = await _partie_a_vs_b(api_client, db_session)
    await api_client.post(
        f"/games/{game.id}/actions", json={"type": "piocher", "numero_attendu": 0}
    )
    # L'identité de la carte piochée, vue par son propriétaire A.
    r_a = await api_client.get(f"/games/{game.id}/state")
    moi = next(j for j in r_a.json()["vue"]["joueurs"] if j["id"] == str(a_id))
    carte_piochee = moi["main"][0]["instance_id"]

    # B regarde la même partie : il ne doit RIEN savoir de cette carte.
    await _login(api_client, email_b)
    r_b = await api_client.get(f"/games/{game.id}/state")
    assert r_b.status_code == 200
    assert carte_piochee not in json.dumps(r_b.json())


async def test_acces_croise_state_et_action(api_client, db_session):
    """Un intrus ne voit pas l'état d'une partie d'autrui (404) et ne peut pas y jouer (404)."""
    email_a, a_id, email_b, b_id, game = await _partie_a_vs_b(api_client, db_session)
    await _register_verify_login(api_client, _email("av-intrus"))  # devient l'utilisateur courant

    r_state = await api_client.get(f"/games/{game.id}/state")
    assert r_state.status_code == 404, r_state.text
    r_action = await api_client.post(
        f"/games/{game.id}/actions", json={"type": "piocher", "numero_attendu": 0}
    )
    assert r_action.status_code == 404, r_action.text


async def test_action_illegale_refusee_et_etat_inchange(api_client, db_session):
    """Un coup illégal reçoit un refus motivé (422) et n'avance jamais l'état."""
    email_a, a_id, email_b, b_id, game = await _partie_a_vs_b(api_client, db_session)

    r = await api_client.post(
        f"/games/{game.id}/actions", json={"type": "coup_truque", "numero_attendu": 0}
    )
    assert r.status_code == 422, r.text
    assert "coup_truque" in r.json()["detail"]  # le motif cite le type inconnu (D9)

    # L'état n'a pas bougé : la partie en est toujours au coup 0, et le coup LÉGAL 0 reste jouable.
    detail = (await api_client.get(f"/games/{game.id}")).json()
    assert detail["current_numero"] == 0
    r_legal = await api_client.post(
        f"/games/{game.id}/actions", json={"type": "piocher", "numero_attendu": 0}
    )
    assert r_legal.status_code == 200, r_legal.text


# --- Traçage des refus et alerte en rafale (anti-triche) ---------------------


async def test_refus_est_trace(db_session, caplog):
    """Un coup refusé est tracé (WARNING) avec sa cause — jamais avalé en silence."""
    reinitialiser_alerte_refus()
    user_a, deck_a, user_b, deck_b = await _deux_joueurs(db_session)
    game = await creer_partie(
        db_session, joueur_a=(user_a, deck_a), joueur_b=(user_b, deck_b)
    )
    with caplog.at_level(logging.WARNING, logger="pbm_api.games.service"):
        with pytest.raises(ActionRefusee):
            await appliquer_action(
                db_session, game_id=game.id, user_id=user_a, type="coup_truque", numero_attendu=0
            )
    assert any("coup refusé" in r.message for r in caplog.records)


async def test_rafale_de_coups_illegaux_leve_une_alerte(db_session, caplog):
    """Au-delà du seuil, une rafale de coups illégaux hausse le ton (alerte ERROR)."""
    reinitialiser_alerte_refus()
    user_a, deck_a, user_b, deck_b = await _deux_joueurs(db_session)
    game = await creer_partie(
        db_session, joueur_a=(user_a, deck_a), joueur_b=(user_b, deck_b)
    )
    with caplog.at_level(logging.ERROR, logger="pbm_api.games.service"):
        for _ in range(5):
            with pytest.raises(ActionRefusee):
                await appliquer_action(
                    db_session,
                    game_id=game.id,
                    user_id=user_a,
                    type="coup_truque",
                    numero_attendu=0,
                )
    assert any("ALERTE anti-triche" in r.message for r in caplog.records)
    # Et l'état n'a toujours pas bougé après la rafale.
    await db_session.refresh(game)
    assert game.current_numero == 0


async def _deux_joueurs(db_session) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """Deux utilisateurs, chacun un deck jouable, sans passer par HTTP : (a, deck_a, b, deck_b)."""
    ua = User(email=_email("svc-a"), password_hash="x", **_IDENTITY)
    ub = User(email=_email("svc-b"), password_hash="x", **_IDENTITY)
    db_session.add_all([ua, ub])
    await db_session.flush()
    deck_a = await _make_deck_jouable(db_session, ua.id)
    deck_b = await _make_deck_jouable(db_session, ub.id)
    return ua.id, deck_a, ub.id, deck_b
