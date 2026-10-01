"""Classification du marqueur de règle normalisé (`pbm_api.catalog.prize_marker`) et garde
d'égalité avec la table du moteur.

Chaque cas de classification porte sur une **vraie carte** du catalogue de référence
(`pbm_catalogue_ref`, mesuré le 01/10/2026) : son `tcgdex_id` est cité, et son triplet (nom,
supertype, `rule_marker`) est reproduit tel quel. Ces cas **échouent avec l'ancien code** (qui
déduisait le nombre de récompenses du suffixe du nom) : une Méga-Évolution Pokémon ex finit par
« ex » mais donne 3 (R-13.7), une TAG TEAM finit par « GX » mais donne 3.
"""

import ast
from pathlib import Path

import pytest

from pbm_api.catalog.prize_marker import (
    MARQUEUR_INCONNU,
    corrected_stage_row,
    is_ordinary_stage,
    normalized_prize_marker,
)
from pbm_api.ingame.rules import LABELS_BY_MARKER, PRIZES_BY_MARKER

_POK = "Pokémon"  # valeur réelle du catalogue (français)


# (tcgdex_id, name, rule_marker, supertype, marqueur attendu)
_CASES = [
    # --- 3 récompenses : les pièges du suffixe du nom (R-13.7) ---
    ("mep-035", "Méga-Roitiflam-ex", "ex", _POK, "mega_ex"),
    ("x-null", "Méga-Diancie-ex", None, _POK, "mega_ex"),  # Méga 2025, rule_marker NULL
    ("smp-SM166", "Magicarpe et Wailord GX", "ESCOUADE", _POK, "tag_team"),
    ("smp-SM217", "Desséliande et Noctunoir GX", None, _POK, "tag_team"),  # TAG TEAM, rm NULL
    ("swsh4-21", "Astronelle VMAX", "VMAX", _POK, "vmax"),
    ("swshp-SWSH139", "Pikachu V-UNION", "V", _POK, "v_union"),
    # --- 2 récompenses ---
    ("ex1-97", "Elektek ex", "ex", _POK, "ex"),
    ("np-31", "Sulfura ex", None, _POK, "ex"),  # Pokémon ex, rule_marker NULL
    ("xy5-19", "Desséliande EX", "EX", _POK, "pokemon_ex"),
    ("xya-24a", "M-Élecsprint-ex", "MÉGA", _POK, "m_pokemon_ex"),
    ("sm6-73", "Zygarde GX", "GX", _POK, "gx"),
    ("swsh4-20", "Astronelle V", "V", _POK, "v"),
    ("swsh10-190", "Fragilady de Hisui VSTAR", "V", _POK, "vstar"),
    ("hgss2-90", "Entei & Raikou LÉGENDE (haut)", "LÉGENDE", _POK, "legende"),
    # --- 1 récompense (cartes à Rule Box) ---
    ("xy8-79", "Ossatueur TURBO", "TURBO", _POK, "break"),
    ("dp5-97", "Carchacrok", "Niveau Sup", _POK, "lv_x"),
    ("swshp-SWSH230", "Évoli Radieux", None, _POK, "radiant"),
    ("sm6-74", "Diancie ◇", None, _POK, "prisme_etoile"),
    ("ex10-113", "Entei ☆", None, _POK, "etoile"),
    # --- Pokémon ordinaire ---
    ("base1-58", "Pikachu", None, _POK, "ordinaire"),
    ("pl1-7", "Dialga G", "SP", _POK, "ordinaire"),  # Pokémon SP : pas un Rule Box
]


@pytest.mark.parametrize(("tcgdex_id", "name", "rule_marker", "supertype", "expected"), _CASES)
def test_classifies_real_catalog_cards(
    tcgdex_id: str, name: str, rule_marker: str | None, supertype: str, expected: str
) -> None:
    assert (
        normalized_prize_marker(name=name, supertype=supertype, rule_marker=rule_marker)
        == expected
    ), tcgdex_id


def test_non_pokemon_returns_none() -> None:
    # Poké Ball (Dresseur, tcgdex_id tk-xy-sy-26) : la règle des Prix ne concerne pas cette carte.
    assert normalized_prize_marker(name="Poké Ball", supertype="Dresseur", rule_marker=None) is None
    assert (
        normalized_prize_marker(name="Énergie Feu", supertype="Énergie", rule_marker=None) is None
    )


def test_english_supertype_is_also_pokemon() -> None:
    # Repli de langue de l'import : « Pokemon » (anglais) est reconnu comme « Pokémon ».
    marker = normalized_prize_marker(name="Pikachu", supertype="Pokemon", rule_marker=None)
    assert marker == "ordinaire"


def test_unknown_rule_box_refuses_to_guess() -> None:
    # Un suffixe à Rule Box jamais vu ne se replie PAS sur « ordinaire » (R-13.4/R-15.22).
    assert (
        normalized_prize_marker(name="Truc ZX", supertype=_POK, rule_marker="ZX-NOUVEAU")
        == MARQUEUR_INCONNU
    )


