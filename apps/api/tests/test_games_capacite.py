"""Plafond de **parties simultanées** : refuser une partie de plus plutôt que ralentir les autres.

Lot ``j-charge-temps-reel``. Les trois critères d'acceptation, chacun avec son test :

1. **le plafond est appliqué** — :func:`test_une_partie_de_plus_que_le_plafond_est_refusee` : à
   plafond atteint, :func:`creer_partie` lève :class:`PlafondPartiesAtteint` en disant le compte et
   le plafond, et **aucune** ligne `games` n'est insérée ;
2. **un refus clair** — :func:`test_route_entrainement_refuse_en_503_avec_retry_after` : la route
   répond **503** avec ``Retry-After``, et :func:`test_les_trois_portes_traduisent_le_plafond`
   garde la parité des trois routes qui peuvent créer une partie (une quatrième porte ajoutée sans
   traduction rendrait une erreur 500 là où le joueur doit lire une phrase) ;
3. **les parties en cours ne ralentissent pas** —
   :func:`test_un_coup_ne_prend_jamais_le_verrou_de_capacite` : le chemin d'un coup ne compte pas
   les parties et ne prend pas le verrou consultatif. C'est la garantie *structurelle*, celle qu'un
   test peut donner sans mesurer une durée (une assertion sur un chronomètre dans un coureur de CI
   partagé serait instable, donc désactivée, donc inutile). Les durées mesurées, elles, sont dans
   ``docs/jeu/CHARGE.md`` et refaites par ``apps/api/scripts/measure_game_load.py``.

Plus ce qui se casserait en silence sans test : une partie **échue** qui confisquerait une place
(:func:`test_une_partie_echue_ne_confisque_pas_sa_place`), la **file d'attente** qui doit absorber
la saturation au lieu de refuser (:func:`test_matchmaking_laisse_les_joueurs_en_file`), et le refus
qui doit se **voir dans la métrique** (:func:`test_le_refus_est_consigne_et_compte_en_metrique`).
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
import pytest_asyncio
from pbm_game.actions import actions_legales
from pbm_game.actions.familles_jeu import familles_jeu
from sqlalchemy import event, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.config import settings
from pbm_api.games import matchmaking as mm
from pbm_api.games.bot import BOT_USER_ID
from pbm_api.games.capacite import (
    PLAFOND_REPLI,
    RETRY_APRES_SECONDES,
    compter_parties_actives,
    plafond,
)
from pbm_api.games.catalogue_jeu import construire_catalogue_jeu
from pbm_api.games.construction import joueur_id_de
from pbm_api.games.errors import PlafondPartiesAtteint
from pbm_api.games.service import (
    appliquer_action,
    creer_partie,
    demarrer_partie,
    reprendre_partie,
)
from pbm_api.models import (
    Card,
    CollectionItem,
    Deck,
    DeckCard,
    Game,
    GameEvent,
    GamePlayer,
    JeuIncident,
    Set,
    User,
)
from pbm_api.models.games import GAME_STATUS_TERMINEE
from pbm_api.models.observabilite import INCIDENT_PARTIE_REFUSEE
from pbm_api.observabilite.consignation import definir_fabrique
from pbm_api.observabilite.metriques import relever
from pbm_api.observabilite.motifs import MOTIF_CAPACITE_ATTEINTE
from pbm_api.security.csrf import CSRF_HEADER_NAME
from pbm_api.security.rate_limit import get_redis

PASSWORD = "Mdp-capacite-2026!"
_IDENTITE = {
    "last_name": "Dresseur",
    "birth_date": date(2000, 1, 1),
    "terms_version": "test",
    "terms_accepted_at": datetime(2000, 1, 1),
}


# --- Fabriques ---------------------------------------------------------------------------------


async def _user(db, *, game_access: bool = True) -> User:
    u = User(
        email=f"cap-{uuid.uuid4().hex[:10]}@example.com",
        password_hash="x",
        game_access=game_access,
        **_IDENTITE,
    )
    db.add(u)
    await db.flush()
    return u


async def _deck_jouable(db, user, *, possede: bool = False) -> Deck:
    """Un deck à dégâts secs, entièrement jouable (D9) : un attaquant et son énergie."""
    s = Set(code=f"cap-{uuid.uuid4().hex[:8]}", name="Set capacité", series="Série test")
    db.add(s)
    await db.flush()
    pokemon = Card(
        set_id=s.id, number=str(uuid.uuid4().int % 100000), name="Pikachu",
        supertype="Pokémon", energy_type="electrique", element_type="electrique", hp=60,
        stage="Base", retreat_cost=1, prize_marker="ordinaire",
        attacks=[{"name": "Charge", "cost": ["electrique"], "damage": "60", "effect": ""}],
    )
    energie = Card(
        set_id=s.id, number=str(uuid.uuid4().int % 100000), name="Énergie Électrique",
        supertype="Énergie", energy_type="Normal", element_type="electrique",
    )
    db.add_all([pokemon, energie])
    await db.flush()

    deck = Deck(user_id=user.id, name="Deck capacité")
    db.add(deck)
    await db.flush()
    for carte, quantite in ((pokemon, 6), (energie, 14)):
        db.add(DeckCard(deck_id=deck.id, card_id=carte.id, quantity=quantite))
        if possede and carte.supertype == "Pokémon":
            for _ in range(quantite):
                db.add(CollectionItem(user_id=user.id, card_id=carte.id))
    await db.flush()
    return deck


async def _occuper(db, places: int) -> list[Game]:
    """Occupe ``places`` places du plafond par de vraies parties (jamais des lignes bricolées).

    On passe par :func:`creer_partie` : un test qui insérerait des `Game` à la main ne prouverait
    rien du chemin réel — c'est précisément le comptage *de ce chemin* qu'on éprouve.
    """
    parties = []
    for _ in range(places):
        joueur = await _user(db)
        deck = await _deck_jouable(db, joueur)
        parties.append(
            await creer_partie(
                db,
                joueur_a=(joueur.id, deck.id),
                joueur_b=(BOT_USER_ID, deck.id),
                entrainement=True,
                bot_niveau="correct",
            )
        )
    return parties


async def _humain_de(db, partie: Game) -> uuid.UUID:
    """L'``user_id`` assis au siège 0 — celui qui joue les coups dans une partie d'entraînement."""
    siege = (
        await db.execute(
            select(GamePlayer).where(GamePlayer.game_id == partie.id, GamePlayer.seat == 0)
        )
    ).scalar_one()
    return siege.user_id


async def _nb_parties(db) -> int:
    return int((await db.execute(select(func.count()).select_from(Game))).scalar_one())


async def _nb_evenements(db) -> int:
    return int((await db.execute(select(func.count()).select_from(GameEvent))).scalar_one())


@pytest_asyncio.fixture
async def incidents_en_test(db_session):
    """Oriente l'écriture des incidents vers la connexion du test (cf. ``test_observabilite``)."""
    connexion = await db_session.connection()

    def fabrique() -> AsyncSession:
        return AsyncSession(
            bind=connexion, join_transaction_mode="create_savepoint", expire_on_commit=False
        )

    definir_fabrique(fabrique)
    yield
    definir_fabrique(None)


