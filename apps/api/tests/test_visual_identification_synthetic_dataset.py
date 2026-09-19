"""Jeu de 100 cartes synthétiques et mesure de la comparaison visuelle (mission
`v3-identification-visuelle` point 4, objectif ≥ 60 % reconnues sans IA, aucune fausse
identification confiante).

⚠️ Aucune vraie photo ni carte physique sur chimera (voir l'avertissement de
`pbm_api.identification.visual_synthetic`) : ce test exerce la vraie mécanique de hachage sur des
images procédurales, pas une vraie photo de carte — `scripts/measure_visual_identification_rate.py`
sert à explorer le détail carte par carte pendant la mise au point (mêmes cartes, même graine).

Avant ce lot, `pbm_api.identification.visual_index`/`visual_synthetic` n'existaient pas : ce test
échoue à la collection et passe une fois les modules ajoutés.
"""

import cv2
import numpy as np

from pbm_api.identification.fingerprint import compute_phash
from pbm_api.identification.visual_build import compute_visual_hashes
from pbm_api.identification.visual_geometry import illustration_region
from pbm_api.identification.visual_index import VisualIndex
from pbm_api.identification.visual_index import resolve as resolve_visual
from pbm_api.identification.visual_synthetic import (
    generate_dataset,
    render_official_image,
    render_user_crop,
)
from pbm_api.models import Card, Set
from pbm_api.models.identification import CardVisualIndex

_TARGET_COVERAGE_WITHOUT_AI = 0.6


async def _seed(db_session, cards) -> dict[str, str]:
    sets_by_code: dict[str, Set] = {}
    card_id_by_synthetic_id: dict[str, str] = {}
    for card in cards:
        set_row = sets_by_code.get(card.set_code)
        if set_row is None:
            set_row = Set(code=card.set_code, name=card.set_code, total_cards=len(cards))
            db_session.add(set_row)
            await db_session.flush()
            sets_by_code[card.set_code] = set_row

        row = Card(set_id=set_row.id, number=card.number, name=card.name)
        db_session.add(row)
        await db_session.flush()
        card_id_by_synthetic_id[card.id] = str(row.id)

        ok, buffer = cv2.imencode(".png", render_official_image(card.base_color, card.shape_seed))
        assert ok
        full_phash, illustration_phash = compute_visual_hashes(buffer.tobytes())
        db_session.add(
            CardVisualIndex(
                card_id=row.id,
                language="fr",
                full_phash=full_phash,
                illustration_phash=illustration_phash,
            )
        )
    await db_session.flush()
    return card_id_by_synthetic_id


async def test_visual_identification_coverage_and_safety_on_synthetic_dataset(db_session):
    cards = generate_dataset()
    assert len(cards) == 100
    rng = np.random.default_rng(1)

    card_id_by_synthetic_id = await _seed(db_session, cards)
    index = await VisualIndex.load(db_session)

    confident_count = 0
    correct_among_confident = 0
    confusable_wrongly_confident = 0

    for card in cards:
        crop = render_user_crop(rng, card.base_color, card.shape_seed)
        full_phash = compute_phash(crop)
        illustration_phash = compute_phash(illustration_region(crop))
        matches = index.search(full_phash=full_phash, illustration_phash=illustration_phash)
        resolution = resolve_visual(matches)

        expected_id = card_id_by_synthetic_id[card.id]
        confident = resolution.confident_match is not None
        if not confident:
            continue

        confident_count += 1
        correct = str(resolution.confident_match.card_id) == expected_id
        correct_among_confident += int(correct)
        if card.confusable_with is not None and not correct:
            confusable_wrongly_confident += 1

    total = len(cards)
    coverage = confident_count / total
    precision = correct_among_confident / confident_count if confident_count else 0.0

    assert coverage >= _TARGET_COVERAGE_WITHOUT_AI, (
        f"coverage sans IA {coverage:.1%} ({confident_count}/{total})"
    )
    # Jamais de fausse confiance : une carte confondue avec une autre (groupe « même
    # illustration ») ne doit jamais être présentée comme sûre — mission « risques & pièges ».
    assert confusable_wrongly_confident == 0
    assert precision == 1.0, f"précision parmi les reconnues : {precision:.1%}"
