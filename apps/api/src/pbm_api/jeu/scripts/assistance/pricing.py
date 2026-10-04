"""Le **coût d'un appel** d'assistance — en tarif *standard*, pas Batch.

L'assistance appelle l'API Messages **synchrone** (un script à la fois, avec une étape de
contradiction et des tests exécutés entre les deux) : la remise de 50 % de la Message Batches API
ne s'applique **pas**. Le tarif standard vaut donc **le double** du tarif Batch tenu par
:mod:`pbm_api.insights_batch.pricing` — qu'on dérive de là plutôt que d'entretenir une seconde
table (une seule source de vérité : réviser les prix se fait à un seul endroit, le lot v4).

Mission point 4 / DJ8 : plafonner le budget et mesurer le coût par carte validée **sur un prix
réel**, jamais une estimation inventée. Un modèle sans tarif connu fait lever une erreur plutôt que
d'être facturé à zéro (ce qui laisserait croire que le plafond n'est jamais atteint).
"""

from __future__ import annotations

from decimal import Decimal

from pbm_api.insights_batch.pricing import (
    BATCH_PRICING_USD_PER_MTOK,
    UnknownModelPricingError,
)

#: Facteur entre le tarif Batch (remisé de 50 %) et le tarif standard de l'API synchrone.
_FACTEUR_STANDARD = Decimal(2)


def cout_usd(model: str, *, input_tokens: int, output_tokens: int) -> Decimal:
    """Coût USD d'un appel synchrone selon les jetons facturés (tarif standard = 2 × Batch).

    Lève :class:`~pbm_api.insights_batch.pricing.UnknownModelPricingError` pour un modèle sans tarif
    connu — on refuse de facturer à zéro un modèle qu'on ne sait pas tarifer (le plafond de budget
    s'appuie dessus ; un zéro inventé le rendrait inopérant).
    """
    if model not in BATCH_PRICING_USD_PER_MTOK:
        raise UnknownModelPricingError(
            f"aucun tarif connu pour {model!r} — ajouter une entrée à "
            "BATCH_PRICING_USD_PER_MTOK (pbm_api.insights_batch.pricing) après vérification."
        )
    prix_entree_batch, prix_sortie_batch = BATCH_PRICING_USD_PER_MTOK[model]
    prix_entree = prix_entree_batch * _FACTEUR_STANDARD
    prix_sortie = prix_sortie_batch * _FACTEUR_STANDARD
    million = Decimal(1_000_000)
    return (Decimal(input_tokens) * prix_entree + Decimal(output_tokens) * prix_sortie) / million


__all__ = ["cout_usd", "UnknownModelPricingError"]
