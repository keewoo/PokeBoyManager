"""Routes des emotes en jeu (``/jeu/emotes``) — lot ``j-echanges-emotes``, décision DJ10.

Ce que ces tests tiennent :

* le **catalogue** publié est bien le vocabulaire du serveur, débit compris (l'écran grise sa
  palette avec ces chiffres, il ne les devine pas) ;
* le **réglage** : défaut DJ10 quand on n'y a jamais touché, modification partielle, CSRF exigé,
  et la garde d'accès au jeu (D11) ;
* l'**accès croisé** : B ne peut ni lire ni modifier le réglage de A. Ces chemins ne portent aucun
  identifiant d'objet — c'est précisément ce qu'on vérifie, plutôt que de le supposer : le réglage
  est borné au compte de la session, donc il n'existe pas de route par laquelle atteindre celui
  d'un autre ;
* l'**absence de route d'envoi** : il n'existe aucun chemin HTTP pour envoyer une emote, et c'est
  une garantie du lot (pas de route = pas de file d'attente = rien à stocker). Un test le vérifie
  sur le schéma OpenAPI réel, pas sur une relecture du code.
"""

from __future__ import annotations

import re
import uuid

import httpx

from pbm_api.config import settings
from pbm_api.games.emotes import CATALOGUE, MAX_PAR_FENETRE
from pbm_api.main import app
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


async def _acces_jeu(db, user_id: uuid.UUID) -> None:
    user = await db.get(User, user_id)
    user.game_access = True
    await db.flush()


async def test_catalogue_publie_le_vocabulaire_et_le_debit(api_client, db_session):
    user_id, _ = await _register_verify_login(api_client, _email("emote-cat"))
    await _acces_jeu(db_session, user_id)

    reponse = await api_client.get("/jeu/emotes/catalogue")

    assert reponse.status_code == 200, reponse.text
    charge = reponse.json()
    assert [e["code"] for e in charge["emotes"]] == [e.code for e in CATALOGUE]
    assert charge["max_par_fenetre"] == MAX_PAR_FENETRE
    # Le débit est publié pour que l'écran puisse griser la palette AVANT le refus : un joueur de
    # onze ans doit comprendre le rythme, pas le découvrir par une erreur.
    assert charge["intervalle_min_secondes"] > 0


async def test_reglage_defaut_dj10(api_client, db_session):
    user_id, _ = await _register_verify_login(api_client, _email("emote-def"))
    await _acces_jeu(db_session, user_id)

    reponse = await api_client.get("/jeu/emotes/reglages")

    assert reponse.status_code == 200, reponse.text
    assert reponse.json() == {"recevoir_emotes": True}


async def test_couper_puis_retablir(api_client, db_session):
    user_id, csrf = await _register_verify_login(api_client, _email("emote-switch"))
    await _acces_jeu(db_session, user_id)

    coupe = await api_client.patch(
        "/jeu/emotes/reglages", json={"recevoir_emotes": False}, headers=_csrf(csrf)
    )
    assert coupe.status_code == 200, coupe.text
    assert coupe.json()["recevoir_emotes"] is False
    # Mémorisé : une relecture le confirme (c'est le compte qui porte le choix, pas l'onglet).
    relu = await api_client.get("/jeu/emotes/reglages")
    assert relu.json()["recevoir_emotes"] is False

    retabli = await api_client.patch(
        "/jeu/emotes/reglages", json={"recevoir_emotes": True}, headers=_csrf(csrf)
    )
    assert retabli.json()["recevoir_emotes"] is True


async def test_patch_partiel_ne_touche_rien(api_client, db_session):
    user_id, csrf = await _register_verify_login(api_client, _email("emote-partiel"))
    await _acces_jeu(db_session, user_id)
    await api_client.patch(
        "/jeu/emotes/reglages", json={"recevoir_emotes": False}, headers=_csrf(csrf)
    )

    reponse = await api_client.patch("/jeu/emotes/reglages", json={}, headers=_csrf(csrf))

    assert reponse.json()["recevoir_emotes"] is False


