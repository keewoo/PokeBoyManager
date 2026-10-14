"""Le rendu des cartes **sur la vue projetée** — lot ``j-rendu-carte``.

C'est ici que se joue le critère d'acceptation du lot : *« le réglage de confidentialité est
respecté côté adversaire »*. On le prouve là où ça compte — sur la charge utile envoyée au client :

* une photo que son propriétaire montre porte une **URL de photo** dans la vue de l'adversaire ;
* dès que le veto est posé, cette URL **disparaît de la charge utile** de l'adversaire (elle n'est
  pas « masquée côté écran » : elle n'est plus là), et reste présente dans celle du propriétaire ;
* une carte sans photo exploitable porte l'image officielle, **sans trou ni attente** ;
* les zones **cachées** (pioche, récompenses, main adverse) ne portent aucun rendu : il n'y a rien
  à enrichir, puisque la projection du moteur n'y laisse aucune carte.

La chaîne testée est complète côté base : joueurs de la partie, decks, réglages, exemplaires
possédés, identifiants de catalogue. Le câblage HTTP de la route de photo est prouvé dans
``test_jeu_rendu_routes`` ; ici on regarde la **vue**.
"""

from __future__ import annotations

import re
import uuid
from datetime import date

import cv2
import httpx
import numpy as np
from pbm_game.sortie import projeter
from pbm_game.state.modele import (
    PHASE_PRINCIPALE,
    Carte,
    EtatPartie,
    Joueur,
    PokemonEnJeu,
    Tour,
)

from pbm_api.games.construction import joueur_id_de
from pbm_api.games.indicateurs import catalogue_pour_etat
from pbm_api.games.rendu_vue import enrichir_rendu
from pbm_api.games.service import creer_partie
from pbm_api.jeu import rendu_service
from pbm_api.models import Card, CollectionItem, Deck, DeckCard, Set, User
from pbm_api.storage.local import LocalObjectStorage

PASSWORD = "correct horse battery staple"


def _email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@example.com"


async def _register_verify_login(client: httpx.AsyncClient, email: str) -> uuid.UUID:
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
    return uuid.UUID(login.json()["id"])


def _photo(luminosite: int = 150) -> bytes:
    image = np.full((880, 630, 3), luminosite, dtype=np.uint8)
    image[::4, :, :] = max(0, luminosite - 110)
    image[:, ::4, :] = min(255, luminosite + 90)
    return cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tobytes()


class _Contexte:
    """Une partie réelle entre A et B, et un plateau garni des deux côtés.

    L'état est construit à la main (plutôt que joué coup par coup) pour une raison : au coup 0,
    **toutes** les cartes sont dans la pioche, donc invisibles — il n'y aurait aucun rendu à
    vérifier. Les lignes de base (sièges, decks, réglages, exemplaires) sont, elles, bien réelles :
    c'est toute la chaîne de résolution qui est exercée.
    """

    def __init__(self, a_id, b_id, card, item, game, deck_a):
        self.a_id, self.b_id = a_id, b_id
        self.card, self.item, self.game, self.deck_a = card, item, game, deck_a
        self.ref = str(card.id)

    def etat(self) -> EtatPartie:
        id_a, id_b = joueur_id_de(self.a_id), joueur_id_de(self.b_id)
        return EtatPartie(
            joueurs=(
                Joueur(
                    id=id_a,
                    actif=PokemonEnJeu(cartes=(Carte(instance_id="a-actif", ref=self.ref),)),
                    main=(Carte(instance_id="a-main", ref=self.ref),),
                    pioche=(Carte(instance_id="a-pioche", ref=self.ref),),
                    recompenses=(Carte(instance_id="a-recomp", ref=self.ref),),
                ),
                Joueur(
                    id=id_b,
                    actif=PokemonEnJeu(cartes=(Carte(instance_id="b-actif", ref=self.ref),)),
                    main=(Carte(instance_id="b-main", ref=self.ref),),
                ),
            ),
            tour=Tour(joueur_actif=id_a, numero=1, phase=PHASE_PRINCIPALE),
        )

    async def vue_pour(self, db, user_id) -> dict:
        """La vue projetée pour ``user_id``, enrichie du rendu — le chemin réel de l'API."""
        etat = self.etat()
        catalogue = await catalogue_pour_etat(db, etat, game_id=self.game.id)
        sortie = projeter(etat, (), pour=joueur_id_de(user_id))
        return enrichir_rendu(sortie["vue"], catalogue.rendus)


