"""Les **variantes de jeu** d'une photo personnelle : produites à l'avance, bornées en poids.

Le risque nommé par la fiche de ``j-rendu-carte`` : servir la photo d'origine pleine résolution. Le
recadrage redressé que porte ``collection_items.photo_s3_key`` fait 630×880 en JPEG qualité 92, soit
**178 Ko** par carte (mesuré sur une carte réelle). Un plateau en montre une vingtaine, une partie
en traverse soixante : **3,5 Mo** à l'écran et **10,5 Mo** pour un deck, sur un téléphone.

Le lot ``j-rendu-carte`` a posé **une** variante (420×587, 44 Ko), servie aussi bien au plateau
qu'au zoom. Le lot ``j-assets-pipeline`` la dédouble, parce qu'une partie affiche jusqu'à 120 cartes
et que 120 × 44 Ko = 5,2 Mo — le jeu meurt là, sur un téléphone en 4G :

* :data:`VARIANTE_PLATEAU` (192×268, **12 Ko**) — la carte telle qu'elle est posée dans l'arène
  (≈ 60 à 96 px CSS, soit 192 px sur un écran à densité double) et la vignette d'une fenêtre de
  décision. C'est **elle** que porte ``rendu.url``, donc elle que le plateau charge 120 fois ;
* :data:`VARIANTE_ZOOM` (420×587, **45 Ko**) — le zoom, ``min(70vw, 16rem)`` soit 256 px CSS, 512 px
  à densité double. Portée par ``rendu.url_zoom``, chargée **une carte à la fois**, à la demande.

Au-delà de ces largeurs on paierait des pixels que personne ne voit ; en dessous, le texte d'une
carte cesse d'être lisible.

**Le plafond de poids est tenu par construction, pas espéré.** Chaque variante déclare son
``plafond_octets`` ; :func:`fabriquer_image_jeu` réencode à qualité décroissante tant qu'elle le
dépasse, et **lève** :class:`VarianteTropLourde` si même la qualité plancher n'y suffit pas. C'est
ce qui rend calculable le budget d'une partie (:mod:`pbm_api.jeu.budget`) : le poids d'un plateau
n'est pas une moyenne constatée, c'est une borne. Une photo si bruitée qu'elle ne tient pas sous son
plafond est déclarée inexploitable et se replie sur l'image officielle — on le **dit** (D9), on ne
sert pas 300 Ko en silence.

Poids mesurés sur une carte réelle (``base1/4``, 600×825 WebP officielle, rééchantillonnée en
630×880 JPEG 92 pour simuler la photo stockée), le 15/10/2026 sur chimera :

===========  ==========  ==========  =============
Largeur      photo nette photo       bruit pur
             (WebP)      bruitée     (incompressible)
===========  ==========  ==========  =============
192 (q76)    12,2 Ko     12,4 Ko     15,9 Ko
420 (q80)    45,2 Ko     55,7 Ko     125,9 Ko
===========  ==========  ==========  =============

Le redressement, lui, n'est **pas refait** ici : il a déjà eu lieu à la détection
(:func:`pbm_api.detection.geometry.warp_card`, lot ``v3-detection``) et la photo stockée est déjà
au format carte. Ce module ne fait que **réduire** — et recadrer en « couvrant » si la source
n'est pas exactement au ratio d'une carte (un exemplaire dont la photo n'est pas venue du parcours
de détection), plutôt que de la déformer.
"""

from __future__ import annotations

import io
import uuid
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image

from pbm_api.detection.geometry import CARD_ASPECT_RATIO

#: Type MIME des variantes — WebP, servi tel quel (le proxy des images officielles sert déjà du
#: WebP : aucun client du produit n'a besoin d'un repli JPEG).
TYPE_MIME_JEU = "image/webp"


@dataclass(frozen=True)
class Variante:
    """Une taille de rendu d'une carte en jeu : sa largeur, sa qualité, et son **plafond de poids**.

    ``plafond_octets`` n'est pas une statistique : c'est la borne que :func:`fabriquer_image_jeu`
    garantit en sortie. Le budget d'une partie (:mod:`pbm_api.jeu.budget`) se calcule à partir de
    ces plafonds — sans eux, on ne pourrait qu'espérer que le plateau reste léger.
    """

    nom: str
    largeur: int
    qualite: int
    plafond_octets: int

    @property
    def hauteur(self) -> int:
        """La hauteur au ratio d'une carte (63×88 mm) — jamais une valeur arrondie à part."""
        return round(self.largeur / CARD_ASPECT_RATIO)


#: La carte posée dans l'arène, et la vignette d'une fenêtre de décision. Chargée jusqu'à 120 fois
#: par partie : c'est elle qui décide du poids d'un plateau, d'où le plafond serré.
VARIANTE_PLATEAU = Variante(nom="plateau", largeur=192, qualite=76, plafond_octets=18 * 1024)

#: Le zoom, lisible sans pincer l'écran. Chargée une carte à la fois, à la demande du joueur.
VARIANTE_ZOOM = Variante(nom="zoom", largeur=420, qualite=80, plafond_octets=64 * 1024)

#: Toutes les variantes produites pour un exemplaire, dans l'ordre où on les fabrique (la plus
#: légère d'abord : c'est celle dont le plateau a besoin en premier).
VARIANTES: tuple[Variante, ...] = (VARIANTE_PLATEAU, VARIANTE_ZOOM)

#: Index par nom, pour relire le paramètre ``?v=`` d'une route sans fabriquer de dictionnaire.
PAR_NOM: dict[str, Variante] = {v.nom: v for v in VARIANTES}

#: Qualités de secours, essayées dans l'ordre quand la qualité nominale dépasse le plafond. En
#: dessous de 45, le texte d'une carte devient illisible : on préfère refuser la photo.
QUALITES_DE_SECOURS: tuple[int, ...] = (70, 60, 45)

