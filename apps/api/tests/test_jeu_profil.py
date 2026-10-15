"""Profil de joueur : badges, carte fétiche, vitrine — lot `j-profil-jeu` (jalon J4, DJ6).

Les trois critères d'acceptation du lot, chacun mesuré :

1. **« Un badge ne peut être attribué deux fois »** —
   :func:`test_rejouer_la_cloture_nattribue_rien_de_plus` rejoue l'attribution sur la même partie
   et compte les lignes ; et comme l'idempotence est tenue par une contrainte de base et non par
   un ``if``, :func:`test_la_base_refuse_un_doublon_de_badge` l'attaque **directement en SQL**,
   ce qu'aucun ``if`` du code ne pourrait empêcher.

2. **« Aucun mécanisme ne récompense le temps passé plutôt que le jeu lui-même »** — trois gardes
   **structurelles**, qui portent sur la déclaration et non sur les badges du jour :
   :func:`test_aucun_fait_de_badge_ne_parle_de_temps` (la parade : les faits ne portent aucun champ
   de temps, donc une condition ne *peut pas* lire une durée),
   :func:`test_le_vocabulaire_des_mesures_ne_contient_aucun_temps` et
   :func:`test_il_nexiste_quun_seul_palier_de_volume` (un palier, pas un tapis roulant).
3. **« La carte fétiche s'affiche au lancement, avec le rendu choisi »** —
   :func:`test_la_carte_fetiche_saffiche_des_deux_cotes_au_lancement` lit la vue du lancement par
   HTTP, des **deux** côtés, et vérifie que la photo du joueur est bien servie
   (:func:`test_la_photo_de_la_carte_fetiche_est_servie_dans_le_cadre_du_lancement`) — avec son
   test d'accès croisé : un tiers reçoit **404**.

Plus ce que le lot promet au-delà des critères : le 404 sans accès au jeu (D11), la vitrine éteinte
par défaut et allumée par le réglage de JF, le refus **nommé** d'une carte qu'on ne possède pas, le
veto « ne jamais montrer mes photos » qui tient aussi sur ce nouveau chemin, et une partie
d'entraînement qui n'accorde aucun badge.

Comme ``test_jeu_stats_joueur``, l'historique est écrit directement dans ``game_results`` /
``game_result_players`` : le contrat des badges porte sur **ces tables**, et c'est
``test_games_fin_compte`` qui prouve déjà qu'une partie close les écrit juste. Rejouer des parties
ici mesurerait une seconde fois le lot précédent, et ne permettrait pas de fabriquer les cas qui
comptent (neuf parties puis dix, un deck bitype, un adversaire qui n'a rien pris).

Aucun test ne cite de ``R-x.y`` : ce lot n'applique aucune règle de jeu, il lit des résultats déjà
écrits. Le seul fait de **règle** qu'il consomme — le K.O. en un coup — est mesuré dans le moteur,
par ``apps/game/tests/test_recapitulatif_ko_en_un_coup.py``.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, date, datetime, timedelta

import cv2
import httpx
import numpy as np
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from pbm_api.config import settings
from pbm_api.jeu.badges import (
    BADGES,
    MESURE_VOLUME,
    MESURES,
    PALIER_PARTIES,
    FaitsBadges,
    attribuer,
    champs_de_temps,
)
from pbm_api.jeu.badges_service import attribuer_pour_partie
from pbm_api.jeu.reglages import CLE_BADGES_ACTIFS, NON, OUI
from pbm_api.jeu.reglages_service import ecrire as ecrire_reglage
from pbm_api.jeu.rendu import RENDU_OFFICIELLE, RENDU_PHOTO
from pbm_api.main import app
from pbm_api.models import (
    RESULTAT_DEFAITE,
    RESULTAT_VICTOIRE,
    Card,
    CollectionItem,
    Deck,
    DeckCard,
    GameInvitation,
    GameResult,
    GameResultPlayer,
    Set,
    User,
)
from pbm_api.models.invitations import INVITATION_MODE_PSEUDO, INVITATION_STATUT_ACCEPTEE
from pbm_api.models.player_badges import PlayerBadge
from pbm_api.routers.jeu_rendu import get_storage as rendu_storage
from pbm_api.routers.profil_jeu import get_storage as profil_storage
from pbm_api.security.csrf import CSRF_HEADER_NAME
from pbm_api.storage.local import LocalObjectStorage

PASSWORD = "correct horse battery staple"

#: Un instant fixe : les dates de l'historique se comparent entre elles, jamais à « maintenant ».
T0 = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)

#: Le même instant, **sans fuseau** : les colonnes d'identité de ``users``
#: (``terms_accepted_at``) sont naïves, et asyncpg refuse une date tz-aware sur une colonne qui ne
#: l'est pas. Deux constantes plutôt qu'une conversion à chaque usage : l'écart est dans le schéma,
#: pas dans le test.
T0_NAIF = datetime(2026, 6, 1, 12, 0)


def _email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@example.com"


def _csrf(token: str) -> dict[str, str]:
    return {CSRF_HEADER_NAME: token}


async def _register_verify_login(client: httpx.AsyncClient, email: str) -> tuple[uuid.UUID, str]:
    """Crée un compte vérifié et **connecte** le client dessus ; rend ``(user_id, jeton CSRF)``."""
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


async def _acces_jeu(db, user_id: uuid.UUID, *, pseudo: str, acces: bool = True) -> None:
    user = await db.get(User, user_id)
    user.game_access = acces
    user.pseudo = pseudo
    await db.flush()


def _photo_nette(luminosite: int = 150) -> bytes:
    """Une « photo » de carte exploitable : contraste franc, bien éclairée, au format carte."""
    image = np.full((880, 630, 3), luminosite, dtype=np.uint8)
    image[::4, :, :] = max(0, luminosite - 110)
    image[:, ::4, :] = min(255, luminosite + 90)
    return cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tobytes()


async def _carte(db, *, nom: str = "Carapuce", element: str | None = "water") -> Card:
    """Une carte Pokémon du catalogue ; ``element=None`` fabrique un Pokémon de type inconnu."""
    set_row = Set(code=f"pj-{uuid.uuid4().hex[:8]}", name="Set profil", series="Série test")
    db.add(set_row)
    await db.flush()
    card = Card(
        set_id=set_row.id,
        number="1",
        name=nom,
        supertype="Pokémon",
        energy_type=element,
        element_type=element,
        hp=60,
        stage="Base",
        retreat_cost=1,
        prize_marker="ordinaire",
    )
    db.add(card)
    await db.flush()
    return card


async def _exemplaire(
    db, storage: LocalObjectStorage, user_id: uuid.UUID, card: Card, *, avec_photo: bool = True
) -> CollectionItem:
    """Un exemplaire possédé, avec ou sans photo dans le stockage."""
    cle = None
    if avec_photo:
        cle = f"uploads/{user_id}/{uuid.uuid4()}/detections/0.jpg"
        await storage.put(cle, _photo_nette(), "image/jpeg")
    item = CollectionItem(
        user_id=user_id,
        card_id=card.id,
        language="fr",
        photo_s3_key=cle,
        acquired_at=date.today(),
    )
    db.add(item)
    await db.flush()
    return item


async def _deck(db, user_id: uuid.UUID, cartes: list[Card], *, nom: str = "Deck") -> uuid.UUID:
    deck = Deck(user_id=user_id, name=nom)
    db.add(deck)
    await db.flush()
    for carte in cartes:
        db.add(DeckCard(deck_id=deck.id, card_id=carte.id, quantity=4))
    await db.flush()
    return deck.id


async def _partie_close(
    db,
    joueur: uuid.UUID,
    resultat: str,
    *,
    jours: int = 0,
    deck_id: uuid.UUID | None = None,
    adversaire: uuid.UUID | None = None,
    recompenses_adverses: int = 0,
    entrainement: bool = False,
) -> uuid.UUID:
    """Pose une partie close dans l'historique, et la ligne de l'adversaire si on en nomme un.

    ``recompenses_adverses`` est ce que **l'adversaire** a pris : c'est la mesure de « sans rien
    céder », et elle vit sur sa ligne, pas sur la mienne.
    """
    game_id = uuid.uuid4()
    finie_a = T0 + timedelta(days=jours)
    compte = not entrainement
    db.add(
        GameResult(
            game_id=game_id,
            statut="terminee",
            raison_fin="derniere_recompense",
            vainqueur_user_id=joueur if resultat == RESULTAT_VICTOIRE else adversaire,
            entrainement=entrainement,
            comptabilisee=compte,
            coups=10,
            tours=4,
            duree_s=600,
            journal_numero=10,
            finie_a=finie_a,
        )
    )
    db.add(
        GameResultPlayer(
            game_id=game_id,
            user_id=joueur,
            seat=0,
            deck_id=deck_id,
            adversaire_user_id=adversaire,
            adversaire_bot=False,
            resultat=resultat,
            comptabilisee=compte,
            finie_a=finie_a,
            duree_s=600,
            degats_infliges=120,
            kos_infliges=3,
            recompenses_prises=6 if resultat == RESULTAT_VICTOIRE else 2,
            cartes_jouees=12,
            energies_attachees=5,
            coups_joues=10,
        )
    )
    if adversaire is not None:
        db.add(
            GameResultPlayer(
                game_id=game_id,
                user_id=adversaire,
                seat=1,
                deck_id=None,
                adversaire_user_id=joueur,
                adversaire_bot=False,
                resultat=(
                    RESULTAT_DEFAITE if resultat == RESULTAT_VICTOIRE else RESULTAT_VICTOIRE
                ),
                comptabilisee=compte,
                finie_a=finie_a,
                duree_s=600,
                degats_infliges=30,
                kos_infliges=recompenses_adverses,
                recompenses_prises=recompenses_adverses,
                cartes_jouees=8,
                energies_attachees=3,
                coups_joues=9,
            )
        )
    await db.flush()
    return game_id


async def _invitation_acceptee(db, inviteur: uuid.UUID, invite: uuid.UUID) -> uuid.UUID:
    """Une invitation **acceptée** entre deux comptes — le point de départ d'un lancement.

    Écrite directement : le parcours complet d'invitation est déjà couvert par
    ``test_jeu_invitations``, et ce lot n'a besoin que du **cadre** d'autorisation. Le lancement
    lui-même est créé par sa propre route au premier accès (``GET /lancements/{invitation_id}``),
    et c'est bien ce chemin-là qu'on veut exercer.
    """
    invitation = GameInvitation(
        mode=INVITATION_MODE_PSEUDO,
        statut=INVITATION_STATUT_ACCEPTEE,
        inviter_user_id=inviteur,
        invitee_user_id=invite,
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    db.add(invitation)
    await db.flush()
    return invitation.id


@pytest.fixture
def storage(tmp_path):
    """Un stockage objet **local** (dossier temporaire) posé sur les deux routeurs concernés."""
    local = LocalObjectStorage(root=str(tmp_path))
    app.dependency_overrides[rendu_storage] = lambda: local
    app.dependency_overrides[profil_storage] = lambda: local
    yield local
    app.dependency_overrides.pop(rendu_storage, None)
    app.dependency_overrides.pop(profil_storage, None)


# --- Critère 2 : aucun badge ne récompense le temps passé (gardes STRUCTURELLES) --------------


def test_aucun_fait_de_badge_ne_parle_de_temps():
    """La parade du lot : :class:`FaitsBadges` ne porte **aucun** champ de temps.

    C'est la garde qui compte, parce qu'elle est structurelle : une condition de badge ne peut pas
    récompenser une durée, un jour de connexion ou une série si la fonction d'attribution n'en sait
    rien. Ajouter ``duree_s`` ou ``jours_consecutifs`` aux faits fait rougir ce test — ce qui est le
    but : le débat doit avoir lieu avant, pas après.
    """
    assert champs_de_temps() == ()


def test_le_vocabulaire_des_mesures_ne_contient_aucun_temps():
    """Les mesures permises sont les quatre déclarées, et aucune ne parle de temps.

    La comparaison est volontairement **exacte** : une cinquième mesure (« assiduité », « temps de
    jeu ») ne peut pas apparaître sans que quelqu'un modifie ce test en connaissance de cause.
    """
    assert MESURES == frozenset({"issue", "exploit", "volume", "construction"})
    for badge in BADGES:
        assert badge.mesure in MESURES, badge.code


def test_il_nexiste_quun_seul_palier_de_volume():
    """Un seul badge de volume : un palier, pas une échelle.

    Dix, puis cinquante, puis cent parties, c'est un tapis roulant — exactement ce que la fiche du
    lot refuse (« une obligation quotidienne »). Un seul palier se franchit puis s'oublie.
    """
    volumes = [b for b in BADGES if b.mesure == MESURE_VOLUME]
    assert len(volumes) == 1
    assert volumes[0].code == "dix-parties"


def test_tous_les_badges_ont_un_code_unique_et_une_description():
    """Les codes sont uniques (ils servent de clé en base) et chaque badge se décrit au joueur."""
    codes = [b.code for b in BADGES]
    assert len(codes) == len(set(codes))
    for badge in BADGES:
        assert badge.nom and badge.description
        assert badge.description.endswith("."), badge.code


# --- L'attribution pure -----------------------------------------------------


def test_une_partie_qui_ne_compte_pas_naccorde_aucun_badge():
    """Entraînement contre le bot ou partie expirée : rien, même avec un exploit.

    Une seule règle, posée une fois, plutôt que répétée dans chaque condition — où elle finirait
    par manquer dans l'une d'elles.
    """
    faits = FaitsBadges(
        comptabilisee=False,
        victoire=True,
        ko_en_un_coup=True,
        recompenses_perdues=0,
        parties_comptabilisees=42,
        deck_monotype=True,
    )
    assert attribuer(faits) == frozenset()


def test_chaque_badge_sobtient_par_sa_propre_condition():
    """Chacun des cinq badges, isolément : ce qui le donne, et ce qui ne le donne pas."""
    base = FaitsBadges(comptabilisee=True, parties_comptabilisees=1)
    assert attribuer(base) == frozenset()

    victoire = FaitsBadges(comptabilisee=True, victoire=True, parties_comptabilisees=1)
    # Une victoire donne d'un coup « première victoire » ET « sans rien céder » (l'adversaire n'a
    # rien pris) : c'est voulu, les conditions sont indépendantes.
    assert victoire.recompenses_perdues == 0
    assert attribuer(victoire) == frozenset(
        {"premiere-victoire", "victoire-sans-recompense-cedee"}
    )

    serree = FaitsBadges(
        comptabilisee=True, victoire=True, recompenses_perdues=3, parties_comptabilisees=1
    )
    assert attribuer(serree) == frozenset({"premiere-victoire"})

    exploit = FaitsBadges(comptabilisee=True, ko_en_un_coup=True, parties_comptabilisees=1)
    assert attribuer(exploit) == frozenset({"ko-en-un-coup"})

    monotype_perdu = FaitsBadges(
        comptabilisee=True, victoire=False, deck_monotype=True, parties_comptabilisees=1
    )
    # Monotype **victorieux** : perdre avec un deck monotype ne l'accorde pas.
    assert attribuer(monotype_perdu) == frozenset()


def test_le_palier_de_volume_se_franchit_a_la_partie_qui_le_franchit():
    """Neuf parties : rien. Dix : le badge — et il reste acquis au-delà."""
    neuf = FaitsBadges(comptabilisee=True, parties_comptabilisees=PALIER_PARTIES - 1)
    dix = FaitsBadges(comptabilisee=True, parties_comptabilisees=PALIER_PARTIES)
    cent = FaitsBadges(comptabilisee=True, parties_comptabilisees=100)
    assert "dix-parties" not in attribuer(neuf)
    assert "dix-parties" in attribuer(dix)
    assert "dix-parties" in attribuer(cent)


def test_les_memes_faits_donnent_toujours_les_memes_badges():
    """Déterminisme : aucune part de hasard, aucune récompense aléatoire (mission du lot)."""
    faits = FaitsBadges(
        comptabilisee=True, victoire=True, ko_en_un_coup=True, parties_comptabilisees=12
    )
    assert attribuer(faits) == attribuer(faits)
    assert len(attribuer(faits)) == 4  # tous sauf le monotype


# --- Critère 1 : un badge ne peut être attribué deux fois ---------------------


@pytest.mark.asyncio
async def test_rejouer_la_cloture_nattribue_rien_de_plus(db_session):
    """Deux attributions sur la même partie : la seconde n'écrit rien et le dit (ensemble vide).

    C'est le cas réel des quatre façons dont une partie se termine « deux fois » (coup rejoué,
    reprise, balayage, requêtes concurrentes) : la clôture est idempotente, l'attribution doit
    l'être aussi.
    """
    user = User(
        email=_email("badge-idem"),
        password_hash="x",
        last_name="D",
        birth_date=date(2000, 1, 1),
        terms_version="t",
        terms_accepted_at=T0_NAIF,
        game_access=True,
    )
    db_session.add(user)
    await db_session.flush()
    game_id = await _partie_close(db_session, user.id, RESULTAT_VICTOIRE)

    premier = await attribuer_pour_partie(
        db_session, game_id=game_id, user_id=user.id, ko_en_un_coup=True
    )
    assert premier == frozenset(
        {"premiere-victoire", "ko-en-un-coup", "victoire-sans-recompense-cedee"}
    )

    second = await attribuer_pour_partie(
        db_session, game_id=game_id, user_id=user.id, ko_en_un_coup=True
    )
    assert second == frozenset(), "la seconde attribution ne doit rien ajouter"

    total = (
        await db_session.execute(
            select(func.count()).select_from(PlayerBadge).where(PlayerBadge.user_id == user.id)
        )
    ).scalar_one()
    assert total == 3


@pytest.mark.asyncio
async def test_la_base_refuse_un_doublon_de_badge(db_session):
    """L'idempotence est une **contrainte**, pas un ``if`` : l'attaquer en SQL direct échoue.

    Un ``if`` dans le code perdrait la course entre deux clôtures concurrentes ; ce test prouve
    qu'il n'y a pas que du code entre un badge et son doublon.
    """
    user = User(
        email=_email("badge-uniq"),
        password_hash="x",
        last_name="D",
        birth_date=date(2000, 1, 1),
        terms_version="t",
        terms_accepted_at=T0_NAIF,
        game_access=True,
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(PlayerBadge(user_id=user.id, code="premiere-victoire"))
    await db_session.flush()

    # Un second insert du MÊME couple (compte, code), sans passer par le service : c'est la base
    # qui refuse, pas le code — exactement ce qu'on veut prouver.
    db_session.add(PlayerBadge(user_id=user.id, code="premiere-victoire"))
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_le_badge_sans_rien_ceder_lit_la_ligne_de_ladversaire(db_session):
    """« Sans rien céder » est faux dès que l'adversaire a pris **une** récompense.

    La mesure vit sur la ligne de l'adversaire : une erreur de côté donnerait le badge à toutes les
    victoires, et personne ne s'en apercevrait (une victoire se gagne presque toujours en prenant
    ses six récompenses).
    """
    vainqueur = User(
        email=_email("ceder-v"),
        password_hash="x",
        last_name="D",
        birth_date=date(2000, 1, 1),
        terms_version="t",
        terms_accepted_at=T0_NAIF,
        game_access=True,
    )
    perdant = User(
        email=_email("ceder-p"),
        password_hash="x",
        last_name="D",
        birth_date=date(2000, 1, 1),
        terms_version="t",
        terms_accepted_at=T0_NAIF,
        game_access=True,
    )
    db_session.add_all([vainqueur, perdant])
    await db_session.flush()

    game_id = await _partie_close(
        db_session,
        vainqueur.id,
        RESULTAT_VICTOIRE,
        adversaire=perdant.id,
        recompenses_adverses=1,
    )
    codes = await attribuer_pour_partie(
        db_session, game_id=game_id, user_id=vainqueur.id, ko_en_un_coup=False
    )
    assert codes == frozenset({"premiere-victoire"})


@pytest.mark.asyncio
async def test_le_deck_monotype_est_juge_sur_les_pokemon_du_deck(db_session):
    """Un deck d'un seul type élémentaire l'accorde ; un deck bitype non.

    Les Dresseurs et les Énergies sont hors du compte : seuls les Pokémon portent un type.
    """
    user = User(
        email=_email("mono"),
        password_hash="x",
        last_name="D",
        birth_date=date(2000, 1, 1),
        terms_version="t",
        terms_accepted_at=T0_NAIF,
        game_access=True,
    )
    db_session.add(user)
    await db_session.flush()

    eau = await _carte(db_session, nom="Carapuce", element="water")
    eau2 = await _carte(db_session, nom="Tortank", element="water")
    feu = await _carte(db_session, nom="Salamèche", element="fire")

    mono = await _deck(db_session, user.id, [eau, eau2], nom="Mono eau")
    bitype = await _deck(db_session, user.id, [eau, feu], nom="Eau et feu")

    g1 = await _partie_close(db_session, user.id, RESULTAT_VICTOIRE, deck_id=mono)
    codes = await attribuer_pour_partie(
        db_session, game_id=g1, user_id=user.id, ko_en_un_coup=False
    )
    assert "deck-monotype-victorieux" in codes

    autre = User(
        email=_email("mono2"),
        password_hash="x",
        last_name="D",
        birth_date=date(2000, 1, 1),
        terms_version="t",
        terms_accepted_at=T0_NAIF,
        game_access=True,
    )
    db_session.add(autre)
    await db_session.flush()
    g2 = await _partie_close(db_session, autre.id, RESULTAT_VICTOIRE, deck_id=bitype)
    codes2 = await attribuer_pour_partie(
        db_session, game_id=g2, user_id=autre.id, ko_en_un_coup=False
    )
    assert "deck-monotype-victorieux" not in codes2


# --- La vitrine (route) ------------------------------------------------------


@pytest.mark.asyncio
async def test_sans_acces_au_jeu_la_vitrine_repond_404(api_client, db_session):
    """D11 : un compte sans accès au jeu ne voit **rien** du jeu, pas même un 403."""
    user_id, _ = await _register_verify_login(api_client, _email("sans-acces"))
    await _acces_jeu(db_session, user_id, pseudo="SansAcces", acces=False)
    assert (await api_client.get("/jeu/profil")).status_code == 404


@pytest.mark.asyncio
async def test_la_vitrine_est_eteinte_par_defaut_et_sallume_par_le_reglage(
    api_client, db_session
):
    """DJ6 : les badges sont « en option, activables par JF » — donc éteints par défaut.

    Et quand JF les allume (une commande sur le serveur, sans redéployer), la vitrine montre les
    cinq badges déclarés, celui qui est obtenu marqué comme tel.
    """
    user_id, _ = await _register_verify_login(api_client, _email("vitrine"))
    await _acces_jeu(db_session, user_id, pseudo="Vitrine")
    await ecrire_reglage(db_session, CLE_BADGES_ACTIFS, NON)
    db_session.add(PlayerBadge(user_id=user_id, code="premiere-victoire"))
    await db_session.flush()

    eteinte = (await api_client.get("/jeu/profil")).json()
    assert eteinte["badges_actifs"] is False
    assert eteinte["badges"] == [], "éteinte, la vitrine ne montre aucun badge"
    # L'identité est reprise du compte, même badges éteints : ce n'est pas la même option.
    assert eteinte["pseudo"] == "Vitrine"
    assert eteinte["palier_parties"] == PALIER_PARTIES
    assert "temps" not in eteinte["mesures_possibles"]

    await ecrire_reglage(db_session, CLE_BADGES_ACTIFS, OUI)
    allumee = (await api_client.get("/jeu/profil")).json()
    assert allumee["badges_actifs"] is True
    assert len(allumee["badges"]) == len(BADGES)
    obtenus = {b["code"] for b in allumee["badges"] if b["obtenu"]}
    assert obtenus == {"premiere-victoire"}
    # Les badges non obtenus sont montrés avec leur description : un objectif, pas un mystère.
    a_obtenir = [b for b in allumee["badges"] if not b["obtenu"]]
    assert all(b["description"] for b in a_obtenir)


@pytest.mark.asyncio
async def test_la_vitrine_montre_les_six_decors_sans_en_verrouiller_aucun(api_client, db_session):
    """Les décors ne se débloquent pas : les six sont disponibles, et le restent.

    `j-arene-decors` les a laissés tous accessibles ; ce lot aurait pu en verrouiller derrière des
    badges, et ne le fait pas — verrouiller aujourd'hui **retirerait** aux joueurs un choix qu'ils
    ont déjà (DJ6 : « sans perte »).
    """
    user_id, _ = await _register_verify_login(api_client, _email("decors"))
    await _acces_jeu(db_session, user_id, pseudo="Decors")
    vitrine = (await api_client.get("/jeu/profil")).json()
    assert vitrine["decors"] == ["arene", "caldeira", "lagon", "orage", "temple", "faille"]
    assert vitrine["decor_choisi"] is None


# --- La carte fétiche --------------------------------------------------------


@pytest.mark.asyncio
async def test_une_carte_non_possedee_est_refusee_en_le_disant(api_client, db_session, storage):
    """422 **nommant la raison** : une carte fétiche se choisit dans sa collection.

    Un refus muet laisserait croire à une panne, alors que le joueur n'a qu'un clic à changer.
    """
    user_id, csrf = await _register_verify_login(api_client, _email("fetiche-refus"))
    await _acces_jeu(db_session, user_id, pseudo="Refus")
    carte = await _carte(db_session)

    refus = await api_client.put(
        "/jeu/profil/carte-fetiche", json={"card_id": str(carte.id)}, headers=_csrf(csrf)
    )
    assert refus.status_code == 422
    assert "collection" in refus.json()["detail"]

    inconnue = await api_client.put(
        "/jeu/profil/carte-fetiche", json={"card_id": str(uuid.uuid4())}, headers=_csrf(csrf)
    )
    assert inconnue.status_code == 422
    assert "catalogue" in inconnue.json()["detail"]


@pytest.mark.asyncio
async def test_poser_puis_retirer_sa_carte_fetiche(api_client, db_session, storage):
    """Une carte possédée est acceptée, et ``null`` la retire — un choix n'est jamais définitif."""
    user_id, csrf = await _register_verify_login(api_client, _email("fetiche-ok"))
    await _acces_jeu(db_session, user_id, pseudo="Fetiche")
    carte = await _carte(db_session, nom="Pikachu", element="lightning")
    await _exemplaire(db_session, storage, user_id, carte)

    pose = await api_client.put(
        "/jeu/profil/carte-fetiche", json={"card_id": str(carte.id)}, headers=_csrf(csrf)
    )
    assert pose.status_code == 200, pose.text
    assert pose.json()["carte_fetiche"]["nom"] == "Pikachu"

    # Hors d'un lancement, la vitrine montre l'image officielle et dit pourquoi : il n'existe
    # aucun cadre qui autoriserait à servir une photo personnelle.
    rendu = pose.json()["carte_fetiche"]["rendu"]
    assert rendu["origine"] == RENDU_OFFICIELLE
    assert rendu["raison"]

    retrait = await api_client.put(
        "/jeu/profil/carte-fetiche", json={"card_id": None}, headers=_csrf(csrf)
    )
    assert retrait.status_code == 200
    assert retrait.json()["carte_fetiche"] is None


