"""`pbm_api.identification.visual_resolve` (mission `v3-identification-visuelle` point 2) :
construit une extraction/candidat directement depuis le catalogue pour une correspondance
visuelle confiante — jamais une seconde recherche floue, la carte est déjà connue.

Avant ce lot, ce module n'existait pas : chacun de ces tests échoue à la collection et passe une
fois le module ajouté.
"""

import uuid

from pbm_api.identification.visual_index import VisualMatch
from pbm_api.identification.visual_resolve import (
    build_ambiguous_candidates,
    build_confident_extraction,
    visual_hint_lines,
)
from pbm_api.models import Card, CardName, Set


async def _seed_pikachu(db_session) -> Card:
    suffix = uuid.uuid4().hex[:8]
    set_row = Set(code=f"vr-{suffix}", name="Visual resolve", total_cards=50)
    db_session.add(set_row)
    await db_session.flush()
    card = Card(set_id=set_row.id, number="25", name="Pikachu")
    db_session.add(card)
    await db_session.flush()
    db_session.add_all(
        [
            CardName(card_id=card.id, language="fr", name="Pikachu"),
            CardName(card_id=card.id, language="en", name="Pikachu"),
        ]
    )
    await db_session.flush()
    return card, set_row


async def test_build_confident_extraction_fills_every_field_from_catalog(db_session):
    card, set_row = await _seed_pikachu(db_session)
    match = VisualMatch(
        card_id=card.id, language="fr", score=0.97, illustration_distance=1, full_distance=2
    )

    built = await build_confident_extraction(db_session, match)
    assert built is not None
    extraction, candidate = built

    assert extraction.name == "Pikachu"
    assert extraction.name_confidence == 1.0
    assert extraction.number == "25"
    assert extraction.set_code == set_row.code
    assert extraction.language == "fr"
    # Rien n'a été "lu" sur la photo au-delà de l'identité de la carte — l'état de l'exemplaire
    # (coins/bords/surface) reste non renseigné, jamais fabriqué (mission `v3-etat`).
    assert extraction.corner_wear is None

    assert candidate.card_id == str(card.id)
    assert candidate.preselected is True
    assert candidate.combined_score == 0.97


async def test_build_confident_extraction_returns_none_for_unknown_card(db_session):
    match = VisualMatch(
        card_id=uuid.uuid4(), language="fr", score=0.99, illustration_distance=0, full_distance=0
    )
    assert await build_confident_extraction(db_session, match) is None


async def test_build_ambiguous_candidates_marks_nothing_preselected(db_session):
    card_1, _ = await _seed_pikachu(db_session)
    card_2, _ = await _seed_pikachu(db_session)
    matches = [
        VisualMatch(
            card_id=card_1.id, language="fr", score=0.9, illustration_distance=1, full_distance=1
        ),
        VisualMatch(
            card_id=card_2.id,
            language="fr",
            score=0.89,
            illustration_distance=1,
            full_distance=2,
        ),
    ]

    candidates = await build_ambiguous_candidates(db_session, matches)

    assert len(candidates) == 2
    assert all(c.preselected is False for c in candidates)


def test_visual_hint_lines_mentions_name_number_and_set():
    from pbm_api.identification.schemas import IdentificationCandidate

    candidate = IdentificationCandidate(
        card_id="x", set_id="y", name="Pikachu", number="25", set_name="151", set_code="sv03pt5",
        catalog_score=0.9, combined_score=0.9, preselected=False,
    )
    lines = visual_hint_lines([candidate])
    assert len(lines) == 1
    assert "Pikachu" in lines[0]
    assert "25" in lines[0]
    assert "151" in lines[0]
