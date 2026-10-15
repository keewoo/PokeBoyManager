"""Lot ``j-anim-pokemon-apparition`` : la découpe, son registre, sa route et son budget.

L'apparition est la décision **DJ3** : *« l'apparition est fabriquée à partir de l'illustration de
la carte elle-même (découpe du Pokémon par segmentation…) : aucune image nouvelle n'est
introduite. »* Ces tests tiennent les quatre moitiés de cette promesse côté serveur :

* la **découpe** (:mod:`pbm_api.jeu.decoupe`) accepte une silhouette et **refuse en nommant le
  critère** — y compris le vrai raté du lot, la ligne de texte « Pokémon Souris… » prise pour le
  sujet, que seul le critère d'allongement attrape ;
* le **registre** (:mod:`pbm_api.jeu.vedettes`) ne peut pas être publié à la main : toute entrée
  publiée porte un verdict humain, une note sans refus et un poids sous plafond ;
* la **route** ``/img/apparitions/{tcgdex_id}`` ne fabrique rien, ne distingue pas « mal formé »
  de « non publié », et pose un cache immuable avec empreinte ;
* le **budget** d'une partie (:mod:`pbm_api.jeu.budget`) absorbe l'apparition sans toucher à la
  mise en place.

⚠️ **Aucun ``onnxruntime`` ici, et c'est délibéré.** La segmentation réelle (U²-Net) est une
dépendance optionnelle absente de la CI : tous les tests de découpe injectent un **segmenteur
factice** déterministe, ce que :func:`pbm_api.jeu.decoupe.decouper` permet par construction (elle
reçoit son segmenteur, elle n'en choisit aucun). La CI fait foi — elle doit donc pouvoir tout
jouer.
"""

from __future__ import annotations

import uuid

import cv2
import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient

from pbm_api.jeu import budget, vedettes
from pbm_api.jeu.decoupe import (
    ALLONGEMENT_MAX,
    VARIANTE_APPARITION,
    DecoupeRefusee,
    decouper,
    fenetre_illustration,
)
from pbm_api.jeu.rendu import (
    RENDU_OFFICIELLE,
    RENDU_PHOTO,
    PhotoDeJeu,
    ReglagesRendu,
    choisir_rendu,
)
from pbm_api.jeu.rendu_qualite import NotePhoto
from pbm_api.main import app
from pbm_api.routers.images import get_storage
from pbm_api.storage.local import LocalObjectStorage

# --- Une carte et des segmenteurs factices ------------------------------------------------------


def _illustration(largeur: int = 630, hauteur: int = 880) -> bytes:
    """Une carte **déterministe** et difficile à compresser, en JPEG comme chez TCGdex.

    Graine fixe : le poids de la découpe mesuré ici doit être le même sur chimera, sur devAI et
    dans la CI — sinon le plafond serait vert ici et rouge là. Dégradés + bruit de capteur : un
    aplat de couleur pèserait deux kilo-octets et ne prouverait rien d'un plafond de 40.
    """
    rng = np.random.default_rng(20261015)
    y, x = np.mgrid[0:hauteur, 0:largeur]
    fond = np.stack(
        [
            (120 + 90 * np.sin(x / 70.0)).astype(np.int16),
            (110 + 80 * np.cos(y / 90.0)).astype(np.int16),
            (140 + 70 * np.sin((x + y) / 110.0)).astype(np.int16),
        ],
        axis=-1,
    )
    fond += rng.normal(0, 11, fond.shape).astype(np.int16)
    image = np.clip(fond, 0, 255).astype(np.uint8)
    return cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tobytes()


def _cadre(crop: np.ndarray) -> tuple[int, int, int, int]:
    """``(hauteur, largeur, centre x, centre y)`` de la fenêtre d'illustration reçue."""
    hauteur, largeur = crop.shape[:2]
    return hauteur, largeur, largeur // 2, hauteur // 2