# --- Critère 3 : la carte fétiche au lancement, des deux côtés ----------------


@pytest.mark.asyncio
async def test_la_carte_fetiche_saffiche_des_deux_cotes_au_lancement(
    api_client, db_session, storage
):
    """La vue du lancement porte les **deux** cartes fétiches, avec le rendu de leur propriétaire.

    C'est le critère d'acceptation du lot, lu par HTTP et des deux côtés : chacun voit ce que
    l'autre a choisi de montrer, et la vue est identique pour les deux (ce qui est la forme même
    d'un lancement, voir ``models/game_launch``).
    """
    email_a = _email("lanc-a")
    a_id, _ = await _register_verify_login(api_client, email_a)
    await _acces_jeu(db_session, a_id, pseudo="Ash")
    carte_a = await _carte(db_session, nom="Pikachu", element="lightning")
    await _exemplaire(db_session, storage, a_id, carte_a)

    email_b = _email("lanc-b")
    b_id, csrf_b = await _register_verify_login(api_client, email_b)
    await _acces_jeu(db_session, b_id, pseudo="Regis")
    carte_b = await _carte(db_session, nom="Bulbizarre", element="grass")
    await _exemplaire(db_session, storage, b_id, carte_b, avec_photo=False)

    # B choisit sa carte fétiche (sans photo : ce sera l'officielle, et la raison le dira).
    pose_b = await api_client.put(
        "/jeu/profil/carte-fetiche", json={"card_id": str(carte_b.id)}, headers=_csrf(csrf_b)
    )
    assert pose_b.status_code == 200, pose_b.text

    # A choisit la sienne, avec sa photo — la variante de jeu est préparée à ce moment-là.
    csrf_a = await _login(api_client, email_a)
    pose_a = await api_client.put(
        "/jeu/profil/carte-fetiche", json={"card_id": str(carte_a.id)}, headers=_csrf(csrf_a)
    )
    assert pose_a.status_code == 200, pose_a.text

    invitation_id = await _invitation_acceptee(db_session, a_id, b_id)

    # C'est la route du lancement qui le crée au premier accès : on exerce ce chemin-là.
    vue = await api_client.get(f"/lancements/{invitation_id}")
    assert vue.status_code == 200, vue.text
    corps = vue.json()
    assert corps["inviter"]["carte_fetiche"]["nom"] == "Pikachu"
    assert corps["invitee"]["carte_fetiche"]["nom"] == "Bulbizarre"
    # Le rendu choisi : la photo pour A (il en a une, préparée), l'officielle pour B.
    assert corps["inviter"]["carte_fetiche"]["rendu"]["origine"] == RENDU_PHOTO
    assert corps["inviter"]["carte_fetiche"]["rendu"]["url_repli"], "repli officiel toujours donné"
    assert corps["invitee"]["carte_fetiche"]["rendu"]["origine"] == RENDU_OFFICIELLE
    assert corps["invitee"]["carte_fetiche"]["rendu"]["raison"]

    # Et l'autre camp voit exactement la même chose (la vue d'un lancement est symétrique).
    await _login(api_client, email_b)
    vue_b = await api_client.get(f"/lancements/{invitation_id}")
    assert vue_b.status_code == 200
    assert vue_b.json()["inviter"]["carte_fetiche"] == corps["inviter"]["carte_fetiche"]


