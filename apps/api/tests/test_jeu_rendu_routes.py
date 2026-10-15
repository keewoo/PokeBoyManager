"""Routes du rendu des cartes en jeu — lot ``j-rendu-carte``.

Ce que ces tests tiennent :

* les **réglages** (DJ5) : défauts publiés, modification partielle, vocabulaire refusé, CSRF, et la
  garde d'accès au jeu (D11, 404 partout) ;
* la **photo servie dans une partie** : accessible aux deux joueurs de la partie, et **404** pour
  tout le reste — un intrus, l'exemplaire d'un tiers, un propriétaire qui a posé son veto. C'est le
  test d'accès croisé exigé par le prompt du lot, et le même 404 partout : un code distinct dirait
  à l'adversaire ce qu'il n'a pas à savoir ;
* l'**aperçu de deck** : ce que chaque carte montrera, et la raison d'un repli (c'est là que le
  joueur l'apprend, avant la partie).

Le stockage objet est **local** (dossier temporaire) : aucun S3 n'est joint, et c'est le même
chemin de code qu'en production sur ``STORAGE_BACKEND=local``.
"""

from __future__ import annotations

import re
import uuid
from datetime import date

import cv2
import httpx
import numpy as np
import pytest

from pbm_api.config import settings
from pbm_api.games.service import creer_partie
from pbm_api.jeu import rendu_service
from pbm_api.jeu.rendu_image import TYPE_MIME_JEU, VARIANTE_PLATEAU, VARIANTE_ZOOM
from pbm_api.main import app
from pbm_api.models import Card, CollectionItem, Deck, DeckCard, Set, User
from pbm_api.routers.images import get_storage as images_storage
from pbm_api.routers.jeu_rendu import get_storage
from pbm_api.security.csrf import CSRF_HEADER_NAME
from pbm_api.storage.local import LocalObjectStorage

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


async def _acces_jeu(db, user_id: uuid.UUID, *, pseudo: str) -> None:
    user = await db.get(User, user_id)
    user.game_access = True
    user.pseudo = pseudo
    await db.flush()


def _photo_nette(luminosite: int = 150) -> bytes:
    """Une « photo » de carte exploitable : contraste franc, bien éclairée, au format carte."""
    image = np.full((880, 630, 3), luminosite, dtype=np.uint8)
    image[::4, :, :] = max(0, luminosite - 110)
    image[:, ::4, :] = min(255, luminosite + 90)
    return cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tobytes()


async def _carte(db) -> Card:
    set_row = Set(code=f"rc-{uuid.uuid4().hex[:8]}", name="Set rendu", series="Série test")
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
    return card


async def _deck_de(db, user_id: uuid.UUID, card: Card) -> uuid.UUID:
    deck = Deck(user_id=user_id, name="Deck rendu")
    db.add(deck)
    await db.flush()
    db.add(DeckCard(deck_id=deck.id, card_id=card.id, quantity=8))
    await db.flush()
    return deck.id


async def _exemplaire_photographie(
    db, storage: LocalObjectStorage, user_id: uuid.UUID, card: Card, *, photo: bytes | None = None
) -> CollectionItem:
    """Un exemplaire possédé **avec sa photo** dans le stockage — comme après une validation."""
    cle = f"uploads/{user_id}/{uuid.uuid4()}/detections/0.jpg"
    await storage.put(cle, photo if photo is not None else _photo_nette(), "image/jpeg")
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


@pytest.fixture
def storage(tmp_path) -> LocalObjectStorage:
    """Stockage objet local, substitué dans le routeur — aucun S3 n'est joint."""
    local = LocalObjectStorage(root=str(tmp_path))
    app.dependency_overrides[get_storage] = lambda: local
    yield local
    app.dependency_overrides.pop(get_storage, None)


# --- Réglages -----------------------------------------------------------------------------------