@pytest.fixture
def plafond_a(monkeypatch):
    """Fixe le plafond pour la durée d'un test, sans toucher au défaut de production."""

    def _fixer(valeur: int) -> None:
        monkeypatch.setattr(settings, "jeu_parties_simultanees_max", valeur, raising=False)

    return _fixer


# --- 1) Le plafond est appliqué ----------------------------------------------------------------


async def test_une_partie_de_plus_que_le_plafond_est_refusee(db_session, plafond_a):
    """Critère 1 et 2 — la partie qui dépasse le plafond est refusée, en le disant, sans rien créer.

    Le refus nomme le compte et le plafond : sans ces deux nombres, la personne qui lit le message
    ne sait pas si elle doit attendre une minute ou agrandir le serveur.
    """
    plafond_a(3)
    await _occuper(db_session, 3)
    assert await compter_parties_actives(db_session) == 3
    avant = await _nb_parties(db_session)

    joueur = await _user(db_session)
    deck = await _deck_jouable(db_session, joueur)
    with pytest.raises(PlafondPartiesAtteint) as refus:
        await creer_partie(
            db_session,
            joueur_a=(joueur.id, deck.id),
            joueur_b=(BOT_USER_ID, deck.id),
            entrainement=True,
            bot_niveau="correct",
        )

    assert refus.value.actives == 3
    assert refus.value.plafond == 3
    assert "3" in str(refus.value)
    # Aucune partie fantôme : le refus arrive avant toute insertion.
    assert await _nb_parties(db_session) == avant


