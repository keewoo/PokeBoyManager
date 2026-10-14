"""La **variante de jeu** d'une photo personnelle : produite à l'avance, légère (``j-rendu-carte``).

Le risque nommé par la fiche du lot : servir la photo d'origine pleine résolution. Le recadrage
redressé que porte ``collection_items.photo_s3_key`` fait 630×880 en JPEG qualité 92, soit
**178 Ko** par carte (mesuré sur une carte réelle). Un plateau en montre une vingtaine, une partie
en traverse soixante : **3,5 Mo** à l'écran et **10,5 Mo** pour un deck, sur un téléphone.

La variante, elle, pèse **44 Ko** (420×587, WebP 80) : **/4,1**, soit 0,86 Mo pour un plateau
entier. Les chiffres sont dans le compte rendu du lot, et un test les garde (une variante qui ne
diviserait pas franchement le poids ne servirait à rien).

La variante de jeu est donc produite **une fois**, rangée dans le stockage objet, et réutilisée à
chaque partie. Sa taille est choisie pour le pire cas d'affichage, qui n'est pas le plateau
(≈ 60 px de large sur un téléphone) mais le **zoom** (``min(70vw, 16rem)``, soit 256 px de large,
512 px sur un écran à densité double) : au-delà, on paierait des pixels que personne ne voit.

Le redressement, lui, n'est **pas refait** ici : il a déjà eu lieu à la détection
(:func:`pbm_api.detection.geometry.warp_card`, lot ``v3-detection``) et la photo stockée est déjà
au format carte. Ce module ne fait que **réduire** — et recadrer en « couvrant » si la source
n'est pas exactement au ratio d'une carte (un exemplaire dont la photo n'est pas venue du parcours
de détection), plutôt que de la déformer.
"""

from __future__ import annotations

import io
import uuid

import cv2
import numpy as np
from PIL import Image

from pbm_api.detection.geometry import CARD_ASPECT_RATIO

#: Largeur de la variante de jeu, en pixels. Couvre le zoom (256 px CSS) à densité double.
LARGEUR_JEU = 420

#: Hauteur de la variante, au ratio d'une carte (63×88 mm) — jamais une valeur arrondie à part.
HAUTEUR_JEU = round(LARGEUR_JEU / CARD_ASPECT_RATIO)

#: Qualité WebP. 80 tient la lisibilité du texte d'une carte en divisant le poids par **4,1** face
#: au JPEG 92 d'origine (178 Ko → 44 Ko, mesuré sur une carte réelle — compte rendu du lot).
QUALITE_WEBP = 80

#: Type MIME de la variante — WebP, servi tel quel (le proxy des images officielles sert déjà du
#: WebP : aucun client du produit n'a besoin d'un repli JPEG).
TYPE_MIME_JEU = "image/webp"


class PhotoIndecodable(Exception):
    """La photo stockée ne se décode pas : on le dit, on ne produit pas une image vide."""


def cle_image_jeu(user_id: uuid.UUID, item_id: uuid.UUID) -> str:
    """La clé de stockage de la variante de jeu d'un exemplaire.

    Rangée sous le propriétaire, comme les photos d'envoi (``uploads/{user_id}/…``) : un préfixe par
    compte permet de tout effacer d'un coup à la suppression d'un compte, sans balayer le bucket.
    """
    return f"jeu/rendu/{user_id}/{item_id}.webp"


def decoder(photo: bytes) -> np.ndarray:
    """Décode la photo stockée en tableau BGR, pour la noter.

    Lève :class:`PhotoIndecodable` plutôt que de rendre un tableau vide : une photo illisible est
    une panne à nommer (elle a pourtant été normalisée à l'envoi), pas un cas normal.
    """
    tableau = cv2.imdecode(np.frombuffer(photo, dtype=np.uint8), cv2.IMREAD_COLOR)
    if tableau is None or tableau.size == 0:
        raise PhotoIndecodable("photo stockée illisible (ni JPEG ni PNG décodable)")
    return tableau


def fabriquer_image_jeu(photo: bytes) -> bytes:
    """Produit la variante de jeu (WebP, :data:`LARGEUR_JEU`×:data:`HAUTEUR_JEU`) de ``photo``.

    Recadre en « couvrant » (centré) si la source n'est pas au ratio d'une carte, puis réduit en
    Lanczos. Jamais d'agrandissement : une photo plus petite que la cible est laissée à sa taille,
    agrandir n'ajouterait aucun détail et ferait croire à une qualité qu'elle n'a pas.
    """
    with Image.open(io.BytesIO(photo)) as source:
        image = source.convert("RGB")
        largeur_cible, hauteur_cible = LARGEUR_JEU, HAUTEUR_JEU
        # Recadrage « couvrant » : on garde le centre et on coupe le débordement, plutôt que de
        # déformer la carte (une carte étirée se repère au premier coup d'œil).
        ratio_source = image.width / image.height
        ratio_cible = largeur_cible / hauteur_cible
        if abs(ratio_source - ratio_cible) > 0.001:
            if ratio_source > ratio_cible:
                largeur = round(image.height * ratio_cible)
                marge = (image.width - largeur) // 2
                image = image.crop((marge, 0, marge + largeur, image.height))
            else:
                hauteur = round(image.width / ratio_cible)
                marge = (image.height - hauteur) // 2
                image = image.crop((0, marge, image.width, marge + hauteur))
        if image.width > largeur_cible:
            image = image.resize((largeur_cible, hauteur_cible), Image.LANCZOS)
        sortie = io.BytesIO()
        image.save(sortie, format="WEBP", quality=QUALITE_WEBP, method=4)
        return sortie.getvalue()


__all__ = [
    "HAUTEUR_JEU",
    "LARGEUR_JEU",
    "QUALITE_WEBP",
    "TYPE_MIME_JEU",
    "PhotoIndecodable",
    "cle_image_jeu",
    "decoder",
    "fabriquer_image_jeu",
]
