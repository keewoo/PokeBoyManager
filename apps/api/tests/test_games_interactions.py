"""Actions légales servies au client + n° d'action — lot `j-plateau-interactions`.

Deux niveaux, la CI faisant foi :

* **adaptateur pur** (`pbm_api.games.actions.actions_pour`) : il sérialise fidèlement ce que le
  moteur déclare — coups légaux, cibles, refus motivés par une règle `R-x.y`, drapeau
  `irreversible` — sans réécrire aucune règle. Rapide, sans base.
* **câblage HTTP** : `GET /games/{id}/state` porte `actions_legales`, `actions_refusees` et le
  `numero` d'action courant ; une réponse de coup porte le `numero` suivant. L'isolation par
  participant (404) est déjà couverte par `test_games_projection` — on ne la redouble pas.

Ces tests échouent sans le lot (ni actions ni numéro dans la vue) : c'est le « test qui échoue
sans le changement et passe avec ».
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime

import httpx
from pbm_game.state import (
    PHASE_CHECKUP,
    PHASE_PRINCIPALE,
    Carte,
    EtatPartie,
    Joueur,
    PokemonEnJeu,
    Tour,
)

from pbm_api.games.actions import actions_pour
from pbm_api.games.service import creer_partie
from pbm_api.models import Card, Deck, DeckCard, Set, User

PASSWORD = "correct horse battery staple"

_IDENTITY = {
    "last_name": "Dresseur",
    "birth_date": date(2000, 1, 1),
    "terms_version": "test",
    "terms_accepted_at": datetime(2000, 1, 1),
}


# --- Adaptateur pur : actions_pour ------------------------------------------


def _etat(
    *, phase: str = PHASE_PRINCIPALE, actif: str = "alice", terminee: bool = False
) -> EtatPartie:
    """Un état minimal vivant à deux joueurs (alice, bob), pour les cas nommés de l'adaptateur."""
    alice = Joueur(id="alice", actif=PokemonEnJeu(cartes=(Carte("a-pk-1", "ref-pk"),)))
    bob = Joueur(id="bob", actif=PokemonEnJeu(cartes=(Carte("b-pk-1", "ref-pk"),)))
    return EtatPartie(
        joueurs=(alice, bob),
        tour=Tour(joueur_actif=actif, numero=3, phase=phase),
        terminee=terminee,
        vainqueur="alice" if terminee else None,
        raison_fin="test" if terminee else None,
    )


def _types(actions: list[dict]) -> set[str]:
    return {a["type"] for a in actions}


def test_actions_pour_joueur_actif_liste_les_coups_sans_refus():
    """Le joueur actif (phase principale) peut avancer la phase et abandonner — rien à griser."""
    out = actions_pour(_etat(actif="alice"), "alice")
    assert _types(out["legales"]) == {"avancer_phase", "abandonner"}
    assert out["refusees"] == []
    # Chaque coup légal porte le contrat complet attendu par l'écran.
    for coup in out["legales"]:
        assert set(coup) == {"type", "params", "etiquette", "cibles", "irreversible"}
    av = next(c for c in out["legales"] if c["type"] == "avancer_phase")
    assert av["etiquette"] == "Passer à la phase suivante"
    assert av["irreversible"] is False  # un simple passage de phase ne se confirme pas
    ab = next(c for c in out["legales"] if c["type"] == "abandonner")
    assert ab["irreversible"] is True  # abandonner demande toujours confirmation (R-14.3)


def test_actions_pour_joueur_passif_grise_avancer_phase_avec_sa_regle():
    """Qui n'a pas le trait : « avancer la phase » refusé (R-5.1), abandon encore ouvert."""
    out = actions_pour(_etat(actif="alice"), "bob")
    assert _types(out["legales"]) == {"abandonner"}  # abandonner reste légal pour tout joueur
    refus = {r["type"]: r for r in out["refusees"]}
    assert "avancer_phase" in refus
    assert refus["avancer_phase"]["regle"] == "R-5.1"
    assert refus["avancer_phase"]["message"]  # un refus ne part jamais sans raison lisible


def test_actions_pour_checkup_termine_le_tour_et_demande_confirmation():
    """En phase de checkup, avancer la phase « termine le tour » — donc irréversible (R-5.7)."""
    av = next(
        c for c in actions_pour(_etat(phase=PHASE_CHECKUP, actif="alice"), "alice")["legales"]
        if c["type"] == "avancer_phase"
    )
    assert av["etiquette"] == "Terminer le tour"
    assert av["irreversible"] is True


def test_actions_pour_partie_terminee_ne_propose_rien_et_motive_le_refus():
    """Une partie terminée est figée (R-14.6) : aucun coup légal, et les refus citent R-14.6."""
    out = actions_pour(_etat(terminee=True), "alice")
    assert out["legales"] == []
    assert out["refusees"]  # la palette est grisée, pas muette
    assert all(r["regle"] == "R-14.6" for r in out["refusees"])


# --- Câblage HTTP : /state et numéro ----------------------------------------


def _email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@example.com"


async def _register_verify_login(client: httpx.AsyncClient, email: str) -> uuid.UUID:
    r = await client.post(
        "/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "last_name": "Dresseur",
            "birth_date": "2000-01-01",
            "accept_terms": True,
        },
    )
    assert r.status_code == 202, r.text
    sent = client.email_sender.sent  # type: ignore[attr-defined]
    match = re.search(r"token=(\S+)", sent[-1]["body"])
    assert match
    await client.post("/auth/verify-email", json={"token": match.group(1)})
    login = await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    return uuid.UUID(login.json()["id"])


async def _make_deck_jouable(db, user_id: uuid.UUID) -> uuid.UUID:
    set_row = Set(code=f"pi-{uuid.uuid4().hex[:8]}", name="Set jeu", series="Série test")
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


async def test_state_porte_actions_legales_refusees_et_numero(api_client, db_session):
    """La vue de A porte sa liste d'actions et le numéro d'action courant (idempotence)."""
    email_a = _email("pi-a")
    a_id = await _register_verify_login(api_client, email_a)
    deck_a = await _make_deck_jouable(db_session, a_id)
    b_id = await _register_verify_login(api_client, _email("pi-b"))
    deck_b = await _make_deck_jouable(db_session, b_id)
    game = await creer_partie(db_session, joueur_a=(a_id, deck_a), joueur_b=(b_id, deck_b))
    for uid in (a_id, b_id):
        u = await db_session.get(User, uid)
        u.game_access = True
    await db_session.flush()
    await api_client.post("/auth/login", json={"email": email_a, "password": PASSWORD})

    r = await api_client.get(f"/games/{game.id}/state")
    assert r.status_code == 200, r.text
    corps = r.json()
    assert corps["numero"] == 0  # partie neuve : prochain coup attendu = 0
    vue = corps["vue"]
    assert isinstance(vue["actions_legales"], list)
    assert isinstance(vue["actions_refusees"], list)
    # Abandonner est toujours légal pour un participant d'une partie vivante (R-14.3).
    assert "abandonner" in {a["type"] for a in vue["actions_legales"]}

    # Un coup légal fait avancer le numéro renvoyé (le client enchaîne sans relire l'état).
    r_coup = await api_client.post(
        f"/games/{game.id}/actions", json={"type": "piocher", "numero_attendu": 0}
    )
    assert r_coup.status_code == 200, r_coup.text
    assert r_coup.json()["numero"] == 1
