"""Lot ``j-assets-pipeline`` : variantes, budget de poids, cache, et **aucune fabrication en jeu**.

Chaque test ci-dessous échoue sur le code d'avant le lot. Les trois critères d'acceptation de la
fiche sont couverts ici :

* « le poids total d'une partie reste sous le plafond fixé, mesuré en CI » →
  :func:`test_le_budget_d_une_partie_tient_sous_son_plafond` et les tests de plafond par variante,
  qui tournent dans le job ``api`` de la CI (c'est elle qui fait foi) ;
* « aucune génération d'image n'a lieu pendant une partie » →
  :func:`test_servir_une_photo_ne_fabrique_jamais_d_image` (un stockage qui **refuse** d'écrire) ;
* le pré-chargement est côté écran : ``apps/web/src/lib/game/prechargement.test.ts`` et
  ``apps/web/e2e/prechargement-4g.spec.ts``.
"""

from __future__ import annotations

import uuid

import cv2
import numpy as np
import pytest

from pbm_api.jeu import budget
from pbm_api.jeu.rendu import RENDU_PHOTO, PhotoDeJeu, ReglagesRendu, choisir_rendu
from pbm_api.jeu.rendu_image import (
    QUALITES_DE_SECOURS,
    VARIANTE_PLATEAU,
    VARIANTE_ZOOM,
    VARIANTES,
    VarianteTropLourde,
    cle_variante,
    decoder,
    fabriquer_image_jeu,
)
from pbm_api.jeu.rendu_qualite import NotePhoto

# --- Les variantes ------------------------------------------------------------------------------


