"""Tarification Anthropic pour la Message Batches API — mission point 2/3 : le plafond de
budget et la mesure de coût doivent porter sur un prix réel, pas une estimation inventée.

Tarifs standards vérifiés le 20/09/2026 sur https://claude.com/pricing ; la remise « Save 50%
with batch processing » de la Message Batches API (vérifiée le même jour sur
https://platform.claude.com/docs/en/build-with-claude/batch-processing) s'applique déjà dans
`BATCH_PRICING_USD_PER_MTOK` ci-dessous. Une évolution tarifaire d'Anthropic ne serait pas
détectée automatiquement : `run_insights_batch.py --model` documente la nécessité de revérifier
cette table avant tout passage réel de grande ampleur.
"""

from decimal import Decimal

# {modèle: (prix entrée $/Mtok, prix sortie $/Mtok)} — déjà à moitié prix (remise Batch).
BATCH_PRICING_USD_PER_MTOK: dict[str, tuple[Decimal, Decimal]] = {
    "claude-haiku-4-5": (Decimal("0.50"), Decimal("2.50")),
    "claude-sonnet-5": (Decimal("1"), Decimal("5")),
}


class UnknownModelPricingError(Exception):
    """Modèle sans tarif connu — refuser un lot plutôt que d'estimer un coût à zéro."""


def batch_cost_usd(model: str, *, input_tokens: int, output_tokens: int) -> Decimal:
    if model not in BATCH_PRICING_USD_PER_MTOK:
        raise UnknownModelPricingError(
            f"aucun tarif connu pour {model!r} — ajouter une entrée à "
            "BATCH_PRICING_USD_PER_MTOK après vérification sur claude.com/pricing"
        )
    input_price, output_price = BATCH_PRICING_USD_PER_MTOK[model]
    million = Decimal(1_000_000)
    return (Decimal(input_tokens) * input_price + Decimal(output_tokens) * output_price) / million
