"""Contrôle de qualité d'un recadrage (lots `h1-decoupe-fiable` puis `h1-seconde-passe-ia`).

Deux défauts se ressemblent à l'œil et se mesurent différemment :

- une **jointure** : le cadre est à cheval sur deux cartes. Une arête droite le traverse d'un
  bord à l'autre. La position de cette arête donne la part du cadre qui n'appartient pas à la
  carte visée.
- un **hors-cadre** : la carte déborde de la photo, le cadre est donc tronqué par le bord de
  l'image. Se mesure sur le quadrilatère, pas sur les pixels.

`truncated` réunit les deux en une seule fraction, de 0 à 1. C'est elle que lit le déclencheur
de seconde passe.

On SIGNALE, on ne supprime jamais : une carte écartée en silence est pire qu'une découpe
douteuse annoncée — l'utilisateur peut corriger ce qu'il voit, pas ce qui a disparu.
"""

from dataclasses import dataclass

import cv2
import numpy as np

# Bande examinée : on ignore les bords, c'est là que vit le liseré de la carte elle-même.
_BANDE_INTERIEURE = (0.12, 0.88)
# On ignore une frange aux extrémités de chaque ligne : le redressement laisse des coins
# imparfaits, et une arête qui s'y arrête n'est pas une jointure.
_FRANGE = 0.03
# Une jointure traverse le cadre d'un bord à l'autre : mesuré sur le jeu synthétique, une
# découpe à cheval sort à 1,000 quel que soit le décalage, une carte bien recadrée à 0,000.
# Le seuil est posé à 0,92 et non 0,85 : à 0,85, un reflet de pochette qui barre la carte sur
# toute sa hauteur passait pour une jointure (1 faux positif sur 147 recadrages justes).
_COUVERTURE_JOINTURE = 0.92


@dataclass(frozen=True)
class CropQuality:
    """Verdict sur un recadrage."""

    seam: bool  # deux cartes se partagent probablement le cadre
    score: float  # 0..1 — couverture de la plus longue arête traversante trouvée
    axis: str | None  # "horizontale" | "verticale" | None
    truncated: float = 0.0  # 0..1 — part du cadre qui n'est pas la carte visée
    reason: str | None = None  # "jointure" | "hors-cadre" | None

    def as_dict(self) -> dict:
        return {
            "seam": self.seam,
            "score": round(self.score, 3),
            "axis": self.axis,
            "truncated": round(self.truncated, 3),
            "reason": self.reason,
        }


def _plus_forte_arete(edges: np.ndarray, *, horizontale: bool) -> tuple[float, float]:
    """Couverture de la plus longue arête traversante, et sa position relative dans le cadre.

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
        taille = hauteur
    else:
        reunies = cv2.dilate(edges, np.ones((1, 3), np.uint8))
        debut, fin = int(largeur * _BANDE_INTERIEURE[0]), int(largeur * _BANDE_INTERIEURE[1])
        marge = int(hauteur * _FRANGE)
        bande = reunies[marge : hauteur - marge, debut:fin]
        couverture = (bande > 0).mean(axis=0) if bande.size else np.array([])
        taille = largeur

    if not couverture.size:
        return 0.0, 0.0
    indice = int(couverture.argmax())
    return float(couverture[indice]), (debut + indice) / taille


def _part_hors_photo(quad: np.ndarray | None, image_shape: tuple[int, ...] | None) -> float:
    """Part du quadrilatère qui tombe hors de la photo — la carte déborde, le cadre est tronqué.

    Mesuré par rastérisation plutôt que par une formule d'aire : le quadrilatère est quelconque
    (perspective), et découper analytiquement son intersection avec le rectangle de l'image
    coûterait plus cher que de compter des pixels sur un masque.
    """
    if quad is None or image_shape is None:
        return 0.0
    hauteur, largeur = image_shape[:2]
    points = np.asarray(quad, dtype=np.float32)
    x_min, y_min = points.min(axis=0)
    x_max, y_max = points.max(axis=0)
    # Masque dans le repère du quadrilatère étendu, pour voir ce qui dépasse.
    marge = 2
    decalage = np.array([x_min - marge, y_min - marge], dtype=np.float32)
    w = int(np.ceil(x_max - x_min)) + 2 * marge
    h = int(np.ceil(y_max - y_min)) + 2 * marge
    if w <= 0 or h <= 0:
        return 0.0
    masque = np.zeros((h, w), dtype=np.uint8)
    cv2.fillConvexPoly(masque, (points - decalage).astype(np.int32), 255)
    aire = int((masque > 0).sum())
    if aire == 0:
        return 0.0

    dedans = np.zeros_like(masque)
    x0 = int(max(0, -decalage[0]))
    y0 = int(max(0, -decalage[1]))
    x1 = int(min(w, largeur - decalage[0]))
    y1 = int(min(h, hauteur - decalage[1]))
    if x1 > x0 and y1 > y0:
        dedans[y0:y1, x0:x1] = 255
    garde = int(((masque > 0) & (dedans > 0)).sum())
    return max(0.0, 1.0 - garde / aire)


def assess_crop(
    crop: np.ndarray,
    *,
    quad: np.ndarray | None = None,
    image_shape: tuple[int, ...] | None = None,
) -> CropQuality:
    """Juge un recadrage déjà redressé (sortie de `geometry.warp_card`).

    `quad` et `image_shape` sont facultatifs : sans eux, seul le contrôle de jointure s'applique.
    """
    hors_photo = _part_hors_photo(quad, image_shape)

    if crop is None or crop.size == 0:
        return CropQuality(
            seam=False,
            score=0.0,
            axis=None,
            truncated=hors_photo,
            reason="hors-cadre" if hors_photo > 0 else None,
        )

    gris = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    contours = cv2.Canny(cv2.GaussianBlur(gris, (3, 3), 0), 60, 180)

    couv_h, pos_h = _plus_forte_arete(contours, horizontale=True)
    couv_v, pos_v = _plus_forte_arete(contours, horizontale=False)
    if couv_h >= couv_v:
        score, position, axe = couv_h, pos_h, "horizontale"
    else:
        score, position, axe = couv_v, pos_v, "verticale"

    seam = score >= _COUVERTURE_JOINTURE
    # La position de la jointure donne la part du cadre occupée par l'autre carte : une arête à
    # 25 % du haut veut dire que le quart supérieur appartient à la voisine.
    part_jointure = min(position, 1.0 - position) if seam else 0.0

    truncated = max(part_jointure, hors_photo)
    if not seam and hors_photo <= 0:
        raison = None
    elif part_jointure >= hors_photo:
        raison = "jointure"
    else:
        raison = "hors-cadre"

    return CropQuality(
        seam=seam,
        score=score,
        axis=axe if seam else None,
        truncated=truncated,
        reason=raison,
    )
