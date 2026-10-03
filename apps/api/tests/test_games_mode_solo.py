"""Mode solo : jouer une partie d'**entraînement contre un bot** (lot ``j-mode-solo``, DJ7).

Prouve les trois critères d'acceptation du lot :

1. **une partie contre le bot se joue de bout en bout et se reprend après un F5** —
   :func:`test_partie_entrainement_de_bout_en_bout_et_reprise` : l'humain joue ses coups par
   :func:`appliquer_action`, le bot répond tout seul (siège serveur), jusqu'à une fin **méritée**
   (récompenses / plus de Pokémon), puis :func:`reprendre_partie` reconstruit l'état et vérifie
   l'empreinte (le « F5 ») ;
2. **le bot n'utilise que** :func:`pbm_game.state.vue` — :func:`test_bot_ne_voit_que_sa_vue`
   espionne chaque décision du bot et vérifie qu'il ne reçoit qu'une **projection** (jamais la main
   adverse, jamais l'``EtatPartie``) ;
3. **la partie figure dans l'historique en « entraînement »** sans toucher au classement —
   :func:`test_historique_entrainement_et_acces_croise` (et l'isolation : l'intrus reçoit 404).

Plus la route « S'entraîner » du salon (:func:`test_route_entrainement_*`). La CI fait foi.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime

import httpx
import pbm_sim.bots as sim_bots
from pbm_game.actions import actions_legales
from pbm_game.actions.familles_jeu import familles_jeu
from pbm_game.journal.modele import ACTION_ABANDONNER
from pbm_game.state.modele import EtatPartie
from sqlalchemy import select

import pbm_api.games.bot as botmod
from pbm_api.config import settings
from pbm_api.games.bot import (
    BOT_USER_ID,
    NiveauBotInconnu,
    creer_partie_entrainement,
    jouer_coups_bot,
)
from pbm_api.games.catalogue_jeu import construire_catalogue_jeu
from pbm_api.games.construction import joueur_id_de
from pbm_api.games.service import (
    appliquer_action,
    creer_partie,
    demarrer_partie,
    reprendre_partie,
)
from pbm_api.models import Card, CollectionItem, Deck, DeckCard, Game, GameEvent, Set, User
from pbm_api.security.csrf import CSRF_HEADER_NAME

PASSWORD = "correct horse battery staple"
_IDENTITY = {
    "last_name": "Dresseur",
    "birth_date": date(2000, 1, 1),
    "terms_version": "test",
    "terms_accepted_at": datetime(2000, 1, 1),
}

BOT_JID = joueur_id_de(BOT_USER_ID)


# --- Fabrique d'un deck jouable (attaquant + énergies), version service -------------------------


async def _user(db, *, game_access: bool = False) -> User:
    u = User(
        email=f"ms-{uuid.uuid4().hex[:10]}@example.com",
        password_hash="x",
        game_access=game_access,
        **_IDENTITY,
    )
    db.add(u)
    await db.flush()
    return u


async def _set(db) -> Set:
    s = Set(code=f"ms-{uuid.uuid4().hex[:8]}", name="Set mode solo", series="Série test")
    db.add(s)
    await db.flush()
    return s


async def _pikachu(db, set_row) -> Card:
    """Attaquant : « Charge » coûte 1 énergie électrique, inflige 60 (K.O. une base de 60 PV)."""
    c = Card(
        set_id=set_row.id, number=str(uuid.uuid4().int % 100000), name="Pikachu",
        supertype="Pokémon", energy_type="electrique", element_type="electrique", hp=60,
        stage="Base", retreat_cost=1, prize_marker="ordinaire",
        attacks=[{"name": "Charge", "cost": ["electrique"], "damage": "60", "effect": ""}],
    )
    db.add(c)
    await db.flush()
    return c


async def _energie(db, set_row) -> Card:
    c = Card(
        set_id=set_row.id, number=str(uuid.uuid4().int % 100000), name="Énergie Électrique",
        supertype="Énergie", energy_type="Normal", element_type="electrique",
    )
    db.add(c)
    await db.flush()
    return c


async def _deck(db, user, cartes: list[tuple[Card, int]], *, possede: bool = False) -> Deck:
    """Un deck du joueur. ``possede=True`` sème les exemplaires en collection (pour la route)."""
    deck = Deck(user_id=user.id, name="Deck mode solo")
    db.add(deck)
    await db.flush()
    for card, qty in cartes:
        db.add(DeckCard(deck_id=deck.id, card_id=card.id, quantity=qty))
        if possede and card.supertype == "Pokémon":
            for _ in range(qty):
                db.add(CollectionItem(user_id=user.id, card_id=card.id))
    await db.flush()
    return deck


def _identite_actif(joueur) -> str | None:
    return joueur.actif.cartes[0].instance_id if joueur.actif is not None else None


def _choisir(etat, jid, catalogue):
    """Stratégie humaine minimale : promouvoir, placer, attaquer, charger l'Actif, sinon passer."""
    legales = actions_legales(etat, jid, familles=familles_jeu(catalogue))
    par_type: dict[str, list] = {}
    for coup in legales:
        par_type.setdefault(coup.action.type, []).append(coup)
    if "promouvoir" in par_type:
        return par_type["promouvoir"][0].action
    if "placer_mise_en_place" in par_type:
        return par_type["placer_mise_en_place"][0].action
    if "declarer_attaque" in par_type:
        return par_type["declarer_attaque"][0].action
    joueur = next(j for j in etat.joueurs if j.id == jid)
    if "attacher_energie" in par_type and joueur.actif is not None and not joueur.actif.energies:
        actif_id = _identite_actif(joueur)
        attaches = par_type["attacher_energie"]
        sur_actif = [c for c in attaches if c.action.params.get("cible") == actif_id]
        if sur_actif:
            return sur_actif[0].action
    if "avancer_phase" in par_type:
        return par_type["avancer_phase"][0].action
    return legales[0].action if legales else None


