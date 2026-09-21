"""Contrôle de légalité des decks — logique pure (missions `v7-decks-api` + `v7-decks-legalite`).

Ce fichier verrouille les règles :
  - socle `v7-decks-api` : 60 cartes, 4 exemplaires par nom, possession, décision D10 (Énergies
    de base illimitées et fournies, Énergies spéciales soumises à possession et à la règle des 4) ;
  - `v7-decks-legalite` : sévérité `bloquant`/`avertissement` de chaque constat, « au moins un
    Pokémon de base », légalité par format (Standard / Étendu / Illimité), exclusion des
    contrefaçons.

Les pièges exigés par la mission (point 3) sont couverts explicitement : 5ᵉ exemplaire d'un même
nom sous deux illustrations, Énergie spéciale non possédée, deck sans Pokémon de base, carte
contrefaite. Chaque assertion de `v7-decks-legalite` échoue sans le lot (sévérité, format,
Pokémon de base et contrefaçon n'existaient pas dans `evaluate`).
"""

import uuid

from pbm_api.decks import energy, formats
from pbm_api.decks.legality import (
    BLOCKING,
    CODE_COPY_LIMIT,
    CODE_COUNTERFEIT_EXCLUDED,
    CODE_DECK_SIZE,
    CODE_NO_BASIC_POKEMON,
    CODE_NOT_OWNED,
    CODE_OUT_OF_FORMAT,
    DECK_SIZE,
    MAX_COPIES_PER_NAME,
    WARNING,
    DeckCardFact,
    evaluate,
    is_basic_pokemon,
)


def _id() -> uuid.UUID:
    return uuid.uuid4()


def _basic_pokemon(qty: int = 4, owned: int | None = None, name: str = "Pikachu") -> DeckCardFact:
    """Un Pokémon de base possédé — de quoi satisfaire la règle « au moins un Pokémon de base »."""
    return DeckCardFact(
        _id(), name, "Pokémon", None, quantity=qty, owned=qty if owned is None else owned,
        stage="Base",
    )


def _basic_energy(qty: int, name: str = "Énergie Feu") -> DeckCardFact:
    return DeckCardFact(_id(), name, "Énergie", "Normal", quantity=qty, owned=0)


def _codes(report) -> list[str]:
    return [i.code for i in report.issues]


# --------------------------------------------------------------------- classification énergies
def test_basic_energy_recognized_by_name_fallback():
    assert energy.is_basic_energy("Énergie", "Énergie Feu", None) is True
    assert energy.is_basic_energy("Énergie", "Énergie Electrik", None) is True
    assert energy.is_basic_energy("Énergie", "Énergie obscurité", None) is True


def test_special_energy_is_not_basic():
    assert energy.is_basic_energy("Énergie", "Double Énergie Incolore", None) is False
    assert energy.is_special_energy("Énergie", "Double Énergie Incolore", None) is True


def test_energy_type_column_is_authoritative_over_name():
    assert energy.is_basic_energy("Énergie", "Énergie inédite 2030", "Normal") is True
    assert energy.is_basic_energy("Énergie", "Énergie Feu", "Special") is False


def test_trainer_and_pokemon_are_never_energy():
    assert energy.is_energy("Dresseur") is False
    assert energy.is_basic_energy("Dresseur", "Recherche d'énergie", None) is False
    assert energy.is_energy("Pokémon") is False


# ------------------------------------------------------------------- Pokémon de base (détection)
def test_is_basic_pokemon_true_for_stage_base():
    assert is_basic_pokemon("Pokémon", "Base") is True


def test_is_basic_pokemon_false_for_evolution():
    assert is_basic_pokemon("Pokémon", "Niveau 1") is False
    assert is_basic_pokemon("Pokémon", "Niveau 2") is False


def test_is_basic_pokemon_false_for_non_pokemon():
    assert is_basic_pokemon("Énergie", "Base") is False
    assert is_basic_pokemon("Dresseur", "Base") is False
    assert is_basic_pokemon("Pokémon", None) is False