def segmenteur_silhouette(crop: np.ndarray) -> np.ndarray:
    """Un segmenteur qui rend une **silhouette de créature** : corps, tête, oreilles, pattes, queue.

    Pourquoi pas une simple ellipse : la compacité d'une ellipse pleine vaut 0,88, au-dessus de
    :data:`~pbm_api.jeu.decoupe.COMPACITE_MAX` — et c'est le critère faisant son travail, pas un
    défaut du test. Un détourage réussi suit un contour long et découpé ; une ellipse nue est
    exactement ce que le critère appelle « découpe rectangulaire ». La silhouette ci-dessous rend
    une note (compacité ≈ 0,30, score ≈ 0,76) du même ordre que les vraies découpes du registre.
    """
    hauteur, largeur, cx, cy = _cadre(crop)
    alpha = np.zeros((hauteur, largeur), np.uint8)
    cv2.ellipse(alpha, (cx, cy + 20), (110, 95), 0, 0, 360, 255, -1)  # corps
    cv2.ellipse(alpha, (cx, cy - 70), (62, 58), 0, 0, 360, 255, -1)  # tête
    oreille_g = np.array([[cx - 55, cy - 110], [cx - 20, cy - 115], [cx - 40, cy - 175]])
    oreille_d = np.array([[cx + 55, cy - 110], [cx + 20, cy - 115], [cx + 40, cy - 175]])
    cv2.fillPoly(alpha, [oreille_g, oreille_d], 255)
    cv2.ellipse(alpha, (cx - 70, cy + 110), (26, 32), 0, 0, 360, 255, -1)  # pattes
    cv2.ellipse(alpha, (cx + 70, cy + 110), (26, 32), 0, 0, 360, 255, -1)
    cv2.polylines(
        alpha, [np.array([[cx + 100, cy + 40], [cx + 150, cy + 10], [cx + 175, cy - 55]])],
        False, 255, 16,
    )
    return alpha


def segmenteur_cadre_plein(crop: np.ndarray) -> np.ndarray:
    """Le segmenteur a gardé **tout le cadre** : le cas du fond holographique du Base Set."""
    hauteur, largeur = crop.shape[:2]
    return np.full((hauteur, largeur), 255, np.uint8)


def segmenteur_deux_morceaux(crop: np.ndarray) -> np.ndarray:
    """Deux taches séparées de taille comparable : le sujet **et** une traînée de fond."""
    hauteur, largeur, cx, cy = _cadre(crop)
    alpha = np.zeros((hauteur, largeur), np.uint8)
    cv2.ellipse(alpha, (cx - 130, cy), (80, 95), 0, 0, 360, 255, -1)
    cv2.ellipse(alpha, (cx + 130, cy), (78, 92), 0, 0, 360, 255, -1)
    return alpha


def segmenteur_bandeau(crop: np.ndarray) -> np.ndarray:
    """Un bandeau horizontal très allongé — **le vrai raté du lot**.

    Avec une fenêtre d'illustration descendant trop bas, le segmenteur trouvait la bande
    descriptive (« Pokémon Souris. Taille : 0,8 m, poids : 30 kg ») plus saillante que le Pokémon,
    et la découpe de Raichu était cette ligne de texte, proprement détourée : compacte, d'un seul
    tenant, loin des bords — acceptée par tous les autres critères.
    """
    hauteur, largeur, cx, cy = _cadre(crop)
    alpha = np.zeros((hauteur, largeur), np.uint8)
    demi_largeur, demi_hauteur = 260, 20
    alpha[cy - demi_hauteur : cy + demi_hauteur, cx - demi_largeur : cx + demi_largeur] = 255
    return alpha


def segmenteur_vide(crop: np.ndarray) -> np.ndarray:
    """Le segmenteur n'a rien trouvé : un alpha entièrement nul."""
    hauteur, largeur = crop.shape[:2]
    return np.zeros((hauteur, largeur), np.uint8)


# --- La découpe ---------------------------------------------------------------------------------