def _carte_de(vue: dict, joueur_id: str, zone: str) -> dict:
    """La carte d'une zone d'un joueur dans la vue (``actif`` = la carte du dessus)."""
    joueur = next(j for j in vue["joueurs"] if j["id"] == joueur_id)
    if zone == "actif":
        return joueur["actif"]["cartes"][-1]
    return joueur[zone][0]


async def _contexte(api_client, db_session, storage: LocalObjectStorage) -> _Contexte:
    email_a, email_b = _email("rp-a"), _email("rp-b")
    a_id = await _register_verify_login(api_client, email_a)
    b_id = await _register_verify_login(api_client, email_b)
    for uid, pseudo in ((a_id, "aymeric"), (b_id, "jf")):
        user = await db_session.get(User, uid)
        user.game_access = True
        user.pseudo = pseudo
    await db_session.flush()

    set_row = Set(code=f"rp-{uuid.uuid4().hex[:8]}", name="Set rendu", series="Série test")
    db_session.add(set_row)
    await db_session.flush()
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
    db_session.add(card)
    await db_session.flush()

    decks = {}
    for uid in (a_id, b_id):
        deck = Deck(user_id=uid, name="Deck rendu")
        db_session.add(deck)
        await db_session.flush()
        db_session.add(DeckCard(deck_id=deck.id, card_id=card.id, quantity=8))
        decks[uid] = deck.id
    await db_session.flush()

    # A possède cette carte, photographiée, et sa variante de jeu est prête (le constructeur de
    # deck l'aurait préparée avant la partie).
    cle = f"uploads/{a_id}/{uuid.uuid4()}/detections/0.jpg"
    await storage.put(cle, _photo(), "image/jpeg")
    item = CollectionItem(
        user_id=a_id, card_id=card.id, language="fr", photo_s3_key=cle, acquired_at=date.today()
    )
    db_session.add(item)
    await db_session.flush()
    note = await rendu_service.preparer_variante(db_session, storage, item)
    assert note is not None and note.exploitable, note

    game = await creer_partie(
        db_session, joueur_a=(a_id, decks[a_id]), joueur_b=(b_id, decks[b_id])
    )
    return _Contexte(a_id, b_id, card, item, game, decks[a_id])


# --- Par défaut, l'adversaire voit ma photo (DJ5) ------------------------------------------------


async def test_l_adversaire_recoit_l_url_de_ma_photo_par_defaut(api_client, db_session, tmp_path):
    """« Oui par défaut côté joueur » : la photo de A arrive bien dans la vue de B."""
    storage = LocalObjectStorage(root=str(tmp_path))
    ctx = await _contexte(api_client, db_session, storage)
    id_a = joueur_id_de(ctx.a_id)

    vue_b = await ctx.vue_pour(db_session, ctx.b_id)
    rendu = _carte_de(vue_b, id_a, "actif")["rendu"]
    assert rendu["origine"] == "photo"
    assert rendu["url"] == f"/jeu/rendu/parties/{ctx.game.id}/photos/{ctx.item.id}"
    # Et le crédit nomme son propriétaire : on joue contre les cartes de quelqu'un.
    assert rendu["credit"] == "photo de aymeric"