def test_is_basic_pokemon_accepts_english_basic_stage():
    # Filet de sécurité : un catalogue en anglais dirait "Basic".
    assert is_basic_pokemon("Pokemon", "Basic") is True


# --------------------------------------------------------------------------------- légalité
def test_legal_deck_is_reported_legal():
    # 4 Pokémon de base possédés + 56 Énergies de base = 60, tout en règle.
    report = evaluate([_basic_pokemon(4), _basic_energy(56)])
    assert report.card_count == DECK_SIZE
    assert report.legal is True
    assert report.issues == []
    assert report.format == formats.STANDARD


def test_deck_size_too_small():
    report = evaluate([_basic_pokemon(4), _basic_energy(55)])  # 59
    assert report.legal is False
    assert report.size_ok is False
    size = [i for i in report.issues if i.code == CODE_DECK_SIZE]
    assert size and size[0].detail == {"count": 59, "expected": DECK_SIZE}


def test_deck_size_too_large():
    report = evaluate([_basic_pokemon(4), _basic_energy(57)])  # 61
    assert any(i.code == CODE_DECK_SIZE for i in report.issues)
    assert report.card_count == 61


def test_four_copy_rule_applies_to_non_basic():
    report = evaluate([_basic_pokemon(4, name="Pikachu"), DeckCardFact(
        _id(), "Bruyverne", "Pokémon", None, quantity=5, owned=5, stage="Niveau 1"
    ), _basic_energy(51)])
    copy = [i for i in report.issues if i.code == CODE_COPY_LIMIT]
    assert len(copy) == 1
    assert copy[0].card_name == "Bruyverne"
    assert copy[0].detail == {"count": 5, "limit": MAX_COPIES_PER_NAME}


def test_fifth_copy_across_two_printings_is_flagged():
    # PIÈGE (mission) : 5ᵉ exemplaire d'un même NOM sous deux illustrations (card_id distincts).
    report = evaluate([
        _basic_pokemon(4),
        DeckCardFact(_id(), "Professeur Chen", "Dresseur", None, quantity=2, owned=2),
        DeckCardFact(_id(), "Professeur Chen", "Dresseur", None, quantity=3, owned=3),
        _basic_energy(51),
    ])
    copy = [i for i in report.issues if i.code == CODE_COPY_LIMIT]
    assert len(copy) == 1
    assert copy[0].detail["count"] == 5


def test_exactly_four_copies_is_allowed():
    report = evaluate([
        _basic_pokemon(1),
        DeckCardFact(_id(), "Sbire", "Dresseur", None, quantity=4, owned=4),
        _basic_energy(55),
    ])
    assert not any(i.code == CODE_COPY_LIMIT for i in report.issues)


def test_basic_energy_exempt_from_four_copy():
    # 55 Énergies de base d'un même nom : jamais de dépassement (illimitée, D10).
    report = evaluate([_basic_pokemon(5, owned=5), _basic_energy(55)])
    assert not any(i.code == CODE_COPY_LIMIT and i.card_name == "Énergie Feu"
                   for i in report.issues)
    fire = next(c for c in report.cards if c.name == "Énergie Feu")
    assert fire.is_basic_energy is True


def test_basic_energy_exempt_from_ownership():
    # 56 Énergies de base non possédées : fournies, jamais un manque (D10).
    report = evaluate([_basic_pokemon(4), _basic_energy(56)])
    fire = next(c for c in report.cards if c.name == "Énergie Feu")
    assert fire.missing == 0
    assert not any(i.code == CODE_NOT_OWNED for i in report.issues)


def test_special_energy_requires_ownership():
    # PIÈGE (mission) : Énergie spéciale non entièrement possédée.
    report = evaluate([
        _basic_pokemon(4),
        DeckCardFact(_id(), "Double Énergie", "Énergie", "Special", quantity=4, owned=1),
        _basic_energy(52),
    ])
    not_owned = [i for i in report.issues if i.code == CODE_NOT_OWNED]
    assert len(not_owned) == 1
    assert not_owned[0].detail == {"required": 4, "owned": 1, "missing": 3}
    assert not_owned[0].severity == BLOCKING


