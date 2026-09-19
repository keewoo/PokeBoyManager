"""Indices de contrefaçon (mission point 3) : le signal explicite rendu par l'IA dans le même
appel que l'identification (police, couleurs, format du numéro — mission), complété par un
contrôle déterministe qui ne dépend d'aucun appel IA : une carte perçue comme « gold »/métal
(`pbm_api.identification.schemas.CardVariantGuess.gold`) alors que la carte du catalogue
retenue n'est répertoriée sous aucune rareté « gold » connue n'existe pas sous cette forme —
elle est probablement une contrefaçon (ou un proxy/fan-made), jamais valorisée comme l'originale.
"""

from dataclasses import dataclass, field

# Mots-clés observés dans les raretés TCGdex des cartes réellement « or »/métal (voir
# `pbm_api.seed`, `pbm_api.catalog.import_service`) — recherche insensible à la casse, en
# sous-chaîne : une rareté absente du catalogue local (import partiel) est traitée comme
# "gold non confirmé", pas comme une preuve d'authenticité par excès de prudence inverse.
_GOLD_RARITY_KEYWORDS = ("gold", "secret", "hyper", "rainbow")


@dataclass(frozen=True)
class CounterfeitAssessment:
    suspected: bool
    reasons: list[str] = field(default_factory=list)


def _is_known_gold_rarity(rarity: str | None) -> bool:
    if not rarity:
        return False
    lowered = rarity.lower()
    return any(keyword in lowered for keyword in _GOLD_RARITY_KEYWORDS)


def assess_counterfeit(
    *,
    ai_suspected: bool,
    ai_reason: str | None,
    variant_guess: str | None,
    matched_card_rarity: str | None,
    has_matched_card: bool,
) -> CounterfeitAssessment:
    """`variant_guess`/`matched_card_rarity` viennent respectivement de l'extraction IA
    (`CardExtraction.variant`) et de la carte candidate retenue par le rapprochement catalogue
    (mission `v3-identification` point 2) — `has_matched_card` distingue « pas de rareté connue
    car aucune carte du catalogue n'a pu être rapprochée » (pas de contrôle possible) de « carte
    rapprochée, mais sa rareté ne confirme pas un tirage gold » (contrôle positif)."""
    reasons: list[str] = []
    if ai_suspected:
        reasons.append(ai_reason or "signal de contrefaçon relevé par l'IA à l'extraction")

    known_gold = has_matched_card and _is_known_gold_rarity(matched_card_rarity)
    if variant_guess == "gold" and has_matched_card and not known_gold:
        reasons.append(
            "carte perçue comme « gold »/métal, mais la carte rapprochée du catalogue n'est "
            "répertoriée sous aucune rareté « gold » connue"
        )

    return CounterfeitAssessment(suspected=bool(reasons), reasons=reasons)