async def test_une_place_liberee_rouvre_la_creation(db_session, plafond_a):
    """Le plafond n'est pas un compteur monotone : une partie finie rend sa place aussitôt."""
    plafond_a(2)
    parties = await _occuper(db_session, 2)

    joueur = await _user(db_session)
    deck = await _deck_jouable(db_session, joueur)
    with pytest.raises(PlafondPartiesAtteint):
        await creer_partie(
            db_session, joueur_a=(joueur.id, deck.id), joueur_b=(BOT_USER_ID, deck.id),
            entrainement=True, bot_niveau="correct",
        )

    # Une partie se termine : la place se libère sans attendre aucun balayage.
    parties[0].status = GAME_STATUS_TERMINEE
    await db_session.flush()
    assert await compter_parties_actives(db_session) == 1

    partie = await creer_partie(
        db_session, joueur_a=(joueur.id, deck.id), joueur_b=(BOT_USER_ID, deck.id),
        entrainement=True, bot_niveau="correct",
    )
    assert partie.id is not None


async def test_une_partie_echue_ne_confisque_pas_sa_place(db_session, plafond_a):
    """Une partie fantôme (``expires_at`` passé) ne compte pas : elle ne consomme plus rien.

    Sans ce filtre, quelques dizaines de parties abandonnées fermeraient le jeu jusqu'au prochain
    passage de ``expirer_parties`` — au pire pendant ``jeu_inactivite_plafond_h`` heures, pour
    protéger un processeur que personne ne sollicite.
    """
    plafond_a(2)
    parties = await _occuper(db_session, 2)
    parties[0].expires_at = datetime.now(UTC) - timedelta(hours=1)
    await db_session.flush()

    assert await compter_parties_actives(db_session) == 1
    joueur = await _user(db_session)
    deck = await _deck_jouable(db_session, joueur)
    partie = await creer_partie(
        db_session, joueur_a=(joueur.id, deck.id), joueur_b=(BOT_USER_ID, deck.id),
        entrainement=True, bot_niveau="correct",
    )
    assert partie.id is not None


def test_un_plafond_absurde_retombe_sur_le_repli(monkeypatch):
    """Un réglage à 0 ou négatif ne doit pas *ouvrir* la vanne : il retombe sur le repli mesuré."""
    for valeur in (0, -5):
        monkeypatch.setattr(settings, "jeu_parties_simultanees_max", valeur, raising=False)
        assert plafond() == PLAFOND_REPLI
    monkeypatch.setattr(settings, "jeu_parties_simultanees_max", 7, raising=False)
    assert plafond() == 7


# --- 2) Un refus clair, et les mêmes mots aux trois portes -------------------------------------


async def test_route_entrainement_refuse_en_503_avec_retry_after(
    api_client, db_session, plafond_a
):
    """Critère 2 — la route répond 503, nomme la cause, et dit quand réessayer."""
    plafond_a(1)
    await _occuper(db_session, 1)

    # Un vrai joueur, inscrit par la porte d'entrée : le refus doit arriver *après* l'authentifi-
    # cation et le contrôle d'accès au jeu, sinon on prouverait un 503 qu'un intrus reçoit aussi.
    email = f"cap-{uuid.uuid4().hex[:8]}@example.com"
    inscription = await api_client.post(
        "/auth/register",
        json={
            "email": email, "password": PASSWORD, "last_name": "Dresseur",
            "birth_date": "2000-01-01", "accept_terms": True,
        },
    )
    assert inscription.status_code == 202, inscription.text
    jeton = re.search(r"token=(\S+)", api_client.email_sender.sent[-1]["body"])
    assert jeton
    await api_client.post("/auth/verify-email", json={"token": jeton.group(1)})
    connexion = await api_client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert connexion.status_code == 200, connexion.text
    csrf = api_client.cookies.get(settings.csrf_cookie_name)

    joueur = await db_session.get(User, uuid.UUID(connexion.json()["id"]))
    joueur.game_access = True
    await db_session.flush()
    deck = await _deck_jouable(db_session, joueur, possede=True)

    reponse = await api_client.post(
        "/matchmaking/entrainement",
        json={"deck_id": str(deck.id), "niveau": "correct"},
        headers={CSRF_HEADER_NAME: csrf},
    )
    assert reponse.status_code == 503, reponse.text
    assert reponse.headers["Retry-After"] == str(RETRY_APRES_SECONDES)
    detail = reponse.json()["detail"]
    assert "plafond" in detail.lower()
    # La phrase doit rassurer sur les parties en cours : c'est ce qui distingue un serveur plein
    # d'un serveur en panne, pour qui lit le message.
    assert "ralenties" in detail


