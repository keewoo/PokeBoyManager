"""Confort et accessibilité du jeu — lot ``j-accessibilite-jeu``.

Ce que ces tests tiennent, et aucun d'eux ne passerait avant ce lot :

* les **réglages** : défauts publiés sans ligne en base, modification partielle, vocabulaire
  refusé, CSRF exigé, et la garde d'accès au jeu (D11, 404 partout) ;
* la **parité des défauts** entre le code pur et les ``server_default`` de la table — deux jeux de
  défauts qui divergent, c'est un réglage qui change de sens selon qu'une ligne existe ou non ;
* le **temps rallongé** (DJ4) de bout en bout : une partie lancée par un joueur qui l'a demandé
  porte des horloges **doublées** dans sa colonne ``games.horloges``, et il suffit **qu'un seul**
  des deux joueurs l'ait demandé. C'est le critère « mode temps rallongé branché sur les
  horloges » ;
* l'**isolement** : le réglage d'un compte ne fuit pas dans la partie d'un autre.

On tourne contre la vraie base de test (la CI fait foi) : les ``server_default`` ne se vérifient
pas en mémoire.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime

import httpx
from pbm_game.horloges.modele import EtatHorloges
from sqlalchemy import text

from pbm_api.config import settings
from pbm_api.games import horloges as adapt
from pbm_api.games.service import creer_partie
from pbm_api.jeu import confort_service
from pbm_api.jeu.confort import (
    ANIMATIONS_COMPLETES,
    ANIMATIONS_REDUITES,
    FACTEUR_TEMPS_RALLONGE,
    TAILLE_NORMALE,
    ReglagesConfort,
    rallonger,
    temps_rallonge_partie,
)
from pbm_api.models import Card, Deck, DeckCard, Set, User
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
    user = await db.get(User, user_id)
    user.game_access = True
    user.pseudo = pseudo
    await db.flush()


# --- Le module pur ------------------------------------------------------------------------------


def test_rallonger_double_les_trois_durees_et_pas_les_marges():
    """Les deux marges compensent le réseau et une déconnexion, pas la lenteur de réflexion."""
    base = adapt.config_horloges(settings)
    double = rallonger(base, True)
    assert double.par_tour_s == base.par_tour_s * FACTEUR_TEMPS_RALLONGE
    assert double.par_joueur_s == base.par_joueur_s * FACTEUR_TEMPS_RALLONGE
    assert double.par_decision_s == base.par_decision_s * FACTEUR_TEMPS_RALLONGE
    assert double.tolerance_reseau_s == base.tolerance_reseau_s
    assert double.pause_deconnexion_s == base.pause_deconnexion_s


def test_rallonger_inactif_ne_touche_a_rien():
    base = adapt.config_horloges(settings)
    assert rallonger(base, False) == base


def test_un_seul_joueur_suffit_a_rallonger_la_partie():
    """Dissymétrie assumée : le jeu penche du côté de qui a besoin de plus de temps."""
    lent = ReglagesConfort(temps_rallonge=True)
    rapide = ReglagesConfort()
    assert temps_rallonge_partie(rapide, lent) is True
    assert temps_rallonge_partie(lent, rapide) is True
    assert temps_rallonge_partie(rapide, rapide) is False


def test_config_horloges_rallongee_par_le_drapeau():
    """L'adaptateur relaie le drapeau — et son défaut laisse l'appel historique intact."""
    normal = adapt.config_horloges(settings)
    rallongee = adapt.config_horloges(settings, temps_rallonge=True)
    assert rallongee.par_tour_s == normal.par_tour_s * FACTEUR_TEMPS_RALLONGE


# --- Les routes ---------------------------------------------------------------------------------


async def test_les_defauts_sont_publies_sans_ligne_en_base(api_client, db_session):
    """Un compte qui n'a jamais ouvert ces réglages joue animé, en texte normal, au temps DJ4."""
    user_id, _ = await _register_verify_login(api_client, _email("cf"))
    await _acces_jeu(db_session, user_id, pseudo="aymeric")

    reponse = await api_client.get("/jeu/confort/reglages")
    assert reponse.status_code == 200, reponse.text
    corps = reponse.json()
    assert corps["animations"] == ANIMATIONS_COMPLETES
    assert corps["taille_texte"] == TAILLE_NORMALE
    assert corps["temps_rallonge"] is False
    assert sorted(corps["animations_possibles"]) == ["completes", "reduites"]
    assert sorted(corps["tailles_possibles"]) == ["grande", "normale", "tres_grande"]
    # Le facteur est publié : un joueur qui active le temps rallongé lit le chiffre.
    assert corps["facteur_temps_rallonge"] == FACTEUR_TEMPS_RALLONGE