async def test_mes_propres_cartes_portent_ma_photo_sans_credit(api_client, db_session, tmp_path):
    storage = LocalObjectStorage(root=str(tmp_path))
    ctx = await _contexte(api_client, db_session, storage)
    id_a = joueur_id_de(ctx.a_id)

    vue_a = await ctx.vue_pour(db_session, ctx.a_id)
    rendu = _carte_de(vue_a, id_a, "actif")["rendu"]
    assert rendu["origine"] == "photo"
    assert rendu["credit"] is None


async def test_la_photo_porte_aussi_les_cartes_de_ma_main(api_client, db_session, tmp_path):
    """Ma main est visible **pour moi** : ses cartes méritent le même rendu que le plateau."""
    storage = LocalObjectStorage(root=str(tmp_path))
    ctx = await _contexte(api_client, db_session, storage)
    id_a = joueur_id_de(ctx.a_id)

    vue_a = await ctx.vue_pour(db_session, ctx.a_id)
    assert _carte_de(vue_a, id_a, "main")["rendu"]["origine"] == "photo"


# --- Le veto, côté adversaire (le critère du lot) ------------------------------------------------


async def test_le_veto_retire_l_url_de_la_charge_utile_de_l_adversaire(
    api_client, db_session, tmp_path
):
    """Le critère d'acceptation : « le réglage de confidentialité est respecté côté adversaire ».

    On ne vérifie pas qu'un écran cache la photo — on vérifie que **l'URL n'est plus envoyée**.
    C'est la différence entre un réglage réel et une politesse : si l'URL partait quand même, la
    photo serait à un clic de l'adversaire quoi qu'affiche l'interface.
    """
    storage = LocalObjectStorage(root=str(tmp_path))
    ctx = await _contexte(api_client, db_session, storage)
    id_a = joueur_id_de(ctx.a_id)

    await rendu_service.enregistrer_reglages(
        db_session, ctx.a_id, jamais_montrer_mes_photos=True
    )

    vue_b = await ctx.vue_pour(db_session, ctx.b_id)
    rendu_b = _carte_de(vue_b, id_a, "actif")["rendu"]
    assert rendu_b["origine"] == "officielle"
    assert rendu_b["url"] == f"/img/cards/{ctx.card.id}?size=low"
    assert rendu_b["raison"] == "le propriétaire ne montre pas ses photos"
    # L'identifiant de l'exemplaire n'apparaît NULLE PART dans la vue de l'adversaire.
    assert str(ctx.item.id) not in str(vue_b)

    # Et A continue de voir ses propres photos : le réglage protège, il ne prive pas.
    vue_a = await ctx.vue_pour(db_session, ctx.a_id)
    assert _carte_de(vue_a, id_a, "actif")["rendu"]["origine"] == "photo"


async def test_le_deck_en_images_officielles_vaut_pour_les_deux_regards(
    api_client, db_session, tmp_path
):
    """« Réglage par deck » : choisir les images officielles s'applique aussi à soi-même."""
    storage = LocalObjectStorage(root=str(tmp_path))
    ctx = await _contexte(api_client, db_session, storage)
    id_a = joueur_id_de(ctx.a_id)
    deck = await db_session.get(Deck, ctx.deck_a)
    deck.rendu_cartes = "officielle"
    await db_session.flush()

    for user_id in (ctx.a_id, ctx.b_id):
        vue = await ctx.vue_pour(db_session, user_id)
        rendu = _carte_de(vue, id_a, "actif")["rendu"]
        assert rendu["origine"] == "officielle", user_id
        assert rendu["raison"] == "images officielles choisies"


# --- Sans photo exploitable : l'officielle, sans trou --------------------------------------------


