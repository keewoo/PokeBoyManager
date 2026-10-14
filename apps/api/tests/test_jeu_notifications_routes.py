"""Routes des notifications du jeu (`/jeu/notifications`) — lot `j-notifications-jeu`, en HTTP.

Ce qui se vérifie ici et nulle part ailleurs :

* **D11** — un compte sans accès au jeu reçoit 404 partout (``test_sans_acces_404_partout``) ;
* **isolation** — la notification d'autrui est *introuvable*, et la liste ne contient jamais que la
  sienne (``test_notification_dautrui_introuvable``, ``test_liste_bornee_a_son_compte``) ;
* **les réglages se posent par l'API**, partiellement, et refusent ce qui n'existe pas
  (``test_reglages_partiels``, ``test_genre_inconnu_refuse``, ``test_fuseau_inconnu_refuse``) ;
* **aucune route n'émet** de notification : il n'en existe pas, et c'est délibéré
  (``test_aucune_route_nemet_de_notification``).

Les notifications sont semées par le service (``pbm_api.notifications.service.notifier``) avec un
**instant explicite en pleine journée** : le silence nocturne est actif par défaut, et une suite qui
dépend de l'heure à laquelle la CI tourne est une suite qui mentira une nuit sur deux.
"""

import re
import uuid
from datetime import UTC, datetime, timedelta

import httpx

from pbm_api.config import settings
from pbm_api.games.construction import joueur_id_de
from pbm_api.models import Game, GamePlayer, User
from pbm_api.models.notifications import (
    NOTIF_ADVERSAIRE_TROUVE,
    NOTIF_GENRES,
    NOTIF_TON_TOUR,
)
from pbm_api.notifications import service
from pbm_api.security.csrf import CSRF_HEADER_NAME

PASSWORD = "correct horse battery staple"

#: Un mardi à 14 h (heure de Paris) : hors silence nocturne, quelle que soit l'heure de la CI.
EN_PLEIN_JOUR = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


def _email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@example.com"


def _csrf(token: str) -> dict[str, str]:
    return {CSRF_HEADER_NAME: token}


async def _register_verify_login(client: httpx.AsyncClient, email: str) -> tuple[uuid.UUID, str]:
    """Crée un compte, le vérifie et l'ouvre — même enchaînement que les tests d'invitations."""
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


async def _donner_acces(db, user_id: uuid.UUID, *, pseudo: str) -> None:
    user = await db.get(User, user_id)
    user.game_access = True
    user.pseudo = pseudo
    await db.flush()


async def creer_partie_nue(db, *, joueurs: list[uuid.UUID]) -> Game:
    """Une ligne ``games`` + ses sièges, sans passer par le moteur.

    Les notifications n'ont besoin que de l'**identité** de la partie et de ses sièges (c'est par
    ``game_players`` que l'on retrouve le compte derrière un joueur du moteur) : fabriquer un état
    initial complet coûterait des decks et un catalogue pour ne rien prouver de plus.
    """
    maintenant = datetime.now(UTC)
    game = Game(
        etat_initial={},
        graine="00" * 16,
        engagement="ff" * 32,
        journal_version=1,
        current_numero=0,
        current_empreinte="00" * 32,
        last_action_at=maintenant,
        expires_at=maintenant + timedelta(hours=6),
    )
    db.add(game)
    await db.flush()
    for siege, user_id in enumerate(joueurs):
        db.add(GamePlayer(game_id=game.id, user_id=user_id, seat=siege))
    await db.flush()
    return game


# --- D11 : le jeu n'existe pas pour un compte non invité --------------------------------------


async def test_sans_acces_404_partout(api_client, db_session):
    """Un compte sans ``game_access`` reçoit 404 sur **toutes** les routes de notification."""
    _, csrf = await _register_verify_login(api_client, _email("noaccess"))
    assert (await api_client.get("/jeu/notifications")).status_code == 404
    assert (await api_client.get("/jeu/notifications/reglages")).status_code == 404
    r = await api_client.patch(
        "/jeu/notifications/reglages", json={"silence_actif": False}, headers=_csrf(csrf)
    )
    assert r.status_code == 404, r.text
    r2 = await api_client.post("/jeu/notifications/lues", headers=_csrf(csrf))
    assert r2.status_code == 404, r2.text


# --- Lecture et isolation ---------------------------------------------------------------------