async def _creer_entrainement_service(db, user, deck, *, niveau="correct") -> Game:
    """Crée une partie d'entraînement par le service : humain siège 0, bot siège 1."""
    game = await creer_partie(
        db,
        joueur_a=(user.id, deck.id),
        joueur_b=(BOT_USER_ID, deck.id),
        entrainement=True,
        bot_niveau=niveau,
    )
    await demarrer_partie(db, game)
    await jouer_coups_bot(db, game.id)  # le bot place son camp tout de suite
    return await db.get(Game, game.id)


# --- 1) De bout en bout + reprise après F5 ------------------------------------------------------


async def test_partie_entrainement_de_bout_en_bout_et_reprise(db_session):
    """Critère 1 — une partie contre le bot se joue jusqu'à une fin méritée, et se reprend (F5)."""
    user = await _user(db_session)
    s = await _set(db_session)
    pika = await _pikachu(db_session, s)
    energie = await _energie(db_session, s)
    deck = await _deck(db_session, user, [(pika, 6), (energie, 14)])

    game = await _creer_entrainement_service(db_session, user, deck, niveau="correct")
    assert game.entrainement is True
    human_jid = joueur_id_de(user.id)

    for _ in range(2000):
        game = await db_session.get(Game, game.id)
        if game.status != "en_cours":
            break
        etat, _rng = await reprendre_partie(db_session, game)  # reprise à chaque tour (« F5 »)
        catalogue = await construire_catalogue_jeu(db_session, etat)
        if etat.mise_en_place is not None:
            idx = next(i for i, j in enumerate(etat.joueurs) if j.id == human_jid)
            if etat.mise_en_place.placements[idx] is not None:
                # L'humain a placé mais la partie attend encore le bot : on le fait jouer.
                await jouer_coups_bot(db_session, game.id)
                continue
            acteur = human_jid
        else:
            acteur = etat.tour.joueur_actif
        if acteur != human_jid:
            # Jamais au tour du bot dans cette boucle (il joue dans appliquer_action) : par sûreté,
            # on l'avance explicitement plutôt que de sauter en silence.
            await jouer_coups_bot(db_session, game.id)
            continue
        action = _choisir(etat, human_jid, catalogue)
        assert action is not None, f"aucun coup humain (phase {etat.tour.phase})"
        await appliquer_action(
            db_session,
            game_id=game.id,
            user_id=user.id,
            type=action.type,
            params=action.params,
            numero_attendu=game.current_numero,
        )

    game = await db_session.get(Game, game.id)
    assert game.status == "terminee", f"la partie ne s'est pas terminée (statut {game.status})"
    assert game.raison_fin not in (None, "abandon"), f"fin non méritée : {game.raison_fin}"

    # Le bot n'abandonne JAMAIS : aucun coup d'abandon sous son identité dans le journal.
    entrees = (
        await db_session.execute(select(GameEvent).where(GameEvent.game_id == game.id))
    ).scalars().all()
    for e in entrees:
        assert not (e.auteur == BOT_JID and e.action.get("type") == ACTION_ABANDONNER), (
            "le bot a abandonné — interdit (il doit jouer, ou perdre aux règles)"
        )

    # F5 final : la reprise reconstruit l'état depuis le journal et vérifie l'empreinte.
    etat_final, _ = await reprendre_partie(db_session, game)
    assert etat_final.terminee