async def test_les_defauts_dj5_sont_publies_sans_ligne_en_base(api_client, db_session):
    """Un compte qui n'a jamais ouvert ces réglages joue avec ses photos (défaut DJ5)."""
    user_id, _ = await _register_verify_login(api_client, _email("rc"))
    await _acces_jeu(db_session, user_id, pseudo="aymeric")

    reponse = await api_client.get("/jeu/rendu/reglages")
    assert reponse.status_code == 200, reponse.text
    corps = reponse.json()
    assert corps["rendu_defaut"] == "photo"
    assert corps["jamais_montrer_mes_photos"] is False
    assert sorted(corps["rendus_possibles"]) == ["officielle", "photo"]
    # La taille réelle servie est publiée : le joueur peut lire le chiffre.
    assert corps["largeur_jeu"] > 0 and corps["hauteur_jeu"] > corps["largeur_jeu"]


async def test_modification_partielle_n_ecrase_pas_l_autre_reglage(api_client, db_session):
    """L'écran bascule un interrupteur sans renvoyer tout l'état — sinon il écraserait un réglage
    changé entre-temps dans un autre onglet."""
    user_id, csrf = await _register_verify_login(api_client, _email("rc"))
    await _acces_jeu(db_session, user_id, pseudo="aymeric")

    r1 = await api_client.patch(
        "/jeu/rendu/reglages", json={"rendu_defaut": "officielle"}, headers=_csrf(csrf)
    )
    assert r1.status_code == 200, r1.text
    r2 = await api_client.patch(
        "/jeu/rendu/reglages", json={"jamais_montrer_mes_photos": True}, headers=_csrf(csrf)
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["rendu_defaut"] == "officielle", "le premier réglage a été écrasé"
    assert r2.json()["jamais_montrer_mes_photos"] is True


async def test_un_rendu_hors_vocabulaire_est_refuse(api_client, db_session):
    """Un réglage qui ne règle rien est un mensonge : « dos » n'est pas une préférence."""
    user_id, csrf = await _register_verify_login(api_client, _email("rc"))
    await _acces_jeu(db_session, user_id, pseudo="aymeric")
    reponse = await api_client.patch(
        "/jeu/rendu/reglages", json={"rendu_defaut": "dos"}, headers=_csrf(csrf)
    )
    assert reponse.status_code == 422, reponse.text


async def test_modifier_les_reglages_exige_le_csrf(api_client, db_session):
    user_id, _ = await _register_verify_login(api_client, _email("rc"))
    await _acces_jeu(db_session, user_id, pseudo="aymeric")
    reponse = await api_client.patch("/jeu/rendu/reglages", json={"rendu_defaut": "officielle"})
    assert reponse.status_code == 403, reponse.text


async def test_sans_acces_au_jeu_404_partout(api_client, db_session):
    """D11 : le jeu n'existe pas pour un compte non invité — ses réglages de rendu non plus."""
    _, csrf = await _register_verify_login(api_client, _email("rc-noaccess"))
    assert (await api_client.get("/jeu/rendu/reglages")).status_code == 404
    r = await api_client.patch(
        "/jeu/rendu/reglages", json={"rendu_defaut": "officielle"}, headers=_csrf(csrf)
    )
    assert r.status_code == 404, r.text
    r2 = await api_client.get(f"/jeu/rendu/decks/{uuid.uuid4()}")
    assert r2.status_code == 404, r2.text
    r3 = await api_client.get(f"/jeu/rendu/parties/{uuid.uuid4()}/photos/{uuid.uuid4()}")
    assert r3.status_code == 404, r3.text


# --- La photo servie dans une partie ------------------------------------------------------------


async def _partie_avec_photo(api_client, db_session, storage):
    """Deux joueurs, une partie, et une photo exploitable chez A. À la fin, **A** est connecté."""
    email_a, email_b = _email("rc-a"), _email("rc-b")
    a_id, _ = await _register_verify_login(api_client, email_a)
    b_id, _ = await _register_verify_login(api_client, email_b)
    await _acces_jeu(db_session, a_id, pseudo="aymeric")
    await _acces_jeu(db_session, b_id, pseudo="jf")
    card = await _carte(db_session)
    deck_a = await _deck_de(db_session, a_id, card)
    deck_b = await _deck_de(db_session, b_id, card)
    item = await _exemplaire_photographie(db_session, storage, a_id, card)
    # Les variantes sont préparées AVANT la partie (lot `j-assets-pipeline`) : à l'ajout en
    # collection dans le produit, explicitement ici. La route de partie n'en fabrique plus aucune.
    await rendu_service.preparer_variante(db_session, storage, item)
    game = await creer_partie(db_session, joueur_a=(a_id, deck_a), joueur_b=(b_id, deck_b))
    await _login(api_client, email_a)
    return {
        "email_a": email_a, "a_id": a_id, "email_b": email_b, "b_id": b_id,
        "card": card, "item": item, "game": game, "deck_a": deck_a,
    }


async def test_le_proprietaire_recoit_sa_photo_en_variante_de_jeu(
    api_client, db_session, storage
):
    """La variante **déjà préparée** est celle qu'on sert, jamais l'originale pleine résolution.

    C'était le risque nommé par la fiche de ``j-rendu-carte``. Depuis ``j-assets-pipeline``, la
    variante n'est plus produite ici : la route la lit, elle ne la fabrique pas.
    """
    ctx = await _partie_avec_photo(api_client, db_session, storage)
    url = f"/jeu/rendu/parties/{ctx['game'].id}/photos/{ctx['item'].id}"

    reponse = await api_client.get(url)
    assert reponse.status_code == 200, reponse.text
    assert reponse.headers["content-type"] == TYPE_MIME_JEU
    # Allégée face à l'originale : c'est tout l'objet de la variante.
    originale = await storage.get(ctx["item"].photo_s3_key)
    assert originale is not None
    assert len(reponse.content) < len(originale) / 2
    # Et jamais dans un cache partagé : c'est la photo d'un joueur.
    assert "private" in reponse.headers.get("cache-control", "")


async def test_l_adversaire_de_la_partie_voit_la_photo_par_defaut(api_client, db_session, storage):
    """DJ5 : « oui par défaut côté joueur ». La partie est ce qui donne le droit de regarder."""
    ctx = await _partie_avec_photo(api_client, db_session, storage)
    url = f"/jeu/rendu/parties/{ctx['game'].id}/photos/{ctx['item'].id}"
    assert (await api_client.get(url)).status_code == 200

    await _login(api_client, ctx["email_b"])
    reponse = await api_client.get(url)
    assert reponse.status_code == 200, reponse.text


async def test_le_veto_ferme_la_photo_a_l_adversaire_mais_pas_a_son_proprietaire(
    api_client, db_session, storage
):
    """Le critère d'acceptation du lot, au niveau de la route : la **même URL** répond 404 à
    l'adversaire et 200 au propriétaire dès que le veto est posé."""
    ctx = await _partie_avec_photo(api_client, db_session, storage)
    url = f"/jeu/rendu/parties/{ctx['game'].id}/photos/{ctx['item'].id}"
    csrf = await _login(api_client, ctx["email_a"])
    r = await api_client.patch(
        "/jeu/rendu/reglages", json={"jamais_montrer_mes_photos": True}, headers=_csrf(csrf)
    )
    assert r.status_code == 200, r.text

    assert (await api_client.get(url)).status_code == 200, "A doit continuer de voir sa photo"
    await _login(api_client, ctx["email_b"])
    assert (await api_client.get(url)).status_code == 404


async def test_choisir_les_images_officielles_ferme_aussi_la_photo(api_client, db_session, storage):
    """Toute la décision est **rejouée** par la route : une URL devinée ou gardée d'une partie
    précédente ne sert rien, même sans veto."""
    ctx = await _partie_avec_photo(api_client, db_session, storage)
    url = f"/jeu/rendu/parties/{ctx['game'].id}/photos/{ctx['item'].id}"
    csrf = await _login(api_client, ctx["email_a"])
    await api_client.patch(
        "/jeu/rendu/reglages", json={"rendu_defaut": "officielle"}, headers=_csrf(csrf)
    )
    assert (await api_client.get(url)).status_code == 404


async def test_un_intrus_ne_voit_pas_la_photo_d_une_partie_ou_il_ne_joue_pas(
    api_client, db_session, storage
):
    """Accès croisé : l'utilisateur C reçoit 404 sur les objets de A (D11)."""
    ctx = await _partie_avec_photo(api_client, db_session, storage)
    email_c = _email("rc-c")
    c_id, _ = await _register_verify_login(api_client, email_c)
    await _acces_jeu(db_session, c_id, pseudo="intrus")
    await _login(api_client, email_c)

    url = f"/jeu/rendu/parties/{ctx['game'].id}/photos/{ctx['item'].id}"
    assert (await api_client.get(url)).status_code == 404


async def test_l_exemplaire_d_un_tiers_n_est_pas_servi_meme_dans_ma_partie(
    api_client, db_session, storage
):
    """La photo doit appartenir à un **joueur de cette partie** : sans ce contrôle, l'URL d'une
    partie suffirait à lire la collection de n'importe qui."""
    ctx = await _partie_avec_photo(api_client, db_session, storage)
    tiers_id, _ = await _register_verify_login(api_client, _email("rc-tiers"))
    item_tiers = await _exemplaire_photographie(db_session, storage, tiers_id, ctx["card"])
    await _login(api_client, ctx["email_a"])

    url = f"/jeu/rendu/parties/{ctx['game'].id}/photos/{item_tiers.id}"
    assert (await api_client.get(url)).status_code == 404


async def test_une_photo_inexploitable_n_est_pas_servie_et_ne_fait_pas_attendre(
    api_client, db_session, storage
):
    """Une photo trop sombre ne devient pas une carte illisible sur le plateau : 404 ici, et la
    vue de partie sert l'officielle (cf. ``test_jeu_rendu_projection``).

    La **raison** est écrite à la préparation (hors partie) et non plus par cette route, qui ne
    fabrique plus rien depuis ``j-assets-pipeline``."""
    ctx = await _partie_avec_photo(api_client, db_session, storage)
    sombre = await _exemplaire_photographie(
        db_session, storage, ctx["a_id"], ctx["card"], photo=_photo_nette(luminosite=15)
    )
    await rendu_service.preparer_variante(db_session, storage, sombre)
    url = f"/jeu/rendu/parties/{ctx['game'].id}/photos/{sombre.id}"
    assert (await api_client.get(url)).status_code == 404
    # La raison est **écrite** : c'est elle que le constructeur de deck montrera.
    await db_session.refresh(sombre)
    assert sombre.jeu_qualite is not None
    assert sombre.jeu_qualite["exploitable"] is False
    assert sombre.jeu_qualite["raison"]


# --- Aperçu de deck -----------------------------------------------------------------------------


async def test_l_apercu_de_deck_dit_ce_que_chaque_carte_montrera(api_client, db_session, storage):
    """Mission point 2 : le repli est **dit au joueur dans le constructeur de deck**."""
    ctx = await _partie_avec_photo(api_client, db_session, storage)
    await _login(api_client, ctx["email_a"])

    reponse = await api_client.get(f"/jeu/rendu/decks/{ctx['deck_a']}")
    assert reponse.status_code == 200, reponse.text
    corps = reponse.json()
    assert corps["rendu_effectif"] == "photo"
    assert corps["nb_photos"] == 1, corps
    assert corps["cartes"] == [], "aucune raison de repli : la photo est exploitable"


async def test_l_apercu_nomme_la_carte_qui_se_replie_et_pourquoi(api_client, db_session, storage):
    """Un deck dont la carte n'a aucune photo : l'aperçu la nomme avec sa raison."""
    email = _email("rc-apercu")
    user_id, _ = await _register_verify_login(api_client, email)
    await _acces_jeu(db_session, user_id, pseudo="aymeric")
    card = await _carte(db_session)
    deck_id = await _deck_de(db_session, user_id, card)

    reponse = await api_client.get(f"/jeu/rendu/decks/{deck_id}")
    assert reponse.status_code == 200, reponse.text
    corps = reponse.json()
    assert corps["nb_photos"] == 0
    assert len(corps["cartes"]) == 1
    assert corps["cartes"][0]["nom"] == "Carapuce"
    assert corps["cartes"][0]["raison"] == "aucune photo de cette carte"


async def test_l_apercu_du_deck_d_un_autre_est_introuvable(api_client, db_session, storage):
    """Accès croisé sur l'aperçu : le deck d'un autre répond 404, pas 403."""
    ctx = await _partie_avec_photo(api_client, db_session, storage)
    email_c = _email("rc-c2")
    c_id, _ = await _register_verify_login(api_client, email_c)
    await _acces_jeu(db_session, c_id, pseudo="intrus2")
    await _login(api_client, email_c)
    assert (await api_client.get(f"/jeu/rendu/decks/{ctx['deck_a']}")).status_code == 404


async def test_le_rendu_du_deck_se_regle_et_revient_au_reglage_du_compte(api_client, db_session):
    """DJ5 : « réglage par deck ». La chaîne vide **efface** la préférence du deck."""
    email = _email("rc-deck")
    user_id, csrf = await _register_verify_login(api_client, email)
    await _acces_jeu(db_session, user_id, pseudo="aymeric")
    card = await _carte(db_session)
    deck_id = await _deck_de(db_session, user_id, card)

    r1 = await api_client.patch(
        f"/me/decks/{deck_id}", json={"rendu_cartes": "officielle"}, headers=_csrf(csrf)
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["rendu_cartes"] == "officielle"

    r2 = await api_client.patch(
        f"/me/decks/{deck_id}", json={"rendu_cartes": ""}, headers=_csrf(csrf)
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["rendu_cartes"] is None, "chaîne vide = suivre le réglage du compte"

    r3 = await api_client.patch(
        f"/me/decks/{deck_id}", json={"rendu_cartes": "dos"}, headers=_csrf(csrf)
    )
    assert r3.status_code == 422, r3.text


# --- Lot `j-assets-pipeline` : variantes servies, et RIEN de fabriqué en partie ------------------


class _StockageQuiRefuseDEcrire:
    """Un stockage qui **lève** à la moindre écriture, pour prouver qu'aucune image n'est fabriquée.

    C'est la seule forme de preuve qui tienne : compter les appels laisserait passer une écriture
    conditionnelle, et relire le source laisserait passer un appel indirect. Ici, toute fabrication
    pendant une partie fait échouer le test — bruyamment.
    """

    def __init__(self, reel):
        self._reel = reel
        self.ecritures = []

    async def get(self, cle):
        return await self._reel.get(cle)

    async def head(self, cle):
        return await self._reel.head(cle)

    async def put(self, cle, donnees, type_mime):
        self.ecritures.append(cle)
        raise AssertionError(
            f"écriture interdite pendant une partie : {cle} — une image a été fabriquée "
            "sur le chemin qui sert le plateau (critère du lot `j-assets-pipeline`)"
        )

    async def delete(self, cle):
        return await self._reel.delete(cle)

    async def ensure_bucket(self):
        return await self._reel.ensure_bucket()


async def test_servir_une_photo_ne_fabrique_jamais_d_image(api_client, db_session, storage):
    """⛔ **Critère du lot** : aucune génération d'image pendant une partie.

    Avant ``j-assets-pipeline``, ``servir_photo`` rattrapait ici la variante manquante : une partie
    à deux joueurs pouvait donc lancer jusqu'à 120 décodages OpenCV sur la machine qui sert. Ce
    test échoue sur ce code-là.
    """
    ctx = await _partie_avec_photo(api_client, db_session, storage)
    refus = _StockageQuiRefuseDEcrire(storage)
    app.dependency_overrides[get_storage] = lambda: refus
    try:
        for variante in (VARIANTE_PLATEAU, VARIANTE_ZOOM):
            url = (
                f"/jeu/rendu/parties/{ctx['game'].id}/photos/{ctx['item'].id}"
                f"?v={variante.nom}"
            )
            reponse = await api_client.get(url)
            assert reponse.status_code == 200, reponse.text
    finally:
        app.dependency_overrides[get_storage] = lambda: storage
    assert refus.ecritures == []


async def test_une_variante_non_preparee_rend_404_au_lieu_de_la_fabriquer(
    api_client, db_session, storage
):
    """Un exemplaire photographié mais jamais préparé : 404, et l'écran prend l'officielle.

    C'est le repli honnête (``url_repli``) plutôt qu'une attente ou une fabrication en pleine
    partie. Le 404 est le même que tous les autres refus de cette route.
    """
    ctx = await _partie_avec_photo(api_client, db_session, storage)
    jamais_prepare = await _exemplaire_photographie(
        db_session, storage, ctx["a_id"], ctx["card"]
    )
    refus = _StockageQuiRefuseDEcrire(storage)
    app.dependency_overrides[get_storage] = lambda: refus
    try:
        url = f"/jeu/rendu/parties/{ctx['game'].id}/photos/{jamais_prepare.id}?v=plateau"
        assert (await api_client.get(url)).status_code == 404
    finally:
        app.dependency_overrides[get_storage] = lambda: storage
    assert refus.ecritures == []


async def test_la_variante_de_plateau_servie_est_bien_plus_legere_que_le_zoom(
    api_client, db_session, storage
):
    """Le gain du lot, mesuré **à travers la route** : c'est ce que le navigateur télécharge."""
    ctx = await _partie_avec_photo(api_client, db_session, storage)
    base = f"/jeu/rendu/parties/{ctx['game'].id}/photos/{ctx['item'].id}"

    plateau = await api_client.get(f"{base}?v=plateau")
    zoom = await api_client.get(f"{base}?v=zoom")
    assert plateau.status_code == 200 and zoom.status_code == 200
    assert plateau.headers["content-type"] == TYPE_MIME_JEU
    assert len(plateau.content) * 2 < len(zoom.content), (
        f"plateau {len(plateau.content)} o contre zoom {len(zoom.content)} o"
    )
    assert len(plateau.content) <= VARIANTE_PLATEAU.plafond_octets


async def test_sans_parametre_de_variante_c_est_le_zoom_comme_avant_le_lot(
    api_client, db_session, storage
):
    """Compatibilité : une URL gardée par un onglet ouvert doit rendre ce qu'elle rendait."""
    ctx = await _partie_avec_photo(api_client, db_session, storage)
    base = f"/jeu/rendu/parties/{ctx['game'].id}/photos/{ctx['item'].id}"
    nu = await api_client.get(base)
    zoom = await api_client.get(f"{base}?v=zoom")
    assert nu.status_code == 200
    assert nu.content == zoom.content


async def test_une_variante_inconnue_est_refusee_sans_rien_servir(
    api_client, db_session, storage
):
    """Un ``?v=`` hors vocabulaire est une erreur de validation, pas un repli silencieux."""
    ctx = await _partie_avec_photo(api_client, db_session, storage)
    url = f"/jeu/rendu/parties/{ctx['game'].id}/photos/{ctx['item'].id}?v=enorme"
    assert (await api_client.get(url)).status_code == 422


async def test_une_photo_deja_connue_du_navigateur_ne_repasse_pas_sur_le_reseau(
    api_client, db_session, storage
):
    """L'empreinte rend un rechargement de plateau gratuit — sinon le budget serait payé
    à chaque F5."""
    ctx = await _partie_avec_photo(api_client, db_session, storage)
    url = f"/jeu/rendu/parties/{ctx['game'].id}/photos/{ctx['item'].id}?v=plateau"

    premiere = await api_client.get(url)
    assert premiere.status_code == 200
    etag = premiere.headers["etag"]
    assert "private" in premiere.headers["cache-control"]

    seconde = await api_client.get(url, headers={"If-None-Match": etag})
    assert seconde.status_code == 304
    assert seconde.content == b""


async def test_l_image_officielle_est_promise_immuable_et_revalidable(
    api_client, db_session, storage
):
    """``/img/cards/{id}`` ne posait AUCUN en-tête avant ce lot : chaque F5 repayait tout."""
    ctx = await _partie_avec_photo(api_client, db_session, storage)
    # La route lit `Card.image_url` pour savoir qu'une image officielle existe, puis sert le cache
    # du stockage objet : sans l'une des deux, c'est un 404 légitime.
    ctx["card"].image_url = "https://assets.example/en/base/base1/4"
    await db_session.flush()
    cle = f"cards/{ctx['card'].id}/low.webp"
    await storage.put(cle, b"image officielle de test", "image/webp")
    app.dependency_overrides[images_storage] = lambda: storage
    try:
        reponse = await api_client.get(f"/img/cards/{ctx['card'].id}?size=low")
        assert reponse.status_code == 200, reponse.text
        assert "immutable" in reponse.headers["cache-control"]
        assert "public" in reponse.headers["cache-control"]
        etag = reponse.headers["etag"]
        rejoue = await api_client.get(
            f"/img/cards/{ctx['card'].id}?size=low", headers={"If-None-Match": etag}
        )
        assert rejoue.status_code == 304
    finally:
        app.dependency_overrides.pop(images_storage, None)


async def test_reprendre_une_photo_efface_ses_variantes_et_sa_note(
    api_client, db_session, storage
):
    """Régénération : les variantes sont nommées d'après l'EXEMPLAIRE, pas d'après la photo.

    Sans effacement, une photo reprise resterait invisible — la clé de la variante ne changerait
    pas, et l'ancienne image serait servie indéfiniment.
    """
    ctx = await _partie_avec_photo(api_client, db_session, storage)
    item = ctx["item"]
    cles = [
        f"jeu/rendu/{item.user_id}/{item.id}.webp",
        f"jeu/rendu/{item.user_id}/{item.id}.plateau.webp",
    ]
    for cle in cles:
        assert await storage.get(cle) is not None

    await rendu_service.invalider_variantes(db_session, storage, item)

    for cle in cles:
        assert await storage.get(cle) is None, f"{cle} est resté dans le stockage"
    assert item.jeu_image_key is None
    assert item.jeu_qualite is None
    # Et la préparation la refait : l'invalidation n'est pas une suppression définitive.
    note = await rendu_service.preparer_variante(db_session, storage, item)
    assert note is not None and note.exploitable
    for cle in cles:
        assert await storage.get(cle) is not None


async def test_un_exemplaire_prepare_avant_le_lot_gagne_sa_variante_de_plateau(
    api_client, db_session, storage
):
    """Rattrapage du parc : ``j-rendu-carte`` ne produisait que le zoom.

    Sans ce rattrapage, un joueur dont la collection date d'avant ce lot n'aurait jamais de
    variante de plateau — donc jouerait avec les images officielles sans que rien ne le dise.
    """
    ctx = await _partie_avec_photo(api_client, db_session, storage)
    item = ctx["item"]
    # On remet l'exemplaire dans l'état exact que laissait `j-rendu-carte` : le zoom seul, et une
    # note sans liste de variantes.
    await storage.delete(f"jeu/rendu/{item.user_id}/{item.id}.plateau.webp")
    item.jeu_qualite = {k: v for k, v in item.jeu_qualite.items() if k != "variantes"}
    await db_session.flush()
    assert rendu_service.variantes_pretes(item) == frozenset()

    note = await rendu_service.preparer_variante(db_session, storage, item)

    assert note is not None and note.exploitable
    assert "plateau" in rendu_service.variantes_pretes(item)
    assert await storage.get(f"jeu/rendu/{item.user_id}/{item.id}.plateau.webp") is not None


async def test_une_seconde_preparation_ne_refait_rien(api_client, db_session, storage):
    """Elle est appelée depuis un écran : la deuxième fois doit coûter zéro écriture."""
    ctx = await _partie_avec_photo(api_client, db_session, storage)
    refus = _StockageQuiRefuseDEcrire(storage)
    note = await rendu_service.preparer_variante(db_session, refus, ctx["item"])
    assert note is not None and note.exploitable
    assert refus.ecritures == []