async def test_liste_bornee_a_son_compte(api_client, db_session):
    """La liste ne rend que ses propres notifications — jamais celles d'un autre compte."""
    a_id, _ = await _register_verify_login(api_client, _email("alice"))
    await _donner_acces(db_session, a_id, pseudo=f"alice{uuid.uuid4().hex[:4]}")
    b_email = _email("bob")
    b_id, _ = await _register_verify_login(api_client, b_email)
    await _donner_acces(db_session, b_id, pseudo=f"bob{uuid.uuid4().hex[:4]}")
    partie = await creer_partie_nue(db_session, joueurs=[a_id, b_id])

    for destinataire in (a_id, b_id):
        assert await service.notifier(
            db_session,
            destinataire_id=destinataire,
            genre=NOTIF_ADVERSAIRE_TROUVE,
            game_id=partie.id,
            instant=EN_PLEIN_JOUR,
        )

    # B est le dernier connecté : il ne voit que la sienne.
    corps = (await api_client.get("/jeu/notifications")).json()
    assert corps["nb_non_lues"] == 1
    assert len(corps["notifications"]) == 1
    assert corps["notifications"][0]["game_id"] == str(partie.id)
    assert corps["notifications"][0]["silencieuse"] is False


async def test_notification_dautrui_introuvable(api_client, db_session):
    """Marquer lue la notification d'un autre compte → **404**, jamais 403 (qui la confirmerait)."""
    a_id, _ = await _register_verify_login(api_client, _email("alice"))
    await _donner_acces(db_session, a_id, pseudo=f"alice{uuid.uuid4().hex[:4]}")
    b_email = _email("bob")
    b_id, _ = await _register_verify_login(api_client, b_email)
    await _donner_acces(db_session, b_id, pseudo=f"bob{uuid.uuid4().hex[:4]}")
    partie = await creer_partie_nue(db_session, joueurs=[a_id, b_id])

    celle_de_a = await service.notifier(
        db_session,
        destinataire_id=a_id,
        genre=NOTIF_TON_TOUR,
        game_id=partie.id,
        instant=EN_PLEIN_JOUR,
    )
    assert celle_de_a is not None

    csrf = await _login(api_client, b_email)
    r = await api_client.post(f"/jeu/notifications/{celle_de_a.id}/lue", headers=_csrf(csrf))
    assert r.status_code == 404, r.text
    # Et elle n'a pas été marquée lue au passage.
    await db_session.refresh(celle_de_a)
    assert celle_de_a.lue_at is None


async def test_marquer_lue_puis_tout_lue(api_client, db_session):
    """Marquer une notification lue, puis tout marquer lu : le compte des non lues suit."""
    uid, csrf = await _register_verify_login(api_client, _email("joueur"))
    await _donner_acces(db_session, uid, pseudo=f"joueur{uuid.uuid4().hex[:4]}")
    partie = await creer_partie_nue(db_session, joueurs=[uid])

    une = await service.notifier(
        db_session,
        destinataire_id=uid,
        genre=NOTIF_ADVERSAIRE_TROUVE,
        game_id=partie.id,
        instant=EN_PLEIN_JOUR,
    )
    deux = await service.notifier(
        db_session,
        destinataire_id=uid,
        genre=NOTIF_TON_TOUR,
        game_id=partie.id,
        instant=EN_PLEIN_JOUR,
    )
    assert une is not None and deux is not None

    assert (await api_client.get("/jeu/notifications")).json()["nb_non_lues"] == 2

    r = await api_client.post(f"/jeu/notifications/{une.id}/lue", headers=_csrf(csrf))
    assert r.status_code == 200, r.text
    assert r.json()["lue_at"] is not None
    assert (await api_client.get("/jeu/notifications")).json()["nb_non_lues"] == 1

    r2 = await api_client.post("/jeu/notifications/lues", headers=_csrf(csrf))
    assert r2.status_code == 200, r2.text
    assert r2.json()["nb_non_lues"] == 0


async def test_filtre_non_lues(api_client, db_session):
    """``?non_lues=true`` ne rend que ce qui attend d'être lu."""
    uid, csrf = await _register_verify_login(api_client, _email("joueur"))
    await _donner_acces(db_session, uid, pseudo=f"joueur{uuid.uuid4().hex[:4]}")
    partie = await creer_partie_nue(db_session, joueurs=[uid])
    lue = await service.notifier(
        db_session,
        destinataire_id=uid,
        genre=NOTIF_ADVERSAIRE_TROUVE,
        game_id=partie.id,
        instant=EN_PLEIN_JOUR,
    )
    assert lue is not None
    await service.notifier(
        db_session,
        destinataire_id=uid,
        genre=NOTIF_TON_TOUR,
        game_id=partie.id,
        instant=EN_PLEIN_JOUR,
    )
    await api_client.post(f"/jeu/notifications/{lue.id}/lue", headers=_csrf(csrf))

    corps = (await api_client.get("/jeu/notifications", params={"non_lues": True})).json()
    assert [n["genre"] for n in corps["notifications"]] == [NOTIF_TON_TOUR]


# --- Réglages ---------------------------------------------------------------------------------


