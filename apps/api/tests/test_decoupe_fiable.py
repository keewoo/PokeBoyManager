"""Lot `h1-decoupe-fiable` — une découpe à cheval sur deux cartes doit se voir.

Le contrôle du rapport hauteur/largeur (±12 %) ne voit rien d'un cadre glissé d'une demi-carte :
il garde un rapport parfaitement valide. Ces tests portent donc sur le CONTENU du recadrage, et
sur le choix du contour au moment d'affiner une boîte du modèle vision.
"""

import cv2
import numpy as np

from pbm_api.detection.geometry import warp_card
from pbm_api.detection.llm_fallback import NormalizedBox
from pbm_api.detection.pipeline import refine_box_with_opencv
from pbm_api.detection.quality import assess_crop
from pbm_api.detection.synthetic import (
    CARD_H,
    CARD_W,
    card_quad,
    draw_card,
    generate_dataset,
    noisy_background,
)

_BLANC = (245, 245, 245)


def _deux_cartes_empilees() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Deux cartes qui se touchent, l'une au-dessus de l'autre.

    Rend le canevas et les deux quads.
    """
    rng = np.random.default_rng(20260922)
    canevas = noisy_background(rng, (760, 420), (38, 38, 42))
    haut = card_quad((210.0, 150.0), 0.0)
    bas = card_quad((210.0, 150.0 + CARD_H), 0.0)
    draw_card(canevas, haut, fill=(70, 120, 200), border=_BLANC)
    draw_card(canevas, bas, fill=(200, 120, 70), border=_BLANC)
    return canevas, haut, bas


class TestQualiteDuRecadrage:
    def test_une_carte_bien_recadree_na_pas_de_jointure(self):
        canevas, haut, _ = _deux_cartes_empilees()

        verdict = assess_crop(warp_card(canevas, haut))

        assert verdict.seam is False, (
            "le liseré de la carte et son illustration ne doivent jamais passer pour une "
            f"jointure (score {verdict.score:.2f})"
        )

    def test_un_recadrage_a_cheval_est_signale(self):
        canevas, _, _ = _deux_cartes_empilees()
        # Décalé d'une demi-carte : il prend le bas de la carte du haut et le haut de l'autre.
        a_cheval = card_quad((210.0, 150.0 + CARD_H / 2), 0.0)

        verdict = assess_crop(warp_card(canevas, a_cheval))

        assert verdict.seam is True, f"jointure non détectée (score {verdict.score:.2f})"
        assert verdict.axis == "horizontale"

    def test_un_recadrage_vide_ne_fait_pas_tomber_le_controle(self):
        assert assess_crop(np.zeros((0, 0, 3), dtype=np.uint8)).seam is False


class TestAffinageDuneBoiteDuModele:
    def test_retient_la_carte_visee_et_non_la_plus_grande_du_voisinage(self):
        """Le défaut constaté en production le 22/09 : la boîte du modèle visait une carte, la
        marge d'affinage faisait entrer la voisine dans la zone analysée, et comme la voisine y
        était plus complète — donc plus grande — c'était elle qui gagnait. La carte ressortait
        alors sous le nom de sa voisine."""
        rng = np.random.default_rng(20260922)
        canevas = noisy_background(rng, (520, 780), (38, 38, 42))

        # À gauche une carte à l'échelle normale (la visée), à droite une nettement plus grande.
        visee = card_quad((150.0, 260.0), 0.0)
        voisine = card_quad((420.0, 260.0), 0.0, scale=1.45)
        draw_card(canevas, visee, fill=(70, 120, 200), border=_BLANC)
        draw_card(canevas, voisine, fill=(200, 120, 70), border=_BLANC)

        hauteur, largeur = canevas.shape[:2]
        x, y, w, h = cv2.boundingRect(visee.astype(np.float32))
        boite = NormalizedBox(
            x_min=x / largeur, y_min=y / hauteur, x_max=(x + w) / largeur, y_max=(y + h) / hauteur
        )

        quad = refine_box_with_opencv(canevas, boite)

        centre_x = float(quad[:, 0].mean())
        assert abs(centre_x - 150.0) < CARD_W / 2, (
            f"le contour retenu est centré en x={centre_x:.0f} : c'est la voisine (x≈420), "
            "pas la carte visée (x≈150)"
        )


class TestSurLeJeuSynthetiqueComplet:
    def test_aucun_recadrage_juste_nest_signale_a_tort(self):
        """Le garde-fou ne vaut que s'il ne crie pas au loup : un utilisateur qui voit
        « découpe douteuse » sur des cartes correctes cesse de lire l'avertissement.

        Mesuré à l'écriture du lot : 0 faux positif sur 147 recadrages justes. C'est ce qui a
        fait monter le seuil de 0,85 à 0,92 — à 0,85, un reflet de pochette barrant la carte sur
        toute sa hauteur passait pour une jointure."""
        signales = [
            (photo.id, verdict.score)
            for photo in generate_dataset()
            for quad in photo.ground_truth_quads
            if (verdict := assess_crop(warp_card(photo.image, quad))).seam
        ]

        assert signales == [], f"recadrages justes signalés à tort : {signales}"

    def test_toute_decoupe_decalee_est_prise(self):
        """De 20 % à 80 % de décalage : c'est la plage où le cadre contient deux morceaux de
        cartes. En dessous et au-dessus, il n'y a plus de jointure à voir."""
        canevas, _, _ = _deux_cartes_empilees()

        for fraction in (0.2, 0.35, 0.5, 0.65, 0.8):
            quad = card_quad((210.0, 150.0 + CARD_H * fraction), 0.0)
            verdict = assess_crop(warp_card(canevas, quad))
            assert verdict.seam is True, (
                f"décalage de {fraction:.0%} non détecté ({verdict.score:.3f})"
            )
