"""Note de qualité d'une photo personnelle, et **décision de repli** (lot ``j-rendu-carte``).

Jouer avec ses propres cartes est la promesse du produit. Mais une photo prise au flash par un
enfant de onze ans n'est pas toujours jouable : trop floue, trop sombre, brûlée par le reflet, ou
coupée. Sur un plateau de téléphone, une carte dans cet état n'est pas « moins belle » — elle est
**illisible**, et le joueur ne sait plus ce qu'il joue.

Ce module note donc chaque photo sur trois axes mesurables, et conclut : ``exploitable`` ou non,
avec la **raison** en français. Cette raison est ce que le constructeur de deck montre au joueur —
« ta photo de Carapuce est trop sombre, l'image officielle sera utilisée ». Un repli muet serait
pire que l'absence de repli : le joueur croirait que sa photo n'a pas été prise en compte.

Ce qui est mesuré ici, et ce qui ne l'est pas :

* la **netteté** et la **luminosité** sont mesurées sur l'image, ici ;
* le **cadrage** ne peut pas l'être : une fois la carte redressée en 630×880
  (:func:`pbm_api.detection.geometry.warp_card`), l'image *remplit* le cadre par construction —
  ce qui a été coupé l'a été **avant**. Il est donc **reçu en donnée**, depuis la qualité de
  découpe déjà mesurée à la détection (``detections.bbox["crop_quality"]``, lot ``v3-detection``) :
  on ne remesure pas ce qui a déjà été mesuré, et on ne l'invente pas quand il manque (D9 —
  ``cadrage`` vaut alors ``None``, et n'empêche rien).

Pur : aucune E/S, aucune base, aucun réseau — ``numpy``/``cv2`` sur un tableau déjà décodé. Les
seuils sont des constantes nommées, pour qu'un réglage se discute sur un chiffre plutôt que sur une
impression.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import cv2
import numpy as np

#: Variance du Laplacien en dessous de laquelle la photo est jugée **floue**. Mesurée sur la bande
#: intérieure de la carte (hors bordure), en niveaux de gris 0–255. Une photo nette de carte, riche
#: en texte et en liseré, dépasse largement ce seuil ; un flou de bougé tombe sous 30.
SEUIL_NETTETE = 60.0

#: Luminance moyenne (0–255) en dessous de laquelle la photo est jugée **trop sombre** : en dessous,
#: les couleurs du type et le texte ne se distinguent plus à la taille d'un plateau de téléphone.
SEUIL_LUMINOSITE_BASSE = 55.0

#: Luminance moyenne au-dessus de laquelle la photo est jugée **délavée** (surexposition générale).
SEUIL_LUMINOSITE_HAUTE = 225.0

#: Part de pixels **brûlés** (≥ 250) au-delà de laquelle le reflet du flash a mangé la carte. C'est
#: le défaut le plus courant d'une photo de carte brillante, et il est invisible sur la moyenne :
#: un flash peut brûler un quart de l'image en laissant une luminance moyenne tout à fait normale.
SEUIL_PART_BRULEE = 0.22

#: Part de la carte **hors du cadre** au-delà de laquelle le recadrage est jugé inexploitable. Plus
#: sévère que le seuil de seconde passe de la détection (0,30) : on peut *identifier* une carte
#: amputée de trois dixièmes, on ne peut pas la **jouer**.
SEUIL_HORS_CADRE = 0.12

#: Bande intérieure analysée (fractions de largeur/hauteur) : on écarte le liseré, dont le contraste
#: franc gonflerait la netteté de n'importe quelle image, même floue.
_BANDE = (0.10, 0.90)

#: Raisons de repli, telles qu'elles sont montrées au joueur (français, lisibles par un enfant).
RAISON_SANS_PHOTO = "aucune photo de cette carte"
RAISON_FLOUE = "photo trop floue"
RAISON_SOMBRE = "photo trop sombre"
RAISON_DELAVEE = "photo trop claire"
RAISON_BRULEE = "reflet du flash sur la carte"
RAISON_CADRAGE = "carte coupée sur la photo"
RAISON_CONFIDENTIALITE = "le propriétaire ne montre pas ses photos"
RAISON_PREFERENCE = "images officielles choisies"


@dataclass(frozen=True)
class NotePhoto:
    """La note d'une photo sur trois axes, et sa conclusion.

    * ``nettete`` — variance du Laplacien sur la bande intérieure (plus haut = plus net) ;
    * ``luminosite`` — luminance moyenne 0–255 ;
    * ``part_brulee`` — part de pixels saturés (reflet du flash), 0–1 ;
    * ``cadrage`` — part de la carte **dans** le cadre (1,0 = entière), ``None`` si inconnue ;
    * ``exploitable`` — la conclusion : la photo peut-elle être jouée telle quelle ;
    * ``raison`` — pourquoi elle ne peut pas, en français, ``None`` quand elle peut.
    """

    nettete: float
    luminosite: float
    part_brulee: float
    cadrage: float | None
    exploitable: bool
    raison: str | None

    def en_json(self) -> dict:
        """Forme JSON stockée dans ``collection_items.jeu_qualite`` et lue par l'écran."""
        return {
            "nettete": round(self.nettete, 2),
            "luminosite": round(self.luminosite, 2),
            "part_brulee": round(self.part_brulee, 4),
            "cadrage": None if self.cadrage is None else round(self.cadrage, 4),
            "exploitable": self.exploitable,
            "raison": self.raison,
        }

    @classmethod
    def depuis_json(cls, donnees: Mapping | None) -> NotePhoto | None:
        """Relit une note stockée, ou ``None`` si rien n'est stocké (jamais une note inventée)."""
        if not donnees:
            return None
        return cls(
            nettete=float(donnees.get("nettete", 0.0)),
            luminosite=float(donnees.get("luminosite", 0.0)),
            part_brulee=float(donnees.get("part_brulee", 0.0)),
            cadrage=None if donnees.get("cadrage") is None else float(donnees["cadrage"]),
            exploitable=bool(donnees.get("exploitable", False)),
            raison=donnees.get("raison"),
        )


