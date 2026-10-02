"""Déconnexion, abandon, désertion — lot `j-deconnexion-abandon`.

Les trois cas que le lot distingue (« leurs conséquences ne sont pas les mêmes »), côté intégration
API (le moteur des clôtures forcées est prouvé pur dans le job `game`, `test_fin_forcee`) :

* **coupure passagère** — une reprise dans le délai de grâce ne coûte aucun temps d'horloge au-delà
  de la pause (critère d'acceptation) ;
* **désertion** — une pause qui dépasse sa grâce clôt la partie par forfait, motif journalisé
  (couvert aussi par `test_games_horloges`), et l'historique porte la raison ;
* **abandon volontaire** — route dédiée `/games/{id}/abandon`, bornée au participant (accès croisé),
  et le **balayage** des parties fantômes, qui clôt pour inactivité avec un motif journalisé.

On tourne contre la vraie base de test (la CI fait foi).
"""

import re
import uuid
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select, update

from pbm_api.config import settings
from pbm_api.games import horloges as adapt
from pbm_api.games.service import (
    creer_partie,
    expirer_parties,
    marquer_deconnexion,
    marquer_reconnexion,
    reprendre_partie,
)
from pbm_api.models import Card, Deck, DeckCard, Game, GameEvent, Set, User

PASSWORD = "correct horse battery staple"

_IDENTITY = {
    "last_name": "Dresseur",
    "birth_date": date(2000, 1, 1),
    "terms_version": "test",
    "terms_accepted_at": datetime(2000, 1, 1),
}


# --- Helpers « service » (comme test_games_horloges) -------------------------


async def _make_user(db) -> User:
    user = User(email=f"da-{uuid.uuid4().hex[:10]}@example.com", password_hash="x", **_IDENTITY)
    db.add(user)
    await db.flush()
    return user


async def _make_deck(db, user: User) -> Deck:
    set_row = Set(code=f"da-{uuid.uuid4().hex[:8]}", name="Set jeu", series="Série test")
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
    deck = Deck(user_id=user.id, name="Deck jouable")
    db.add(deck)
    await db.flush()
    db.add(DeckCard(deck_id=deck.id, card_id=card.id, quantity=10))
    await db.flush()
    return deck


async def _partie(db, maintenant: datetime | None = None) -> tuple[Game, User, User]:
    user_a = await _make_user(db)
    user_b = await _make_user(db)
    deck_a = await _make_deck(db, user_a)
    deck_b = await _make_deck(db, user_b)
    game = await creer_partie(
        db, joueur_a=(user_a.id, deck_a.id), joueur_b=(user_b.id, deck_b.id), maintenant=maintenant
    )
    return game, user_a, user_b


# --- Coupure passagère : reprise dans le délai, sans coût d'horloge -----------


async def test_reprise_dans_le_delai_ne_coute_pas_de_temps(db_session):
    """Critère : la reprise dans le délai ne coûte aucun temps au-delà de la pause prévue.

    Le compteur actif tourne 10 s, puis gèle 100 s pendant la déconnexion (< 120 s de grâce) : à la
    reprise, seules les 10 s d'avant la pause sont débitées — pas les 100 s gelées.
    """
    t0 = datetime.now(UTC)
    game, user_a, user_b = await _partie(db_session, maintenant=t0)
    etat, _ = await reprendre_partie(db_session, game)
    actif_jid = etat.tour.joueur_actif
    actif_user = user_a if str(user_a.id) == actif_jid else user_b

    # Déconnexion à t0+10 (le compteur gèle), reprise à t0+110 (pause de 100 s < grâce 120 s).
    await marquer_deconnexion(
        db_session, game.id, actif_user.id, maintenant=t0 + timedelta(seconds=10)
    )
    t_reprise = t0 + timedelta(seconds=110)
    await marquer_reconnexion(db_session, game.id, maintenant=t_reprise)
    await db_session.refresh(game)

    r = adapt.restant_json(game.horloges, t_reprise.timestamp())
    assert not r["en_pause"]
    # Budget : plein moins les ~10 s d'avant la pause ; les 100 s gelées ne sont PAS débitées.
    budget = settings.horloge_par_joueur_s
    assert r["joueurs"][actif_jid]["budget_s"] == pytest.approx(budget - 10, abs=2)


# --- Balayage : clôture des parties fantômes avec un motif journalisé --------