def test_missing_ownership_reported_for_pokemon():
    report = evaluate([
        DeckCardFact(_id(), "Dracaufeu", "Pokémon", None, quantity=3, owned=0, stage="Niveau 2"),
        _basic_pokemon(1),
        _basic_energy(56),
    ])
    not_owned = [i for i in report.issues if i.code == CODE_NOT_OWNED]
    assert not_owned and not_owned[0].card_name == "Dracaufeu"
    assert not_owned[0].detail["missing"] == 3


def test_owned_exactly_enough_is_legal():
    report = evaluate([_basic_pokemon(4, owned=4), _basic_energy(56)])
    assert not any(i.code == CODE_NOT_OWNED for i in report.issues)


# ------------------------------------------------------------------- au moins un Pokémon de base
def test_deck_without_basic_pokemon_is_illegal():
    # PIÈGE (mission) : deck sans Pokémon de base — 60 Énergies de base, pourtant injouable.
    report = evaluate([_basic_energy(60)])
    no_basic = [i for i in report.issues if i.code == CODE_NO_BASIC_POKEMON]
    assert len(no_basic) == 1
    assert no_basic[0].severity == BLOCKING
    assert report.legal is False


def test_evolution_only_deck_is_flagged_no_basic_pokemon():
    report = evaluate([
        DeckCardFact(_id(), "Reptincel", "Pokémon", None, quantity=4, owned=4, stage="Niveau 1"),
        _basic_energy(56),
    ])
    assert any(i.code == CODE_NO_BASIC_POKEMON for i in report.issues)


def test_deck_with_basic_pokemon_passes_that_rule():
    report = evaluate([_basic_pokemon(4), _basic_energy(56)])
    assert not any(i.code == CODE_NO_BASIC_POKEMON for i in report.issues)


def test_empty_deck_does_not_add_no_basic_pokemon_noise():
    # Un deck vide échoue sur la taille ; on ne double pas avec « pas de Pokémon de base ».
    report = evaluate([])
    assert _codes(report) == [CODE_DECK_SIZE]


# ------------------------------------------------------------------------------ sévérité
def test_core_issues_are_all_blocking():
    report = evaluate([
        DeckCardFact(_id(), "Pikachu", "Pokémon", None, quantity=5, owned=1, stage="Niveau 1"),
    ])  # trop peu de cartes, pas de Pokémon de base, dépassement, non possédé
    codes = set(_codes(report))
    assert {CODE_DECK_SIZE, CODE_COPY_LIMIT, CODE_NOT_OWNED, CODE_NO_BASIC_POKEMON} <= codes
    assert all(i.severity == BLOCKING for i in report.issues)
    assert report.legal is False


def test_counterfeit_is_a_warning_not_blocking():
    # Un avertissement seul ne retire pas la légalité.
    report = evaluate([
        DeckCardFact(_id(), "Pikachu", "Pokémon", None, quantity=4, owned=4, stage="Base",
                     counterfeit_owned=2),
        _basic_energy(56),
    ])
    warn = [i for i in report.issues if i.code == CODE_COUNTERFEIT_EXCLUDED]
    assert len(warn) == 1
    assert warn[0].severity == WARNING
    assert warn[0].detail == {"counterfeit": 2}
    assert report.legal is True  # l'avertissement n'interdit pas


def test_counterfeit_excluded_can_cause_not_owned():
    # PIÈGE (mission) : carte contrefaite — les exemplaires contrefaçon sont exclus du décompte,
    # ce qui peut créer un manque de possession bloquant, expliqué par l'avertissement.
    report = evaluate([
        DeckCardFact(_id(), "Dracaufeu", "Pokémon", None, quantity=2, owned=0, stage="Niveau 2",
                     counterfeit_owned=2),
        _basic_pokemon(1),
        _basic_energy(57),
    ])
    codes = _codes(report)
    assert CODE_NOT_OWNED in codes
    assert CODE_COUNTERFEIT_EXCLUDED in codes
    assert report.legal is False  # à cause du not_owned, pas de l'avertissement


