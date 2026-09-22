"""Indices de contrefaçon (mission `v3-etat` point 3, étendue par `v6-contrefacon` mission
point 1) : le signal explicite rendu par l'IA dans le même appel que l'identification (police,
couleurs, format du numéro — « indices visuels par le LLM »), complété par des contrôles
déterministes qui ne dépendent d'aucun appel IA :

- une carte perçue comme « gold »/métal (`pbm_api.identification.schemas.CardVariantGuess.gold`)
  alors que la carte du catalogue retenue n'est répertoriée sous aucune rareté « gold » connue ;
- plus généralement, une variante perçue (holo, reverse holo, 1ère édition) alors que la carte du
  catalogue retenue (`Card.variants`, TCGdex) déclare explicitement cette variante absente —
  mission point 1, « variante absente du catalogue » ;
- un total de série imprimé incohérent avec l'extension reconnue (`Set.total_cards`) — mission
  point 1, « numéro impossible ».

Dans les trois cas, la carte est probablement une contrefaçon (ou un proxy/fan-made), jamais
valorisée comme l'originale — mais toujours « probable », jamais « certaine » (mission « risques
& pièges » : faux positifs possibles sur des promos rares, contestable par l'utilisateur).
"""

from dataclasses import dataclass, field

# Mots-clés observés dans les raretés TCGdex des cartes réellement « or »/métal (voir
# `pbm_api.seed`, `pbm_api.catalog.import_service`) — recherche insensible à la casse, en
# sous-chaîne : une rareté absente du catalogue local (import partiel) est traitée comme
# "gold non confirmé", pas comme une preuve d'authenticité par excès de prudence inverse.
_GOLD_RARITY_KEYWORDS = ("gold", "secret", "hyper", "rainbow")

# `CardVariantGuess` (perception IA, `pbm_api.identification.schemas`) -> clé du JSONB
# `Card.variants` (déclaratif catalogue, TCGdex `variants`) — seules les variantes que TCGdex
# modélise explicitement sont contrôlables ainsi ; "gold" est déjà couvert par la rareté
# ci-dessus (TCGdex n'a pas de clé "gold" dans `variants`), et "full_art"/"other" n'ont aucune
# clé de catalogue correspondante (pas de contrôle possible, jamais un faux positif par défaut).
_VARIANT_CATALOG_KEYS = {
    "holo": "holo",
    "reverse_holo": "reverse",
    "first_edition": "firstEdition",
}


@dataclass(frozen=True)
class CounterfeitAssessment:
    suspected: bool
    reasons: list[str] = field(default_factory=list)


def _is_known_gold_rarity(rarity: str | None) -> bool:
    if not rarity:
        return False
    lowered = rarity.lower()
    return any(keyword in lowered for keyword in _GOLD_RARITY_KEYWORDS)


def _variant_absent_from_catalog(
    variant_guess: str | None, matched_card_variants: dict | None
) -> str | None:
    """`None` = pas de signal (variante non modélisée par TCGdex, ou catalogue incomplet pour
    cette carte — l'absence de donnée n'est jamais traitée comme une preuve d'inauthenticité)."""
    catalog_key = _VARIANT_CATALOG_KEYS.get(variant_guess or "")
    if catalog_key is None or matched_card_variants is None:
        return None
    if catalog_key not in matched_card_variants:
        return None
    if matched_card_variants[catalog_key] is False:
        return (
            f"variante « {variant_guess} » perçue, mais absente des variantes connues du "
            "catalogue pour cette carte"
        )
    return None


def _number_impossible(
    extraction_total: int | None, matched_set_total_cards: int | None
) -> str | None:
    """Le total de série imprimé sur la carte (`CardExtraction.total`, ce que l'utilisateur a
    photographié) doit correspondre au total officiel de l'extension reconnue
    (`Set.total_cards`) — vrai même pour un secret rare, dont le NUMÉRO dépasse ce total sans que
    le total imprimé change (ex. "202/198") : ne jamais comparer le numéro lui-même à ce total,
    seulement les deux totaux entre eux, pour ne pas signaler à tort une rareté légitime."""
    if extraction_total is None or matched_set_total_cards is None:
        return None
    if extraction_total != matched_set_total_cards:
        return (
            f"total imprimé ({extraction_total}) incohérent avec l'extension reconnue "
            f"({matched_set_total_cards} cartes)"
        )
    return None


def assess_counterfeit(
    *,
    ai_suspected: bool,
    ai_reason: str | None,
    variant_guess: str | None,
    matched_card_rarity: str | None,
    has_matched_card: bool,
    matched_card_variants: dict | None = None,
    extraction_total: int | None = None,
    matched_set_total_cards: int | None = None,
) -> CounterfeitAssessment:
    """`variant_guess`/`matched_card_rarity` viennent respectivement de l'extraction IA
    (`CardExtraction.variant`) et de la carte candidate retenue par le rapprochement catalogue
    (mission `v3-identification` point 2) — `has_matched_card` distingue « pas de rareté connue
    car aucune carte du catalogue n'a pu être rapprochée » (pas de contrôle possible) de « carte
    rapprochée, mais sa rareté ne confirme pas un tirage gold » (contrôle positif).
    `matched_card_variants`/`matched_set_total_cards` (mission `v6-contrefacon`) ne sont
    exploités que si `has_matched_card` — comme le contrôle « gold », un rapprochement manqué ne
    doit jamais produire un signal par excès de prudence inverse."""
    reasons: list[str] = []
    if ai_suspected:
        reasons.append(ai_reason or "signal de contrefaçon relevé par l'IA à l'extraction")

    known_gold = has_matched_card and _is_known_gold_rarity(matched_card_rarity)
    if variant_guess == "gold" and has_matched_card and not known_gold:
        reasons.append(
            "carte perçue comme « gold »/métal, mais la carte rapprochée du catalogue n'est "
            "répertoriée sous aucune rareté « gold » connue"
        )

    if has_matched_card:
        variant_reason = _variant_absent_from_catalog(variant_guess, matched_card_variants)
        if variant_reason:
            reasons.append(variant_reason)

        number_reason = _number_impossible(extraction_total, matched_set_total_cards)
        if number_reason:
            reasons.append(number_reason)

    return CounterfeitAssessment(suspected=bool(reasons), reasons=reasons)
