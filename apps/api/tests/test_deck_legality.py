"""Contrôle de légalité des decks — logique pure (mission `v7-decks-api`).

Aucune de ces assertions ne passe sans le lot : `pbm_api.decks.legality`/`energy` n'existaient
pas. Elles verrouillent la décision D10 (Énergies de base illimitées et fournies, Énergies
spéciales soumises à possession et à la règle des 4) et les trois règles : 60 cartes, 4
exemplaires par nom, possession.
"""

import uuid

from pbm_api.decks import energy
from pbm_api.decks.legality import (
    DECK_SIZE,
    MAX_COPIES_PER_NAME,
    DeckCardFact,
    evaluate,
)


def _id() -> uuid.UUID:
    return uuid.uuid4()


# --------------------------------------------------------------------- classification énergies
def test_basic_energy_recognized_by_name_fallback():
    # `energy_type` absent (données importées avant la colonne) : le nom tranche.
    assert energy.is_basic_energy("Énergie", "Énergie Feu", None) is True
    # Ancienne localisation de l'Éclair, réellement présente au catalogue.
    assert energy.is_basic_energy("Énergie", "Énergie Electrik", None) is True
    # La casse ne doit pas compter.
    assert energy.is_basic_energy("Énergie", "Énergie obscurité", None) is True


def test_special_energy_is_not_basic():
    assert energy.is_basic_energy("Énergie", "Double Énergie Incolore", None) is False
    assert energy.is_special_energy("Énergie", "Double Énergie Incolore", None) is True


def test_energy_type_column_is_authoritative_over_name():
    # `energy_type` prime : un nom inconnu marqué "Normal" est de base…
    assert energy.is_basic_energy("Énergie", "Énergie inédite 2030", "Normal") is True
    # …et une carte au nom d'Énergie de base marquée "Special" ne l'est pas.
    assert energy.is_basic_energy("Énergie", "Énergie Feu", "Special") is False


def test_trainer_and_pokemon_are_never_energy():
    # Une carte Dresseur dont le nom contient « énergie » n'est pas une Énergie.
    assert energy.is_energy("Dresseur") is False
    assert energy.is_basic_energy("Dresseur", "Recherche d'énergie", None) is False
    assert energy.is_energy("Pokémon") is False


# --------------------------------------------------------------------------------- légalité
def test_legal_deck_is_reported_legal():
    # 4 Énergie spéciale possédées + 56 Énergie de base = 60 cartes, tout en règle.
    facts = [
        DeckCardFact(_id(), "Double Énergie", "Énergie", "Special", quantity=4, owned=4),
        DeckCardFact(_id(), "Énergie Feu", "Énergie", "Normal", quantity=56, owned=0),
    ]
    report = evaluate(facts)
    assert report.card_count == DECK_SIZE
    assert report.legal is True
    assert report.issues == []


def test_deck_size_must_be_exactly_60():
    facts = [DeckCardFact(_id(), "Énergie Feu", "Énergie", "Normal", quantity=59, owned=0)]
    report = evaluate(facts)
    assert report.legal is False
    assert report.size_ok is False
    assert [i.code for i in report.issues] == ["deck_size"]
    assert report.issues[0].detail == {"count": 59, "expected": DECK_SIZE}


def test_over_60_is_flagged():
    facts = [DeckCardFact(_id(), "Énergie Feu", "Énergie", "Normal", quantity=61, owned=0)]
    report = evaluate(facts)
    assert any(i.code == "deck_size" for i in report.issues)


def test_four_copy_rule_applies_to_non_basic():
    facts = [
        DeckCardFact(_id(), "Pikachu", "Pokémon", None, quantity=5, owned=5),
        DeckCardFact(_id(), "Énergie Feu", "Énergie", "Normal", quantity=55, owned=0),
    ]
    report = evaluate(facts)
    copy_issues = [i for i in report.issues if i.code == "copy_limit"]
    assert len(copy_issues) == 1
    assert copy_issues[0].card_name == "Pikachu"
    assert copy_issues[0].detail == {"count": 5, "limit": MAX_COPIES_PER_NAME}


def test_four_copy_rule_counts_by_name_across_printings():
    # Deux impressions (card_id différents) du même nom : la limite est par NOM.
    facts = [
        DeckCardFact(_id(), "Professeur Chen", "Dresseur", None, quantity=2, owned=2),
        DeckCardFact(_id(), "Professeur Chen", "Dresseur", None, quantity=3, owned=3),
        DeckCardFact(_id(), "Énergie Feu", "Énergie", "Normal", quantity=55, owned=0),
    ]
    report = evaluate(facts)
    copy_issues = [i for i in report.issues if i.code == "copy_limit"]
    assert len(copy_issues) == 1
    assert copy_issues[0].detail["count"] == 5


def test_basic_energy_is_exempt_from_four_copy_and_ownership():
    # 60 Énergie de base, aucune possédée : légal (illimitée, fournie — D10).
    facts = [DeckCardFact(_id(), "Énergie Feu", "Énergie", "Normal", quantity=60, owned=0)]
    report = evaluate(facts)
    assert report.legal is True
    assert report.issues == []
    assert report.cards[0].is_basic_energy is True
    assert report.cards[0].missing == 0


def test_special_energy_requires_ownership():
    facts = [
        DeckCardFact(_id(), "Double Énergie", "Énergie", "Special", quantity=4, owned=1),
        DeckCardFact(_id(), "Énergie Feu", "Énergie", "Normal", quantity=56, owned=0),
    ]
    report = evaluate(facts)
    not_owned = [i for i in report.issues if i.code == "not_owned"]
    assert len(not_owned) == 1
    assert not_owned[0].detail == {"required": 4, "owned": 1, "missing": 3}


def test_missing_ownership_reported_for_pokemon():
    facts = [
        DeckCardFact(_id(), "Dracaufeu", "Pokémon", None, quantity=3, owned=0),
        DeckCardFact(_id(), "Énergie Feu", "Énergie", "Normal", quantity=57, owned=0),
    ]
    report = evaluate(facts)
    not_owned = [i for i in report.issues if i.code == "not_owned"]
    assert not_owned and not_owned[0].card_name == "Dracaufeu"
    assert not_owned[0].detail["missing"] == 3