def test_une_silhouette_donne_une_decoupe_sous_plafond_et_exploitable():
    """Le cas nominal : une découpe publiable tient dans son plafond **par construction**.

    Le plafond n'est pas un vœu : c'est lui qui rend le budget d'une partie calculable
    (:mod:`pbm_api.jeu.budget`). Une découpe rendue au-dessus de son plafond ne bornerait rien.
    """
    apparition = decouper(_illustration(), segmenteur_silhouette, moteur="factice")

    assert len(apparition.image) <= VARIANTE_APPARITION.plafond_octets, (
        f"{len(apparition.image)} o > plafond {VARIANTE_APPARITION.plafond_octets} o"
    )
    assert apparition.image[:4] == b"RIFF" and apparition.image[8:12] == b"WEBP"
    assert apparition.note.exploitable
    assert apparition.note.refus == ()
    assert apparition.note.moteur == "factice"
    assert apparition.note.score > 0.5, "une silhouette nette doit se classer haut"
    assert apparition.largeur <= VARIANTE_APPARITION.largeur
    assert apparition.hauteur > 0


def test_la_decoupe_est_cadree_au_plus_juste_pas_sur_la_fenetre_entiere():
    """Le sujet est recadré sur sa boîte englobante : transporter du vide coûterait des octets.

    C'est aussi ce qui permet à l'écran de poser la découpe au-dessus de la carte sans connaître
    la géométrie de la fenêtre d'illustration.
    """
    illustration = _illustration()
    fenetre = fenetre_illustration(cv2.imdecode(np.frombuffer(illustration, np.uint8), 1))
    apparition = decouper(illustration, segmenteur_silhouette, moteur="factice")
    assert apparition.largeur < fenetre.shape[1]
    assert apparition.hauteur < fenetre.shape[0]


def test_un_cadre_plein_est_refuse_en_disant_que_le_fond_a_ete_garde():
    """Le fond holographique gardé : refusé, et le message nomme le critère — pas un score opaque.

    Mesuré à 0,62-0,68 d'aire sur le Base Set quand on segmente par modèle de couleur : c'est le
    défaut le plus fréquent, et le plus trompeur, parce que l'image « a l'air » d'une découpe.
    """
    with pytest.raises(DecoupeRefusee) as refus:
        decouper(_illustration(), segmenteur_cadre_plein, moteur="factice")

    message = str(refus.value)
    assert "le fond a été gardé" in message or "découpe rectangulaire" in message, message
    assert not refus.value.note.exploitable
    assert refus.value.note.refus, "un refus doit porter sa note complète, lisible sans relancer"


def test_deux_morceaux_comparables_sont_refuses_comme_decoupe_eclatee():
    """Le sujet **et** une traînée de fond : deux blocs, donc pas une silhouette."""
    with pytest.raises(DecoupeRefusee) as refus:
        decouper(_illustration(), segmenteur_deux_morceaux, moteur="factice")

    assert "découpe éclatée" in str(refus.value), str(refus.value)
    assert refus.value.note.morceaux == 2


def test_un_bandeau_horizontal_est_refuse_comme_du_texte_pas_un_pokemon():
    """⛔ Le critère né du raté de Raichu : aucun Pokémon n'est quatre fois plus large que haut.

    Ce test échoue sur une version du module sans critère d'allongement — et c'est exactement
    l'état dans lequel une ligne de texte détourée partait en production.
    """
    with pytest.raises(DecoupeRefusee) as refus:
        decouper(_illustration(), segmenteur_bandeau, moteur="factice")

    message = str(refus.value)
    assert "découpe en bandeau" in message, message
    assert refus.value.note.allongement > ALLONGEMENT_MAX
    # Le bandeau passe les autres critères : c'est pour ça qu'il fallait celui-là.
    assert refus.value.note.morceaux == 1
    assert len(refus.value.note.refus) == 1, refus.value.note.refus


def test_un_alpha_vide_est_refuse_comme_sujet_trop_petit_jamais_en_divisant_par_zero():
    """Rien trouvé n'est pas « une découpe vide » : c'est un refus nommé, levé avant tout cadrage.

    Sans ce refus, le recadrage sur la boîte englobante appellerait ``min()`` sur un tableau vide
    et le script de production mourrait sur une exception illisible, au milieu d'un lot.
    """
    with pytest.raises(DecoupeRefusee) as refus:
        decouper(_illustration(), segmenteur_vide, moteur="factice")

    assert "sujet trop petit" in str(refus.value), str(refus.value)
    assert refus.value.note.morceaux == 0


# --- Le registre des vedettes -------------------------------------------------------------------