def test_les_trois_portes_traduisent_le_plafond():
    """Garde de parité : les trois routes qui créent une partie traduisent toutes le refus.

    Ce contrôle lit le **source** parce qu'aucun test fonctionnel ne le ferait : monter une
    invitation complète ou une revanche pour y vérifier un code HTTP coûte dix fois ce qu'il
    rapporte, et surtout le jour où une quatrième porte s'ouvre, c'est ici que le manque se voit —
    une exception non traduite sort en 500, et le joueur lit « erreur interne » au lieu d'une
    phrase qui lui dit d'attendre trente secondes.
    """
    from pathlib import Path

    import pbm_api

    routers = Path(pbm_api.__file__).parent / "routers"
    for fichier in ("games.py", "matchmaking.py", "lancement.py"):
        source = (routers / fichier).read_text(encoding="utf-8")
        assert "PlafondPartiesAtteint" in source, f"{fichier} ne traduit pas le plafond"
        assert "erreur_capacite" in source, f"{fichier} n'utilise pas le refus commun"


# --- 3) Les parties en cours ne ralentissent pas -----------------------------------------------


async def test_un_coup_ne_prend_jamais_le_verrou_de_capacite(db_session, plafond_a):
    """Critère 3 — jouer un coup ne compte pas les parties et ne prend aucun verrou de capacité.

    C'est *pour cela* que les parties en vol ne ralentissent pas quand le serveur est plein : la
    garde vit sur le chemin de la **création**, pas sur celui du coup. On l'éprouve en espionnant
    le SQL réellement émis pendant un coup — une garde déplacée par erreur dans ``appliquer_action``
    ferait échouer ce test, là où un chronomètre n'aurait rien vu.
    """
    plafond_a(1)
    (partie,) = await _occuper(db_session, 1)

    # Le plafond est atteint : une création échoue…
    autre = await _user(db_session)
    deck_autre = await _deck_jouable(db_session, autre)
    with pytest.raises(PlafondPartiesAtteint):
        await creer_partie(
            db_session, joueur_a=(autre.id, deck_autre.id), joueur_b=(BOT_USER_ID, deck_autre.id),
            entrainement=True, bot_niveau="correct",
        )

    # … et pourtant la partie en cours joue son coup suivant, sans verrou ni comptage.
    await demarrer_partie(db_session, partie)
    etat, _rng = await reprendre_partie(db_session, partie)
    catalogue = await construire_catalogue_jeu(db_session, etat)
    humain = await _humain_de(db_session, partie)
    jid = joueur_id_de(humain)
    legales = actions_legales(etat, jid, familles=familles_jeu(catalogue))
    assert legales, "aucun coup légal : le test ne prouverait rien"

    requetes: list[str] = []

    def espion(conn, cursor, instruction, parametres, contexte, executemany) -> None:
        requetes.append(instruction)

    event.listen(Engine, "before_cursor_execute", espion)
    try:
        resultat = await appliquer_action(
            db_session,
            game_id=partie.id,
            user_id=humain,
            type=legales[0].action.type,
            params=legales[0].action.params,
            numero_attendu=partie.current_numero,
        )
    finally:
        event.remove(Engine, "before_cursor_execute", espion)

    assert resultat is not None
    assert requetes, "l'espion n'a rien vu — le test ne prouverait rien"
    sql = "\n".join(requetes).lower()
    assert "pg_advisory_xact_lock" not in sql, "jouer un coup prend le verrou de capacité"
    # Et le coup ne compte pas non plus les parties actives : ce serait une requête de plus par
    # coup, payée par toutes les parties pour une garde qui ne les concerne pas.
    assert "expires_at >" not in sql, "jouer un coup compte les parties actives"


