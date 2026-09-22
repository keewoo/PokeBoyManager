"""Lot `h1-seconde-passe-ia` — la règle de JF du 22/09/2026.

> si la découpe présente 30 % d'image tronquée OU si le taux de reconnaissance moyen est
> inférieur à 55 %, alors on demande à l'IA de faire ET la découpe, ET la reconnaissance.
"""

import numpy as np
import pytest

from pbm_api.detection.geometry import warp_card
from pbm_api.detection.quality import assess_crop
from pbm_api.detection.seconde_passe import (
    SEUIL_CONFIANCE_MOYENNE,
    SEUIL_TRONCATURE,
    evaluer,
)
from pbm_api.detection.synthetic import CARD_H, card_quad, draw_card, noisy_background

_BLANC = (245, 245, 245)


class _Detection:
    """Le strict nécessaire : `evaluer` ne lit que `bbox` et `candidates`."""

    def __init__(self, truncated: float = 0.0, confiances: list[float] | None = None):
        self.bbox = {"crop_quality": {"truncated": truncated}}
        self.candidates = (
            None if confiances is None else [{"combined_score": c} for c in confiances]
        )


def _deux_cartes_empilees():
    rng = np.random.default_rng(20260922)
    canevas = noisy_background(rng, (760, 420), (38, 38, 42))
    haut = card_quad((210.0, 150.0), 0.0)
    bas = card_quad((210.0, 150.0 + CARD_H), 0.0)
    draw_card(canevas, haut, fill=(70, 120, 200), border=_BLANC)
    draw_card(canevas, bas, fill=(200, 120, 70), border=_BLANC)
    return canevas, haut


class TestMesureDeLaTroncature:
    @pytest.mark.parametrize("decalage", [0.2, 0.3, 0.5])
    def test_la_position_de_la_jointure_donne_la_part_tronquee(self, decalage):
        """Une jointure à 20 % du haut veut dire qu'un cinquième du cadre appartient à l'autre
        carte. C'est cette fraction que lit le déclencheur de seconde passe."""
        canevas, _ = _deux_cartes_empilees()
        quad = card_quad((210.0, 150.0 + CARD_H * decalage), 0.0)

        verdict = assess_crop(warp_card(canevas, quad))

        attendu = min(decalage, 1.0 - decalage)
        assert verdict.seam is True
        assert verdict.reason == "jointure"
        assert abs(verdict.truncated - attendu) < 0.08, (
            f"part tronquée mesurée {verdict.truncated:.2f}, attendue ≈ {attendu:.2f}"
        )

    def test_une_carte_bien_recadree_nest_pas_tronquee(self):
        canevas, haut = _deux_cartes_empilees()

        verdict = assess_crop(warp_card(canevas, haut), quad=haut, image_shape=canevas.shape)

        assert verdict.truncated == 0.0
        assert verdict.reason is None

    def test_une_carte_qui_deborde_de_la_photo_est_tronquee(self):
        """Sans jointure visible : la carte sort par le bord de l'image, le recadrage est
        amputé d'autant. Se mesure sur le quadrilatère, pas sur les pixels."""
        rng = np.random.default_rng(20260922)
        canevas = noisy_background(rng, (400, 400), (38, 38, 42))
        # Carte centrée sur le bord droit : la moitié tombe hors de la photo.
        quad = card_quad((400.0, 200.0), 0.0)
        draw_card(canevas, quad, fill=(70, 120, 200), border=_BLANC)

        verdict = assess_crop(warp_card(canevas, quad), quad=quad, image_shape=canevas.shape)

        assert verdict.reason == "hors-cadre"
        assert 0.4 < verdict.truncated < 0.6, f"part hors photo mesurée {verdict.truncated:.2f}"


class TestRegleDeSecondePasse:
    def test_pas_de_seconde_passe_quand_tout_va_bien(self):
        verdict = evaluer([_Detection(truncated=0.05, confiances=[0.88, 0.4])])

        assert verdict.needed is False
        assert verdict.reason is None

    def test_trente_pour_cent_de_troncature_declenche(self):
        verdict = evaluer(
            [
                _Detection(truncated=0.05, confiances=[0.9]),
                _Detection(truncated=SEUIL_TRONCATURE, confiances=[0.9]),
            ]
        )

        assert verdict.needed is True
        assert verdict.reason == "troncature"
        assert verdict.truncated_max == pytest.approx(SEUIL_TRONCATURE)

    def test_juste_sous_trente_pour_cent_ne_declenche_pas(self):
        verdict = evaluer([_Detection(truncated=SEUIL_TRONCATURE - 0.01, confiances=[0.9])])

        assert verdict.needed is False

    def test_confiance_moyenne_sous_cinquante_cinq_declenche(self):
        """Les découpes constatées le 22/09 sortaient à 34 % et 43 %."""
        verdict = evaluer(
            [
                _Detection(confiances=[0.34]),
                _Detection(confiances=[0.43]),
                _Detection(confiances=[0.8]),
            ]
        )

        assert verdict.needed is True
        assert verdict.reason == "confiance"
        assert verdict.mean_confidence == pytest.approx((0.34 + 0.43 + 0.80) / 3)

    def test_une_moyenne_juste_au_dessus_du_seuil_ne_declenche_pas(self):
        verdict = evaluer([_Detection(confiances=[SEUIL_CONFIANCE_MOYENNE])])

        assert verdict.needed is False

    def test_les_deux_raisons_se_cumulent(self):
        verdict = evaluer([_Detection(truncated=0.6, confiances=[0.2])])

        assert verdict.reason == "troncature+confiance"

    def test_une_detection_sans_candidat_ne_compte_pas_comme_zero(self):
        """Une détection non identifiée (job interrompu) n'a rien à dire sur la qualité du
        rapprochement. La compter à zéro ferait chuter la moyenne et déclencherait une seconde
        passe pour une raison qui n'est pas la bonne."""
        verdict = evaluer([_Detection(confiances=[0.9]), _Detection(confiances=None)])

        assert verdict.mean_confidence == pytest.approx(0.9)
        assert verdict.needed is False

    def test_aucune_detection_ne_declenche_rien(self):
        verdict = evaluer([])

        assert verdict.needed is False
        assert verdict.mean_confidence is None