async def test_reglages_defauts_publies_avec_les_plafonds(api_client, db_session):
    """Les défauts sont servis sans qu'aucune ligne n'existe, plafonds du produit compris."""
    uid, _ = await _register_verify_login(api_client, _email("joueur"))
    await _donner_acces(db_session, uid, pseudo=f"joueur{uuid.uuid4().hex[:4]}")

    corps = (await api_client.get("/jeu/notifications/reglages")).json()
    assert corps["genres_desactives"] == []
    assert corps["silence_actif"] is True
    assert corps["silence_debut"].startswith("21:00")
    assert corps["silence_fin"].startswith("07:00")
    assert sorted(corps["genres_connus"]) == sorted(NOTIF_GENRES)
    assert corps["plafond_par_partie"] >= 1
    assert corps["plafond_par_genre"][NOTIF_TON_TOUR] >= 1


async def test_reglages_partiels(api_client, db_session):
    """Une modification partielle ne touche pas aux autres réglages (un interrupteur à la fois)."""
    uid, csrf = await _register_verify_login(api_client, _email("joueur"))
    await _donner_acces(db_session, uid, pseudo=f"joueur{uuid.uuid4().hex[:4]}")

    r = await api_client.patch(
        "/jeu/notifications/reglages",
        json={"genres_desactives": [NOTIF_TON_TOUR]},
        headers=_csrf(csrf),
    )
    assert r.status_code == 200, r.text
    assert r.json()["genres_desactives"] == [NOTIF_TON_TOUR]
    assert r.json()["silence_actif"] is True, "non fourni = inchangé"

    r2 = await api_client.patch(
        "/jeu/notifications/reglages",
        json={"silence_debut": "22:30:00", "silence_fin": "08:00:00"},
        headers=_csrf(csrf),
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["silence_debut"].startswith("22:30")
    assert r2.json()["genres_desactives"] == [NOTIF_TON_TOUR], "le genre coupé n'a pas été écrasé"


async def test_genre_inconnu_refuse(api_client, db_session):
    """Désactiver un genre inexistant est refusé : un interrupteur qui ne coupe rien mentirait."""
    uid, csrf = await _register_verify_login(api_client, _email("joueur"))
    await _donner_acces(db_session, uid, pseudo=f"joueur{uuid.uuid4().hex[:4]}")
    r = await api_client.patch(
        "/jeu/notifications/reglages",
        json={"genres_desactives": ["sonnerie_imaginaire"]},
        headers=_csrf(csrf),
    )
    assert r.status_code == 422, r.text


async def test_fuseau_inconnu_refuse(api_client, db_session):
    """Un fuseau fautif est refusé **à l'écriture**, pas plus tard dans le chemin d'un coup."""
    uid, csrf = await _register_verify_login(api_client, _email("joueur"))
    await _donner_acces(db_session, uid, pseudo=f"joueur{uuid.uuid4().hex[:4]}")
    r = await api_client.patch(
        "/jeu/notifications/reglages", json={"fuseau": "Mars/Olympus"}, headers=_csrf(csrf)
    )
    assert r.status_code == 422, r.text


async def test_reglage_sans_csrf_refuse(api_client, db_session):
    """Toute écriture exige le jeton CSRF, comme partout dans le produit."""
    uid, _ = await _register_verify_login(api_client, _email("joueur"))
    await _donner_acces(db_session, uid, pseudo=f"joueur{uuid.uuid4().hex[:4]}")
    r = await api_client.patch("/jeu/notifications/reglages", json={"silence_actif": False})
    assert r.status_code == 403, r.text


# --- Garde de conception ----------------------------------------------------------------------


async def test_aucune_route_nemet_de_notification(api_client):
    """**Aucune** route ne permet de créer une notification, pour soi ou pour autrui.

    Garde de conception, pas de confort : si une telle route existait, n'importe quel client
    pourrait se fabriquer une sonnerie — ou en fabriquer une à l'autre, en contournant ses réglages
    et les plafonds. Les notifications naissent d'un événement du jeu, point.
    """
    from pbm_api.routers.notifications import router

    emettrices = [
        (route.path, sorted(route.methods))
        for route in router.routes
        if "POST" in getattr(route, "methods", set())
        and not route.path.endswith(("/lue", "/lues"))
    ]
    assert emettrices == [], f"routes d'émission inattendues : {emettrices}"


def test_identifiant_de_joueur_reste_celui_du_compte():
    """Parité : résoudre « joueur du moteur → compte » suppose ``joueur_id_de == str(user_id)``.

    Si cette convention changeait, ``_user_du_joueur`` cesserait de trouver le destinataire et les
    notifications de partie disparaîtraient **en silence**. Ce test tient la convention.
    """
    uid = uuid.uuid4()
    assert joueur_id_de(uid) == str(uid)