def test_publiees_ne_contient_que_les_entrees_marquees_publiees():
    """``publiees()`` est la liste **annoncée** au jeu : elle doit coller au fichier, exactement."""
    attendu = {v.tcgdex_id for v in vedettes.charger() if v.publie}
    assert vedettes.publiees() == attendu
    assert attendu, "un registre sans aucune vedette publiée priverait le jeu de toute apparition"


@pytest.mark.parametrize(
    "vedette", [v for v in vedettes.charger() if v.publie], ids=lambda v: v.tcgdex_id
)
def test_toute_vedette_publiee_a_ete_vue_mesuree_et_tient_son_plafond(vedette):
    """⛔ **La garde anti-dérive du registre : on ne publie pas à la main.**

    Trois conditions, et chacune a sa raison :

    * ``verdict_oeil == accepte`` — le critère du lot (« les découpes des vedettes sont validées à
      l'œil, une par une ») : la note mesurée ne sait pas dire qu'une aile a été coupée ni qu'un
      morceau de fond sombre est resté accroché ;
    * une note **sans refus** — publier une découpe que les critères refusent, c'est annoncer au
      jeu une image dont on sait qu'elle est mauvaise ;
    * un poids **sous le plafond** — c'est lui qui tient le poste du budget d'une partie. Une
      découpe de 80 Ko publiée à la main ferait sauter le budget sans qu'aucun autre test ne
      bronche, parce que le budget raisonne sur le plafond, pas sur le fichier.
    """
    assert vedette.verdict_oeil == vedettes.VERDICT_ACCEPTE, vedette.motif_oeil
    assert vedette.note, "une vedette publiée sans note n'a pas été produite par la chaîne"
    assert not vedette.note.get("refus"), vedette.note.get("refus")
    octets = vedette.note.get("octets")
    assert isinstance(octets, int), "la chaîne inscrit le poids mesuré : son absence = pas produite"
    assert octets <= VARIANTE_APPARITION.plafond_octets, (
        f"{vedette.tcgdex_id} : {octets} o > plafond {VARIANTE_APPARITION.plafond_octets} o"
    )


@pytest.mark.parametrize(
    "identifiant", ["../../etc/passwd", "base1-4/../x", "jeu/apparitions/base1-4", "", "BASE1-4"]
)
def test_la_cle_de_stockage_refuse_un_identifiant_hors_motif_sans_l_assainir(identifiant):
    """Une clé ne s'assainit pas, elle se refuse : assainir, c'est accepter une entrée douteuse.

    L'identifiant vient de l'URL d'une route publique ; un ``..`` qui franchirait cette fonction
    sortirait du préfixe ``jeu/apparitions/`` et ferait de la route un lecteur de fichiers.
    """
    with pytest.raises(ValueError):
        vedettes.cle_apparition(identifiant)


def test_la_cle_et_l_url_d_une_vedette_sont_celles_qu_attend_la_route():
    """Les deux bouts du contrat : ce que le rendu annonce, et ce que la route va chercher."""
    publiee = sorted(vedettes.publiees())[0]
    assert vedettes.cle_apparition(publiee) == f"jeu/apparitions/{publiee}.webp"
    assert vedettes.url_apparition(publiee) == f"/img/apparitions/{publiee}"


# --- La route /img/apparitions/{tcgdex_id} ------------------------------------------------------


@pytest.fixture
def vedette_publiee() -> str:
    """Un identifiant réellement publié par le registre — jamais une valeur recopiée à la main."""
    return sorted(vedettes.publiees())[0]


@pytest.fixture
def vedette_non_publiee() -> str:
    """Une vedette du registre **non** publiée (refusée à l'œil, ou par la note mesurée)."""
    non_publiees = [v.tcgdex_id for v in vedettes.charger() if not v.publie]
    if not non_publiees:
        pytest.skip("le registre ne contient aucune vedette non publiée")
    return sorted(non_publiees)[0]


class StockageQuiRefuseDEcrire:
    """Un stockage qui **lève** à la moindre écriture — la preuve que la route ne fabrique rien.

    Un simple compteur d'appels se contenterait de constater ; celui-ci rend le test impossible à
    passer si quelqu'un rebranche un jour une production à la volée sur la route.
    """

    def __init__(self, contenu: dict[str, bytes] | None = None) -> None:
        self.contenu = dict(contenu or {})

    async def get(self, key: str) -> bytes | None:
        return self.contenu.get(key)

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        raise AssertionError(f"écriture interdite pendant une partie : {key}")

    async def delete(self, key: str) -> None:
        raise AssertionError(f"suppression interdite : {key}")

    async def ensure_bucket(self) -> None:
        return None


