"""Contrôle de qualité d'un recadrage (lot `h1-decoupe-fiable`).

Le contrôle du rapport hauteur/largeur de `opencv_pipeline` (±12 %) rejette une découpe qui
FUSIONNE deux cartes, mais il ne voit rien d'une découpe DÉCALÉE : un cadre glissé d'une
demi-carte garde un rapport parfaitement valide. Le garde-fou doit donc porter sur le CONTENU
du recadrage, pas sur sa forme.

Signal retenu : une **jointure**, c'est-à-dire une arête droite qui traverse le cadre d'un bord
à l'autre, à l'intérieur. Une carte bien recadrée n'en a pas : ses lignes internes (bas de
l'illustration, séparateur des attaques) vivent à l'INTÉRIEUR de son liseré et n'atteignent
jamais les bords du recadrage. Deux demi-cartes, elles, se touchent sur toute la largeur.

On SIGNALE, on ne supprime jamais. Un seuil trop strict écarterait des cartes valides, et une
carte écartée en silence est pire qu'une découpe douteuse annoncée : l'utilisateur peut corriger
ce qu'il voit, pas ce qui a disparu.
"""

from dataclasses import dataclass

import cv2
import numpy as np

# Bande examinée : on ignore les bords, c'est là que vit le liseré de la carte elle-même.
_BANDE_INTERIEURE = (0.12, 0.88)
# On ignore aussi une frange aux extrémités de chaque ligne : le redressement laisse des coins
# imparfaits, et une arête qui s'y arrête n'est pas une jointure.
_FRANGE = 0.03
# Une jointure traverse le cadre d'un bord à l'autre : mesuré sur le jeu synthétique, une
# découpe à cheval sort à 1,000 quel que soit le décalage, une carte bien recadrée à 0,000.
# Le seuil est posé à 0,92 et non 0,85 : à 0,85, un reflet de pochette qui barre la carte sur
# toute sa hauteur passait pour une jointure (1 faux positif sur 147 recadrages justes).
# Signaler une carte valide coûte un geste inutile à l'utilisateur — la marge reste immense.
_COUVERTURE_JOINTURE = 0.92


@dataclass(frozen=True)
class CropQuality:
    """Verdict sur un recadrage. `seam` vrai = deux cartes se partagent probablement le cadre."""

    seam: bool
    score: float  # 0..1 — couverture de la plus longue arête traversante trouvée
    axis: str | None  # "horizontale" | "verticale" | None

    def as_dict(self) -> dict:
        return {"seam": self.seam, "score": round(self.score, 3), "axis": self.axis}


def _meilleure_couverture(edges: np.ndarray, *, horizontale: bool) -> float:
    """Plus forte proportion de pixels de contour sur une ligne (ou colonne) de la bande.

    Les arêtes se répartissent sur deux ou trois pixels après le redressement : on les réunit
    par une dilatation dans l'axe perpendiculaire avant de mesurer, sinon une jointure bien
    réelle se compte deux fois à moitié.
    """
    hauteur, largeur = edges.shape
    if horizontale:
        reunies = cv2.dilate(edges, np.ones((3, 1), np.uint8))
        debut, fin = int(hauteur * _BANDE_INTERIEURE[0]), int(hauteur * _BANDE_INTERIEURE[1])
        marge = int(largeur * _FRANGE)
        bande = reunies[debut:fin, marge : largeur - marge]
        couverture = (bande > 0).mean(axis=1) if bande.size else np.array([])
    else:
        reunies = cv2.dilate(edges, np.ones((1, 3), np.uint8))
        debut, fin = int(largeur * _BANDE_INTERIEURE[0]), int(largeur * _BANDE_INTERIEURE[1])
        marge = int(hauteur * _FRANGE)
        bande = reunies[marge : hauteur - marge, debut:fin]
        couverture = (bande > 0).mean(axis=0) if bande.size else np.array([])
    return float(couverture.max()) if couverture.size else 0.0


def assess_crop(crop: np.ndarray) -> CropQuality:
    """Juge un recadrage déjà redressé (sortie de `geometry.warp_card`)."""
    if crop is None or crop.size == 0:
        return CropQuality(seam=False, score=0.0, axis=None)

    gris = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    contours = cv2.Canny(cv2.GaussianBlur(gris, (3, 3), 0), 60, 180)

    horizontale = _meilleure_couverture(contours, horizontale=True)
    verticale = _meilleure_couverture(contours, horizontale=False)

    if horizontale >= verticale:
        score, axe = horizontale, "horizontale"
    else:
        score, axe = verticale, "verticale"

    if score < _COUVERTURE_JOINTURE:
        return CropQuality(seam=False, score=score, axis=None)
    return CropQuality(seam=True, score=score, axis=axe)
