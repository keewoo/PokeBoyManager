"""Service `valuation` (mission point 3) : valeur d'un exemplaire et d'une collection.

Référence de prix (mission point 2) : tendance Cardmarket (EUR) en priorité, sinon tendance
TCGplayer convertie en EUR au taux BCE le plus récent connu à la date demandée. Risque documenté
du lot (« une valeur aberrante ne doit pas faire exploser la valeur d'une collection ») :
`_sanitize_trend` borne la tendance à un multiple du prix moyen quand les deux sont connus,
au lieu de la prendre telle quelle — une tendance sans prix moyen de référence n'est pas bornée
(marché trop fin pour juger, on la garde plutôt que d'inventer une borne).
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
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

    total_eur = Decimal("0")
    priced_count = 0
    missing_count = 0
    for item in items:
        value_eur = await item_value(session, item, as_of, currency="EUR")
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