@pytest.fixture(autouse=True)
def _nettoyer_les_substitutions():
    yield
    app.dependency_overrides.clear()


def _client(storage) -> AsyncClient:
    """Client HTTP contre l'app réelle : la route d'apparition ne touche **pas** à la base."""
    app.dependency_overrides[get_storage] = lambda: storage
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_la_route_sert_la_decoupe_avec_un_cache_immuable_et_une_empreinte(
    tmp_path, vedette_publiee
):
    """Une découpe publiée ne change pas : un an de validité, ``immutable``, et une empreinte."""
    stockage = LocalObjectStorage(root=str(tmp_path))
    await stockage.ensure_bucket()
    await stockage.put(vedettes.cle_apparition(vedette_publiee), b"des-octets-webp", "image/webp")

    async with _client(stockage) as client:
        reponse = await client.get(f"/img/apparitions/{vedette_publiee}")

    assert reponse.status_code == 200, reponse.text
    assert reponse.content == b"des-octets-webp"
    assert reponse.headers["content-type"] == "image/webp"
    assert reponse.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert reponse.headers["etag"].startswith('"')


async def test_la_route_rend_304_quand_le_navigateur_detient_deja_la_decoupe(
    tmp_path, vedette_publiee
):
    """Recharger un plateau ne doit pas repayer les apparitions déjà vues."""
    stockage = LocalObjectStorage(root=str(tmp_path))
    await stockage.ensure_bucket()
    await stockage.put(vedettes.cle_apparition(vedette_publiee), b"des-octets-webp", "image/webp")

    async with _client(stockage) as client:
        premiere = await client.get(f"/img/apparitions/{vedette_publiee}")
        seconde = await client.get(
            f"/img/apparitions/{vedette_publiee}",
            headers={"If-None-Match": premiere.headers["etag"]},
        )

    assert seconde.status_code == 304
    assert seconde.content == b""
    assert seconde.headers["etag"] == premiere.headers["etag"]


@pytest.mark.parametrize(
    "identifiant",
    ["base1-999", "pas_un_identifiant", "Base1-4", "base1_4", "x"],
    ids=["inconnu-bien-forme", "motif-invalide", "majuscules", "souligne", "trop-court"],
)
async def test_la_route_rend_404_sur_tout_identifiant_hors_registre(identifiant):
    """Mal formé ou simplement non publié : **le même** 404, avec le même détail.

    La route est publique. Distinguer les deux cas donnerait à qui la sonde de quoi reconstituer
    la liste des vedettes sans charger une seule image, et sans qu'aucun journal ne s'en émeuve.
    """
    stockage = StockageQuiRefuseDEcrire()
    async with _client(stockage) as client:
        reponse = await client.get(f"/img/apparitions/{identifiant}")

    assert reponse.status_code == 404, reponse.text
    assert reponse.json()["detail"] == "aucune apparition pour cette carte"


@pytest.mark.parametrize(
    "chemin",
    [
        "/img/apparitions/../../etc/passwd",
        "/img/apparitions/..%2F..%2Fetc%2Fpasswd",
        "/img/apparitions/base1-4%2F..%2Fx",
    ],
    ids=["traversee-nue", "traversee-encodee", "traversee-depuis-une-vedette"],
)
async def test_une_tentative_de_traversee_ne_sert_jamais_de_fichier(chemin):
    """Aucune traversée ne ressort : 404, et **rien n'est lu** au stockage.

    Ces formes-là n'atteignent même pas la route — un segment de chemin FastAPI ne contient pas de
    ``/``, et le client normalise ``..`` avant d'émettre. Le test est là quand même : il vaut pour
    la pile entière, qui est ce qu'un attaquant attaque. La garde du motif dans
    :func:`pbm_api.jeu.vedettes.cle_apparition` reste la deuxième barrière, testée à part — on ne
    fait pas reposer une frontière de sécurité sur un détail de normalisation d'URL.
    """
    stockage = StockageQuiRefuseDEcrire()
    async with _client(stockage) as client:
        reponse = await client.get(chemin)

    assert reponse.status_code == 404, reponse.text
    assert b"root:" not in reponse.content


