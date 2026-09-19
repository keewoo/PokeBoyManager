"""Extraction des prix bruts (TCGdex `pricing.cardmarket`, Pokémon TCG API `tcgplayer`).

Les objets `CARDMARKET_PRICING`/`PTCG_TCGPLAYER` reproduisent la forme réelle capturée le
2026-09-19 (voir compte rendu du lot) : `test_extract_cardmarket_prices_reads_normal_and_holo`
échoue sans ce lot (le module `pbm_api.pricing.extract` n'existe pas) et passe avec.
"""

from decimal import Decimal

from pbm_api.models import PriceVariant
from pbm_api.pricing.extract import extract_cardmarket_prices, extract_tcgplayer_prices

CARDMARKET_PRICING = {
    "updated": "2026-09-18T22:54:57.892Z",
    "unit": "EUR",
    "idProduct": 733601,
    "avg": 8.74,
    "low": 4,
    "trend": 8.74,
    "avg1": 7.49,
    "avg7": 7.83,
    "avg30": 8.53,
    "avg-holo": None,
    "low-holo": None,
    "trend-holo": 0,
    "avg1-holo": None,
    "avg7-holo": None,
    "avg30-holo": None,
}

PTCG_TCGPLAYER = {
    "url": "https://prices.pokemontcg.io/tcgplayer/base1-4",
    "updatedAt": "2026/09/18",
    "prices": {
        "holofoil": {
            "low": 4.49,
            "mid": 9.25,
            "high": 158.4,
            "market": 8.36,
            "directLow": 10.81,
        }
    },
}


def test_extract_cardmarket_prices_reads_normal_and_holo():
    prices = extract_cardmarket_prices(CARDMARKET_PRICING)

    assert prices[PriceVariant.normal] == {
        "low": Decimal("4"),
        "mid": Decimal("8.74"),
        "trend": Decimal("8.74"),
    }
    # trend-holo == 0 et avg-holo/low-holo nuls : pas de version holo pour cette carte, aucune
    # entrée écrite (pas de faux zéro en base).
    assert PriceVariant.holo not in prices


def test_extract_cardmarket_prices_keeps_holo_when_present():
    pricing = {**CARDMARKET_PRICING, "low-holo": 20, "avg-holo": 25.5, "trend-holo": 27}

    prices = extract_cardmarket_prices(pricing)

    assert prices[PriceVariant.holo] == {
        "low": Decimal("20"),
        "mid": Decimal("25.5"),
        "trend": Decimal("27"),
    }


def test_extract_cardmarket_prices_empty_block_yields_nothing():
    assert extract_cardmarket_prices({}) == {}


def test_extract_tcgplayer_prices_reads_holofoil():
    prices = extract_tcgplayer_prices(PTCG_TCGPLAYER)

    assert prices == {
        PriceVariant.holo: {
            "low": Decimal("4.49"),
            "mid": Decimal("9.25"),
            "trend": Decimal("8.36"),
        }
    }
    assert PriceVariant.normal not in prices


def test_extract_tcgplayer_prices_prefers_1st_edition_holofoil_over_normal():
    tcgplayer = {
        "prices": {
            "1stEditionNormal": {"low": 1, "mid": 2, "market": 3},
            "1stEditionHolofoil": {"low": 10, "mid": 20, "market": 30},
        }
    }

    prices = extract_tcgplayer_prices(tcgplayer)

    assert prices[PriceVariant.first_edition]["trend"] == Decimal("30")


def test_extract_tcgplayer_prices_missing_block_yields_nothing():
    assert extract_tcgplayer_prices({}) == {}
    assert extract_tcgplayer_prices({"prices": {}}) == {}
