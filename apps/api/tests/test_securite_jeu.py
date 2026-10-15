"""Revue de sécurité du jeu — les correctifs côté API, lot ``j-securite-jeu``.

Ce fichier prouve les trois critères d'acceptation que la revue a trouvés **non tenus**, plus la
porte de refus des scripts fuitants. Les deux fuites du moteur et le balayage génératif des scripts
sont prouvés côté `game` (``apps/game/tests/test_securite_scripts_fuite.py``, job `game` de la CI).

Ce qui était **déjà** couvert, et qu'on ne redouble pas (on le cite, c'est le travail de la revue) :

* vue projetée et accès croisé sur ``/state`` et ``/actions`` → ``test_games_projection`` ;
* coup illégal refusé, refus tracé, rafale qui alerte → ``test_games_projection`` ;
* message de type inconnu sur le canal, ping/pong → ``test_games_temps_reel`` ;
* défense anti-CSWSH (``origine_autorisee``) → ``test_games_ws_routes`` ;
* partie complète HTTP + WS sans fuite ni 500 → ``test_games_http_ws_partie_complete``.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import date, datetime

import httpx
import pytest
from sqlalchemy import func, select

from pbm_api.config import settings
from pbm_api.games.errors import ConflitNumero
from pbm_api.games.service import appliquer_action, creer_partie
from pbm_api.jeu.scripts.chargeur import refus_scripts_cartes
from pbm_api.jeu.scripts.depot import enregistrer_script
from pbm_api.models import (
    SCRIPT_STATUT_SCRIPTE,
    Card,
    Deck,
    DeckCard,
    Game,
    GameEvent,
    GamePlayer,
    GameSnapshot,
    Set,
    User,
)
from pbm_api.security.csrf import CSRF_HEADER_NAME

PASSWORD = "correct horse battery staple"

_IDENTITY = {
    "last_name": "Dresseur",
    "birth_date": date(2000, 1, 1),
    "terms_version": "test",
    "terms_accepted_at": datetime(2000, 1, 1),
}
_IDENTITY_FIELDS = {"last_name": "Dresseur", "birth_date": "2000-01-01", "accept_terms": True}


def _email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@example.com"


def _csrf(token: str) -> dict[str, str]:
    return {CSRF_HEADER_NAME: token}


async def _register_verify_login(client: httpx.AsyncClient, email: str) -> tuple[uuid.UUID, str]:
    """Inscrit, vérifie et connecte ; renvoie ``(user_id, jeton CSRF)``."""
    response = await client.post(
        "/auth/register", json={"email": email, "password": PASSWORD, **_IDENTITY_FIELDS}
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


async def _deck_jouable(db, user_id: uuid.UUID) -> uuid.UUID:
    set_row = Set(code=f"sj-{uuid.uuid4().hex[:8]}", name="Set jeu", series="Série test")
    db.add(set_row)
    await db.flush()
    card = Card(
        set_id=set_row.id,
        number=str(uuid.uuid4().int % 100000),
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


async def _partie_a_vs_b(api_client, db_session):
    """Deux joueurs vérifiés avec accès au jeu, et une partie entre eux. A reste connecté."""
    email_a, email_b = _email("sj-a"), _email("sj-b")
    a_id, _ = await _register_verify_login(api_client, email_a)
    deck_a = await _deck_jouable(db_session, a_id)
    b_id, _ = await _register_verify_login(api_client, email_b)
    deck_b = await _deck_jouable(db_session, b_id)
    game = await creer_partie(db_session, joueur_a=(a_id, deck_a), joueur_b=(b_id, deck_b))
    for uid in (a_id, b_id):
        u = await db_session.get(User, uid)
        u.game_access = True
    await db_session.flush()
    csrf_a = await _login(api_client, email_a)
    return {
        "email_a": email_a,
        "a_id": a_id,
        "csrf_a": csrf_a,
        "email_b": email_b,
        "b_id": b_id,
        "game": game,
    }


# ===============================================================================================
# Critère n°2 — « toute action sur une partie étrangère est refusée ET JOURNALISÉE »
# ===============================================================================================
async def test_action_sur_une_partie_etrangere_est_journalisee(api_client, db_session, caplog):
    """Un intrus reçoit 404 (déjà couvert) **et** le serveur en garde une trace (ce qui manquait).

    Le refus était parfaitement étanche et parfaitement muet : ``_game_pour_participant`` levait
    sans une ligne de journal. Un canal permanent entre deux comptes, dont celui d'un mineur, doit
    laisser une trace de qui a frappé à la porte d'une partie qui n'est pas la sienne — sans quoi
    une énumération d'identifiants ne se voit nulle part.
    """
    ctx = await _partie_a_vs_b(api_client, db_session)
    intrus_id, csrf_intrus = await _register_verify_login(api_client, _email("sj-intrus"))
    intrus = await db_session.get(User, intrus_id)
    intrus.game_access = True  # il a le droit de jouer, il ne joue pas CETTE partie
    await db_session.flush()

    with caplog.at_level(logging.WARNING, logger="pbm_api.games.service"):
        reponse = await api_client.post(
            f"/games/{ctx['game'].id}/actions",
            json={"type": "piocher", "numero_attendu": 0},
            headers=_csrf(csrf_intrus),
        )
    assert reponse.status_code == 404, reponse.text  # toujours 404, jamais 403 : aucune fuite

    traces = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("ÉTRANGÈRE" in t for t in traces), traces
    assert any(str(ctx["game"].id) in t and str(intrus_id) in t for t in traces), traces


async def test_une_partie_inconnue_ne_crie_pas_dans_le_journal(api_client, db_session, caplog):
    """Un identifiant périmé se trace en INFO, pas en WARNING — sinon personne ne lit le journal.

    C'est la moitié qui rend l'autre utile : si un signet mort produisait la même alerte qu'une
    tentative d'accès croisé, la trace d'accès croisé serait noyée dans le bruit.
    """
    _uid, csrf = await _register_verify_login(api_client, _email("sj-inconnue"))
    user = await db_session.get(User, _uid)
    user.game_access = True
    await db_session.flush()

    inexistante = uuid.uuid4()
    with caplog.at_level(logging.INFO, logger="pbm_api.games.service"):
        reponse = await api_client.get(f"/games/{inexistante}/state")
    assert reponse.status_code == 404

    pertinents = [r for r in caplog.records if str(inexistante) in r.getMessage()]
    assert pertinents, "une partie inconnue doit laisser une trace, même discrète"
    assert all(r.levelno < logging.WARNING for r in pertinents), [
        (r.levelname, r.getMessage()) for r in pertinents
    ]


# ===============================================================================================
# Jeton CSRF — les trois mutations du jeu qui en étaient dépourvues
# ===============================================================================================
@pytest.mark.parametrize(
    ("chemin", "corps"),
    [
        ("actions", {"type": "piocher", "numero_attendu": 0}),
        ("abandon", None),
        ("conseil", None),
    ],
)
async def test_les_mutations_du_jeu_exigent_le_jeton_csrf(
    api_client, db_session, chemin: str, corps: dict | None
):
    """``/actions``, ``/abandon`` et ``/conseil`` écrivaient **sans** jeton CSRF.

    Toutes les autres mutations du jeu l'exigeaient déjà (revanche, partages de replay, réglages,
    file d'attente, invitations, lancement) ; ces trois-là — dont celle qui joue les coups — ne le
    faisaient pas, et rien ne documentait pourquoi. La porte est fermée par cohérence et par
    défense en profondeur : le CORS ne laisse passer que l'origine du front, mais une seule ligne
    de configuration le sépare d'un trou, et la session vit dans un cookie.
    """
    ctx = await _partie_a_vs_b(api_client, db_session)
    reponse = await api_client.post(f"/games/{ctx['game'].id}/{chemin}", json=corps)
    assert reponse.status_code == 403, reponse.text


async def test_jouer_un_coup_avec_le_jeton_csrf_reste_possible(api_client, db_session):
    """Le contre-test : avec le jeton, le coup passe — sinon on aurait fermé le jeu."""
    ctx = await _partie_a_vs_b(api_client, db_session)
    reponse = await api_client.post(
        f"/games/{ctx['game'].id}/actions",
        json={"type": "piocher", "numero_attendu": 0},
        headers=_csrf(ctx["csrf_a"]),
    )
    assert reponse.status_code == 200, reponse.text


# ===============================================================================================
# Critère n°3 — « la suppression d'un compte efface ses parties et ses journaux »
# ===============================================================================================
async def test_supprimer_son_compte_efface_ses_parties_et_leurs_journaux(api_client, db_session):
    """Les parties d'un compte supprimé **restaient en base**, son `user_id` en clair dedans.

    `games` n'a aucune clé étrangère vers `users` : la cascade du `DELETE FROM users` ne la touchait
    pas. Restaient donc `games.etat_initial` (les identifiants de joueur **sont** les `user_id`),
    `game_events.auteur` (un `str(user_id)` par coup) et `game_snapshots.etat`. Et une partie
    `en_cours` n'est jamais ramassée par la purge d'ancienneté : elle serait restée indéfiniment.
    """
    ctx = await _partie_a_vs_b(api_client, db_session)
    game_id = ctx["game"].id
    # Un coup joué : il y a donc un journal à effacer, pas seulement un en-tête de partie.
    joue = await api_client.post(
        f"/games/{game_id}/actions",
        json={"type": "piocher", "numero_attendu": 0},
        headers=_csrf(ctx["csrf_a"]),
    )
    assert joue.status_code == 200, joue.text
    await db_session.commit()

    evenements_avant = (
        await db_session.execute(
            select(func.count()).select_from(GameEvent).where(GameEvent.game_id == game_id)
        )
    ).scalar_one()
    assert evenements_avant > 0, "sans journal, ce test ne prouverait rien"

    csrf_a = await _login(api_client, ctx["email_a"])
    suppression = await api_client.request(
        "DELETE", "/me", json={"password": PASSWORD}, headers=_csrf(csrf_a)
    )
    assert suppression.status_code == 204, suppression.text

    db_session.expire_all()
    assert await db_session.get(User, ctx["a_id"]) is None
    assert await db_session.get(Game, game_id) is None
    for modele, colonne in (
        (GameEvent, GameEvent.game_id),
        (GameSnapshot, GameSnapshot.game_id),
        (GamePlayer, GamePlayer.game_id),
    ):
        reste = (
            await db_session.execute(
                select(func.count()).select_from(modele).where(colonne == game_id)
            )
        ).scalar_one()
        assert reste == 0, f"{modele.__tablename__} garde {reste} ligne(s) de la partie effacée"


async def test_la_suppression_ne_touche_pas_les_parties_d_un_autre_compte(api_client, db_session):
    """Effacer un compte n'efface que **ses** parties : celle de deux autres joueurs survit.

    Le pendant obligatoire du test précédent : une suppression trop large serait une perte de
    données, pas une mise en conformité.
    """
    victime = await _partie_a_vs_b(api_client, db_session)
    temoin = await _partie_a_vs_b(api_client, db_session)
    # Les identifiants sont relevés **avant** `expire_all()` : lire `.id` sur un objet ORM expiré
    # déclencherait une entrée/sortie paresseuse hors du contexte asynchrone (`MissingGreenlet`).
    game_victime, game_temoin = victime["game"].id, temoin["game"].id
    await db_session.commit()

    csrf = await _login(api_client, victime["email_a"])
    suppression = await api_client.request(
        "DELETE", "/me", json={"password": PASSWORD}, headers=_csrf(csrf)
    )
    assert suppression.status_code == 204, suppression.text

    db_session.expire_all()
    assert await db_session.get(Game, game_victime) is None
    assert await db_session.get(Game, game_temoin) is not None
    assert await db_session.get(User, temoin["a_id"]) is not None
    assert await db_session.get(User, victime["b_id"]) is not None  # l'adversaire reste


# ===============================================================================================
# Critère n°1 (côté API) — un script qui fuiterait est refusé AVANT la partie
# ===============================================================================================
async def _carte_avec_effet(db, texte: str) -> Card:
    set_row = Set(code=f"sj-{uuid.uuid4().hex[:8]}", name="Set audit", series="Série test")
    db.add(set_row)
    await db.flush()
    card = Card(
        set_id=set_row.id,
        number=str(uuid.uuid4().int % 100000),
        name="Pokémon à effet",
        supertype="Pokémon",
        energy_type="water",
        element_type="water",
        hp=60,
        stage="Base",
        retreat_cost=1,
        prize_marker="ordinaire",
        attacks=[{"name": "Fouille", "cost": ["water"], "damage": "10", "effect": texte}],
    )
    db.add(card)
    await db.flush()
    return card


async def test_un_script_qui_fuiterait_rend_la_carte_refusee(db_session):
    """Un script **valide** mais fuitant ne se joue pas : la carte est refusée, la raison nommée.

    « Cherchez une carte dans la main de votre adversaire » se charge sans problème (le schéma
    l'autorise) et s'exécuterait très bien — en publiant les ``ref`` de cartes que personne n'a le
    droit de montrer. On refuse donc la carte à la construction du deck, comme un effet non
    implémenté (D9), plutôt que de la jouer en fuitant. C'est l'audit de confidentialité branché
    sur la porte qui existait déjà.
    """
    texte = "Cherchez une carte dans la main de votre adversaire et ajoutez-la à votre main."
    card = await _carte_avec_effet(db_session, texte)
    await enregistrer_script(
        db_session,
        source_text=texte,
        statut=SCRIPT_STATUT_SCRIPTE,
        dsl_version=1,
        script={
            "version": 1,
            "effets": [
                {
                    "op": "chercher",
                    "nombre": 1,
                    "cible": {"zone": "main", "proprietaire": "adversaire"},
                }
            ],
        },
        author="test_securite_jeu",
        notes="script fuitant, posé exprès pour prouver le refus",
    )
    await db_session.flush()

    refus = await refus_scripts_cartes(db_session, [card])
    assert refus, "un script fuitant doit bloquer sa carte"
    raisons = " ".join(raison for _libelle, raison in refus)
    assert "confidentialité" in raisons
    assert "chercher" in raisons and "main" in raisons


async def test_un_script_de_recherche_dans_son_deck_reste_jouable(db_session):
    """Le contre-test : « cherchez dans VOTRE deck, montrez-la » reste parfaitement jouable.

    C'est la carte de recherche la plus banale du jeu (type Super Ball) : si l'audit la refusait,
    il aurait fermé le jeu au lieu d'une fuite.
    """
    texte = "Cherchez un Pokémon dans votre deck, montrez-le et ajoutez-le à votre main."
    card = await _carte_avec_effet(db_session, texte)
    await enregistrer_script(
        db_session,
        source_text=texte,
        statut=SCRIPT_STATUT_SCRIPTE,
        dsl_version=1,
        script={
            "version": 1,
            "effets": [
                {
                    "op": "chercher",
                    "nombre": 1,
                    "cible": {"zone": "pioche", "proprietaire": "moi", "categorie": "pokemon"},
                },
                {"op": "melanger"},
            ],
        },
        author="test_securite_jeu",
        notes="recherche légitime dans son propre deck (R-5.2)",
    )
    await db_session.flush()

    assert await refus_scripts_cartes(db_session, [card]) == []


# ===============================================================================================
# Le canal : charge utile hostile sur la route de repli
# ===============================================================================================
async def test_une_charge_utile_hostile_est_refusee_sans_500(api_client, db_session):
    """Charges utiles hostiles : refus motivé (4xx), jamais une 500, jamais un secret rendu.

    ``ActionIn.params`` est un ``dict`` non contraint, passé tel quel au moteur : c'est voulu (le
    moteur est seul juge de la légalité), mais il faut prouver qu'un client hostile n'en tire qu'un
    refus. Mission 2 du lot : « éprouver le canal — message malformé ».
    """
    ctx = await _partie_a_vs_b(api_client, db_session)
    game_id = ctx["game"].id
    graine = ctx["game"].graine
    await db_session.commit()  # la partie existe vraiment : les incidents consignés ont leur FK
    a_refuser = [
        {"type": "../../admin", "numero_attendu": 0},
        # ⚠️ `-1` **faisait tomber la route en 500** (`NoResultFound` non rattrapé dans le chemin
        # de rejeu idempotent) : un seul entier négatif suffisait. Corrigé en deux couches —
        # borne `ge=0` au schéma, refus nommé au service.
        {"type": "piocher", "numero_attendu": -1},
        {"type": "piocher", "numero_attendu": 10**12},
        {"type": "x" * 5000, "numero_attendu": 0},
        {"type": "piocher"},  # champ obligatoire absent
        {"type": None, "numero_attendu": 0},
        {"type": "piocher", "numero_attendu": "zéro"},
        {"type": "piocher", "numero_attendu": 0, "params": "pas-un-objet"},
    ]
    for corps in a_refuser:
        reponse = await api_client.post(
            f"/games/{game_id}/actions", json=corps, headers=_csrf(ctx["csrf_a"])
        )
        assert 400 <= reponse.status_code < 500, (
            f"{corps} → {reponse.status_code} {reponse.text}"
        )
        # Aucun secret dans le message d'erreur rendu au client.
        assert graine not in json.dumps(reponse.json())

    # Et aucun de ces refus n'a avancé la partie : elle en est toujours au numéro 0.
    detail = await api_client.get(f"/games/{game_id}")
    assert detail.json()["current_numero"] == 0


async def test_des_params_inconnus_sont_ignores_et_non_interpretes(api_client, db_session):
    """Constat **documenté**, pas une faille : un ``params`` inconnu est ignoré, jamais interprété.

    Un coup dont les ``params`` portent des clés que l'action ne lit pas (``{"$ne": null}``,
    ``"../../etc/passwd"``) est **accepté** : `piocher` n'a pas de paramètre, et le dictionnaire
    est simplement inutilisé. Rien n'est interprété — il n'y a ni requête construite par
    concaténation ni chemin de fichier dérivé d'un ``params`` — donc ni injection ni traversée.

    Ce que ce test fixe, c'est la **frontière** : le contenu est inerte côté moteur, et il est
    journalisé tel quel dans ``game_events.action``. La conséquence (un client peut écrire du JSON
    arbitraire dans le journal de **sa** partie, sans plafond de taille) est nommée comme risque
    résiduel dans `docs/jeu/SECURITE-JEU.md` — la borner demande de choisir un chiffre, ce qui
    relève du lot de charge, pas d'une revue.
    """
    ctx = await _partie_a_vs_b(api_client, db_session)
    game_id = ctx["game"].id
    await db_session.commit()
    reponse = await api_client.post(
        f"/games/{game_id}/actions",
        json={
            "type": "piocher",
            "numero_attendu": 0,
            "params": {"cible": {"$ne": None}, "chemin": "../../etc/passwd"},
        },
        headers=_csrf(ctx["csrf_a"]),
    )
    assert reponse.status_code == 200, reponse.text
    # Le coup joué est bien « piocher », et rien d'autre : les clés étrangères n'ont rien déclenché.
    assert reponse.json()["numero"] == 1


async def test_un_numero_en_retard_sans_coup_est_un_conflit_nomme(api_client, db_session):
    """La garde de fond, sous le schéma : `appliquer_action` refuse un numéro impossible en 409.

    La borne `ge=0` du schéma protège la route ; elle ne protège pas les appels **internes** (bot,
    revanche, scripts), ni un journal troué. On vise donc le service directement, comme le ferait
    un bot — et on exige un refus nommé, pas un `NoResultFound`.
    """
    ctx = await _partie_a_vs_b(api_client, db_session)
    with pytest.raises(ConflitNumero):
        await appliquer_action(
            db_session,
            game_id=ctx["game"].id,
            user_id=ctx["a_id"],
            type="piocher",
            numero_attendu=-1,
        )