async def test_la_route_rend_404_pour_une_vedette_connue_mais_non_publiee(
    tmp_path, vedette_non_publiee
):
    """Une découpe refusée à l'œil ne doit pas se servir, même si son objet traîne au stockage.

    Le registre tranche **avant** le stockage : c'est lui qui fait autorité sur ce qu'on annonce.
    """
    stockage = StockageQuiRefuseDEcrire(
        {f"jeu/apparitions/{vedette_non_publiee}.webp": b"une-vieille-decoupe"}
    )
    async with _client(stockage) as client:
        reponse = await client.get(f"/img/apparitions/{vedette_non_publiee}")

    assert reponse.status_code == 404
    assert reponse.json()["detail"] == "aucune apparition pour cette carte"


async def test_la_route_rend_404_et_ne_fabrique_rien_quand_l_objet_manque(
    tmp_path, vedette_publiee
):
    """⛔ Le critère du lot : **aucune image n'est fabriquée pendant une partie.**

    Le registre annonce la découpe, le stockage ne l'a pas (objet effacé, déploiement partiel) :
    la réponse est 404 et l'écran joue l'effet de type générique (D9). Segmenter à la volée
    coûterait un U²-Net et plusieurs secondes de CPU sur une machine à deux cœurs qui sert deux
    joueurs ; proxyfier l'illustration entière afficherait un rectangle de carte au lieu d'un
    sujet détouré, ce qui est pire qu'une animation absente.
    """
    stockage = StockageQuiRefuseDEcrire()  # toute écriture lève
    async with _client(stockage) as client:
        reponse = await client.get(f"/img/apparitions/{vedette_publiee}")

    assert reponse.status_code == 404
    assert reponse.json()["detail"] == "aucune apparition pour cette carte"


def test_la_route_d_apparition_ne_sait_pas_fabriquer_d_image():
    """Garde statique : le module de route n'importe **aucun** outil de production de découpe.

    Un test de comportement ne couvre que les cas qu'on a imaginés ; celui-ci interdit le chemin
    lui-même. S'il casse, quelqu'un a rebranché la segmentation sur la route qui sert le plateau.
    """
    import inspect

    from pbm_api.routers import images

    source = inspect.getsource(images)
    assert "from pbm_api.jeu.segmentation" not in source, (
        "la route qui sert le plateau ne doit pas pouvoir charger U²-Net"
    )
    assert "import decouper" not in source and "decouper(" not in source, (
        "aucune découpe ne se fabrique sur le chemin d'une requête d'image"
    )


# --- Le champ `apparition` du rendu --------------------------------------------------------------

GAME = uuid.uuid4()
CARD = uuid.uuid4()
ITEM = uuid.uuid4()


def _photo_prete() -> PhotoDeJeu:
    return PhotoDeJeu(
        item_id=ITEM,
        prete=True,
        note=NotePhoto(
            nettete=500.0, luminosite=128.0, part_brulee=0.0, cadrage=1.0,
            exploitable=True, raison=None,
        ),
    )


def _rendu(*, tcgdex_id: str | None, officielle: bool):
    return choisir_rendu(
        card_id=CARD,
        photo=None if officielle else _photo_prete(),
        reglages=ReglagesRendu(),
        preference_deck=RENDU_OFFICIELLE if officielle else None,
        pseudo_proprietaire="Aymeric",
        cest_moi=True,
        game_id=GAME,
        tcgdex_id=tcgdex_id,
    )


