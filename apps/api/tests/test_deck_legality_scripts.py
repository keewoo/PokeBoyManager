"""Légalité : catégorie des constats et effets non scriptés (lot `j-effets-couverture-outil`).

Logique **pure** (aucune base). Deux apports du lot, tous deux absents de `evaluate` avant lui —
donc chaque test échoue sans le lot et passe avec :

* chaque constat porte une **catégorie** (`possession` / `legalite` / `script`) : le constructeur
  peut dire CE QUI bloque chaque carte refusée (critère n°1) ;
* un effet non scripté devient un constat `unsupported_effect` **bloquant**, émis uniquement pour
  les cartes réellement dans le deck jugé (jamais la carte d'un autre deck).
"""

import uuid

from pbm_api.decks import formats
from pbm_api.decks.legality import (
    BLOCKING,
    CATEGORY_LEGALITE,
    CATEGORY_POSSESSION,
    CATEGORY_SCRIPT,
    CODE_NOT_OWNED,
    CODE_UNSUPPORTED_EFFECT,
    DeckCardFact,
    category_for,
    evaluate,
)


def _id() -> uuid.UUID:
    return uuid.uuid4()


def _basic_pokemon(card_id=None, qty=4, owned=None, name="Pikachu") -> DeckCardFact:
    return DeckCardFact(
        card_id or _id(), name, "Pokémon", None, quantity=qty,
        owned=qty if owned is None else owned, stage="Base",
    )


def _basic_energy(qty=56, name="Énergie Feu") -> DeckCardFact:
    return DeckCardFact(_id(), name, "Énergie", "Normal", quantity=qty, owned=0)


# ----------------------------------------------------------------------------------- catégories
def test_category_for_classe_chaque_code():
    assert category_for(CODE_NOT_OWNED) == CATEGORY_POSSESSION
    assert category_for(CODE_UNSUPPORTED_EFFECT) == CATEGORY_SCRIPT
    assert category_for("deck_size") == CATEGORY_LEGALITE
    assert category_for("code_inconnu") == CATEGORY_LEGALITE  # défaut prudent


def test_issue_not_owned_porte_la_categorie_possession():
    report = evaluate([
        DeckCardFact(_id(), "Dracaufeu", "Pokémon", None, quantity=3, owned=0, stage="Niveau 2"),
        _basic_pokemon(),
        _basic_energy(56),
    ])
    not_owned = next(i for i in report.issues if i.code == CODE_NOT_OWNED)
    assert not_owned.category == CATEGORY_POSSESSION


def test_issue_de_format_porte_la_categorie_legalite():
    report = evaluate([
        DeckCardFact(_id(), "Vieux Dresseur", "Dresseur", None, quantity=1, owned=1,
                     legal_standard=False, legal_expanded=True),
        _basic_pokemon(), _basic_energy(55),
    ], formats.STANDARD)
    out = next(i for i in report.issues if i.code == "out_of_format")
    assert out.category == CATEGORY_LEGALITE


# ----------------------------------------------------------------------- effet non scripté (D9)
def test_unsupported_effect_devient_un_constat_bloquant_categorie_script():
    cid = _id()
    report = evaluate(
        [_basic_pokemon(card_id=cid, name="Pikachu étrange"), _basic_energy(56)],
        formats.STANDARD,
        unsupported={cid: "attaque — aucun script écrit pour ce texte d'effet"},
    )
    issue = next(i for i in report.issues if i.code == CODE_UNSUPPORTED_EFFECT)
    assert issue.category == CATEGORY_SCRIPT
    assert issue.severity == BLOCKING
    assert issue.card_id == cid
    assert "aucun script" in issue.message
    assert report.legal is False


def test_unsupported_sans_carte_dans_le_deck_nemet_rien():
    # La carte citée dans `unsupported` n'est PAS dans ce deck : aucun constat (pas de fuite).
    report = evaluate(
        [_basic_pokemon(), _basic_energy(56)],
        formats.STANDARD,
        unsupported={_id(): "effet d'un autre deck"},
    )
    assert not any(i.code == CODE_UNSUPPORTED_EFFECT for i in report.issues)


def test_unsupported_absent_ne_change_rien():
    # Sans `unsupported`, le comportement d'avant le lot est préservé (deck légal reste légal).
    report = evaluate([_basic_pokemon(), _basic_energy(56)])
    assert report.legal is True
    assert not any(i.code == CODE_UNSUPPORTED_EFFECT for i in report.issues)
