"""Décors d'arène — lot ``j-arene-decors``.

Ce que ces tests tiennent, et aucun ne passerait avant ce lot :

* le réglage **se lit, s'écrit et se révoque** : une clé connue est acceptée, une clé inventée est
  **refusée** (et non repliée en silence sur le défaut, D9), et un ``null`` explicite ramène au
  thème automatique — ce dernier point est le piège de ce lot, parce que ``null`` est pour ce champ
  une *valeur*, pas une absence de réponse ;
* la **garde d'accès au jeu** (D11, 404 partout) et le CSRF, comme toute route du jeu ;
* l'**accès croisé** : le décor d'un compte ne fuit pas dans les réglages d'un autre ;
* la **parité des défauts** code / base : une ligne insérée nue porte bien « aucun décor » ;
* la **parité du vocabulaire** serveur / client : les six clés du module Python sont exactement
  celles du module TypeScript. Le serveur refuse ce qu'il ne connaît pas — si les deux listes
  divergeaient, l'écran proposerait un décor que l'API rejette, ou l'inverse.

On tourne contre la vraie base de test (la CI fait foi) : un ``server_default`` ne se vérifie pas
en mémoire.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from pathlib import Path

import httpx
from sqlalchemy import text

from pbm_api.config import settings
from pbm_api.jeu import confort_service
from pbm_api.jeu.confort import ReglagesConfort
from pbm_api.jeu.decors import DECOR_DEFAUT, DECORS, decor_valide
from pbm_api.models import User
from pbm_api.security.csrf import CSRF_HEADER_NAME

PASSWORD = "correct horse battery staple"

_IDENTITY = {
    "last_name": "Dresseur",
    "birth_date": date(2000, 1, 1),
    "terms_version": "test",
    "terms_accepted_at": datetime(2000, 1, 1),
}


def _email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@example.com"


def _csrf(token: str) -> dict[str, str]:
    return {CSRF_HEADER_NAME: token}


async def _register_verify_login(client: httpx.AsyncClient, email: str) -> tuple[uuid.UUID, str]:
    """Crée un compte, le vérifie et l'ouvre — rend son identifiant et son jeton CSRF."""
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


async def _acces_jeu(db, user_id: uuid.UUID, *, pseudo: str) -> None:
    """Accorde l'accès au jeu (D11) à ce compte."""
    user = await db.get(User, user_id)
    user.game_access = True
    user.pseudo = pseudo
    await db.flush()


# --- Le module pur ------------------------------------------------------------------------------


def test_le_vocabulaire_accepte_les_six_cles_et_l_absence_de_choix():
    for cle in DECORS:
        assert decor_valide(cle), cle
    # `None` est le réglage par défaut (« suis mon deck »), donc une valeur légitime.
    assert decor_valide(None)
    assert not decor_valide("atlantide")
    assert not decor_valide("")


def test_le_decor_par_defaut_fait_partie_du_vocabulaire():
    # Un défaut hors vocabulaire serait refusé par la validation qu'il est censé satisfaire.
    assert DECOR_DEFAUT in DECORS


def test_entre_quatre_et_six_decors():
    assert 4 <= len(DECORS) <= 6


# --- Parité serveur / client --------------------------------------------------------------------


def test_les_cles_du_serveur_sont_celles_du_client():
    """Les six clés du module Python sont exactement celles du module TypeScript, dans l'ordre.

    Le serveur **refuse** une clé inconnue : une divergence ne se verrait donc pas à la lecture,
    seulement le jour où un joueur clique sur un décor et reçoit un 422. L'ordre compte aussi — il
    est publié par l'API (`decors_possibles`) et c'est celui de l'écran de choix.
    """
    ts = (
        Path(__file__).resolve().parents[2] / "web" / "src" / "lib" / "game" / "decors.ts"
    ).read_text(encoding="utf-8")
    # Les entrées de la table TS sont de la forme `  <cle>: {` au premier niveau d'indentation.
    cles_ts = re.findall(r"^  ([a-z][a-z0-9_]*): \{$", ts, re.M)
    assert cles_ts, "aucune clé de décor trouvée dans decors.ts — le format a changé"
    assert list(DECORS) == cles_ts, (
        f"vocabulaires divergents — serveur {list(DECORS)}, client {cles_ts}"
    )


def test_le_defaut_du_serveur_est_celui_du_client():
    ts = (
        Path(__file__).resolve().parents[2] / "web" / "src" / "lib" / "game" / "decors.ts"
    ).read_text(encoding="utf-8")
    trouve = re.search(r'export const DECOR_DEFAUT = "([a-z0-9_]+)"', ts)
    assert trouve, "DECOR_DEFAUT introuvable dans decors.ts"
    assert trouve.group(1) == DECOR_DEFAUT


# --- Les routes ---------------------------------------------------------------------------------


async def test_aucun_decor_choisi_par_defaut(api_client, db_session):
    """Un compte neuf n'a pas de décor imposé : le jeu suit son deck."""
    user_id, _ = await _register_verify_login(api_client, _email("dec"))
    await _acces_jeu(db_session, user_id, pseudo="aymeric")

    reponse = await api_client.get("/jeu/confort/reglages")
    assert reponse.status_code == 200, reponse.text
    corps = reponse.json()
    assert corps["decor"] is None
    # L'écran liste les décors depuis cette liste, il ne les code pas en dur.
    assert corps["decors_possibles"] == list(DECORS)