# --- 2) Le bot ne voit que sa vue ---------------------------------------------------------------


async def test_bot_ne_voit_que_sa_vue(db_session, monkeypatch):
    """Critère 2 — chaque décision du bot ne reçoit qu'une projection, jamais l'état complet."""
    captures: list = []
    reel = sim_bots.bot_heuristique

    def _recorder(niveau: str):
        def _f(vue_arg, legales, alea=None):
            captures.append(vue_arg)
            return reel(vue_arg, legales, alea)

        return _f

    monkeypatch.setattr(botmod, "_resoudre_bot", _recorder)

    user = await _user(db_session)
    s = await _set(db_session)
    pika = await _pikachu(db_session, s)
    energie = await _energie(db_session, s)
    deck = await _deck(db_session, user, [(pika, 6), (energie, 14)])
    game = await _creer_entrainement_service(db_session, user, deck, niveau="correct")

    # Quelques coups humains pour que le bot décide au moins une fois en phase de jeu aussi.
    human_jid = joueur_id_de(user.id)
    for _ in range(12):
        game = await db_session.get(Game, game.id)
        if game.status != "en_cours":
            break
        etat, _ = await reprendre_partie(db_session, game)
        catalogue = await construire_catalogue_jeu(db_session, etat)
        if etat.mise_en_place is not None:
            idx = next(i for i, j in enumerate(etat.joueurs) if j.id == human_jid)
            if etat.mise_en_place.placements[idx] is not None:
                await jouer_coups_bot(db_session, game.id)
                continue
            acteur = human_jid
        else:
            acteur = etat.tour.joueur_actif
        if acteur != human_jid:
            await jouer_coups_bot(db_session, game.id)
            continue
        action = _choisir(etat, human_jid, catalogue)
        if action is None:
            break
        await appliquer_action(
            db_session, game_id=game.id, user_id=user.id,
            type=action.type, params=action.params, numero_attendu=game.current_numero,
        )

    assert captures, "le bot n'a jamais décidé — le test ne prouve rien"
    for vue_arg in captures:
        # Ce que le bot reçoit est une PROJECTION, pas l'état du moteur.
        assert isinstance(vue_arg, dict), "le bot a reçu autre chose qu'une vue projetée"
        assert not isinstance(vue_arg, EtatPartie)
        assert vue_arg["pour"] == BOT_JID
        adversaire = next(j for j in vue_arg["joueurs"] if j["id"] != BOT_JID)
        # La main adverse n'est JAMAIS détaillée : seulement son nombre (anti-triche).
        assert "main" not in adversaire, "fuite : la main adverse est visible par le bot"
        assert "main_nombre" in adversaire


# --- 3) Historique « entraînement » + isolation -------------------------------------------------


def _email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@example.com"


def _csrf(token: str) -> dict[str, str]:
    return {CSRF_HEADER_NAME: token}


async def _register_verify_login(client: httpx.AsyncClient, email: str) -> tuple[uuid.UUID, str]:
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": PASSWORD, "last_name": "Dresseur",
              "birth_date": "2000-01-01", "accept_terms": True},
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


