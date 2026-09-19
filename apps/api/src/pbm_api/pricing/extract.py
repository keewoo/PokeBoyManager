"""Extraction des blocs de prix bruts (TCGdex, Pokémon TCG API) vers nos variantes (`PriceVariant`).

Formes capturées le 2026-09-19 (voir compte rendu du lot `v2-prix`) :
- TCGdex `pricing.cardmarket` : clés plates `low`/`avg`/`trend` (normal) et `*-holo` (holo) ;
  ni `reverse_holo` ni `first_edition` n'y apparaissent — la table de clés reste ouverte à
  compléter si TCGdex les expose un jour, mais aucune carte de test ne les a montrées.
- Pokémon TCG API `tcgplayer.prices.<variante>` : `low`/`mid`/`market`/`high`/`directLow`.
"""

from decimal import Decimal, InvalidOperation

from pbm_api.models import PriceVariant

# variante -> (clé low, clé mid/moyenne, clé tendance) dans `pricing.cardmarket` (TCGdex).
CARDMARKET_VARIANT_KEYS: dict[PriceVariant, tuple[str, str, str]] = {
    PriceVariant.normal: ("low", "avg", "trend"),
    PriceVariant.holo: ("low-holo", "avg-holo", "trend-holo"),
}

# variante -> clés candidates dans `tcgplayer.prices` (Pokémon TCG API), par ordre de préférence.
TCGPLAYER_VARIANT_KEYS: dict[PriceVariant, tuple[str, ...]] = {
    PriceVariant.normal: ("normal",),
    PriceVariant.holo: ("holofoil",),
    PriceVariant.reverse_holo: ("reverseHolofoil",),
    PriceVariant.first_edition: ("1stEditionHolofoil", "1stEditionNormal"),
}


def _decimal_or_none(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        dec = Decimal(str(value))
    except InvalidOperation:
        return None
    return dec if dec > 0 else None


def extract_cardmarket_prices(pricing: dict) -> dict[PriceVariant, dict[str, Decimal | None]]:
    """`pricing` = le bloc `pricing.cardmarket` d'une carte TCGdex.

    Une variante dont les trois champs sont absents/nuls/à zéro (carte non déclinée dans ce
    format, ex: pas de version holo) n'est jamais écrite — pas de faux zéro en base.
    """
    out: dict[PriceVariant, dict[str, Decimal | None]] = {}
    for variant, (low_key, mid_key, trend_key) in CARDMARKET_VARIANT_KEYS.items():
        low = _decimal_or_none(pricing.get(low_key))
        mid = _decimal_or_none(pricing.get(mid_key))
        trend = _decimal_or_none(pricing.get(trend_key))
        if low is None and mid is None and trend is None:
            continue
        out[variant] = {"low": low, "mid": mid, "trend": trend}
    return out


def extract_tcgplayer_prices(tcgplayer: dict) -> dict[PriceVariant, dict[str, Decimal | None]]:
    """`tcgplayer` = le bloc `tcgplayer` d'une carte Pokémon TCG API.

    Une carte peut avoir `1stEditionHolofoil` et `1stEditionNormal` : la première présente dans
    l'ordre de préférence l'emporte pour la variante `first_edition` — on n'écrit jamais les
    deux sous la même clé (card_id, source, variant, day).
    """
    prices = tcgplayer.get("prices") or {}
    out: dict[PriceVariant, dict[str, Decimal | None]] = {}
    for variant, keys in TCGPLAYER_VARIANT_KEYS.items():
        for key in keys:
            block = prices.get(key)
            if not block:
                continue
            low = _decimal_or_none(block.get("low"))
            mid = _decimal_or_none(block.get("mid"))
            trend = _decimal_or_none(block.get("market"))
            if low is None and mid is None and trend is None:
                continue
            out[variant] = {"low": low, "mid": mid, "trend": trend}
            break
    return out