async def test_choisir_un_decor_puis_revenir_a_l_automatique(api_client, db_session):
    """Le cas qui justifie `decor_fourni` : `null` doit pouvoir **révoquer** un choix."""
    user_id, csrf = await _register_verify_login(api_client, _email("dec"))
    await _acces_jeu(db_session, user_id, pseudo="aymeric")

    r1 = await api_client.patch(
        "/jeu/confort/reglages", json={"decor": "lagon"}, headers=_csrf(csrf)
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["decor"] == "lagon"

    # `null` explicite = « reviens au thème automatique ». Sans la distinction portée par
    # `decor_fourni`, ce PATCH serait indiscernable d'un PATCH qui ne parle pas du décor, et le
    # joueur ne pourrait plus jamais revenir à l'automatique.
    r2 = await api_client.patch(
        "/jeu/confort/reglages", json={"decor": None}, headers=_csrf(csrf)
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["decor"] is None


async def test_un_patch_qui_ne_parle_pas_du_decor_ne_l_efface_pas(api_client, db_session):
    """L'autre moitié de la même règle : champ absent = réglage inchangé."""
    user_id, csrf = await _register_verify_login(api_client, _email("dec"))
    await _acces_jeu(db_session, user_id, pseudo="aymeric")

    await api_client.patch("/jeu/confort/reglages", json={"decor": "temple"}, headers=_csrf(csrf))
    r = await api_client.patch(
        "/jeu/confort/reglages", json={"animations": "reduites"}, headers=_csrf(csrf)
    )
    assert r.status_code == 200, r.text
    assert r.json()["decor"] == "temple", "le décor a été effacé par un réglage voisin"
    assert r.json()["animations"] == "reduites"


async def test_un_decor_inconnu_est_refuse(api_client, db_session):
    """D9 : on refuse plutôt que de replier en silence.

    Un décor qui n'existe pas donnerait un fond nu — le joueur croirait avoir choisi quelque chose.
    """
    user_id, csrf = await _register_verify_login(api_client, _email("dec"))
    await _acces_jeu(db_session, user_id, pseudo="aymeric")

    r = await api_client.patch(
        "/jeu/confort/reglages", json={"decor": "atlantide"}, headers=_csrf(csrf)
    )
    assert r.status_code == 422, r.text
    # Et rien n'a été écrit au passage.
    assert (await api_client.get("/jeu/confort/reglages")).json()["decor"] is None


async def test_choisir_un_decor_exige_le_csrf(api_client, db_session):
    user_id, _ = await _register_verify_login(api_client, _email("dec"))
    await _acces_jeu(db_session, user_id, pseudo="aymeric")
    r = await api_client.patch("/jeu/confort/reglages", json={"decor": "orage"})
    assert r.status_code == 403, r.text


async def test_sans_acces_au_jeu_le_decor_n_existe_pas(api_client, db_session):
    """D11 : le jeu n'existe pas pour un compte non invité — son décor non plus."""
    _, csrf = await _register_verify_login(api_client, _email("dec-noaccess"))
    assert (await api_client.get("/jeu/confort/reglages")).status_code == 404
    r = await api_client.patch(
        "/jeu/confort/reglages", json={"decor": "caldeira"}, headers=_csrf(csrf)
    )
    assert r.status_code == 404, r.text


async def test_mon_decor_n_est_pas_celui_du_voisin(api_client, db_session):
    """Accès croisé : le décor de A ne se lit pas depuis la session de B."""
    id_a, csrf_a = await _register_verify_login(api_client, _email("dec-a"))
    await _acces_jeu(db_session, id_a, pseudo="joueur-a")
    r = await api_client.patch(
        "/jeu/confort/reglages", json={"decor": "faille"}, headers=_csrf(csrf_a)
    )
    assert r.status_code == 200, r.text

    id_b, _ = await _register_verify_login(api_client, _email("dec-b"))
    await _acces_jeu(db_session, id_b, pseudo="joueur-b")
    assert (await api_client.get("/jeu/confort/reglages")).json()["decor"] is None


# --- Parité des défauts code / base -------------------------------------------------------------


async def test_une_ligne_nue_ne_porte_aucun_decor(db_session):
    """La colonne est nullable **sans** `server_default` : l'automatique reste ainsi joignable.

    Si la migration avait posé `DEFAULT 'arene'`, tous les comptes existants se retrouveraient
    avec un choix explicite qu'ils n'ont jamais fait — et le thème automatique serait inatteignable
    sans un second geste, en silence.
    """
    user = User(email=_email("dec-parite"), password_hash="x", **_IDENTITY)
    db_session.add(user)
    await db_session.flush()
    await db_session.execute(
        text("INSERT INTO jeu_confort_reglages (user_id) VALUES (:uid)"), {"uid": user.id}
    )
    await db_session.flush()
    depuis_base = await confort_service.charger_reglages(db_session, user.id)
    assert depuis_base.decor is None
    assert depuis_base == ReglagesConfort()


async def test_le_service_refuse_un_decor_inconnu_avant_toute_ecriture(db_session):
    """La validation est dans le service, pas seulement dans le routeur.

    Un futur appelant (script d'import, migration de données) passe par là sans HTTP : la garde
    doit vivre au niveau où l'écriture se fait.
    """
    user = User(email=_email("dec-serv"), password_hash="x", **_IDENTITY)
    db_session.add(user)
    await db_session.flush()

    try:
        await confort_service.enregistrer_reglages(
            db_session, user.id, decor="atlantide", decor_fourni=True
        )
    except confort_service.ConfortValeurInvalide as exc:
        assert "atlantide" in str(exc)
    else:  # pragma: no cover - le test échoue si l'exception n'est pas levée
        raise AssertionError("un décor inconnu a été accepté par le service")

    # Rien n'a été écrit : pas de ligne créée au passage.
    assert (await confort_service.charger_reglages(db_session, user.id)).decor is None
