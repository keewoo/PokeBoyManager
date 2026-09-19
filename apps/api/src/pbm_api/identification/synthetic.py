"""Jeu de 100 cartes étiquetées (mission point 5, objectif top-3 ≥ 95 %) — inclut les 9 cartes
de démonstration (`pbm_api.seed.DEMO_CARDS`, la « photo de référence » du classeur 3×3).

Aucune vraie photo ni clé IA réelle sur chimera (même contrainte que
`pbm_api.detection.synthetic`, voir son avertissement) : ce module ne simule pas une image, il
simule directement la sortie de l'extraction IA (`CardExtraction`) à partir d'une carte connue,
avec un bruit contrôlé et reproductible (numéro décalé ou absent, nom sans accents/en
majuscules, code d'extension absent ou faux) — ce qu'une vraie extraction imparfaite produirait.
Il valide donc le *rapprochement* (`pbm_api.identification.reconciliation.reconcile`), pas la
lecture visuelle elle-même, hors de portée sans clé réelle (voir
`scripts/test_identification_manual.py`).
"""

import random
from dataclasses import dataclass

from pbm_api.identification.schemas import CardExtraction
from pbm_api.seed import DEMO_CARDS, DEMO_SETS

# Extensions synthétiques pour les 91 cartes générées en plus des 9 cartes de démonstration —
# des cartes homonymes y sont délibérément réparties (ex: le même nom dans deux extensions) pour
# stresser la désambiguïsation par numéro + extension (mission point 2).
_SYNTHETIC_SETS = [
    {"code": "syn-a", "name": "Ensemble synthétique A", "total_cards": 32},
    {"code": "syn-b", "name": "Ensemble synthétique B", "total_cards": 32},
    {"code": "syn-c", "name": "Ensemble synthétique C", "total_cards": 32},
]

# (nom FR, nom EN) — noms réels, réutilisés en base de test comme le fait déjà `pbm_api.seed`.
_BASE_NAMES: list[tuple[str, str]] = [
    ("Bulbizarre", "Bulbasaur"), ("Herbizarre", "Ivysaur"), ("Florizarre", "Venusaur"),
    ("Salamèche", "Charmander"), ("Reptincel", "Charmeleon"), ("Dracaufeu", "Charizard"),
    ("Carapuce", "Squirtle"), ("Carabaffe", "Wartortle"), ("Tortank", "Blastoise"),
    ("Chenipan", "Caterpie"), ("Aspicot", "Weedle"), ("Roucool", "Pidgey"),
    ("Rattata", "Rattata"), ("Piafabec", "Spearow"), ("Abo", "Ekans"),
    ("Sabelette", "Sandshrew"), ("Mélofée", "Clefairy"), ("Goupix", "Vulpix"),
    ("Rondoudou", "Jigglypuff"), ("Nosferapti", "Zubat"), ("Mystherbe", "Oddish"),
    ("Paras", "Paras"), ("Mimitoss", "Venonat"), ("Ponyta", "Ponyta"),
    ("Ramoloss", "Slowpoke"), ("Magnéti", "Magnemite"), ("Canarticho", "Farfetch'd"),
    ("Doduo", "Doduo"), ("Otaria", "Seel"), ("Tadmorv", "Grimer"),
    ("Krabby", "Krabby"), ("Voltorbe", "Voltorb"), ("Osselait", "Cubone"),
    ("Kicklee", "Hitmonlee"), ("Tygnon", "Hitmonchan"), ("Lippoutou", "Lickitung"),
    ("Smogo", "Koffing"), ("Rhinocorne", "Rhyhorn"), ("Leveinard", "Chansey"),
    ("Saquedeneu", "Tangela"), ("Kangourex", "Kangaskhan"), ("Hypotrempe", "Horsea"),
    ("Hypocéan", "Seadra"), ("Poissirène", "Goldeen"),
]

_EXTRA_CARDS_COUNT = 91
_TOTAL_CARDS = _EXTRA_CARDS_COUNT + len(DEMO_CARDS)


@dataclass(frozen=True)
class LabeledCatalogCard:
    set_code: str
    set_name: str
    total_cards: int | None
    number: str
    name_fr: str
    name_en: str