def part_dans_le_cadre(crop_quality: Mapping | None) -> float | None:
    """La part de la carte **dans** le cadre, d'après la qualité de découpe de la détection.

    ``crop_quality`` est le dict écrit par :func:`pbm_api.detection.quality.assess_crop` dans
    ``detections.bbox["crop_quality"]`` : son ``truncated`` est la part **hors** photo. Rend
    ``None`` quand la donnée manque — un exemplaire dont la photo n'est pas venue du parcours de
    détection n'a pas de cadrage mesuré, et on ne le devine pas.
    """
    if not crop_quality or "truncated" not in crop_quality:
        return None
    try:
        hors = float(crop_quality["truncated"])
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, 1.0 - hors))


def noter_photo(image: np.ndarray, *, crop_quality: Mapping | None = None) -> NotePhoto:
    """Note la photo redressée ``image`` (BGR) et conclut sur son exploitabilité en jeu.

    L'ordre des verdicts n'est pas indifférent : on nomme d'abord le défaut qu'on **peut corriger
    en reprenant la photo** dans de meilleures conditions (cadrage, lumière), puis le flou. Le
    joueur reçoit une consigne utile, pas un diagnostic complet.
    """
    if image is None or image.size == 0:
        raise ValueError("image vide : rien à noter (aucune note par défaut, cf. D9)")

    gris = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    hauteur, largeur = gris.shape[:2]
    y0, y1 = int(hauteur * _BANDE[0]), int(hauteur * _BANDE[1])
    x0, x1 = int(largeur * _BANDE[0]), int(largeur * _BANDE[1])
    interieur = gris[y0:y1, x0:x1]
    if interieur.size == 0:  # image minuscule : la bande intérieure est vide, on prend tout
        interieur = gris

    nettete = float(cv2.Laplacian(interieur, cv2.CV_64F).var())
    luminosite = float(np.mean(interieur))
    part_brulee = float(np.count_nonzero(interieur >= 250) / interieur.size)
    cadrage = part_dans_le_cadre(crop_quality)

    raison: str | None = None
    if cadrage is not None and cadrage < 1.0 - SEUIL_HORS_CADRE:
        raison = RAISON_CADRAGE
    elif luminosite < SEUIL_LUMINOSITE_BASSE:
        raison = RAISON_SOMBRE
    elif part_brulee > SEUIL_PART_BRULEE:
        raison = RAISON_BRULEE
    elif luminosite > SEUIL_LUMINOSITE_HAUTE:
        raison = RAISON_DELAVEE
    elif nettete < SEUIL_NETTETE:
        raison = RAISON_FLOUE

    return NotePhoto(
        nettete=nettete,
        luminosite=luminosite,
        part_brulee=part_brulee,
        cadrage=cadrage,
        exploitable=raison is None,
        raison=raison,
    )


__all__ = [
    "RAISON_BRULEE",
    "RAISON_CADRAGE",
    "RAISON_CONFIDENTIALITE",
    "RAISON_DELAVEE",
    "RAISON_FLOUE",
    "RAISON_PREFERENCE",
    "RAISON_SANS_PHOTO",
    "RAISON_SOMBRE",
    "SEUIL_HORS_CADRE",
    "SEUIL_LUMINOSITE_BASSE",
    "SEUIL_LUMINOSITE_HAUTE",
    "SEUIL_NETTETE",
    "SEUIL_PART_BRULEE",
    "NotePhoto",
    "noter_photo",
    "part_dans_le_cadre",
]
