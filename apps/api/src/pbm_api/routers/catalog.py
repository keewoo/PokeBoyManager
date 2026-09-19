"""Recherche dans le catalogue — mission `v2-recherche`, point 1.

Catalogue public (pas d'utilisateur, pas de session) : aucun filtrage par `user_id`, le contrôle
sécurité de ce lot est sans objet (voir `docs/roadmap/comptes-rendus/v2-recherche.md`).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.catalog.search import DEFAULT_LIMIT, CardCandidate, match_candidates, parse_query
from pbm_api.db import get_session

router = APIRouter(prefix="/catalog", tags=["catalog"])


class CardSearchResult(BaseModel):
    card_id: uuid.UUID
    set_id: uuid.UUID
    number: str
    name: str
    matched_name: str
    language: str | None
    set_name: str
    set_code: str
    score: float

    @classmethod
    def from_candidate(cls, candidate: CardCandidate) -> "CardSearchResult":
        return cls(
            card_id=candidate.card_id,
            set_id=candidate.set_id,
            number=candidate.number,
            name=candidate.name,
            matched_name=candidate.matched_name,
            language=candidate.language,
            set_name=candidate.set_name,
            set_code=candidate.set_code,
            score=candidate.score,
        )


async def _search_by_name(
    session: AsyncSession, name: str, *, set_code: str | None, langue: str | None
) -> list[CardCandidate]:
    """Essaie chaque découpage `<nom> <indice d'extension>` (ex: "Pikachu VMAX Voltage
    Éclatant" -> nom="Pikachu VMAX", indice="Voltage Éclatant") et garde le meilleur score par
    carte — un utilisateur tape souvent le nom de l'extension à la suite du nom de la carte, sans
    séparateur reconnaissable autrement qu'en essayant les coupures."""
    words = name.split()
    best_by_card: dict[uuid.UUID, CardCandidate] = {}
    for split_index in range(len(words), 0, -1):
        nom_part = " ".join(words[:split_index])
        set_hint_part = " ".join(words[split_index:]) or None
        results = await match_candidates(
            session,
            nom=nom_part,
            set_hint=set_hint_part,
            set_code=set_code,
            langue=langue,
        )
        for candidate in results:
            existing = best_by_card.get(candidate.card_id)
            if existing is None or candidate.score > existing.score:
                best_by_card[candidate.card_id] = candidate
    return sorted(best_by_card.values(), key=lambda c: c.score, reverse=True)[:DEFAULT_LIMIT]


@router.get("/search", response_model=list[CardSearchResult])
async def search_catalog(
    session: Annotated[AsyncSession, Depends(get_session)],
    q: str = Query(..., min_length=1, max_length=255),
    set: str | None = Query(None, max_length=255),  # noqa: A002 — nom du paramètre imposé par la mission
    lang: str | None = Query(None, min_length=2, max_length=8),
) -> list[CardSearchResult]:
    parsed = parse_query(q)

    if parsed.number is not None:
        candidates = await match_candidates(
            session, numero=parsed.number, total=parsed.total, set_code=set, langue=lang
        )
    elif parsed.name is not None:
        candidates = await _search_by_name(session, parsed.name, set_code=set, langue=lang)
    else:
        candidates = []

    return [CardSearchResult.from_candidate(c) for c in candidates]