async def test_modification_partielle_n_ecrase_pas_les_autres(api_client, db_session):
    user_id, csrf = await _register_verify_login(api_client, _email("cf"))
    await _acces_jeu(db_session, user_id, pseudo="aymeric")

    r1 = await api_client.patch(
        "/jeu/confort/reglages", json={"animations": ANIMATIONS_REDUITES}, headers=_csrf(csrf)
    )
    assert r1.status_code == 200, r1.text
    r2 = await api_client.patch(
        "/jeu/confort/reglages", json={"temps_rallonge": True}, headers=_csrf(csrf)
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["animations"] == ANIMATIONS_REDUITES, "le premier réglage a été écrasé"
    assert r2.json()["temps_rallonge"] is True
    assert r2.json()["taille_texte"] == TAILLE_NORMALE


async def test_une_valeur_hors_vocabulaire_est_refusee(api_client, db_session):
    """Un réglage qui ne règle rien est un mensonge : on refuse, on ne retombe pas sur le défaut."""
    user_id, csrf = await _register_verify_login(api_client, _email("cf"))
    await _acces_jeu(db_session, user_id, pseudo="aymeric")
    for charge in ({"animations": "clignote"}, {"taille_texte": "enorme"}):
        reponse = await api_client.patch(
            "/jeu/confort/reglages", json=charge, headers=_csrf(csrf)
        )
        assert reponse.status_code == 422, reponse.text
    # Et rien n'a été écrit au passage.
    assert (await api_client.get("/jeu/confort/reglages")).json()["animations"] == (
        ANIMATIONS_COMPLETES
    )


async def test_modifier_exige_le_csrf(api_client, db_session):
    user_id, _ = await _register_verify_login(api_client, _email("cf"))
    await _acces_jeu(db_session, user_id, pseudo="aymeric")
    reponse = await api_client.patch(
        "/jeu/confort/reglages", json={"animations": ANIMATIONS_REDUITES}
    )
    assert reponse.status_code == 403, reponse.text


async def test_sans_acces_au_jeu_404_partout(api_client, db_session):
    """D11 : le jeu n'existe pas pour un compte non invité — ses réglages de confort non plus."""
    _, csrf = await _register_verify_login(api_client, _email("cf-noaccess"))
    assert (await api_client.get("/jeu/confort/reglages")).status_code == 404
    r = await api_client.patch(
        "/jeu/confort/reglages", json={"animations": ANIMATIONS_REDUITES}, headers=_csrf(csrf)
    )
    assert r.status_code == 404, r.text


async def test_mes_reglages_ne_sont_pas_ceux_du_voisin(api_client, db_session):
    """Accès croisé : deux comptes, deux lignes — B ne lit jamais le réglage de A."""
    id_a, csrf_a = await _register_verify_login(api_client, _email("cf-a"))
    await _acces_jeu(db_session, id_a, pseudo="joueur-a")
    r = await api_client.patch(
        "/jeu/confort/reglages",
        json={"animations": ANIMATIONS_REDUITES, "temps_rallonge": True},
        headers=_csrf(csrf_a),
    )
    assert r.status_code == 200, r.text

    id_b, _ = await _register_verify_login(api_client, _email("cf-b"))
    await _acces_jeu(db_session, id_b, pseudo="joueur-b")
    corps = (await api_client.get("/jeu/confort/reglages")).json()
    assert corps["animations"] == ANIMATIONS_COMPLETES
    assert corps["temps_rallonge"] is False


# --- Parité des défauts code / base -------------------------------------------------------------


async def test_les_defauts_du_code_et_de_la_table_sont_les_memes(db_session):
    """Une ligne insérée **sans aucun champ** doit porter exactement les défauts du code.

    Sans cette garde, un compte qui a touché un seul réglage se retrouverait avec d'autres valeurs
    qu'un compte qui n'y a jamais touché — pour les mêmes réglages affichés.
    """
    user = User(email=_email("cf-parite"), password_hash="x", **_IDENTITY)
    db_session.add(user)
    await db_session.flush()
    await db_session.execute(
        text("INSERT INTO jeu_confort_reglages (user_id) VALUES (:uid)"), {"uid": user.id}
    )
    await db_session.flush()
    depuis_base = await confort_service.charger_reglages(db_session, user.id)
    assert depuis_base == ReglagesConfort()


# --- Le temps rallongé, de bout en bout ---------------------------------------------------------


async def _make_card(db, *, name: str) -> Card:
    set_row = Set(code=f"cf-{uuid.uuid4().hex[:8]}", name="Set confort", series="Série test")
    db.add(set_row)
    await db.flush()
    card = Card(
        set_id=set_row.id,
        number=str(uuid.uuid4().int % 1000),
        name=name,
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
    return card


async def _make_user(db) -> User:
    user = User(email=_email("cf-j"), password_hash="x", **_IDENTITY)
    db.add(user)
    await db.flush()
    return user


async def _make_deck(db, user: User, card: Card, qty: int) -> Deck:
    deck = Deck(user_id=user.id, name="Deck confort")
    db.add(deck)
    await db.flush()
    db.add(DeckCard(deck_id=deck.id, card_id=card.id, quantity=qty))
    await db.flush()
    return deck


async def _partie(db, *, rallonge_premier: bool = False):
    """Deux comptes neufs, deux decks jouables, une partie.

    ``rallonge_premier`` pose le réglage sur le **joueur A de cette partie** avant sa création :
    c'est le seul moment où il est lu. Le poser après ne change rien, et c'est précisément ce qu'un
    des tests vérifie.
    """
    user_a = await _make_user(db)
    user_b = await _make_user(db)
    deck_a = await _make_deck(db, user_a, await _make_card(db, name="Carpanaud"), 10)
    deck_b = await _make_deck(db, user_b, await _make_card(db, name="Tiplouf"), 10)
    if rallonge_premier:
        await confort_service.enregistrer_reglages(db, user_a.id, temps_rallonge=True)
    game = await creer_partie(
        db, joueur_a=(user_a.id, deck_a.id), joueur_b=(user_b.id, deck_b.id)
    )
    return game, user_a, user_b


async def test_une_partie_ordinaire_garde_les_horloges_dj4(db_session):
    game, _, _ = await _partie(db_session)
    h = EtatHorloges.depuis_json(game.horloges)
    assert set(h.budgets_s.values()) == {settings.horloge_par_joueur_s}
    assert h.config.par_tour_s == settings.horloge_par_tour_s


async def test_le_temps_rallonge_du_premier_joueur_double_les_horloges(db_session):
    """Le critère du lot : le réglage est **branché** sur les horloges, pas seulement stocké."""
    game, _, _ = await _partie(db_session, rallonge_premier=True)
    h = EtatHorloges.depuis_json(game.horloges)
    assert h.config.par_tour_s == settings.horloge_par_tour_s * FACTEUR_TEMPS_RALLONGE
    assert h.config.par_decision_s == settings.horloge_par_decision_s * FACTEUR_TEMPS_RALLONGE
    assert set(h.budgets_s.values()) == {
        settings.horloge_par_joueur_s * FACTEUR_TEMPS_RALLONGE
    }


async def test_le_temps_rallonge_du_second_joueur_compte_aussi(db_session):
    """Celui qui a besoin de temps n'est pas toujours celui qui lance la partie."""
    user_a = await _make_user(db_session)
    user_b = await _make_user(db_session)
    carte_a = await _make_card(db_session, name="Salamèche")
    carte_b = await _make_card(db_session, name="Carapuce")
    deck_a = await _make_deck(db_session, user_a, carte_a, 10)
    deck_b = await _make_deck(db_session, user_b, carte_b, 10)
    await confort_service.enregistrer_reglages(db_session, user_b.id, temps_rallonge=True)
    game = await creer_partie(
        db_session, joueur_a=(user_a.id, deck_a.id), joueur_b=(user_b.id, deck_b.id)
    )
    h = EtatHorloges.depuis_json(game.horloges)
    assert h.config.par_tour_s == settings.horloge_par_tour_s * FACTEUR_TEMPS_RALLONGE


async def test_un_reglage_pose_apres_la_creation_ne_change_pas_la_partie(db_session):
    """Une partie fige ses horloges à sa création : le réglage vaut pour la partie SUIVANTE.

    C'est ce que l'écran promet au joueur (« ça vaut pour tes prochaines parties ») ; si le code en
    décidait autrement, la promesse serait fausse dans un sens ou dans l'autre.
    """
    game, user_a, _ = await _partie(db_session)
    await confort_service.enregistrer_reglages(db_session, user_a.id, temps_rallonge=True)
    await db_session.refresh(game)
    h = EtatHorloges.depuis_json(game.horloges)
    assert h.config.par_tour_s == settings.horloge_par_tour_s


async def test_le_reglage_d_un_tiers_ne_rallonge_pas_ma_partie(db_session):
    """Isolement : le confort est lu pour **les deux joueurs de cette partie**, et eux seuls."""
    tiers = await _make_user(db_session)
    await confort_service.enregistrer_reglages(db_session, tiers.id, temps_rallonge=True)
    game, _, _ = await _partie(db_session)
    h = EtatHorloges.depuis_json(game.horloges)
    assert h.config.par_tour_s == settings.horloge_par_tour_s