# -------------------------------------------------------------------------------- formats
def test_unlimited_format_allows_any_card():
    fact = DeckCardFact(_id(), "Vieux Dresseur", "Dresseur", None, quantity=1, owned=1,
                        legal_standard=False, legal_expanded=False)
    report = evaluate([fact, _basic_pokemon(4), _basic_energy(55)], formats.UNLIMITED)
    assert not any(i.code == CODE_OUT_OF_FORMAT for i in report.issues)
    assert report.format == formats.UNLIMITED
    assert report.format_label == "Illimité"


def test_standard_format_flags_out_of_format_card():
    fact = DeckCardFact(_id(), "Vieux Dresseur", "Dresseur", None, quantity=1, owned=1,
                        legal_standard=False, legal_expanded=True)
    report = evaluate([fact, _basic_pokemon(4), _basic_energy(55)], formats.STANDARD)
    out = [i for i in report.issues if i.code == CODE_OUT_OF_FORMAT]
    assert len(out) == 1
    assert out[0].card_name == "Vieux Dresseur"
    assert out[0].severity == BLOCKING
    assert out[0].detail == {"format": "standard"}


def test_expanded_format_uses_expanded_legality():
    # legal_standard False mais legal_expanded True : hors Standard, dans Étendu.
    fact = DeckCardFact(_id(), "Carte Étendu", "Dresseur", None, quantity=1, owned=1,
                        legal_standard=False, legal_expanded=True)
    std = evaluate([fact, _basic_pokemon(4), _basic_energy(55)], formats.STANDARD)
    exp = evaluate([fact, _basic_pokemon(4), _basic_energy(55)], formats.EXPANDED)
    assert any(i.code == CODE_OUT_OF_FORMAT for i in std.issues)
    assert not any(i.code == CODE_OUT_OF_FORMAT for i in exp.issues)


def test_unknown_legality_is_not_flagged():
    # legal_standard None (vieille carte non réévaluée) : bénéfice du doute, jamais bloquée.
    fact = DeckCardFact(_id(), "Carte inconnue", "Dresseur", None, quantity=1, owned=1,
                        legal_standard=None, legal_expanded=None)
    report = evaluate([fact, _basic_pokemon(4), _basic_energy(55)], formats.STANDARD)
    assert not any(i.code == CODE_OUT_OF_FORMAT for i in report.issues)


def test_basic_energy_always_in_format():
    # Une Énergie de base marquée non-légale reste autorisée dans tous les formats.
    fact = DeckCardFact(_id(), "Énergie Feu", "Énergie", "Normal", quantity=56, owned=0,
                        legal_standard=False, legal_expanded=False)
    report = evaluate([_basic_pokemon(4), fact], formats.STANDARD)
    assert not any(i.code == CODE_OUT_OF_FORMAT for i in report.issues)
    fire = next(c for c in report.cards if c.name == "Énergie Feu")
    assert fire.in_format is True


def test_invalid_format_falls_back_to_default():
    report = evaluate([_basic_pokemon(4), _basic_energy(56)], "pas-un-format")
    assert report.format == formats.DEFAULT_FORMAT


def test_card_legality_carries_format_and_counterfeit_flags():
    report = evaluate([
        DeckCardFact(_id(), "Pikachu", "Pokémon", None, quantity=4, owned=4, stage="Base",
                     counterfeit_owned=1, legal_standard=True),
        _basic_energy(56),
    ], formats.STANDARD)
    pika = next(c for c in report.cards if c.name == "Pikachu")
    assert pika.is_basic_pokemon is True
    assert pika.in_format is True
    assert pika.counterfeit_excluded == 1
