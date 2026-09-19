"""Service `valuation` (mission point 3) : valeur d'un exemplaire et d'une collection.

Référence de prix (mission point 2) : tendance Cardmarket (EUR) en priorité, sinon tendance
TCGplayer convertie en EUR au taux BCE le plus récent connu à la date demandée. Risque documenté
du lot (« une valeur aberrante ne doit pas faire exploser la valeur d'une collection ») :
`_sanitize_trend` borne la tendance à un multiple du prix moyen quand les deux sont connus,
au lieu de la prendre telle quelle — une tendance sans prix moyen de référence n'est pas bornée
(marché trop fin pour juger, on la garde plutôt que d'inventer une borne).
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.models import CardPriceDaily, CollectionItem, PriceSource, PriceVariant
from pbm_api.pricing.exchange_rates import convert_from_eur, convert_to_eur, get_rate_to_eur

# Décote par état — barème usuel du marché des cartes (Mint/Near Mint/Excellent/Good/Light
# Played/Played/Poor), documenté ici faute de barème propre à PokeBoyManager. `collection_items`
# ne porte aujourd'hui que l'état saisi par l'utilisateur (`condition_grade`, texte libre) : la
# mesure automatique (centrage, coins, bords) est une mission de reconnaissance future (v3+).
# État absent ou non reconnu -> "near_mint" (0.90), hypothèse conservatrice documentée par défaut
# plutôt qu'une pleine valeur "mint" non vérifiée.
CONDITION_MULTIPLIERS: dict[str, Decimal] = {
    "mint": Decimal("1.00"),
    "near_mint": Decimal("0.90"),
    "excellent": Decimal("0.75"),
    "good": Decimal("0.60"),
    "light_played": Decimal("0.45"),
    "played": Decimal("0.30"),
    "poor": Decimal("0.15"),
}
DEFAULT_CONDITION = "near_mint"

# Borne d'écrêtage d'une tendance aberrante par rapport au prix moyen du même relevé.
OUTLIER_TREND_MULTIPLE = Decimal("3")


def condition_multiplier(grade: str | None) -> Decimal:
    default = CONDITION_MULTIPLIERS[DEFAULT_CONDITION]
    return CONDITION_MULTIPLIERS.get(grade or DEFAULT_CONDITION, default)


def _sanitize_trend(
    price_low: Decimal | None, price_mid: Decimal | None, price_trend: Decimal | None
) -> Decimal | None:
    if price_trend is None or price_trend <= 0:
        return None
    if price_mid is not None and price_mid > 0 and price_trend > price_mid * OUTLIER_TREND_MULTIPLE:
        return price_mid * OUTLIER_TREND_MULTIPLE
    return price_trend


async def _latest_price_row(
    session: AsyncSession, card_id: Any, source: PriceSource, variant: PriceVariant, as_of: date
) -> CardPriceDaily | None:
    result = await session.execute(
        select(CardPriceDaily)
        .where(
            CardPriceDaily.card_id == card_id,
            CardPriceDaily.source == source,
            CardPriceDaily.variant == variant,
            CardPriceDaily.day <= as_of,
        )
        .order_by(CardPriceDaily.day.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def reference_price_eur(
    session: AsyncSession, card_id: Any, variant: PriceVariant, as_of: date
) -> Decimal | None:
    """Tendance Cardmarket en EUR si connue, sinon tendance TCGplayer convertie (mission point 2).
    `None` si aucune des deux sources n'a de relevé exploitable à cette date — jamais une valeur
    inventée (risque documenté : prix manquants pour les cartes rares ou récentes)."""
    cardmarket = await _latest_price_row(session, card_id, PriceSource.cardmarket, variant, as_of)
    if cardmarket is not None:
        trend = _sanitize_trend(cardmarket.price_low, cardmarket.price_mid, cardmarket.price_trend)
        if trend is not None:
            return trend

    tcgplayer = await _latest_price_row(session, card_id, PriceSource.tcgplayer, variant, as_of)
    if tcgplayer is not None:
        trend = _sanitize_trend(tcgplayer.price_low, tcgplayer.price_mid, tcgplayer.price_trend)
        if trend is not None:
            rate = await get_rate_to_eur(session, tcgplayer.currency, as_of)
            if rate is not None:
                return convert_to_eur(trend, rate)

    return None


_PriceRow = tuple[Decimal | None, Decimal | None, Decimal | None, str]


async def _bulk_latest_prices(
    session: AsyncSession, card_ids: set[Any], as_of: date
) -> dict[tuple[Any, PriceVariant, PriceSource], _PriceRow]:
    """Dernier relevé par `(card_id, variant, source)` à `as_of` ou avant, cardmarket et
    tcgplayer réunis dans une seule requête — mission `v4-collection` point 4 (5 000 exemplaires
    en moins de 300 ms) : deux économies mesurées ici, une requête au lieu de deux, et des
    colonnes explicites plutôt que l'entité `CardPriceDaily` complète (pas de matérialisation
    ORM inutile à 5 000 × 2 lignes)."""
    if not card_ids:
        return {}
    result = await session.execute(
        select(
            CardPriceDaily.card_id,
            CardPriceDaily.variant,
            CardPriceDaily.source,
            CardPriceDaily.price_low,
            CardPriceDaily.price_mid,
            CardPriceDaily.price_trend,
            CardPriceDaily.currency,
        )
        .distinct(CardPriceDaily.card_id, CardPriceDaily.variant, CardPriceDaily.source)
        .where(CardPriceDaily.card_id.in_(card_ids), CardPriceDaily.day <= as_of)
        .order_by(
            CardPriceDaily.card_id,
            CardPriceDaily.variant,
            CardPriceDaily.source,
            CardPriceDaily.day.desc(),
        )
    )
    return {
        (card_id, variant, source): (price_low, price_mid, price_trend, currency)
        for card_id, variant, source, price_low, price_mid, price_trend, currency in result
    }


async def bulk_reference_prices_eur(
    session: AsyncSession, pairs: set[tuple[Any, PriceVariant]], as_of: date
) -> dict[tuple[Any, PriceVariant], Decimal | None]:
    """Version en masse de `reference_price_eur`, pour un ensemble de `(card_id, variant)` —
    une seule requête de prix, jamais une par paire ni une par source."""
    if not pairs:
        return {}
    card_ids = {card_id for card_id, _variant in pairs}
    latest = await _bulk_latest_prices(session, card_ids, as_of)

    rate_cache: dict[str, Decimal | None] = {}

    async def _cached_rate(currency: str) -> Decimal | None:
        if currency not in rate_cache:
            rate_cache[currency] = await get_rate_to_eur(session, currency, as_of)
        return rate_cache[currency]

    references: dict[tuple[Any, PriceVariant], Decimal | None] = {}
    for pair in pairs:
        card_id, variant = pair
        cm = latest.get((card_id, variant, PriceSource.cardmarket))
        trend = _sanitize_trend(*cm[:3]) if cm else None
        if trend is not None:
            references[pair] = trend
            continue

        tc = latest.get((card_id, variant, PriceSource.tcgplayer))
        trend = _sanitize_trend(*tc[:3]) if tc else None
        if trend is not None:
            rate = await _cached_rate(tc[3])
            references[pair] = convert_to_eur(trend, rate) if rate is not None else None
            continue

        references[pair] = None
    return references


async def bulk_item_values(
    session: AsyncSession,
    items: list[CollectionItem],
    as_of: date | None = None,
    currency: str = "EUR",
) -> dict[uuid.UUID, Decimal | None]:
    """Version en masse de `item_value` (mission point 4) : une poignée de requêtes au total,
    jamais une par exemplaire — c'est elle qui rend `GET /me/collection` tenable à 5 000
    exemplaires (`pbm_api.collection.service`, `scripts/measure_collection_performance.py`)."""
    as_of = as_of or datetime.now(UTC).date()
    pairs = {
        (item.card_id, item.variant) for item in items if not item.counterfeit_suspected
    }
    references = await bulk_reference_prices_eur(session, pairs, as_of)
    rate = Decimal("1") if currency == "EUR" else await get_rate_to_eur(session, currency, as_of)

    values: dict[uuid.UUID, Decimal | None] = {}
    for item in items:
        if item.counterfeit_suspected:
            values[item.id] = Decimal("0")
            continue
        reference = references.get((item.card_id, item.variant))
        if reference is None:
            values[item.id] = None
            continue
        value_eur = reference * condition_multiplier(item.condition_grade)
        values[item.id] = None if rate is None else convert_from_eur(value_eur, rate)
    return values


async def _bulk_latest_prices_multi(
    session: AsyncSession, card_ids: set[Any], as_of_dates: tuple[date, ...]
) -> dict[date, dict[tuple[Any, PriceVariant, PriceSource], _PriceRow]]:
    """Comme `_bulk_latest_prices`, pour plusieurs dates de référence en une seule requête
    (`UNION ALL` de sous-requêtes `DISTINCT ON`, chacune indexée par sa date) — c'est elle qui
    évite à `GET /me/collection` un aller-retour SQL par fenêtre de variation (mission point 4 :
    aujourd'hui, -7 j, -30 j pour les agrégats, en un seul appel réseau plutôt que trois)."""
    if not card_ids or not as_of_dates:
        return {as_of: {} for as_of in as_of_dates}

    branches = []
    for as_of in as_of_dates:
        subquery = (
            select(
                CardPriceDaily.card_id,
                CardPriceDaily.variant,
                CardPriceDaily.source,
                CardPriceDaily.price_low,
                CardPriceDaily.price_mid,
                CardPriceDaily.price_trend,
                CardPriceDaily.currency,
            )
            .distinct(CardPriceDaily.card_id, CardPriceDaily.variant, CardPriceDaily.source)
            .where(CardPriceDaily.card_id.in_(card_ids), CardPriceDaily.day <= as_of)
            .order_by(
                CardPriceDaily.card_id,
                CardPriceDaily.variant,
                CardPriceDaily.source,
                CardPriceDaily.day.desc(),
            )
            .subquery()
        )
        branches.append(
            select(
                literal(as_of).label("as_of"),
                subquery.c.card_id,
                subquery.c.variant,
                subquery.c.source,
                subquery.c.price_low,
                subquery.c.price_mid,
                subquery.c.price_trend,
                subquery.c.currency,
            )
        )

    result = await session.execute(union_all(*branches))

    by_window: dict[date, dict[tuple[Any, PriceVariant, PriceSource], _PriceRow]] = {
        as_of: {} for as_of in as_of_dates
    }
    for row_as_of, card_id, variant, source, price_low, price_mid, price_trend, currency in result:
        by_window[row_as_of][(card_id, variant, source)] = (
            price_low,
            price_mid,
            price_trend,
            currency,
        )
    return by_window


async def bulk_reference_prices_eur_multi(
    session: AsyncSession, pairs: set[tuple[Any, PriceVariant]], as_of_dates: tuple[date, ...]
) -> dict[date, dict[tuple[Any, PriceVariant], Decimal | None]]:
    """Version multi-date de `bulk_reference_prices_eur` (mission point 4)."""
    if not pairs or not as_of_dates:
        return {as_of: {} for as_of in as_of_dates}
    card_ids = {card_id for card_id, _variant in pairs}
    by_window = await _bulk_latest_prices_multi(session, card_ids, as_of_dates)

    rate_cache: dict[tuple[str, date], Decimal | None] = {}

    async def _cached_rate(currency: str, as_of: date) -> Decimal | None:
        key = (currency, as_of)
        if key not in rate_cache:
            rate_cache[key] = await get_rate_to_eur(session, currency, as_of)
        return rate_cache[key]

    result: dict[date, dict[tuple[Any, PriceVariant], Decimal | None]] = {}
    for as_of in as_of_dates:
        latest = by_window[as_of]
        references: dict[tuple[Any, PriceVariant], Decimal | None] = {}
        for pair in pairs:
            card_id, variant = pair
            cm = latest.get((card_id, variant, PriceSource.cardmarket))
            trend = _sanitize_trend(*cm[:3]) if cm else None
            if trend is not None:
                references[pair] = trend
                continue

            tc = latest.get((card_id, variant, PriceSource.tcgplayer))
            trend = _sanitize_trend(*tc[:3]) if tc else None
            if trend is not None:
                rate = await _cached_rate(tc[3], as_of)
                references[pair] = convert_to_eur(trend, rate) if rate is not None else None
                continue

            references[pair] = None
        result[as_of] = references
    return result


async def bulk_item_values_multi(
    session: AsyncSession,
    items: list[CollectionItem],
    as_of_dates: tuple[date, ...],
    currency: str = "EUR",
) -> dict[date, dict[uuid.UUID, Decimal | None]]:
    """Version multi-date de `bulk_item_values` : une seule requête de prix pour toutes les
    dates demandées (mission point 4), utilisée par `pbm_api.collection.service.list_collection`
    pour la valeur du jour et les variations 7/30 j en un seul aller-retour de prix."""
    pairs = {(item.card_id, item.variant) for item in items if not item.counterfeit_suspected}
    references_by_date = await bulk_reference_prices_eur_multi(session, pairs, as_of_dates)

    rate_cache: dict[date, Decimal | None] = {}

    async def _cached_output_rate(as_of: date) -> Decimal | None:
        if as_of not in rate_cache:
            if currency == "EUR":
                rate_cache[as_of] = Decimal("1")
            else:
                rate_cache[as_of] = await get_rate_to_eur(session, currency, as_of)
        return rate_cache[as_of]

    result: dict[date, dict[uuid.UUID, Decimal | None]] = {}
    for as_of in as_of_dates:
        references = references_by_date[as_of]
        rate = await _cached_output_rate(as_of)
        values: dict[uuid.UUID, Decimal | None] = {}
        for item in items:
            if item.counterfeit_suspected:
                values[item.id] = Decimal("0")
                continue
            reference = references.get((item.card_id, item.variant))
            if reference is None:
                values[item.id] = None
                continue
            value_eur = reference * condition_multiplier(item.condition_grade)
            values[item.id] = None if rate is None else convert_from_eur(value_eur, rate)
        result[as_of] = values
    return result


async def _convert_from_eur_or_none(
    session: AsyncSession, amount_eur: Decimal | None, currency: str, as_of: date
) -> Decimal | None:
    if amount_eur is None:
        return None
    if currency == "EUR":
        return amount_eur
    rate = await get_rate_to_eur(session, currency, as_of)
    if rate is None:
        return None
    return convert_from_eur(amount_eur, rate)


async def item_value(
    session: AsyncSession,
    item: CollectionItem,
    as_of: date | None = None,
    currency: str = "EUR",
) -> Decimal | None:
    """Valeur d'un exemplaire = référence de prix de sa variante × décote de son état.

    Neutralisée à zéro pour un exemplaire signalé contrefaçon probable (mission `v3-etat`
    point 3, `pbm_api.state.counterfeit`) : jamais valorisée comme l'originale, mais toujours un
    exemplaire « pricé » plutôt qu'une valeur manquante (`None`), qui signifierait plutôt
    « aucune référence de prix disponible »."""
    if item.counterfeit_suspected:
        # Zéro dans n'importe quelle devise ne dépend d'aucun taux de change du jour — jamais
        # `None` ici, qui signifierait « aucune référence de prix disponible » plutôt que
        # « valeur neutralisée ».
        return Decimal("0")
    as_of = as_of or datetime.now(UTC).date()
    reference = await reference_price_eur(session, item.card_id, item.variant, as_of)
    if reference is None:
        return None
    value_eur = reference * condition_multiplier(item.condition_grade)
    return await _convert_from_eur_or_none(session, value_eur, currency, as_of)


async def collection_value(
    session: AsyncSession,
    user_id: Any,
    as_of: date | None = None,
    currency: str = "EUR",
) -> dict[str, Any]:
    """Valeur totale de la collection d'un utilisateur à une date, dans la devise demandée.

    Filtre toujours par `user_id` reçu en paramètre — jamais par un identifiant fourni côté
    client (isolation entre utilisateurs, voir `CLAUDE.md`)."""
    as_of = as_of or datetime.now(UTC).date()
    items = (
        (await session.execute(select(CollectionItem).where(CollectionItem.user_id == user_id)))
        .scalars()
        .all()
    )

    # `bulk_item_values` (mission `v4-collection` point 4) plutôt qu'un `item_value` par
    # exemplaire : une collection de plusieurs milliers d'exemplaires ne doit jamais coûter
    # deux requêtes SQL par exemplaire.
    values_eur = await bulk_item_values(session, list(items), as_of, currency="EUR")
    total_eur = Decimal("0")
    priced_count = 0
    missing_count = 0
    for item in items:
        value_eur = values_eur.get(item.id)
        if value_eur is None:
            missing_count += 1
            continue
        total_eur += value_eur
        priced_count += 1

    total = await _convert_from_eur_or_none(session, total_eur, currency, as_of)

    return {
        "as_of": as_of.isoformat(),
        "currency": currency,
        "total": total,
        "items_total": len(items),
        "items_priced": priced_count,
        "items_missing_price": missing_count,
    }
