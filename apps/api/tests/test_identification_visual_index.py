"""`pbm_api.identification.visual_index` (mission `v3-identification-visuelle` point 2) : plus
proches voisins par distance de Hamming pondérée (illustration + carte entière) et décision
« reconnue sans IA » — logique pure, testée sans base de données (`VisualIndex` construit
directement en mémoire) ; `test_identification_service.py` couvre l'intégration bout en bout.

Avant ce lot, `pbm_api.identification.visual_index` n'existait pas : chacun de ces tests échoue
à la collection et passe une fois le module ajouté.
"""

import uuid

import numpy as np

from pbm_api.identification.visual_index import (
    AMBIGUITY_MARGIN,
    CONFIDENT_SCORE_THRESHOLD,
    VisualIndex,
    VisualMatch,
    resolve,
)

CARD_A = uuid.uuid4()
CARD_B = uuid.uuid4()
CARD_C = uuid.uuid4()


def _index(rows: list[tuple[uuid.UUID, str, int, int]]) -> VisualIndex:
    """`rows` = (card_id, language, full_phash, illustration_phash)."""
    mask = 0xFFFFFFFFFFFFFFFF
    return VisualIndex(
        card_ids=[r[0] for r in rows],
        languages=[r[1] for r in rows],
        full_phashes=np.array([r[2] & mask for r in rows], dtype=np.uint64),
        illustration_phashes=np.array([r[3] & mask for r in rows], dtype=np.uint64),
    )


def _fake_match(card_id: uuid.UUID, score: float, *, language: str = "fr") -> VisualMatch:
    return VisualMatch(
        card_id=card_id, language=language, score=score, illustration_distance=0, full_distance=0
    )


def test_search_returns_empty_on_empty_index():
    index = _index([])
    assert index.search(full_phash=0, illustration_phash=0) == []


def test_search_ranks_exact_match_first():
    index = _index(
        [
            (CARD_A, "fr", 0b1010, 0b1010),
            (CARD_B, "fr", 0xFFFFFFFFFFFFFFFF, 0xFFFFFFFFFFFFFFFF),  # tous les bits opposés
        ]
    )
    matches = index.search(full_phash=0b1010, illustration_phash=0b1010)
    assert matches[0].card_id == CARD_A
    assert matches[0].score == 1.0
    assert matches[0].illustration_distance == 0
    assert matches[0].full_distance == 0


def test_search_keeps_only_best_score_per_card_across_languages():
    """Une carte apparaît deux fois (fr/en) — une seule ligne dans le résultat, la meilleure."""
    index = _index(
        [
            (CARD_A, "fr", 0, 0),  # loin de la cible
            (CARD_A, "en", 0b1, 0b1),  # 1 bit d'écart, plus proche
        ]
    )
    matches = index.search(full_phash=0b1, illustration_phash=0b1)
    assert len(matches) == 1
    assert matches[0].language == "en"
    assert matches[0].full_distance == 0


def test_search_respects_limit_and_order():
    rows = [
        (uuid.uuid4(), "fr", i, i)  # distance croissante avec i (nombre de bits à 1 croissant)
        for i in (0, 0b1, 0b11, 0b111, 0b1111, 0b11111)
    ]
    index = _index(rows)
    matches = index.search(full_phash=0, illustration_phash=0, limit=3)
    assert len(matches) == 3
    scores = [m.score for m in matches]
    assert scores == sorted(scores, reverse=True)


def test_resolve_returns_none_below_confidence_threshold():
    matches = [_fake_match(CARD_A, CONFIDENT_SCORE_THRESHOLD - 0.1)]
    resolution = resolve(matches)
    assert resolution.confident_match is None
    assert resolution.candidates == matches


def test_resolve_confident_when_clear_winner():
    matches = [
        _fake_match(CARD_A, 0.98),
        _fake_match(CARD_B, 0.98 - AMBIGUITY_MARGIN - 0.05),
    ]
    resolution = resolve(matches)
    assert resolution.confident_match is not None
    assert resolution.confident_match.card_id == CARD_A


def test_resolve_ambiguous_when_two_different_cards_are_close():
    """Groupe « même illustration » (mission « risques & pièges ») : deux cartes différentes se
    disputent le premier rang à la marge près — jamais résolu automatiquement."""
    matches = [
        _fake_match(CARD_A, 0.95),
        _fake_match(CARD_B, 0.95 - AMBIGUITY_MARGIN + 0.01),
    ]
    resolution = resolve(matches)
    assert resolution.confident_match is None
    assert resolution.candidates == matches


def test_resolve_not_ambiguous_when_runner_up_is_same_card_different_language():
    """Les lignes fr/en de la MÊME carte ne comptent jamais comme un concurrent : `VisualIndex.
    search` a déjà dédoublonné par carte, mais `resolve` doit rester robuste si jamais un appelant
    lui passait malgré tout deux entrées du même `card_id`."""
    matches = [
        _fake_match(CARD_A, 0.95, language="fr"),
        _fake_match(CARD_A, 0.94, language="en"),
        _fake_match(CARD_C, 0.5),
    ]
    resolution = resolve(matches)
    assert resolution.confident_match is not None
    assert resolution.confident_match.card_id == CARD_A
