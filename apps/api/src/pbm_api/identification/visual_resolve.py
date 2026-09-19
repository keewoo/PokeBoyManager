"""Construction d'une extraction/candidat à partir d'un résultat de comparaison visuelle
(mission `v3-identification-visuelle` point 2) : la carte est déjà identifiée avec certitude
(correspondance confiante) ou fait partie d'un petit groupe ambigu — jamais recherchée une
seconde fois par `pbm_api.catalog.search`, qui sert le cas inverse (texte lu par l'IA, carte
inconnue à retrouver)."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.identification.schemas import CardExtraction, IdentificationCandidate
from pbm_api.identification.visual_index import VisualMatch
from pbm_api.models import Card, CardName, Set


async def _load_card_row(session: AsyncSession, card_id: uuid.UUID) -> tuple[Card, Set] | None:
    result = await session.execute(
        select(Card, Set).join(Set, Set.id == Card.set_id).where(Card.id == card_id)
    )
    return result.one_or_none()


async def _localized_name(session: AsyncSession, card: Card, language: str) -> str:
    result = await session.execute(
        select(CardName.name).where(CardName.card_id == card.id, CardName.language == language)
    )
    name = result.scalar_one_or_none()
    return name or card.name


async def _to_candidate(
    session: AsyncSession, match: VisualMatch, *, preselected: bool
) -> tuple[IdentificationCandidate, Card, Set, str] | None:
    row = await _load_card_row(session, match.card_id)
    if row is None:
        # Carte disparue du catalogue depuis l'indexation (jamais observé dans ce dépôt, l'index
        # est reconstruit après tout import) — ignorée plutôt qu'une erreur, comme un candidat
        # catalogue introuvable ailleurs dans le rapprochement.
        return None
    card, set_row = row
    name = await _localized_name(session, card, match.language)
    candidate = IdentificationCandidate(
        card_id=str(card.id),
        set_id=str(set_row.id),
        name=name,
        number=card.number,
        set_name=set_row.name,
        set_code=set_row.code,
        catalog_score=match.score,
        combined_score=match.score,
        preselected=preselected,
    )
    return candidate, card, set_row, name


async def build_confident_extraction(
    session: AsyncSession, match: VisualMatch
) -> tuple[CardExtraction, IdentificationCandidate] | None:
    """Correspondance visuelle confiante (mission point 2) : les champs viennent directement du
    catalogue, confiance 1.0 partout (rien n'a été "lu", la carte est connue avec certitude) —
    jamais repassée par le rapprochement flou, qui réintroduirait l'incertitude que la
    comparaison visuelle vient justement d'éliminer."""
    built = await _to_candidate(session, match, preselected=True)
    if built is None:
        return None
    _candidate, card, set_row, name = built
    extraction = CardExtraction(
        name=name,
        name_confidence=1.0,
        number=card.number,
        number_confidence=1.0,
        total=set_row.total_cards,
        total_confidence=1.0 if set_row.total_cards is not None else 0.0,
        set_code=set_row.code,
        set_code_confidence=1.0,
        language=match.language,
        language_confidence=1.0,
    )
    return extraction, built[0]


async def build_ambiguous_candidates(
    session: AsyncSession, matches: list[VisualMatch]
) -> list[IdentificationCandidate]:
    """Groupe « même illustration » (mission « risques & pièges ») : plusieurs candidats
    plausibles, aucun retenu automatiquement — proposés à l'IA (point 3, `visual_hint_lines`) ou
    à la validation humaine si aucune clé n'est disponible (D4)."""
    candidates = []
    for match in matches:
        built = await _to_candidate(session, match, preselected=False)
        if built is not None:
            candidates.append(built[0])
    return candidates


def visual_hint_lines(candidates: list[IdentificationCandidate]) -> list[str]:
    """Une ligne courte par candidat visuel, injectée dans le prompt d'extraction (mission point
    3) — jamais un second appel IA, juste plus de contexte dans l'appel déjà prévu."""
    return [f"{c.name} — n°{c.number}, extension {c.set_name} ({c.set_code})" for c in candidates]
