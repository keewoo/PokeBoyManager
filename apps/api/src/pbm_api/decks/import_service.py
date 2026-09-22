"""Import d'une liste de deck collée → deck « à compléter » + rapport ligne par ligne.

Mission `v7-decks-import-export` point 1, et son risque : **une liste importée ne crée JAMAIS de
cartes dans la collection** (aucun `CollectionItem` touché). Elle crée un deck, y met les cartes
rapprochées au catalogue, et rend un rapport qui dit, ligne par ligne : la carte retenue,
d'éventuelles cartes proches (fautes de frappe), ce qui n'existe pas au catalogue, et ce qui
manque dans la collection.

Le rapprochement réutilise tel quel `catalog.search.match_candidates` (mission `v2-recherche`) :
nom (trigram FR/EN, tolérant aux fautes de frappe) + numéro (filtre strict quand fourni), avec un
repli progressif si l'extension puis le numéro fournis ne donnent rien — jamais un repli
silencieux, chaque abandon d'indice est noté sur la ligne. La possession affichée par ligne est
comptée par le même chemin que la légalité (`service._owned_counts` + `energy.is_basic_energy`) :
une seule règle de possession, jamais deux qui divergent.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.catalog.search import CardCandidate, match_candidates
from pbm_api.decks import energy, service
from pbm_api.decks.parsing import ParsedLine, parse_deck_list
from pbm_api.decks.schemas import CreateDeckRequest, DeckCardInput
from pbm_api.models import Card, Deck, User

# Nombre de cartes distinctes proposées en alternative sur une ligne ambiguë.
MAX_ALTERNATIVES = 3
# Candidats demandés au catalogue par ligne (top + alternatives).
MATCH_LIMIT = 5
# En deçà de cet écart de score entre le 1er et le 2e candidat, la ligne est « ambiguë ».
AMBIGUITY_GAP = 0.08
# Garde-fou : au-delà, la liste est tronquée (jamais en silence — signalé dans le rapport).
MAX_IMPORT_LINES = 400
# Quantité maximale conservée par carte (aligne `DeckCardInput`, `quantity <= 60`).
MAX_QUANTITY = 60

DEFAULT_DECK_NAME = "Deck importé"

STATUS_MATCHED = "matched"
STATUS_AMBIGUOUS = "ambiguous"
STATUS_NOT_FOUND = "not_found"
STATUS_SECTION = "section"


@dataclass
class CandidateOut:
    card_id: uuid.UUID
    name: str
    set_code: str
    set_name: str
    number: str
    score: float


@dataclass
class ImportLine:
    line_no: int
    raw: str
    status: str
    quantity: int = 1
    parsed_name: str | None = None
    parsed_set: str | None = None
    parsed_number: str | None = None
    notes: list[str] = field(default_factory=list)
    card: CandidateOut | None = None
    alternatives: list[CandidateOut] = field(default_factory=list)
    owned: int = 0
    missing: int = 0


@dataclass
class ImportResult:
    deck_id: uuid.UUID | None
    lines: list[ImportLine]
    matched: int = 0
    ambiguous: int = 0
    not_found: int = 0
    sections_ignored: int = 0
    cards_added: int = 0
    distinct_cards: int = 0
    truncated: bool = False
    warnings: list[str] = field(default_factory=list)


def _candidate_out(c: CardCandidate) -> CandidateOut:
    return CandidateOut(
        card_id=c.card_id,
        name=c.name,
        set_code=c.set_code,
        set_name=c.set_name,
        number=c.number,
        score=round(c.score, 4),
    )


async def _match_one(
    session: AsyncSession, line: ParsedLine
) -> tuple[list[CardCandidate], list[str]]:
    """Rapproche une ligne, avec repli progressif. Renvoie (candidats classés, notes de repli)."""
    notes: list[str] = []
    name = line.name
    number = line.number
    set_code = line.set_code

    # 1) nom + numéro + extension (le plus strict).
    if name or number:
        cands = await match_candidates(
            session,
            nom=name,
            numero=number,
            total=line.total if number else None,
            set_code=set_code,
            limit=MATCH_LIMIT,
        )
        if cands:
            return cands, notes

    # 2) on lâche l'extension (les pastilles d'extension collées d'un autre site ne
    #    correspondent pas toujours à nos codes).
    if set_code and (name or number):
        cands = await match_candidates(
            session, nom=name, numero=number, total=line.total if number else None,
            limit=MATCH_LIMIT,
        )
        if cands:
            notes.append(f"extension « {set_code} » ignorée : aucune carte à ce code")
            return cands, notes

    # 3) on lâche le numéro (faute de frappe, ou numéro absent de notre catalogue).
    if number and name:
        cands = await match_candidates(session, nom=name, limit=MATCH_LIMIT)
        if cands:
            notes.append(f"numéro « {number} » ignoré : rapproché par le nom seul")
            return cands, notes

    return [], notes


def _classify(cands: list[CardCandidate]) -> str:
    if not cands:
        return STATUS_NOT_FOUND
    if len(cands) == 1 or (cands[0].score - cands[1].score) >= AMBIGUITY_GAP:
        return STATUS_MATCHED
    return STATUS_AMBIGUOUS


async def _ownership(
    session: AsyncSession, user_id: uuid.UUID, card_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[int, str | None, str, str | None]]:
    """Par carte retenue : (possédés hors contrefaçon, supertype, name, energy_type). Deux
    requêtes au total, jamais une par carte — pour calculer un « manquant » aligné sur la
    légalité (une Énergie de base n'est jamais manquante)."""
    if not card_ids:
        return {}
    owned, _counterfeit = await service._owned_counts(session, user_id, card_ids)
    rows = await session.execute(
        select(Card.id, Card.supertype, Card.name, Card.energy_type).where(Card.id.in_(card_ids))
    )
    out: dict[uuid.UUID, tuple[int, str | None, str, str | None]] = {}
    for cid, supertype, name, energy_type in rows.all():
        out[cid] = (owned.get(cid, 0), supertype, name, energy_type)
    return out


async def import_deck(
    session: AsyncSession,
    user: User,
    *,
    text: str,
    name: str | None = None,
    deck_format: str = "standard",
    dry_run: bool = False,
) -> ImportResult:
    parsed = parse_deck_list(text)
    result = ImportResult(deck_id=None, lines=[])

    card_lines = [p for p in parsed if p.kind == "card"]
    if len(card_lines) > MAX_IMPORT_LINES:
        result.truncated = True
        result.warnings.append(
            f"{len(card_lines)} lignes de carte : seules les {MAX_IMPORT_LINES} premières sont "
            f"importées."
        )
        keep = set(id(p) for p in card_lines[:MAX_IMPORT_LINES])
    else:
        keep = None

    # Quantité voulue par carte retenue (fusion des lignes citant la même carte).
    merged: dict[uuid.UUID, int] = {}
    # Ligne de rapport où reporter owned/missing pour chaque carte retenue.
    lines_by_card: dict[uuid.UUID, list[ImportLine]] = {}

    for p in parsed:
        if p.kind in ("blank", "comment"):
            continue
        if p.kind == "section":
            result.sections_ignored += 1
            result.lines.append(
                ImportLine(line_no=p.line_no, raw=p.raw, status=STATUS_SECTION)
            )
            continue

        # kind == "card"
        if keep is not None and id(p) not in keep:
            continue

        cands, match_notes = await _match_one(session, p)
        status = _classify(cands)
        report_line = ImportLine(
            line_no=p.line_no,
            raw=p.raw,
            status=status,
            quantity=p.quantity,
            parsed_name=p.name,
            parsed_set=p.set_code,
            parsed_number=p.number,
            notes=list(p.notes) + match_notes,
        )

        if status == STATUS_NOT_FOUND:
            result.not_found += 1
            report_line.notes.append("introuvable au catalogue : non ajoutée au deck")
        else:
            chosen = cands[0]
            report_line.card = _candidate_out(chosen)
            if status == STATUS_AMBIGUOUS:
                result.ambiguous += 1
                report_line.alternatives = [
                    _candidate_out(c) for c in cands[1 : 1 + MAX_ALTERNATIVES]
                ]
                report_line.notes.append(
                    "plusieurs cartes proches : meilleure retenue, à vérifier"
                )
            else:
                result.matched += 1
            merged[chosen.card_id] = merged.get(chosen.card_id, 0) + p.quantity
            lines_by_card.setdefault(chosen.card_id, []).append(report_line)

        result.lines.append(report_line)

    # Écrêtage des quantités (aligne la borne de `DeckCardInput`).
    for cid, qty in list(merged.items()):
        if qty > MAX_QUANTITY:
            merged[cid] = MAX_QUANTITY
            result.warnings.append(
                f"quantité ramenée à {MAX_QUANTITY} pour une carte (demandé {qty})."
            )

    # Possession, pour un « manquant » aligné sur la légalité du deck.
    ownership = await _ownership(session, user.id, list(merged))
    for cid in merged:
        owned, supertype, cname, energy_type = ownership.get(cid, (0, None, "", None))
        is_basic = energy.is_basic_energy(supertype, cname, energy_type)
        for rline in lines_by_card.get(cid, []):
            rline.owned = owned
            rline.missing = 0 if is_basic else max(0, rline.quantity - owned)

    result.distinct_cards = len(merged)
    result.cards_added = sum(merged.values())

    if not dry_run and merged:
        deck = await _create_from_merged(
            session, user, name=name, deck_format=deck_format, merged=merged
        )
        result.deck_id = deck.id
    elif not dry_run:
        # Aucune carte rapprochée : on crée tout de même un deck vide « à compléter », pour que
        # l'utilisateur reparte de son import plutôt que de rien.
        deck = await _create_from_merged(
            session, user, name=name, deck_format=deck_format, merged={}
        )
        result.deck_id = deck.id

    return result


async def _create_from_merged(
    session: AsyncSession,
    user: User,
    *,
    name: str | None,
    deck_format: str,
    merged: dict[uuid.UUID, int],
) -> Deck:
    request = CreateDeckRequest(
        name=(name or DEFAULT_DECK_NAME),
        format=deck_format,
        cards=[DeckCardInput(card_id=cid, quantity=qty) for cid, qty in merged.items()],
    )
    return await service.create_deck(session, user, request)