@pytest.mark.parametrize("officielle", [False, True], ids=["photo", "officielle"])
def test_l_apparition_est_la_meme_quelle_que_soit_l_origine_de_l_image(officielle):
    """La découpe vient de l'**illustration officielle**, jamais de la photo du joueur.

    Elle est donc identique qu'on joue avec ses propres photos ou avec les images du catalogue :
    deux joueurs qui s'affrontent voient surgir le même Dracaufeu. Détourer la photo de chacun en
    direct aurait coûté un U²-Net par carte et par partie, et une photo de travers aurait donné
    une apparition difforme.
    """
    publiee = sorted(vedettes.publiees())[0]
    rendu = _rendu(tcgdex_id=publiee, officielle=officielle)
    assert rendu is not None
    assert rendu.origine == (RENDU_OFFICIELLE if officielle else RENDU_PHOTO)
    assert rendu.apparition == f"/img/apparitions/{publiee}"
    assert rendu.en_json()["apparition"] == rendu.apparition


@pytest.mark.parametrize("officielle", [False, True], ids=["photo", "officielle"])
def test_une_carte_sans_vedette_publiee_n_annonce_aucune_apparition(
    officielle, vedette_non_publiee
):
    """Pas de découpe = pas de champ inventé : l'écran joue l'effet de type générique (D9).

    Une URL annoncée sans objet derrière ferait tenter un chargement en 404 à chaque attaque.
    """
    assert _rendu(tcgdex_id=vedette_non_publiee, officielle=officielle).apparition is None
    assert _rendu(tcgdex_id="base1-999", officielle=officielle).apparition is None


@pytest.mark.parametrize("officielle", [False, True], ids=["photo", "officielle"])
def test_un_appelant_qui_ne_resout_pas_le_catalogue_n_a_simplement_pas_d_apparition(officielle):
    """``tcgdex_id`` est facultatif : le constructeur de deck n'a pas à le fournir pour exister."""
    assert _rendu(tcgdex_id=None, officielle=officielle).apparition is None


# --- Le câblage : une requête par vue, jamais une question au stockage --------------------------


class _BaseQuiRefuseDEtreInterrogee:
    """Une base qui **lève** à la moindre requête — pour prouver qu'on ne l'interroge pas."""

    async def execute(self, *args, **kwargs):
        raise AssertionError("aucune requête ne doit partir sans vedette publiée")


async def test_sans_vedette_publiee_aucune_requete_ne_part():
    """Un environnement sans découpes déployées ne doit **rien** coûter à chaque vue de partie.

    C'est le cas nominal d'une recette fraîche ou d'un déploiement où le registre n'a encore rien
    de publié : y laisser une requête par rafraîchissement d'écran serait payer pour du vide.
    """
    from pbm_api.jeu import rendu_service

    publiees = vedettes.publiees
    vedettes.publiees = lambda: frozenset()
    try:
        resultat = await rendu_service._vedettes_visibles(
            _BaseQuiRefuseDEtreInterrogee(), [uuid.uuid4()]
        )
    finally:
        vedettes.publiees = publiees
    assert resultat == {}


async def test_sans_carte_visible_aucune_requete_ne_part():
    """Même raison, l'autre borne : une vue sans carte résolue n'a rien à demander."""
    from pbm_api.jeu import rendu_service

    assert await rendu_service._vedettes_visibles(_BaseQuiRefuseDEtreInterrogee(), []) == {}


