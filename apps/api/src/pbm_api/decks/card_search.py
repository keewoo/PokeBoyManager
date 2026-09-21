"""Recherche de cartes du constructeur de deck (mission `v7-decks-recherche`).

Cherche dans le CATALOGUE partagé (~22 000 cartes), **pas** dans la collection : le constructeur
propose toutes les cartes du jeu, chacune annotée du nombre d'exemplaires que l'utilisateur
POSSÈDE (`owned_count`) et du nombre déjà placés dans le deck en cours d'édition
(`in_deck_count`, quand `deck_id` est fourni). L'isolation ne porte donc pas sur les cartes
elles-mêmes (le catalogue est public, comme `GET /catalog/search`) mais sur ces deux annotations
et sur `deck_id` : ces comptes sont TOUJOURS calculés pour l'utilisateur de la session, jamais
pour un identifiant reçu du client, et un `deck_id` d'un autre utilisateur lève
`DeckNotFoundError` (→ 404, jamais 403 : pas de fuite d'existence).

Performances (mission point 2, cible 150 ms au 95e centile sur 22 000 cartes / 5 000
exemplaires) : filtrage, tri ET pagination poussés en SQL, jamais un chargement du catalogue
entier en mémoire par requête (contrairement à `v4-collection`, qui ne scanne que les ≤ 5 000
exemplaires d'un utilisateur). Index posés par la migration `f4a1c8d0b7e2` : trigram unaccent
sur les noms FR/EN (recherche par sous-chaîne accent-insensible), btree sur type/rareté/PV, et
composé `(user_id, card_id)` sur la collection (sous-requête de possession). Pagination par
curseur *keyset* (clé de tri + `card_id`, jamais OFFSET : un OFFSET de 20 000 relirait 20 000
lignes à chaque page). La valeur d'une carte vient de la vue matérialisée `card_value_rank`
(`reference_price_eur`, lot `v4-ranking`), déjà rafraîchie par le job de prix : aucun calcul de
prix lourd par requête (« job lourd = job bridé », `~/.claude/CLAUDE.md`).
"""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from sqlalchemy import (
    ColumnElement,
    and_,
    case,
    column,
    func,
    literal,
    or_,
    select,
    table,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from pbm_api.catalog.reconciliation import normalize_card_number
from pbm_api.catalog.search import parse_query
from pbm_api.decks.energy import is_basic_energy, is_special_energy
from pbm_api.decks.errors import DeckNotFoundError
from pbm_api.models import Card, CardName, CollectionItem, Deck, DeckCard, Set, User

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
DEFAULT_LANG = "fr"

# Vue matérialisée `card_value_rank` (lot `v4-ranking`, migration `11f10f8c0f40`) : une ligne par
# carte, `reference_price_eur` NULL tant qu'aucun prix n'a été relevé. Référencée en Core (elle
# n'est pas un modèle ORM) — jointure gauche, jamais un calcul de prix par requête.
_card_value_rank = table("card_value_rank", column("card_id"), column("reference_price_eur"))


class DeckCardSort(StrEnum):
    value_desc = "value_desc"
    value_asc = "value_asc"
    name_asc = "name_asc"
    number_asc = "number_asc"
    acquired_at_desc = "acquired_at_desc"
    acquired_at_asc = "acquired_at_asc"


# Sens croissant de chaque tri (les `_desc` sont décroissants).
_ASCENDING = {
    DeckCardSort.value_asc,
    DeckCardSort.name_asc,
    DeckCardSort.number_asc,
    DeckCardSort.acquired_at_asc,
}


@dataclass(frozen=True)
class DeckCardSearchFilters:
    q: str | None = None
    set_ids: frozenset[uuid.UUID] = field(default_factory=frozenset)
    rarities: frozenset[str] = field(default_factory=frozenset)
    card_types: frozenset[str] = field(default_factory=frozenset)
    hp_min: int | None = None
    hp_max: int | None = None
    owned_only: bool = False
    duplicates_only: bool = False
    lang: str | None = None


@dataclass(frozen=True)
class DeckCardResult:
    card_id: uuid.UUID
    set_id: uuid.UUID
    number: str
    name: str
    set_name: str
    set_code: str
    series: str | None
    rarity: str | None
    supertype: str | None
    hp: int | None
    image_url: str | None
    energy_type: str | None
    is_basic_energy: bool
    is_special_energy: bool
    value_eur: Decimal | None
    owned_count: int
    in_deck_count: int
    is_duplicate: bool


@dataclass(frozen=True)
class DeckCardSearchPage:
    results: list[DeckCardResult]
    next_cursor: str | None


@dataclass(frozen=True)
class DeckCardFacets:
    sets: list[tuple[uuid.UUID, str, str]]
    rarities: list[str]
    card_types: list[str]
    hp_min: int | None
    hp_max: int | None
    owned_card_count: int
    duplicate_card_count: int


# Ordre des colonnes du SELECT de recherche — nommé une fois pour bâtir le curseur depuis la
# ligne brute (la clé de tri doit être IDENTIQUE à `_sort_column`, y compris le nom CANONIQUE
# pour `name_asc`, pas le nom localisé affiché).
_C_CARD_ID = 0
_C_NUMBER = 2
_C_CANONICAL_NAME = 3
_C_VALUE = 15
_C_LAST_ACQUIRED = 16


# ------------------------------------------------------------------ recherche par nom / numéro
def _unaccent(expr: ColumnElement) -> ColumnElement:
    """`pbm_immutable_unaccent(lower(...))` — même expression que l'index trigram fonctionnel posé
    par la migration, pour que la recherche par sous-chaîne l'utilise. Accent-insensible et
    casse-insensible des DEUX côtés (colonne ET motif), avec la MÊME table unaccent : un `é` tapé
    trouve un `e` et inversement, sans dépendre d'une normalisation Python qui pourrait diverger."""
    return func.pbm_immutable_unaccent(func.lower(expr))


def _number_filter(numero: str) -> ColumnElement[bool]:
    """`006` == `6` == `TG05` (casse ignorée) — même normalisation que `catalog.search`
    (`reconciliation.normalize_card_number`), pour que la barre de recherche du constructeur se
    comporte comme celle du catalogue."""
    normalized = normalize_card_number(numero)
    if normalized.isdigit():
        return or_(
            func.upper(Card.number) == numero.upper(),
            func.ltrim(Card.number, "0") == normalized,
        )
    return func.upper(Card.number) == normalized


def _text_filter(name: str, lang: str | None) -> ColumnElement[bool]:
    """Sous-chaîne accent-insensible sur le nom canonique (`cards.name`) OU un nom localisé FR/EN
    (`card_names`, `EXISTS` corrélé — jamais une jointure qui multiplierait les lignes). `lang`
    restreint les noms localisés à cette langue quand il est fourni."""
    needle = func.concat("%", _unaccent(literal(name)), "%")
    localized = select(literal(1)).where(
        CardName.card_id == Card.id, _unaccent(CardName.name).like(needle)
    )
    if lang:
        localized = localized.where(CardName.language == lang)
    return or_(_unaccent(Card.name).like(needle), localized.exists())


def _apply_search(stmt, q: str | None, lang: str | None):
    if not q or not q.strip():
        return stmt
    parsed = parse_query(q)
    if parsed.number is not None:
        return stmt.where(_number_filter(parsed.number))
    if parsed.name is not None:
        return stmt.where(_text_filter(parsed.name, lang))
    return stmt


# ------------------------------------------------------------------------------- keyset / tri
def _sort_column(sort: DeckCardSort, value_col, last_acquired_col):
    if sort in (DeckCardSort.value_desc, DeckCardSort.value_asc):
        return value_col
    if sort in (DeckCardSort.acquired_at_desc, DeckCardSort.acquired_at_asc):
        return last_acquired_col
    if sort is DeckCardSort.number_asc:
        return Card.number
    return func.lower(Card.name)  # name_asc — nom canonique (l'index existe dessus)


def _order_by(sort_col, ascending: bool):
    """`null_rank` en tête met les valeurs manquantes en DERNIER dans les DEUX sens (une carte
    sans prix, ou non possédée pour le tri par date d'ajout, n'est jamais mélangée aux cartes
    valorisées) ; départage stable par `card_id`."""
    null_rank = case((sort_col.is_(None), 1), else_=0)
    direction = sort_col.asc() if ascending else sort_col.desc()
    return [null_rank.asc(), direction, Card.id.asc()]


def _keyset_where(sort_col, ascending: bool, null_rank: int, sort_value, card_id: uuid.UUID):
    """Clause « lignes strictement APRÈS le curseur » pour l'ordre
    `(null_rank asc, sort_col <dir>, card_id asc)`. Reproduit exactement l'ordre de tri, sans
    OFFSET : c'est ce qui tient la cible de 150 ms quelle que soit la profondeur de page."""
    col_null_rank = case((sort_col.is_(None), 1), else_=0)
    if null_rank == 0:
        cmp = sort_col > sort_value if ascending else sort_col < sort_value
        return or_(
            col_null_rank > 0,  # toutes les lignes à valeur manquante viennent après
            and_(sort_col.is_not(None), cmp),
            and_(sort_col.is_not(None), sort_col == sort_value, Card.id > card_id),
        )
    # Déjà dans la traîne des valeurs manquantes : il ne reste qu'à départager par card_id.
    return and_(sort_col.is_(None), Card.id > card_id)


def _encode_cursor(sort: DeckCardSort, null_rank: int, sort_value, card_id: uuid.UUID) -> str:
    if isinstance(sort_value, Decimal):
        raw_value: str | None = str(sort_value)
    elif isinstance(sort_value, date):
        raw_value = sort_value.isoformat()
    elif sort_value is None:
        raw_value = None
    else:
        raw_value = str(sort_value)
    payload = {"s": sort.value, "n": null_rank, "v": raw_value, "i": str(card_id)}
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def _decode_cursor(cursor: str, sort: DeckCardSort):
    """Retourne `(null_rank, sort_value, card_id)` ou `None` si le curseur est illisible, forgé,
    ou émis pour un autre tri (on repart alors du début plutôt que d'échouer la requête — même
    tolérance que `v4-collection`)."""
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        if payload.get("s") != sort.value:
            return None
        null_rank = int(payload["n"])
        card_id = uuid.UUID(payload["i"])
        raw_value = payload["v"]
    except (ValueError, binascii.Error, KeyError, TypeError):
        return None
    if raw_value is None:
        return null_rank, None, card_id
    if sort in (DeckCardSort.value_desc, DeckCardSort.value_asc):
        try:
            return null_rank, Decimal(raw_value), card_id
        except (InvalidOperation, ValueError):
            return None
    if sort in (DeckCardSort.acquired_at_desc, DeckCardSort.acquired_at_asc):
        try:
            return null_rank, date.fromisoformat(raw_value), card_id
        except ValueError:
            return None
    return null_rank, raw_value, card_id


def _raw_sort_value(sort: DeckCardSort, row):
    """Valeur de tri de la ligne BRUTE (pour bâtir le curseur), strictement cohérente avec
    `_sort_column` — dont, pour `name_asc`, le nom CANONIQUE en minuscules (jamais le nom
    localisé affiché, qui n'est pas la colonne de tri)."""
    if sort in (DeckCardSort.value_desc, DeckCardSort.value_asc):
        return row[_C_VALUE]
    if sort in (DeckCardSort.acquired_at_desc, DeckCardSort.acquired_at_asc):
        return row[_C_LAST_ACQUIRED]
    if sort is DeckCardSort.number_asc:
        return row[_C_NUMBER]
    name = row[_C_CANONICAL_NAME]
    return name.lower() if name is not None else None


# ------------------------------------------------------------------------------ deck (isolation)
async def owned_deck_or_raise(session: AsyncSession, user: User, deck_id: uuid.UUID) -> Deck:
    """Le deck doit appartenir à l'utilisateur de la session — sinon `DeckNotFoundError` (→ 404).
    Même règle que tout le module decks : jamais un id du client sans contrôle de propriété."""
    deck = await session.get(Deck, deck_id)
    if deck is None or deck.user_id != user.id:
        raise DeckNotFoundError
    return deck


# ------------------------------------------------------------------------------------ recherche
async def search_deck_cards(
    session: AsyncSession,
    user: User,
    filters: DeckCardSearchFilters,
    sort: DeckCardSort,
    deck_id: uuid.UUID | None,
    cursor: str | None,
    limit: int,
) -> DeckCardSearchPage:
    if deck_id is not None:
        await owned_deck_or_raise(session, user, deck_id)

    limit = max(1, min(limit, MAX_LIMIT))
    lang = filters.lang or None

    # Sous-requête « possession » : bornée à l'utilisateur de la session, jamais tout le monde.
    owned = (
        select(
            CollectionItem.card_id.label("card_id"),
            func.count().label("owned_count"),
            func.max(CollectionItem.acquired_at).label("last_acquired"),
        )
        .where(CollectionItem.user_id == user.id)
        .group_by(CollectionItem.card_id)
        .subquery()
    )
    owned_count_col = func.coalesce(owned.c.owned_count, 0)

    display = aliased(CardName)  # nom localisé d'affichage (FR par défaut), repli sur le canonique
    value_col = _card_value_rank.c.reference_price_eur
    last_acquired_col = owned.c.last_acquired

    if deck_id is not None:
        deck_cards = (
            select(DeckCard.card_id.label("card_id"), DeckCard.quantity.label("in_deck_count"))
            .where(DeckCard.deck_id == deck_id)
            .subquery()
        )
        in_deck_col = func.coalesce(deck_cards.c.in_deck_count, 0)
    else:
        deck_cards = None
        in_deck_col = literal(0)

    # ORDRE des colonnes = les constantes `_C_*` ci-dessus.
    stmt = (
        select(
            Card.id,
            Card.set_id,
            Card.number,
            Card.name,
            Card.rarity,
            Card.supertype,
            Card.hp,
            Card.image_url,
            Card.energy_type,
            Set.name,
            Set.code,
            Set.series,
            display.name,
            owned_count_col,
            in_deck_col,
            value_col,
            last_acquired_col,
        )
        .select_from(Card)
        .join(Set, Set.id == Card.set_id)
        .outerjoin(owned, owned.c.card_id == Card.id)
        .outerjoin(
            display,
            and_(display.card_id == Card.id, display.language == (lang or DEFAULT_LANG)),
        )
        .outerjoin(_card_value_rank, _card_value_rank.c.card_id == Card.id)
    )
    if deck_cards is not None:
        stmt = stmt.outerjoin(deck_cards, deck_cards.c.card_id == Card.id)

    # ---- filtres (tous indexés) ----
    stmt = _apply_search(stmt, filters.q, lang)
    if filters.set_ids:
        stmt = stmt.where(Card.set_id.in_(filters.set_ids))
    if filters.rarities:
        stmt = stmt.where(Card.rarity.in_(filters.rarities))
    if filters.card_types:
        stmt = stmt.where(Card.supertype.in_(filters.card_types))
    if filters.hp_min is not None:
        stmt = stmt.where(Card.hp >= filters.hp_min)
    if filters.hp_max is not None:
        stmt = stmt.where(Card.hp <= filters.hp_max)
    if filters.duplicates_only:
        stmt = stmt.where(owned.c.owned_count >= 2)
    elif filters.owned_only:
        stmt = stmt.where(owned.c.owned_count >= 1)

    # ---- tri + keyset ----
    ascending = sort in _ASCENDING
    sort_col = _sort_column(sort, value_col, last_acquired_col)
    stmt = stmt.order_by(*_order_by(sort_col, ascending))

    decoded = _decode_cursor(cursor, sort) if cursor else None
    if decoded is not None:
        null_rank, sort_value, cursor_card_id = decoded
        stmt = stmt.where(_keyset_where(sort_col, ascending, null_rank, sort_value, cursor_card_id))

    stmt = stmt.limit(limit + 1)

    rows = (await session.execute(stmt)).all()
    has_more = len(rows) > limit
    page_rows = rows[:limit]

    results = [
        DeckCardResult(
            card_id=row[0],
            set_id=row[1],
            number=row[2],
            name=row[12] or row[3],
            set_name=row[9],
            set_code=row[10],
            series=row[11],
            rarity=row[4],
            supertype=row[5],
            hp=row[6],
            image_url=row[7],
            energy_type=row[8],
            is_basic_energy=is_basic_energy(row[5], row[3], row[8]),
            is_special_energy=is_special_energy(row[5], row[3], row[8]),
            value_eur=row[15],
            owned_count=int(row[13]),
            in_deck_count=int(row[14]),
            is_duplicate=int(row[13]) >= 2,
        )
        for row in page_rows
    ]

    next_cursor: str | None = None
    if has_more and page_rows:
        last = page_rows[-1]
        sort_value = _raw_sort_value(sort, last)
        null_rank = 1 if sort_value is None else 0
        next_cursor = _encode_cursor(sort, null_rank, sort_value, last[_C_CARD_ID])

    return DeckCardSearchPage(results=results, next_cursor=next_cursor)


# ------------------------------------------------------------------------------------ facettes
async def get_facets(session: AsyncSession, user: User) -> DeckCardFacets:
    """Valeurs de filtre à l'échelle du CATALOGUE (toutes cartes sélectionnables dans un deck),
    plus deux compteurs propres à l'utilisateur pour les bascules « mes cartes »/« doublons ».
    Requêtes agrégées bon marché (distinct sur colonnes indexées) — jamais un balayage par carte."""
    sets_rows = (
        await session.execute(select(Set.id, Set.name, Set.code).order_by(func.lower(Set.name)))
    ).all()
    rarities = (
        (
            await session.execute(
                select(Card.rarity)
                .where(Card.rarity.is_not(None))
                .distinct()
                .order_by(Card.rarity)
            )
        )
        .scalars()
        .all()
    )
    card_types = (
        (
            await session.execute(
                select(Card.supertype)
                .where(Card.supertype.is_not(None))
                .distinct()
                .order_by(Card.supertype)
            )
        )
        .scalars()
        .all()
    )
    hp_bounds = (await session.execute(select(func.min(Card.hp), func.max(Card.hp)))).one()

    owned_card_count = (
        await session.execute(
            select(func.count(func.distinct(CollectionItem.card_id))).where(
                CollectionItem.user_id == user.id
            )
        )
    ).scalar_one()
    duplicate_card_count = (
        await session.execute(
            select(func.count()).select_from(
                select(CollectionItem.card_id)
                .where(CollectionItem.user_id == user.id)
                .group_by(CollectionItem.card_id)
                .having(func.count() >= 2)
                .subquery()
            )
        )
    ).scalar_one()

    return DeckCardFacets(
        sets=[(s.id, s.name, s.code) for s in sets_rows],
        rarities=list(rarities),
        card_types=list(card_types),
        hp_min=hp_bounds[0],
        hp_max=hp_bounds[1],
        owned_card_count=int(owned_card_count),
        duplicate_card_count=int(duplicate_card_count),
    )