@pytest.mark.asyncio
async def test_la_photo_de_la_carte_fetiche_est_servie_dans_le_cadre_du_lancement(
    api_client, db_session, storage
):
    """La photo est servie aux **deux** camps du lancement, et **404** pour un tiers.

    C'est le test d'accès croisé du lot : un compte invité qui ne participe pas à ce lancement
    reçoit le même 404 que n'importe quel refus — un code distinct lui dirait que la photo existe.
    """
    email_a = _email("photo-a")
    a_id, csrf_a = await _register_verify_login(api_client, email_a)
    await _acces_jeu(db_session, a_id, pseudo="PhotoA")
    carte = await _carte(db_session, nom="Salamèche", element="fire")
    item = await _exemplaire(db_session, storage, a_id, carte)
    pose = await api_client.put(
        "/jeu/profil/carte-fetiche", json={"card_id": str(carte.id)}, headers=_csrf(csrf_a)
    )
    assert pose.status_code == 200, pose.text

    email_b = _email("photo-b")
    b_id, _ = await _register_verify_login(api_client, email_b)
    await _acces_jeu(db_session, b_id, pseudo="PhotoB")
    email_c = _email("photo-c")
    c_id, _ = await _register_verify_login(api_client, email_c)
    await _acces_jeu(db_session, c_id, pseudo="PhotoC")

    invitation_id = await _invitation_acceptee(db_session, a_id, b_id)
    # A ouvre le lancement : c'est son premier accès qui le crée, et son identifiant borne l'URL.
    await _login(api_client, email_a)
    ouverture = await api_client.get(f"/lancements/{invitation_id}")
    assert ouverture.status_code == 200, ouverture.text
    launch_id = ouverture.json()["launch_id"]

    url = f"/jeu/rendu/lancements/{launch_id}/photos/{item.id}"
    # Le tiers d'abord : C ne participe pas à ce lancement.
    await _login(api_client, email_c)
    assert (await api_client.get(url)).status_code == 404

    await _login(api_client, email_b)
    assert (await api_client.get(url)).status_code == 200

    await _login(api_client, email_a)
    assert (await api_client.get(url)).status_code == 200