async def test_une_carte_sans_photo_se_joue_avec_l_image_officielle(
    api_client, db_session, tmp_path
):
    """Premier critère d'acceptation du lot. B ne possède pas cette carte en photo : sa carte
    porte l'officielle — une URL utilisable tout de suite, pas un trou ni une attente."""
    storage = LocalObjectStorage(root=str(tmp_path))
    ctx = await _contexte(api_client, db_session, storage)
    id_b = joueur_id_de(ctx.b_id)

    for user_id in (ctx.a_id, ctx.b_id):
        vue = await ctx.vue_pour(db_session, user_id)
        rendu = _carte_de(vue, id_b, "actif")["rendu"]
        assert rendu["origine"] == "officielle"
        assert rendu["url"] == f"/img/cards/{ctx.card.id}?size=low"
        assert rendu["url_zoom"] == f"/img/cards/{ctx.card.id}?size=high"
        assert rendu["raison"] == "aucune photo de cette carte"


async def test_une_photo_trop_sombre_replie_en_le_disant(api_client, db_session, tmp_path):
    """La photo existe mais serait illisible sur un plateau : l'officielle, raison mesurée."""
    storage = LocalObjectStorage(root=str(tmp_path))
    ctx = await _contexte(api_client, db_session, storage)
    id_a = joueur_id_de(ctx.a_id)

    # On remplace la photo exploitable de A par une photo trop sombre, notée comme telle.
    item = await db_session.get(CollectionItem, ctx.item.id)
    item.jeu_image_key = None
    item.jeu_qualite = None
    await storage.put(item.photo_s3_key, _photo(luminosite=15), "image/jpeg")
    note = await rendu_service.preparer_variante(db_session, storage, item)
    assert note is not None and not note.exploitable

    vue_b = await ctx.vue_pour(db_session, ctx.b_id)
    rendu = _carte_de(vue_b, id_a, "actif")["rendu"]
    assert rendu["origine"] == "officielle"
    assert rendu["raison"] == "photo trop sombre"


# --- Rien ne fuite par le rendu ------------------------------------------------------------------


async def test_les_zones_cachees_ne_portent_aucun_rendu(api_client, db_session, tmp_path):
    """La pioche, les récompenses et la main adverse sont des **nombres** dans la vue : il n'y a
    aucune carte à enrichir, donc aucune image à y attacher. C'est l'écran qui dessine un dos."""
    storage = LocalObjectStorage(root=str(tmp_path))
    ctx = await _contexte(api_client, db_session, storage)
    id_a, id_b = joueur_id_de(ctx.a_id), joueur_id_de(ctx.b_id)

    vue_b = await ctx.vue_pour(db_session, ctx.b_id)
    joueur_a_vu = next(j for j in vue_b["joueurs"] if j["id"] == id_a)
    assert "main" not in joueur_a_vu, "la main adverse n'est jamais exposée"
    assert joueur_a_vu["pioche_nombre"] == 1
    assert joueur_a_vu["recompenses_nombre"] == 1
    # Aucune des instances cachées de A n'apparaît dans la vue de B.
    for cachee in ("a-pioche", "a-recomp", "a-main"):
        assert cachee not in str(vue_b)
    assert id_b == next(j for j in vue_b["joueurs"] if j["id"] == id_b)["id"]


async def test_la_route_d_etat_porte_le_rendu_sans_casser_la_partie_neuve(
    api_client, db_session, tmp_path
):
    """Câblage HTTP : au coup 0, toutes les cartes sont cachées — la vue est donc **sans
    rendu**, et la route répond quand même 200. C'est le cas qui aurait cassé si
    l'enrichissement supposait qu'une carte visible existe toujours."""
    storage = LocalObjectStorage(root=str(tmp_path))
    ctx = await _contexte(api_client, db_session, storage)

    reponse = await api_client.get(f"/games/{ctx.game.id}/state")
    assert reponse.status_code == 200, reponse.text
    # La charge utile de la route est ``{"vue": …, "evenements": […], "horloges": …, "numero": …}``.
    vue = reponse.json()["vue"]
    assert vue["joueurs"][0]["actif"] is None, "au coup 0, rien n'est encore en jeu"
    assert "rendu" not in str(vue), "aucune carte visible : donc aucun rendu, et aucune fuite"