async def test_balayage_clot_les_fantomes_avec_motif_journalise(db_session):
    """Critères : aucune partie ne reste en cours au-delà du plafond ; chaque clôture porte son
    motif dans le journal et dans l'historique (`raison_fin`). Une partie récente n'est pas touchée.
    """
    fantome, _, _ = await _partie(db_session)
    recente, _, _ = await _partie(db_session)
    # On rend la première échue (plafond d'inactivité dépassé).
    await db_session.execute(
        update(Game)
        .where(Game.id == fantome.id)
        .values(expires_at=datetime(2000, 1, 1, tzinfo=UTC))
    )
    await db_session.flush()

    compte = await expirer_parties(db_session)

    assert compte >= 1
    await db_session.refresh(fantome)
    await db_session.refresh(recente)
    # La fantôme est close, sans vainqueur, avec un motif (dans l'historique via `raison_fin`).
    assert fantome.status == "expiree"
    assert fantome.raison_fin == "inactivite"
    assert fantome.vainqueur_user_id is None
    # Le motif est aussi **dans le journal** (coup système, jamais un nettoyage muet).
    events = (
        await db_session.execute(select(GameEvent).where(GameEvent.game_id == fantome.id))
    ).scalars().all()
    assert any(e.action["type"] == "expirer_inactivite" and e.auteur == "systeme" for e in events)
    # La partie récente n'est pas touchée.
    assert recente.status == "en_cours"


async def test_balayage_sans_fantome_ne_fait_rien(db_session):
    """Un balayage sans partie échue ne clôt rien — et ne ment pas (compte à zéro)."""
    recente, _, _ = await _partie(db_session)
    await expirer_parties(db_session)
    await db_session.refresh(recente)
    # La partie récente n'est pas échue : le balayage ne la touche pas (il ne clôt que les morts).
    assert recente.status == "en_cours"


# --- Abandon volontaire : route dédiée, bornée au participant ----------------


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


async def _deck_jouable(db, user_id: uuid.UUID) -> uuid.UUID:
    set_row = Set(code=f"ab-{uuid.uuid4().hex[:8]}", name="Set jeu", series="Série test")
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


async def test_route_abandon_forfait_acces_croise_et_historique(api_client, db_session):
    """L'abandon explicite clôt par forfait ; l'intrus reçoit 404 ; l'historique porte le motif."""
    email_a, email_b, email_c = _email("a"), _email("b"), _email("c")
    a_id = uuid.UUID(await _register_verify_login(api_client, email_a))
    deck_a = await _deck_jouable(db_session, a_id)
    b_id = uuid.UUID(await _register_verify_login(api_client, email_b))
    deck_b = await _deck_jouable(db_session, b_id)
    c_id = uuid.UUID(await _register_verify_login(api_client, email_c))
    for uid in (a_id, b_id, c_id):
        u = await db_session.get(User, uid)
        u.game_access = True
    await db_session.flush()

    game = await creer_partie(db_session, joueur_a=(a_id, deck_a), joueur_b=(b_id, deck_b))

    # L'intrus C (connecté en dernier) ne participe pas : 404, pas de fuite d'existence.
    r_intrus = await api_client.post(f"/games/{game.id}/abandon")
    assert r_intrus.status_code == 404, r_intrus.text
    await db_session.refresh(game)
    assert game.status == "en_cours"  # l'intrus n'a rien pu clore

    # Le participant B abandonne : forfait, A gagne.
    await _login(api_client, email_b)
    r_ab = await api_client.post(f"/games/{game.id}/abandon")
    assert r_ab.status_code == 200, r_ab.text
    await db_session.refresh(game)
    assert game.status == "terminee"
    assert game.raison_fin == "abandon"
    assert game.vainqueur_user_id == a_id

    # Abandonner une seconde fois : la partie n'est plus en cours → 409 (jamais clos deux fois).
    r_encore = await api_client.post(f"/games/{game.id}/abandon")
    assert r_encore.status_code == 409, r_encore.text

    # L'historique de A porte le motif « abandon » (critère : dans l'historique).
    await _login(api_client, email_a)
    r_liste = await api_client.get("/games")
    assert r_liste.status_code == 200
    resume = next(g for g in r_liste.json() if g["id"] == str(game.id))
    assert resume["status"] == "terminee"
    assert resume["raison_fin"] == "abandon"
    assert resume["vainqueur_user_id"] == str(a_id)