def test_complex_is_not_an_ex_card() -> None:
    # « Complex » finit par « ex » sans séparateur : ce n'est pas une carte ex (garde de l'ancien
    # test, conservée).
    assert normalized_prize_marker(name="Complex", supertype=_POK, rule_marker=None) == "ordinaire"


def test_tag_team_without_joiner_stays_gx() -> None:
    # Un Pokémon-GX ordinaire finit par « GX » sans jointeur « et »/« & » → gx, pas tag_team.
    assert normalized_prize_marker(name="Dracaufeu GX", supertype=_POK, rule_marker=None) == "gx"


# --- Stade d'évolution ordinaire recopié par erreur dans `rule_marker` -------------------------
# Défaut PROD du 01/10/2026 (release 20261001-234045) : 564 cartes avec `rule_marker`=`Stage1`/
# `Stage2` (sans espace), classées `inconnu`. Un stade ordinaire n'est JAMAIS un marqueur de règle :
# il donne 1 récompense (R-13.3). Comparaison sans casse ET sans espaces/tirets. Ces cas échouent
# avec l'ancien code (qui ne reconnaissait que `stage 1`/`stage 2`).
_STAGE_CASES = [
    ("Stage1", "ordinaire"),  # le cas exact de la PROD (sans espace)
    ("Stage2", "ordinaire"),
    ("Stage 1", "ordinaire"),  # libellé anglais avec espace
    ("stage-2", "ordinaire"),  # tiret + minuscules
    ("Basic", "ordinaire"),
    ("Niveau 1", "ordinaire"),  # libellé français
    ("Niveau 2", "ordinaire"),
    ("Base", "ordinaire"),
]


@pytest.mark.parametrize(("rule_marker", "expected"), _STAGE_CASES)
def test_ordinary_stage_in_rule_marker_is_ordinary(rule_marker: str, expected: str) -> None:
    # Un stade ordinaire mal rangé dans `rule_marker` → « ordinaire », jamais « inconnu ».
    assert (
        normalized_prize_marker(name="Pikachu", supertype=_POK, rule_marker=rule_marker) == expected
    )


def test_is_ordinary_stage_normalizes_case_and_separators() -> None:
    for value in ("Stage1", "stage 1", "Stage-1", "STAGE 2", "Niveau 1", "Basic", "Base"):
        assert is_ordinary_stage(value), value
    for value in (None, "", "VMAX", "ex", "GX", "Niveau Sup", "ZX-NOUVEAU"):
        assert not is_ordinary_stage(value), value


def test_migration_corrects_stage_row_and_leaves_vmax_intact() -> None:
    # La décision pure que la migration `fix-marqueur-stades` applique ligne par ligne.
    # Une ligne `Stage1` : `rule_marker` vidé, `prize_marker` recalculé à « ordinaire ».
    assert corrected_stage_row(name="Pikachu", supertype=_POK, rule_marker="Stage1") == (
        None,
        "ordinaire",
    )
    assert corrected_stage_row(name="Pikachu", supertype=_POK, rule_marker="Stage2") == (
        None,
        "ordinaire",
    )
    # Une vraie Rule Box (VMAX) n'est PAS concernée → laissée intacte (None = aucune correction).
    assert corrected_stage_row(name="Astronelle VMAX", supertype=_POK, rule_marker="VMAX") is None
    # Un `rule_marker` à Rule Box inconnu n'est pas davantage touché (il reste `inconnu`, pas vidé).
    assert corrected_stage_row(name="Truc ZX", supertype=_POK, rule_marker="ZX-NOUVEAU") is None


def _engine_marqueur_recompenses() -> dict[str, int]:
    """Lit `MARQUEUR_RECOMPENSES` dans le **source** du moteur (`pbm_game.combat.fin`) sans
    importer le paquet (il n'est pas en dépendance d'`apps/api`) : parse AST + littéral."""
    repo_root = Path(__file__).resolve().parents[3]
    engine_src = repo_root / "apps" / "game" / "src" / "pbm_game" / "combat" / "fin.py"
    tree = ast.parse(engine_src.read_text(encoding="utf-8"))
    for node in tree.body:
        targets = (
            node.targets if isinstance(node, ast.Assign)
            else [node.target] if isinstance(node, ast.AnnAssign)
            else []
        )
        for target in targets:
            if isinstance(target, ast.Name) and target.id == "MARQUEUR_RECOMPENSES":
                return ast.literal_eval(node.value)
    raise AssertionError("MARQUEUR_RECOMPENSES introuvable dans le source du moteur")


def test_prizes_table_matches_engine() -> None:
    # L'unique table de vérité est celle du moteur ; la copie d'apps/api doit lui rester ÉGALE.
    assert PRIZES_BY_MARKER == _engine_marqueur_recompenses()


def test_labels_cover_every_marker() -> None:
    assert set(LABELS_BY_MARKER) == set(PRIZES_BY_MARKER)