async def test_patch_sans_csrf_refuse(api_client, db_session):
    user_id, _ = await _register_verify_login(api_client, _email("emote-csrf"))
    await _acces_jeu(db_session, user_id)

    reponse = await api_client.patch("/jeu/emotes/reglages", json={"recevoir_emotes": False})

    assert reponse.status_code == 403, reponse.text


async def test_sans_droit_de_jeu_404(api_client):
    """D11 : sans droit de jeu, ces routes n'existent pas (404, pas 403)."""
    await _register_verify_login(api_client, _email("emote-nojeu"))

    assert (await api_client.get("/jeu/emotes/reglages")).status_code == 404
    assert (await api_client.get("/jeu/emotes/catalogue")).status_code == 404


async def test_sans_session_401(api_client):
    reponse = await api_client.get("/jeu/emotes/reglages")
    assert reponse.status_code == 401, reponse.text


async def test_acces_croise_le_reglage_de_b_ne_touche_pas_celui_de_a(api_client, db_session):
    """Accès croisé : le réglage est borné au compte de la session, point.

    A coupe ses emotes, B les garde. B n'a **aucun** moyen de lire ou d'écrire le réglage de A :
    ces chemins ne portent pas d'identifiant d'objet, donc B qui interroge « le » réglage obtient
    toujours le sien. C'est la forme que prend le test d'accès croisé exigé par le prompt sur une
    ressource propre au compte.
    """
    email_a = _email("emote-a")
    user_a, csrf_a = await _register_verify_login(api_client, email_a)
    await _acces_jeu(db_session, user_a)
    await api_client.patch(
        "/jeu/emotes/reglages", json={"recevoir_emotes": False}, headers=_csrf(csrf_a)
    )

    email_b = _email("emote-b")
    user_b, csrf_b = await _register_verify_login(api_client, email_b)
    await _acces_jeu(db_session, user_b)

    # B lit SON réglage (le défaut), pas celui de A.
    assert (await api_client.get("/jeu/emotes/reglages")).json()["recevoir_emotes"] is True
    # B écrit : seul le sien change.
    await api_client.patch(
        "/jeu/emotes/reglages", json={"recevoir_emotes": True}, headers=_csrf(csrf_b)
    )

    csrf_a = await _login(api_client, email_a)
    assert (await api_client.get("/jeu/emotes/reglages")).json()["recevoir_emotes"] is False


def test_aucune_route_http_nenvoie_une_emote():
    """Garde structurelle : il n'existe **aucun** chemin HTTP pour envoyer une emote.

    C'est ce qui rend tenable « rien n'est conservé au-delà de la partie » : pas de route veut dire
    pas de file d'attente, donc rien à stocker. Les emotes passent uniquement par le canal temps
    réel (``WS /games/{id}/ws``). Si quelqu'un ajoute un jour un ``POST /jeu/emotes/envoyer`` — ou
    une route de chat —, ce test le dira avant la revue.
    """
    # Le schéma OpenAPI plutôt que `app.routes` : il nomme les chemins réellement servis, sans
    # dépendre de la forme interne des objets de routage de Starlette (qui varie d'une version à
    # l'autre — `_IncludedRouter` n'a pas de `.path`).
    schema = app.openapi()["paths"]
    chemins = {chemin: {m.upper() for m in ops} for chemin, ops in schema.items()}
    emotes_http = {
        chemin: methodes
        for chemin, methodes in chemins.items()
        if chemin.startswith("/jeu/emotes")
    }
    assert set(emotes_http) == {"/jeu/emotes/catalogue", "/jeu/emotes/reglages"}, emotes_http
    assert emotes_http["/jeu/emotes/reglages"] <= {"GET", "PATCH", "HEAD"}, emotes_http
    # Et aucune route « chat » / « message » n'existe nulle part dans l'API du jeu.
    assert not [c for c in chemins if "chat" in c or "message" in c]
