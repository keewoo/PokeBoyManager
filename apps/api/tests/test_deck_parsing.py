"""Analyseur de liste de deck (mission `v7-decks-import-export`, point 1) — logique pure.

Sans ces tests le module `parsing` n'existe pas : ils échouent tous à l'import avant le lot, et
passent avec (livrable « un test qui échoue sans le changement »)."""

from pbm_api.decks.parsing import parse_deck_list, parse_line


def test_quantity_name_set_number():
    line = parse_line(1, "3 Dracaufeu ex PAF 234")
    assert line.kind == "card"
    assert line.quantity == 3
    assert line.name == "Dracaufeu ex"
    assert line.set_code == "PAF"
    assert line.number == "234"


def test_quantity_with_x():
    assert parse_line(1, "2x Pikachu").quantity == 2
    assert parse_line(1, "2x Pikachu").name == "Pikachu"
    assert parse_line(1, "4 x Roucool").quantity == 4


def test_implicit_quantity_is_one_and_noted():
    line = parse_line(1, "Iono")
    assert line.quantity == 1
    assert line.name == "Iono"
    assert any("implicite" in n for n in line.notes)


def test_number_with_total():
    line = parse_line(1, "1 Nidoran 236/197")
    assert line.name == "Nidoran"
    assert line.number == "236"
    assert line.total == 197


def test_promo_number_prefix():
    line = parse_line(1, "1 Pikachu SVP 085")
    assert line.number == "085"
    assert line.set_code == "SVP"
    assert line.name == "Pikachu"


def test_name_suffix_not_taken_for_set_code():
    """« Dracaufeu VMAX 020 » : VMAX est un suffixe de nom, pas une pastille d'extension."""
    line = parse_line(1, "3 Dracaufeu VMAX 020")
    assert line.number == "020"
    assert line.set_code is None
    assert line.name == "Dracaufeu VMAX"


def test_energy_name_kept_whole():
    line = parse_line(1, "10 Énergie Feu")
    assert line.name == "Énergie Feu"
    assert line.number is None


def test_parenthesized_set_number_our_export():
    line = parse_line(1, "3 Dracaufeu ex (PAF 234)")
    assert line.name == "Dracaufeu ex"
    assert line.set_code == "PAF"
    assert line.number == "234"


def test_section_headers_recognized():
    for raw in ["Pokémon: 12", "Trainer", "Énergie : 6", "Total Cards: 60", "Dresseur: 30"]:
        assert parse_line(1, raw).kind == "section", raw


def test_comments_and_blanks():
    assert parse_line(1, "# un commentaire").kind == "comment"
    assert parse_line(1, "// autre").kind == "comment"
    assert parse_line(1, "   ").kind == "blank"


def test_bullets_stripped():
    line = parse_line(1, "- 2 Professeur Chen")
    assert line.quantity == 2
    assert line.name == "Professeur Chen"


def test_parse_full_ptcgl_export():
    text = (
        "Pokémon: 3\n"
        "3 Dracaufeu ex PAF 234\n"
        "\n"
        "Trainer: 2\n"
        "2 Iono PAL 185\n"
        "# note libre\n"
        "Energy: 1\n"
        "10 Énergie Feu\n"
        "Total Cards: 60\n"
    )
    lines = parse_deck_list(text)
    kinds = [ln.kind for ln in lines]
    assert kinds.count("section") == 4  # Pokémon, Trainer, Energy, Total Cards
    cards = [ln for ln in lines if ln.kind == "card"]
    assert [c.name for c in cards] == ["Dracaufeu ex", "Iono", "Énergie Feu"]
    assert [c.quantity for c in cards] == [3, 2, 10]
