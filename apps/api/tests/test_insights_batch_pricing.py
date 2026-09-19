"""Tarification Batch (mission `v4-insights-batch` point 2/3) —
`pbm_api.insights_batch.pricing`.

Avant ce lot, ce module n'existait pas : la suite échoue à la collection
(`ModuleNotFoundError`) et passe une fois le fichier ajouté. Les prix eux-mêmes sont vérifiés
(20/09/2026, claude.com/pricing + platform.claude.com/docs) — ces tests figent le calcul, pas
la véracité des tarifs, qui ne peut se vérifier qu'en relisant la doc Anthropic."""

from decimal import Decimal

import pytest

from pbm_api.insights_batch.pricing import (
    BATCH_PRICING_USD_PER_MTOK,
    UnknownModelPricingError,
    batch_cost_usd,
)


def test_known_models_have_a_batch_discounted_price() -> None:
    assert "claude-haiku-4-5" in BATCH_PRICING_USD_PER_MTOK
    assert "claude-sonnet-5" in BATCH_PRICING_USD_PER_MTOK


def test_batch_cost_usd_computes_input_and_output_at_their_own_rate() -> None:
    # Haiku 4.5 batch : 0,50 $/Mtok entrée, 2,50 $/Mtok sortie.
    cost = batch_cost_usd("claude-haiku-4-5", input_tokens=1_000_000, output_tokens=1_000_000)
    assert cost == Decimal("3.00")


def test_batch_cost_usd_is_zero_for_no_usage() -> None:
    assert batch_cost_usd("claude-haiku-4-5", input_tokens=0, output_tokens=0) == Decimal("0")


def test_batch_cost_usd_raises_for_unknown_model_instead_of_guessing() -> None:
    with pytest.raises(UnknownModelPricingError):
        batch_cost_usd("claude-modele-inconnu", input_tokens=1, output_tokens=1)