@dataclass(frozen=True)
class SyntheticIdentificationCase:
    id: str
    card: LabeledCatalogCard
    extraction: CardExtraction


def _build_extra_cards() -> list[LabeledCatalogCard]:
    sets_by_code = {s["code"]: s for s in _SYNTHETIC_SETS}
    set_cycle = [s["code"] for s in _SYNTHETIC_SETS]
    counters = dict.fromkeys(set_cycle, 1)

    cards = []
    for i in range(_EXTRA_CARDS_COUNT):
        name_fr, name_en = _BASE_NAMES[i % len(_BASE_NAMES)]
        set_code = set_cycle[i % len(set_cycle)]
        number = counters[set_code]
        counters[set_code] += 1
        set_info = sets_by_code[set_code]
        cards.append(
            LabeledCatalogCard(
                set_code=set_code,
                set_name=set_info["name"],
                total_cards=set_info["total_cards"],
                number=str(number),
                name_fr=name_fr,
                name_en=name_en,
            )
        )
    return cards


def _build_demo_cards() -> list[LabeledCatalogCard]:
    sets_by_code = {s["code"]: s for s in DEMO_SETS}
    return [
        LabeledCatalogCard(
            set_code=card["set_code"],
            set_name=sets_by_code[card["set_code"]]["name"],
            total_cards=sets_by_code[card["set_code"]]["total_cards"],
            number=card["number"],
            name_fr=card["names"]["fr"],
            name_en=card["names"]["en"],
        )
        for card in DEMO_CARDS
    ]


def _noisy_extraction(
    rng: random.Random, card: LabeledCatalogCard, language: str
) -> CardExtraction:
    name = card.name_fr if language == "fr" else card.name_en

    if rng.random() < 0.2:
        # Accents perdus et casse changée — ce qu'un OCR/LLM lit souvent mal sur une pastille ou
        # un nom stylisé, mais que `unaccent` + trigram (mission `v2-recherche`) retrouvent.
        name_out = name.replace("é", "e").replace("è", "e").replace("É", "E").upper()
        name_confidence = rng.uniform(0.55, 0.75)
    else:
        name_out = name
        name_confidence = rng.uniform(0.85, 0.99)

    number_roll = rng.random()
    if number_roll < 0.15:
        number_out, number_confidence = None, 0.0
    elif number_roll < 0.30 and card.number.isdigit():
        number_out = str(int(card.number) + rng.choice([-1, 1]))
        number_confidence = rng.uniform(0.3, 0.5)
    else:
        number_out, number_confidence = card.number, rng.uniform(0.85, 0.99)

    set_code_roll = rng.random()
    if set_code_roll < 0.4:
        set_code_out, set_code_confidence = None, 0.0
    elif set_code_roll < 0.55:
        set_code_out, set_code_confidence = "??", rng.uniform(0.2, 0.4)
    else:
        set_code_out, set_code_confidence = card.set_code, rng.uniform(0.8, 0.97)

    total_out = card.total_cards if rng.random() < 0.5 else None

    return CardExtraction(
        name=name_out,
        name_confidence=name_confidence,
        number=number_out,
        number_confidence=number_confidence,
        total=total_out,
        total_confidence=rng.uniform(0.6, 0.9) if total_out is not None else 0.0,
        set_code=set_code_out,
        set_code_confidence=set_code_confidence,
        language=language,
        language_confidence=rng.uniform(0.8, 0.99),
    )


def generate_dataset(seed: int = 20260919) -> list[SyntheticIdentificationCase]:
    """100 cas étiquetés (mission point 5) : les 9 cartes de démonstration
    (`pbm_api.seed.DEMO_CARDS`) + 91 cartes synthétiques, chacune avec une extraction bruitée
    déterministe (langue alternée FR/EN)."""
    rng = random.Random(seed)
    cards = _build_demo_cards() + _build_extra_cards()
    assert len(cards) == _TOTAL_CARDS == 100

    cases = []
    for index, card in enumerate(cards):
        language = "fr" if index % 2 == 0 else "en"
        extraction = _noisy_extraction(rng, card, language)
        cases.append(
            SyntheticIdentificationCase(id=f"case_{index:03d}", card=card, extraction=extraction)
        )
    return cases