@pytest.mark.asyncio
async def test_le_veto_de_confidentialite_tient_sur_ce_nouveau_chemin(
    api_client, db_session, storage
):
    """« Ne jamais montrer mes photos » (DJ5) vaut aussi pour la carte fétiche.

    Un nouveau chemin d'image est un nouveau risque de fuite : le veto n'est pas réécrit ici, il est
    **appelé** (``decider_origine``), et ce test le prouve de bout en bout — l'adversaire reçoit
    l'officielle dans la vue, et 404 sur la photo.
    """
    email_a = _email("veto-a")
    a_id, csrf_a = await _register_verify_login(api_client, email_a)
    await _acces_jeu(db_session, a_id, pseudo="VetoA")
    carte = await _carte(db_session, nom="Évoli", element="colorless")
    item = await _exemplaire(db_session, storage, a_id, carte)
    assert (
        await api_client.put(
            "/jeu/profil/carte-fetiche", json={"card_id": str(carte.id)}, headers=_csrf(csrf_a)
        )
    ).status_code == 200
    assert (
        await api_client.patch(
            "/jeu/rendu/reglages",
            json={"jamais_montrer_mes_photos": True},
            headers=_csrf(csrf_a),
        )
    ).status_code == 200

    email_b = _email("veto-b")
    b_id, _ = await _register_verify_login(api_client, email_b)
    await _acces_jeu(db_session, b_id, pseudo="VetoB")
    invitation_id = await _invitation_acceptee(db_session, a_id, b_id)

    reponse = await api_client.get(f"/lancements/{invitation_id}")
    assert reponse.status_code == 200, reponse.text
    vue = reponse.json()
    assert vue["inviter"]["carte_fetiche"]["rendu"]["origine"] == RENDU_OFFICIELLE
    assert (
        await api_client.get(f"/jeu/rendu/lancements/{vue['launch_id']}/photos/{item.id}")
    ).status_code == 404