async def test_historique_entrainement_et_acces_croise(api_client, db_session):
    """Critère 3 — la partie figure dans l'historique marquée « entraînement » ; l'intrus a 404."""
    email_a, email_c = _email("a"), _email("c")
    a_id, _ = await _register_verify_login(api_client, email_a)
    user_a = await db_session.get(User, a_id)
    user_a.game_access = True
    await db_session.flush()
    s = await _set(db_session)
    pika = await _pikachu(db_session, s)
    energie = await _energie(db_session, s)
    deck = await _deck(db_session, user_a, [(pika, 6), (energie, 14)])
    game = await _creer_entrainement_service(db_session, user_a, deck, niveau="correct")

    # A voit la partie dans son historique, marquée entraînement.
    r_liste = await api_client.get("/games")
    assert r_liste.status_code == 200
    mienne = next((g for g in r_liste.json() if g["id"] == str(game.id)), None)
    assert mienne is not None, "la partie d'entraînement n'apparaît pas dans l'historique"
    assert mienne["entrainement"] is True

    # Le détail nomme le siège du bot (son niveau) et laisse le siège humain sans niveau.
    r_detail = await api_client.get(f"/games/{game.id}")
    assert r_detail.status_code == 200, r_detail.text
    detail = r_detail.json()
    assert detail["entrainement"] is True
    niveaux = {p["seat"]: p["bot_niveau"] for p in detail["players"]}
    assert niveaux == {0: None, 1: "correct"}, niveaux

    # Isolation : un autre compte ne voit pas la partie (404), et son historique est vide.
    c_id, _ = await _register_verify_login(api_client, email_c)
    user_c = await db_session.get(User, c_id)
    user_c.game_access = True
    await db_session.flush()
    r_intrus = await api_client.get(f"/games/{game.id}")
    assert r_intrus.status_code == 404, r_intrus.text
    assert await api_client.get("/games") and (await api_client.get("/games")).json() == []


# --- La route « S'entraîner » du salon ----------------------------------------------------------


async def test_route_entrainement_cree_la_partie(api_client, db_session):
    """La route POST /matchmaking/entrainement crée la partie et le bot a déjà placé son camp."""
    email_a = _email("a")
    a_id, csrf = await _register_verify_login(api_client, email_a)
    user_a = await db_session.get(User, a_id)
    user_a.game_access = True
    await db_session.flush()
    s = await _set(db_session)
    pika = await _pikachu(db_session, s)
    energie = await _energie(db_session, s)
    deck = await _deck(db_session, user_a, [(pika, 6), (energie, 14)], possede=True)

    r = await api_client.post(
        "/matchmaking/entrainement",
        json={"deck_id": str(deck.id), "niveau": "coriace"},
        headers=_csrf(csrf),
    )
    assert r.status_code == 201, r.text
    corps = r.json()
    assert corps["niveau"] == "coriace"
    assert corps["bot_delai_ms"] > 0
    game_id = corps["game_id"]

    r_detail = await api_client.get(f"/games/{game_id}")
    assert r_detail.status_code == 200, r_detail.text
    detail = r_detail.json()
    assert detail["entrainement"] is True
    assert {p["seat"]: p["bot_niveau"] for p in detail["players"]} == {0: None, 1: "coriace"}


async def test_route_entrainement_niveau_inconnu_422(api_client, db_session):
    """Un niveau hors DJ7 est refusé (422), jamais un repli silencieux sur un défaut."""
    email_a = _email("a")
    a_id, csrf = await _register_verify_login(api_client, email_a)
    user_a = await db_session.get(User, a_id)
    user_a.game_access = True
    await db_session.flush()
    s = await _set(db_session)
    pika = await _pikachu(db_session, s)
    deck = await _deck(db_session, user_a, [(pika, 6)], possede=True)

    r = await api_client.post(
        "/matchmaking/entrainement",
        json={"deck_id": str(deck.id), "niveau": "impossible"},
        headers=_csrf(csrf),
    )
    assert r.status_code == 422, r.text


def test_niveau_inconnu_leve_cote_service():
    """La garde est aussi dans le service : un niveau inconnu lève (unité, sans base)."""
    import asyncio

    async def _run():
        with_pytest = False
        try:
            await creer_partie_entrainement(
                None, user_id=uuid.uuid4(), deck_id=uuid.uuid4(), niveau="xx"
            )
        except NiveauBotInconnu:
            return True
        return with_pytest

    assert asyncio.run(_run()) is True
