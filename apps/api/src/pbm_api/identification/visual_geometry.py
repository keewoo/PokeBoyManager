"""Normalisation géométrique partagée entre l'image officielle (indexation, mission
`v3-identification-visuelle` point 1) et le recadrage utilisateur (comparaison, point 2) : les
deux doivent être ramenés au même cadrage avant de calculer une empreinte, sinon une simple
différence d'échelle ou de bordure fait diverger deux hachages qui devraient être proches.

La zone d'illustration est approximée par un rectangle relatif fixe (mise en page Pokémon TCG
standard : bandeau de nom en haut, illustration au centre, texte/attaques en bas) — une
simplification documentée (compte rendu du lot) : elle ne colle pas exactement à chaque design
(promos, cartes pleine illustration), mais reste stable d'une carte à l'autre, ce qui est ce dont
une comparaison par hachage a besoin (le même décalage systématique des deux côtés de la
comparaison n'affecte pas la distance de Hamming).
"""

import cv2
import numpy as np

from pbm_api.detection.geometry import CARD_HEIGHT_PX, CARD_WIDTH_PX

# Fraction de la largeur/hauteur du cadre 630×880 occupée par la zone d'illustration — mesurée à
# l'œil sur plusieurs générations de cartes (Base/XY/Écarlate-Violet) : bandeau de nom (~0-11 %),
# illustration (~11-58 %), texte/attaques/numéro (58-100 %). Une marge latérale exclut le liseré
# coloré de rareté/type qui varie plus que l'illustration elle-même.
ILLUSTRATION_TOP_RATIO = 0.11
ILLUSTRATION_BOTTOM_RATIO = 0.58
ILLUSTRATION_LEFT_RATIO = 0.08
ILLUSTRATION_RIGHT_RATIO = 0.92


def normalize_to_card_canvas(image_bgr: np.ndarray) -> np.ndarray:
    """Redimensionne n'importe quelle image (photo officielle basse définition, recadrage déjà
    redressé) vers le même cadre 630×880 px que `pbm_api.detection.geometry` — sans ça, une
    image officielle 245×337 et un recadrage utilisateur 630×880 ne sont pas comparables pixel à
    pixel avant réduction en hachage."""
    return cv2.resize(
        image_bgr, (CARD_WIDTH_PX, CARD_HEIGHT_PX), interpolation=cv2.INTER_AREA
    )


def illustration_region(card_canvas_bgr: np.ndarray) -> np.ndarray:
    """Découpe la zone d'illustration d'une image déjà ramenée au cadre 630×880
    (`normalize_to_card_canvas`)."""
    height, width = card_canvas_bgr.shape[:2]
    top = int(height * ILLUSTRATION_TOP_RATIO)
    bottom = int(height * ILLUSTRATION_BOTTOM_RATIO)
    left = int(width * ILLUSTRATION_LEFT_RATIO)
    right = int(width * ILLUSTRATION_RIGHT_RATIO)
    return card_canvas_bgr[top:bottom, left:right]