# --- La file d'attente absorbe la saturation ---------------------------------------------------


async def test_matchmaking_laisse_les_joueurs_en_file(db_session, plafond_a):
    """Saturation côté file : personne n'est refusé, personne n'est apparié, les rangs tiennent.

    « File d'attente plutôt que dégradation » : un joueur qui a demandé « trouve-moi un adversaire »
    n'a rien à faire d'un 503 — il a déjà accepté d'attendre. Il garde donc sa place, et sera
    apparié au premier passage où une place se libère.
    """
    redis = await get_redis()
    plafond_a(1)
    await _occuper(db_session, 1)

    a, b = await _user(db_session), await _user(db_session)
    for joueur in (a, b):
        deck = await _deck_jouable(db_session, joueur)
        await mm.rejoindre(db_session, redis, user_id=joueur.id, deck_id=deck.id)

    # Aucun appariement, aucune exception : les deux restent en file.
    assert await mm.apparier(db_session, redis) == []
    assert await redis.zcard(mm._QUEUE) == 2


# --- Le refus se voit dans la métrique ---------------------------------------------------------


async def test_le_refus_est_consigne_et_compte_en_metrique(
    db_session, plafond_a, incidents_en_test
):
    """Un refus de capacité laisse une trace agrégeable, et remonte dans ``GET /jeu/metriques``.

    Le motif est distinct de celui d'une carte non scriptée : les deux refusent une partie, mais
    l'un se corrige en écrivant un script et l'autre en agrandissant la machine.
    """
    plafond_a(1)
    await _occuper(db_session, 1)

    joueur = await _user(db_session)
    deck = await _deck_jouable(db_session, joueur)
    with pytest.raises(PlafondPartiesAtteint):
        await creer_partie(
            db_session, joueur_a=(joueur.id, deck.id), joueur_b=(BOT_USER_ID, deck.id),
            entrainement=True, bot_niveau="correct",
        )

    incidents = list(
        (
            await db_session.execute(
                select(JeuIncident).where(JeuIncident.genre == INCIDENT_PARTIE_REFUSEE)
            )
        )
        .scalars()
        .all()
    )
    motifs = [i.motif for i in incidents]
    assert MOTIF_CAPACITE_ATTEINTE in motifs
    # Consigné **une** fois, pas deux : le second contrôle (sous verrou) ne recompte pas le refus.
    assert motifs.count(MOTIF_CAPACITE_ATTEINTE) == 1

    releve = await relever(db_session, fenetre_heures=24)
    assert releve.parties_refusees >= 1
    assert releve.capacite_plafond == 1
    assert releve.parties_actives == 1
    assert releve.capacite_taux == pytest.approx(1.0)


async def test_metrique_distingue_parties_en_cours_et_parties_actives(db_session, plafond_a):
    """``parties_actives`` ≤ ``parties_en_cours`` : l'écart, ce sont les parties fantômes."""
    plafond_a(5)
    parties = await _occuper(db_session, 2)
    parties[0].expires_at = datetime.now(UTC) - timedelta(hours=1)
    await db_session.flush()

    releve = await relever(db_session, fenetre_heures=24)
    assert releve.parties_en_cours == 2
    assert releve.parties_actives == 1
    assert releve.capacite_plafond == 5


# --- Garde de non-régression sur le journal ----------------------------------------------------


async def test_le_refus_n_ecrit_rien_au_journal_de_partie(db_session, plafond_a):
    """Un refus de capacité n'est pas un coup : il ne laisse aucune entrée dans ``game_events``."""
    plafond_a(1)
    await _occuper(db_session, 1)
    avant = await _nb_evenements(db_session)

    joueur = await _user(db_session)
    deck = await _deck_jouable(db_session, joueur)
    with pytest.raises(PlafondPartiesAtteint):
        await creer_partie(
            db_session, joueur_a=(joueur.id, deck.id), joueur_b=(BOT_USER_ID, deck.id),
            entrainement=True, bot_niveau="correct",
        )

    assert await _nb_evenements(db_session) == avant