async def test_la_vue_de_partie_porte_l_apparition_des_vedettes_et_d_elles_seules(db_session):
    """Le câblage de bout en bout, sur une vraie partie : deux cartes, une seule vedette.

    ⛔ **On ne demande jamais au stockage objet « cette découpe existe-t-elle ? ».** Une vue
    résout jusqu'à 120 cartes pour deux regards : une vérification par carte, ce sont jusqu'à
    120 allers-retours réseau à chaque rafraîchissement, et un plateau se relit plusieurs fois par
    seconde. L'appartenance se lit dans le registre, en mémoire — d'où ce test qui ne monte
    **aucun** stockage.
    """
    from datetime import date, datetime

    from pbm_api.games.service import creer_partie
    from pbm_api.jeu import rendu_service
    from pbm_api.models import Card, Deck, DeckCard, Set, User

    publiee = sorted(vedettes.publiees())[0]
    comptes = []
    for pseudo in ("aymeric-app", "jf-app"):
        user = User(
            email=f"{pseudo}-{uuid.uuid4().hex[:8]}@example.com",
            password_hash="x",
            last_name="Dresseur",
            birth_date=date(2000, 1, 1),
            email_verified_at=date.today(),
            terms_version="v1",
            terms_accepted_at=datetime.now(),
            game_access=True,
            pseudo=f"{pseudo}-{uuid.uuid4().hex[:4]}",
        )
        db_session.add(user)
        comptes.append(user)
    await db_session.flush()

    set_row = Set(code=f"app-{uuid.uuid4().hex[:8]}", name="Set apparition")
    db_session.add(set_row)
    await db_session.flush()
    jouable = dict(
        set_id=set_row.id,
        supertype="Pokémon",
        energy_type="water",
        element_type="water",
        hp=60,
        stage="Base",
        retreat_cost=1,
        prize_marker="ordinaire",
    )
    vedette = Card(number="1", name="Dracaufeu", tcgdex_id=publiee, **jouable)
    quelconque = Card(number="2", name="Carapuce", tcgdex_id=None, **jouable)
    db_session.add_all([vedette, quelconque])
    await db_session.flush()

    decks = {}
    for user in comptes:
        deck = Deck(user_id=user.id, name="Deck apparition")
        db_session.add(deck)
        await db_session.flush()
        db_session.add(DeckCard(deck_id=deck.id, card_id=vedette.id, quantity=8))
        decks[user.id] = deck.id
    await db_session.flush()

    partie = await creer_partie(
        db_session,
        joueur_a=(comptes[0].id, decks[comptes[0].id]),
        joueur_b=(comptes[1].id, decks[comptes[1].id]),
    )
    rendus = await rendu_service.rendus_de_partie(
        db_session,
        partie.id,
        ids_par_ref={str(vedette.id): vedette.id, str(quelconque.id): quelconque.id},
    )

    assert rendus, "la partie doit résoudre un rendu pour chaque regard"
    for (_regard, _proprietaire, ref), rendu in rendus.par_regard.items():
        attendu = f"/img/apparitions/{publiee}" if ref == str(vedette.id) else None
        assert rendu["apparition"] == attendu, (ref, rendu["apparition"])


# --- Le budget ------------------------------------------------------------------------------------


def test_l_apparition_entre_au_budget_d_une_partie_sans_le_faire_deborder():
    """Une apparition à la fois, comme le zoom : il n'y a qu'un Pokémon actif par camp.

    Si ce test casse après un changement de plafond, la réponse n'est pas de relever le plafond de
    la partie : c'est que le plateau est redevenu trop lourd pour un téléphone en 4G.
    """
    attendu = (
        budget.CARTES_PAR_PARTIE * 18 * 1024  # variante plateau
        + 64 * 1024  # variante zoom
        + VARIANTE_APPARITION.plafond_octets
    )
    assert budget.poids_pire_cas_partie() == attendu
    assert budget.poids_pire_cas_partie() <= budget.PLAFOND_PARTIE_OCTETS
    assert budget.depassements() == (), "\n".join(budget.depassements())

    postes = {p.quoi: p for p in budget.postes_partie()}
    apparition = postes["apparition du Pokémon (une à la fois)"]
    assert apparition.nombre == 1
    assert apparition.octets_unite == VARIANTE_APPARITION.plafond_octets


def test_l_apparition_ne_pese_pas_sur_la_mise_en_place():
    """⛔ Les 2,2 s de première impression ne bougent pas, et ce n'est pas de la prudence.

    Pendant la mise en place on pose des Pokémon : on n'attaque pas, rien n'évolue — les deux
    seuls moments qui déclenchent une apparition. Compter la découpe ici aurait allongé l'attente
    initiale pour une image que personne ne regarde à cet instant.
    """
    from pbm_api.jeu.rendu_image import VARIANTE_PLATEAU

    assert budget.poids_pire_cas_mise_en_place() == (
        budget.CARTES_MISE_EN_PLACE * VARIANTE_PLATEAU.plafond_octets
    )
    assert budget.poids_pire_cas_mise_en_place() <= budget.PLAFOND_MISE_EN_PLACE_OCTETS
    assert budget.secondes_en_4g(budget.poids_pire_cas_mise_en_place()) <= 4.0


def test_le_rapport_de_budget_nomme_l_apparition():
    """Le rapport sert de preuve dans un compte rendu : le poste doit y être lisible."""
    assert "apparition" in budget.rapport()
