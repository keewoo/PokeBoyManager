"""Recherche dans le catalogue (mission `v2-recherche`).

`match_candidates` est le cœur, réutilisable tel quel par la reconnaissance (lot futur) : donné
un nom et/ou un numéro déjà extraits (OCR ou saisie utilisateur), plus des indices optionnels
d'extension et de langue, elle retourne les cartes candidates classées par score (trigram +
unaccent sur les noms FR/EN, `pg_trgm`/`unaccent` posées par la migration initiale).

`parse_query` sépare la responsabilité de reconnaître un numéro (`GET /catalog/search?q=...`,
`pbm_api.routers.catalog`) : formats observés au 2026-09-19 — simple (`25`), avec total
(`236/217`), promo/galerie (`XY121`, `TG05`, `GG10`, `SV107`). Pas de norme publiée par TCGdex :
un numéro qui ne suit aucun de ces formats est traité comme du texte (dégradation raisonnable,
pas une panne).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import ColumnElement, case, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.catalog.reconciliation import normalize_card_number
from pbm_api.models import Card, CardName, Set

_NUMBER_TOTAL_RE = re.compile(r"^(?P<number>[A-Za-z0-9]{1,8})\s*/\s*(?P<total>\d{1,4})$")
# Numéro "pur" : préfixe de lettres optionnel (promo/galerie) suivi de chiffres, éventuellement
# suivi d'une lettre de variante. Ne matche pas un nom de carte réel (aucun n'a cette forme).
_NUMBER_ONLY_RE = re.compile(r"^[A-Za-z]{0,4}\d{1,4}[A-Za-z]?$")

# Score minimal de similarité trigram (0..1) en dessous duquel un candidat est ignoré — sans ce
# plancher, une requête courte remonterait tout le catalogue trié par un score proche de zéro.
NAME_SCORE_THRESHOLD = 0.15
DEFAULT_LIMIT = 25
# Marge interne avant dédoublonnage par carte (une carte peut apparaître une fois par langue
# quand `langue` n'est pas fixé) : on sur-récupère puis on tronque après avoir gardé le meilleur
# score par carte.
_OVERFETCH_FACTOR = 4


@dataclass(frozen=True)
class ParsedQuery:
    """Résultat de l'analyse d'une requête libre : soit un numéro, soit un nom."""

    number: str | None
    total: int | None
    name: str | None


def parse_query(q: str) -> ParsedQuery:
    q = q.strip()
    if not q:
        return ParsedQuery(None, None, None)
    total_match = _NUMBER_TOTAL_RE.match(q)
    if total_match:
        return ParsedQuery(total_match.group("number"), int(total_match.group("total")), None)
    if _NUMBER_ONLY_RE.match(q):
        return ParsedQuery(q, None, None)
    return ParsedQuery(None, None, q)


@dataclass(frozen=True)
class CardCandidate:
    card_id: uuid.UUID
    set_id: uuid.UUID
    number: str
    name: str
    matched_name: str
    language: str | None
    set_name: str
    set_code: str
    score: float


def _number_filter(numero: str) -> ColumnElement[bool]:
    """`006` == `6` == `TG05` (casse ignorée) — voir `reconciliation.normalize_card_number`."""
    normalized = normalize_card_number(numero)
    if normalized.isdigit():
        return or_(
            func.upper(Card.number) == numero.upper(),
            func.ltrim(Card.number, "0") == normalized,
        )
    return func.upper(Card.number) == normalized


def _set_filter(set_code: str) -> ColumnElement[bool]:
    return or_(func.lower(Set.code) == set_code.lower(), func.lower(Set.name) == set_code.lower())


async def match_candidates(
    session: AsyncSession,
    *,
    nom: str | None = None,
    numero: str | None = None,
    total: int | None = None,
    set_hint: str | None = None,
    set_code: str | None = None,
    langue: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> list[CardCandidate]:
    """Cartes candidates, classées par score décroissant.

    - `numero` (et `total`, le nombre après `/`) filtrent strictement : un numéro fourni doit
      correspondre exactement (normalisé), le score ne fait alors que départager les candidats.
    - `nom` filtre par un plancher de similarité trigram (`NAME_SCORE_THRESHOLD`), sur les noms
      localisés FR/EN (`card_names`), unaccent + casse ignorée.
    - `set_hint` (indice bruité, ex: extraction OCR de la pastille d'extension) ne fait que
      pondérer le score, jamais filtrer — un mauvais indice ne doit pas faire disparaître la
      bonne carte. `set_code` (choix explicite dans une liste, ex: filtre UI) filtre strictement.
    - `langue` restreint aux noms de cette langue si fourni, sinon les deux langues sont
      comparées et la meilleure gagne (dédoublonnage par carte).

    Sans `nom` ni `numero`, aucun critère de recherche n'existe : renvoie une liste vide plutôt
    que le catalogue entier.
    """
    if not nom and not numero:
        return []

    score_terms: list[ColumnElement[float]] = []
    name_score_expr: ColumnElement[float] | None = None

    stmt = select(Card, Set).select_from(Card).join(Set, Set.id == Card.set_id)

    if nom:
        name_score_expr = func.similarity(
            func.unaccent(func.lower(CardName.name)), func.unaccent(func.lower(nom))
        )
        stmt = stmt.add_columns(CardName.language, CardName.name).join(
            CardName, CardName.card_id == Card.id
        )
        if langue:
            stmt = stmt.where(CardName.language == langue)
        stmt = stmt.where(name_score_expr > NAME_SCORE_THRESHOLD)
        score_terms.append(name_score_expr * 0.5)
    else:
        stmt = stmt.add_columns(literal(None), Card.name)

    if numero:
        stmt = stmt.where(_number_filter(numero))
        score_terms.append(literal(0.4))

    if set_code:
        stmt = stmt.where(_set_filter(set_code))

    if set_hint:
        set_hint_norm = func.unaccent(func.lower(literal(set_hint)))
        set_score_expr = func.greatest(
            func.similarity(func.unaccent(func.lower(Set.name)), set_hint_norm),
            func.coalesce(
                func.similarity(func.unaccent(func.lower(Set.series)), set_hint_norm), 0.0
            ),
        )
        score_terms.append(set_score_expr * 0.15)

    if total is not None:
        score_terms.append(case((Set.total_cards == total, 0.1), else_=0.0))

    score_expr: ColumnElement[float] = literal(0.0)
    for term in score_terms:
        score_expr = score_expr + term

    stmt = stmt.add_columns(score_expr.label("score"))
    stmt = stmt.order_by(score_expr.desc()).limit(limit * _OVERFETCH_FACTOR)

    result = await session.execute(stmt)

    best_by_card: dict[uuid.UUID, CardCandidate] = {}
    for card, set_row, language, matched_name, score in result.all():
        candidate = CardCandidate(
            card_id=card.id,
            set_id=set_row.id,
            number=card.number,
            name=card.name,
            matched_name=matched_name,
            language=language,
            set_name=set_row.name,
            set_code=set_row.code,
            score=float(score),
        )
        existing = best_by_card.get(candidate.card_id)
        if existing is None or candidate.score > existing.score:
            best_by_card[candidate.card_id] = candidate

    ordered = sorted(best_by_card.values(), key=lambda c: c.score, reverse=True)
    return ordered[:limit]