# --- Compatibilité : les noms du lot `j-rendu-carte`, qui ne connaissait qu'une variante ---------
#: Largeur de la variante de zoom. Conservé : des tests et des appels antérieurs au dédoublement
#: s'y réfèrent, et sa valeur n'a pas changé.
LARGEUR_JEU = VARIANTE_ZOOM.largeur
#: Hauteur de la variante de zoom.
HAUTEUR_JEU = VARIANTE_ZOOM.hauteur
#: Qualité WebP de la variante de zoom.
QUALITE_WEBP = VARIANTE_ZOOM.qualite


class PhotoIndecodable(Exception):
    """La photo stockée ne se décode pas : on le dit, on ne produit pas une image vide."""


class VarianteTropLourde(Exception):
    """Même à la qualité plancher, la variante dépasse son plafond : on refuse de la servir.

    Levée plutôt que de rendre une image hors budget : le plafond d'une variante est ce qui rend le
    poids d'une partie calculable. Une photo dans ce cas (bruit de capteur extrême) est déclarée
    inexploitable et se replie sur l'image officielle, **en le disant**.
    """


def cle_variante(user_id: uuid.UUID, item_id: uuid.UUID, variante: Variante) -> str:
    """La clé de stockage d'une variante d'un exemplaire.

    Rangée sous le propriétaire, comme les photos d'envoi (``uploads/{user_id}/…``) : un préfixe par
    compte permet de tout effacer d'un coup à la suppression d'un compte, sans balayer le bucket.

    La variante de **zoom** garde la clé historique ``…/{item_id}.webp`` : c'est celle que portent
    les lignes ``collection_items.jeu_image_key`` écrites avant le dédoublement des variantes, et la
    renommer aurait orphelinné des milliers d'objets déjà produits pour rien.
    """
    if variante is VARIANTE_ZOOM or variante.nom == VARIANTE_ZOOM.nom:
        return f"jeu/rendu/{user_id}/{item_id}.webp"
    return f"jeu/rendu/{user_id}/{item_id}.{variante.nom}.webp"


def cle_image_jeu(user_id: uuid.UUID, item_id: uuid.UUID) -> str:
    """La clé de la variante de zoom — celle que porte ``collection_items.jeu_image_key``."""
    return cle_variante(user_id, item_id, VARIANTE_ZOOM)


def decoder(photo: bytes) -> np.ndarray:
    """Décode la photo stockée en tableau BGR, pour la noter.

    Lève :class:`PhotoIndecodable` plutôt que de rendre un tableau vide : une photo illisible est
    une panne à nommer (elle a pourtant été normalisée à l'envoi), pas un cas normal.
    """
    tableau = cv2.imdecode(np.frombuffer(photo, dtype=np.uint8), cv2.IMREAD_COLOR)
    if tableau is None or tableau.size == 0:
        raise PhotoIndecodable("photo stockée illisible (ni JPEG ni PNG décodable)")
    return tableau


def _recadrer_et_reduire(photo: bytes, variante: Variante) -> Image.Image:
    """La photo ramenée au ratio et à la largeur de ``variante``, prête à être encodée.

    Recadre en « couvrant » (centré) si la source n'est pas au ratio d'une carte, puis réduit en
    Lanczos. Jamais d'agrandissement : une photo plus petite que la cible est laissée à sa taille,
    agrandir n'ajouterait aucun détail et ferait croire à une qualité qu'elle n'a pas.
    """
    with Image.open(io.BytesIO(photo)) as source:
        image = source.convert("RGB")
        largeur_cible, hauteur_cible = variante.largeur, variante.hauteur
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
        return image


def _encoder(image: Image.Image, qualite: int) -> bytes:
    """Encode ``image`` en WebP à ``qualite``. ``method=4`` : le compromis temps/poids de Pillow."""
    sortie = io.BytesIO()
    image.save(sortie, format="WEBP", quality=qualite, method=4)
    return sortie.getvalue()


def fabriquer_image_jeu(photo: bytes, variante: Variante = VARIANTE_ZOOM) -> bytes:
    """Produit la variante ``variante`` de ``photo``, **garantie sous son plafond de poids**.

    Encode à la qualité nominale, puis réessaie aux :data:`QUALITES_DE_SECOURS` tant que le résultat
    dépasse ``variante.plafond_octets``. Lève :class:`VarianteTropLourde` si aucune qualité n'y
    suffit — c'est le seul cas où rien n'est produit, et il est nommé.

    Le défaut est la variante de **zoom** : c'était la seule variante du lot ``j-rendu-carte``, et
    les appels écrits avant le dédoublement continuent donc de produire exactement la même image.
    """
    image = _recadrer_et_reduire(photo, variante)
    dernier = b""
    for qualite in (variante.qualite, *QUALITES_DE_SECOURS):
        dernier = _encoder(image, qualite)
        if len(dernier) <= variante.plafond_octets:
            return dernier
    raise VarianteTropLourde(
        f"variante « {variante.nom} » : {len(dernier)} o même à la qualité "
        f"{QUALITES_DE_SECOURS[-1]}, plafond {variante.plafond_octets} o"
    )


__all__ = [
    "HAUTEUR_JEU",
    "LARGEUR_JEU",
    "PAR_NOM",
    "QUALITES_DE_SECOURS",
    "QUALITE_WEBP",
    "TYPE_MIME_JEU",
    "VARIANTES",
    "VARIANTE_PLATEAU",
    "VARIANTE_ZOOM",
    "PhotoIndecodable",
    "Variante",
    "VarianteTropLourde",
    "cle_image_jeu",
    "cle_variante",
    "decoder",
    "fabriquer_image_jeu",
]