def _carte_realiste(largeur: int = 630, hauteur: int = 880) -> bytes:
    """Une image de carte **déterministe** et difficile à compresser, en JPEG 92 comme en base.

    Déterministe (graine fixe) : le poids mesuré doit être le même sur chimera, sur devAI et dans la
    CI, sinon un plafond serait vert ici et rouge là. Difficile à compresser (dégradés + bruit de
    capteur + texte simulé) : un aplat de couleur donnerait 2 Ko et prouverait qu'un plafond de
    18 Ko tient, ce qui ne voudrait rien dire.
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
    # Quelques bandes contrastées : l'illustration et les blocs de texte d'une carte réelle.
    haut, bas = int(hauteur * 0.08), int(hauteur * 0.55)
    image[haut:bas, int(largeur * 0.08) : int(largeur * 0.92)] //= 2
    for ligne in range(int(hauteur * 0.62), int(hauteur * 0.92), 18):
        image[ligne : ligne + 7, int(largeur * 0.12) : int(largeur * 0.88)] = 240
    return cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tobytes()


def test_chaque_variante_tient_son_plafond_sur_une_carte_realiste():
    """Le plafond d'une variante n'est pas un vœu : il est tenu sur une vraie carte, sans dégrader.

    Sans ce lot il n'existait qu'une variante (420 px) et aucun plafond : ce test ne pouvait pas
    s'écrire.
    """
    photo = _carte_realiste()
    for variante in VARIANTES:
        donnees = fabriquer_image_jeu(photo, variante)
        assert len(donnees) <= variante.plafond_octets, (
            f"variante « {variante.nom} » : {len(donnees)} o > plafond "
            f"{variante.plafond_octets} o — le budget d'une partie ne tient plus"
        )
        relue = decoder(donnees)
        assert relue.shape[1] == variante.largeur
        assert relue.shape[0] == variante.hauteur


def test_la_variante_de_plateau_est_bien_plus_legere_que_celle_de_zoom():
    """Tout le lot repose sur cet écart : c'est lui qui divise le poids d'un plateau.

    Un facteur 2 au moins — en dessous, dédoubler les variantes ne vaudrait pas sa complexité.
    """
    photo = _carte_realiste()
    plateau = fabriquer_image_jeu(photo, VARIANTE_PLATEAU)
    zoom = fabriquer_image_jeu(photo, VARIANTE_ZOOM)
    assert len(plateau) * 2 < len(zoom), (
        f"plateau {len(plateau)} o contre zoom {len(zoom)} o : l'écart ne justifie pas "
        "deux variantes"
    )


def test_une_photo_incompressible_est_refusee_plutot_que_servie_hors_budget():
    """Le plafond est tenu **par construction** : ou l'image passe, ou on le dit (D9).

    Du bruit pur à 420 px pèse ~126 Ko à qualité nominale : la fabrication réessaie plus bas, et
    si même la qualité plancher ne suffit pas, elle **lève**. Elle ne rend jamais 126 Ko en
    silence — ce serait sept fois le budget de cette carte, cent vingt fois par partie.
    """
    rng = np.random.default_rng(7)
    bruit = rng.integers(0, 256, (880, 630, 3), dtype=np.uint8)
    photo = cv2.imencode(".jpg", bruit, [cv2.IMWRITE_JPEG_QUALITY, 98])[1].tobytes()

    for variante in VARIANTES:
        try:
            donnees = fabriquer_image_jeu(photo, variante)
        except VarianteTropLourde as exc:
            # Le refus nomme le poids et le plafond : une exception muette ne servirait à rien.
            assert str(variante.plafond_octets) in str(exc)
            assert str(QUALITES_DE_SECOURS[-1]) in str(exc)
            continue
        assert len(donnees) <= variante.plafond_octets, (
            "une variante rendue DOIT être sous son plafond : sinon le plafond ne borne rien"
        )


def test_la_cle_de_la_variante_de_zoom_n_a_pas_change():
    """Compatibilité : des milliers de ``jeu_image_key`` portent déjà cette clé exacte.

    La renommer aurait orphelinné autant d'objets dans le stockage, pour rien.
    """
    user_id, item_id = uuid.uuid4(), uuid.uuid4()
    assert cle_variante(user_id, item_id, VARIANTE_ZOOM) == f"jeu/rendu/{user_id}/{item_id}.webp"
    assert (
        cle_variante(user_id, item_id, VARIANTE_PLATEAU)
        == f"jeu/rendu/{user_id}/{item_id}.plateau.webp"
    )


# --- Le budget d'une partie ---------------------------------------------------------------------


def test_le_budget_d_une_partie_tient_sous_son_plafond():
    """⛔ **La garde de budget du lot.** Rouge ici = la CI refuse, et c'est voulu.

    Si ce test casse après un changement de variante, la réponse n'est pas de relever le plafond :
    c'est que le plateau est redevenu trop lourd pour un téléphone en 4G. Le message nomme le
    dépassement et de combien.
    """
    assert budget.depassements() == (), "\n".join(budget.depassements())
    assert budget.poids_pire_cas_partie() <= budget.PLAFOND_PARTIE_OCTETS
    assert budget.poids_pire_cas_mise_en_place() <= budget.PLAFOND_MISE_EN_PLACE_OCTETS


def test_le_budget_est_une_consequence_des_plafonds_pas_un_chiffre_recopie():
    """Le total doit **suivre** les plafonds de variantes, sinon il vieillirait en silence.

    Le poste d'apparition est arrivé avec ``j-anim-pokemon-apparition`` : une découpe à la fois,
    comme le zoom (il n'y a qu'un Pokémon actif par camp). Il est nommé ici plutôt que toléré par
    une inégalité, pour qu'un poste ajouté sans y penser fasse rougir ce test.
    """
    from pbm_api.jeu.decoupe import VARIANTE_APPARITION

    attendu = (
        budget.CARTES_PAR_PARTIE * VARIANTE_PLATEAU.plafond_octets
        + VARIANTE_ZOOM.plafond_octets
        + VARIANTE_APPARITION.plafond_octets
    )
    assert budget.poids_pire_cas_partie() == attendu
    assert budget.CARTES_PAR_PARTIE == 120  # « jusqu'à 120 cartes », fiche du lot


def test_la_mise_en_place_tient_en_quelques_secondes_de_4g():
    """Le critère du lot : le pré-chargement finit avant la fin de la mise en place.

    Quatre secondes de 4G est la borne qu'on se donne — au-delà, un joueur qui pose trois cartes
    aurait fini avant les images, et le plateau se remplirait sous ses yeux.
    """
    secondes = budget.secondes_en_4g(budget.poids_pire_cas_mise_en_place())
    assert secondes <= 4.0, f"{secondes:.1f} s de 4G pour la mise en place : trop long"


def test_le_rapport_de_budget_nomme_les_deux_plafonds():
    """Le rapport sert dans un journal de CI et un compte rendu : il doit être lisible seul."""
    texte = budget.rapport()
    assert "total partie" in texte
    assert "mise en place" in texte
    assert "4G" in texte


# --- L'URL de la vue porte la bonne variante ----------------------------------------------------


def test_la_vue_sert_le_plateau_en_leger_et_le_zoom_en_lourd():
    """``rendu.url`` (chargée jusqu'à 120 fois) doit être la variante **plateau**.

    Avant ce lot, ``url`` et ``url_zoom`` pointaient la MÊME image de 45 Ko : c'est exactement le
    défaut que le budget borne. Ce test échoue sur le code d'avant.
    """
    item_id, game_id, card_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    rendu = choisir_rendu(
        card_id=card_id,
        photo=PhotoDeJeu(
            item_id=item_id,
            prete=True,
            note=NotePhoto(
                nettete=500.0, luminosite=128.0, part_brulee=0.0, cadrage=1.0,
                exploitable=True, raison=None,
            ),
        ),
        reglages=ReglagesRendu(),
        preference_deck=None,
        pseudo_proprietaire=None,
        cest_moi=True,
        game_id=game_id,
    )
    assert rendu is not None
    assert rendu.origine == RENDU_PHOTO
    assert rendu.url.endswith(f"?v={VARIANTE_PLATEAU.nom}")
    assert rendu.url_zoom.endswith(f"?v={VARIANTE_ZOOM.nom}")
    assert rendu.url != rendu.url_zoom


# --- Le cache avec empreinte --------------------------------------------------------------------


def test_une_image_immuable_promet_un_an_et_une_empreinte():
    """L'image officielle d'une carte ne change jamais : le navigateur ne doit rien redemander."""
    from pbm_api.http_images import reponse_image

    reponse = reponse_image(b"des octets d'image", "image/webp", immuable=True)
    cache = reponse.headers["cache-control"]
    assert "immutable" in cache
    assert "max-age=31536000" in cache
    assert "public" in cache
    assert reponse.headers["etag"].startswith('"')


def test_une_variante_de_photo_est_privee_et_revalidable_jamais_immuable():
    """Une photo peut être reprise : ``immutable`` afficherait l'ancienne pendant un an."""
    from pbm_api.http_images import reponse_image

    reponse = reponse_image(b"photo", "image/webp", privee=True)
    cache = reponse.headers["cache-control"]
    assert "private" in cache
    assert "immutable" not in cache
    assert reponse.headers["etag"]


def test_l_empreinte_connue_rend_304_sans_corps():
    """Tout l'intérêt de l'empreinte : recharger un plateau ne repaie pas ses images."""
    from pbm_api.http_images import empreinte, reponse_image

    donnees = b"une variante de jeu"
    etag = empreinte(donnees)
    reponse = reponse_image(donnees, "image/webp", if_none_match=etag, privee=True)
    assert reponse.status_code == 304
    assert reponse.body == b""
    assert reponse.headers["etag"] == etag


def test_une_empreinte_faible_ou_multiple_est_reconnue():
    """Un navigateur peut envoyer ``W/"x", "y"`` : comparer la chaîne entière ne rendrait
    jamais 304."""
    from pbm_api.http_images import empreinte, reponse_image

    donnees = b"une variante de jeu"
    etag = empreinte(donnees)
    reponse = reponse_image(
        donnees, "image/webp", if_none_match=f'"autre-chose", W/{etag}', privee=True
    )
    assert reponse.status_code == 304


def test_une_empreinte_differente_renvoie_bien_l_image():
    """La photo a changé : le navigateur doit recevoir la nouvelle, pas un 304."""
    from pbm_api.http_images import reponse_image

    reponse = reponse_image(b"nouvelle photo", "image/webp", if_none_match='"vieille"', privee=True)
    assert reponse.status_code == 200
    assert reponse.body == b"nouvelle photo"


def test_deux_contenus_differents_ont_des_empreintes_differentes():
    """Sinon une photo reprise resterait invisible : l'empreinte est la seule révocation."""
    from pbm_api.http_images import empreinte

    assert empreinte(b"photo a") != empreinte(b"photo b")
    assert empreinte(b"photo a") == empreinte(b"photo a")


@pytest.mark.parametrize("variante", VARIANTES, ids=[v.nom for v in VARIANTES])
def test_chaque_variante_a_un_plafond_et_une_qualite_plausibles(variante):
    """Garde-fou contre une variante ajoutée sans plafond, qui ouvrirait un trou dans le budget."""
    assert variante.plafond_octets > 0
    assert 1 <= variante.qualite <= 100
    assert variante.largeur > 0
    assert variante.hauteur == round(variante.largeur / (63 / 88))
