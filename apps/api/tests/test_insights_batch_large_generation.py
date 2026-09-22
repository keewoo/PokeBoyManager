"""Génération à contenu réduit (lot `pbm-insights-ciblage-large`) —
`pbm_api.insights_batch.large_generation`.

`test_parse_large_result_rejects_*` est la preuve ciblée de l'anti-mélange exigé par la mission
(« un paquet incohérent est rejeté en entier ») : sans l'égalité exacte des `card_ref`, un paquet
auquel il manque une carte — ou qui en ajoute une inconnue — passerait, attribuant potentiellement
les anecdotes d'une carte à une autre. `test_build_large_prompt_*` prouve que les règles de jeu
sont bien construites À PARTIR DES DONNÉES CATALOGUE (attaques, coûts, légalités, règle des Prix)
et non inventées — la contrainte du lot (« le modèle les met en forme, il ne les invente pas »).
"""

import pytest
from pydantic import ValidationError

from pbm_api.insights.context import ContextPage
from pbm_api.insights_batch.large_generation import (
    LARGE_JSON_SCHEMA,
    MAX_ANECDOTES,
    LargeAnecdote,
    LargeCardInsight,
    LargeInsightExtraction,
    PacketCard,
    PacketMixingError,
    allowed_urls_for,
    build_large_prompt,
    parse_large_result,
)


def _card(ref: str, url: str) -> LargeCardInsight:
    return LargeCardInsight(
        card_ref=ref,
        anecdotes=[LargeAnecdote(text="Illustrée par X.", source_url=url)],
        game_rules="Attaque à 2 énergies, légale en Standard.",
    )


def _payload(refs_with_urls: list[tuple[str, str]]) -> str:
    return LargeInsightExtraction(
        cards=[_card(ref, url) for ref, url in refs_with_urls]
    ).model_dump_json()


def test_max_anecdotes_is_two() -> None:
    # Décision de JF : deux anecdotes, pas cinq.
    assert MAX_ANECDOTES == 2


def test_large_schema_strips_unsupported_constraints_and_keeps_fields() -> None:
    # Anthropic refuse `output_config.format` avec une borne de longueur/d'items (voir
    # `ai.json_schema`) : le schéma envoyé ne DOIT porter aucune borne, seulement la structure.
    card_schema = LARGE_JSON_SCHEMA["properties"]["cards"]
    assert "maxItems" not in card_schema
    item = card_schema["items"]
    assert set(item["properties"]) == {"card_ref", "anecdotes", "game_rules"}
    assert "maxItems" not in item["properties"]["anecdotes"]
    assert item["additionalProperties"] is False


def test_parse_large_result_happy_path_indexes_by_ref() -> None:
    text = _payload([("c1", "https://w/1"), ("c2", "https://w/2")])
    parsed = parse_large_result(text, requested_refs=["c1", "c2"])
    assert set(parsed) == {"c1", "c2"}
    assert parsed["c1"].anecdotes[0].source_url == "https://w/1"
    assert parsed["c2"].game_rules


def test_parse_large_result_rejects_missing_ref() -> None:
    text = _payload([("c1", "https://w/1")])
    with pytest.raises(PacketMixingError):
        parse_large_result(text, requested_refs=["c1", "c2"])


def test_parse_large_result_rejects_unknown_ref() -> None:
    text = _payload([("c1", "https://w/1"), ("c9", "https://w/9")])
    with pytest.raises(PacketMixingError):
        parse_large_result(text, requested_refs=["c1", "c2"])


def test_parse_large_result_rejects_duplicate_ref() -> None:
    text = _payload([("c1", "https://w/1"), ("c1", "https://w/1b")])
    with pytest.raises(PacketMixingError):
        parse_large_result(text, requested_refs=["c1", "c2"])


def test_parse_large_result_rejects_invalid_or_truncated_json() -> None:
    truncated = _payload([("c1", "https://w/1")])[:-15]
    with pytest.raises((ValidationError, ValueError)):
        parse_large_result(truncated, requested_refs=["c1"])


def test_parse_large_result_remaps_card_name_to_ref() -> None:
    # Défaut réel observé (diagnostic du lot) : sur les paquets courts, le modèle renvoie le NOM de
    # la carte en `card_ref` (« Dracaufeu GX ») au lieu du code court demandé. Avec la table
    # ref→nom, le libellé est remappé vers son `cN` — le paquet n'est pas perdu, l'anecdote reste
    # rattachée à la bonne carte.
    text = _payload([("Dracaufeu GX", "https://w/1"), ("c2", "https://w/2")])
    parsed = parse_large_result(
        text,
        requested_refs=["c1", "c2"],
        card_names_by_ref={"c1": "Dracaufeu GX", "c2": "Bulbizarre"},
    )
    assert set(parsed) == {"c1", "c2"}
    assert parsed["c1"].anecdotes[0].source_url == "https://w/1"
    assert parsed["c2"].anecdotes[0].source_url == "https://w/2"


def test_parse_large_result_name_remap_ambiguous_is_rejected() -> None:
    # Deux cartes de même nom dans le paquet : le nom est ambigu, on NE remappe pas → le paquet
    # est rejeté plutôt que de risquer d'attribuer une anecdote à la mauvaise carte.
    text = _payload([("Énergie Eau", "https://w/1"), ("c2", "https://w/2")])
    with pytest.raises(PacketMixingError):
        parse_large_result(
            text,
            requested_refs=["c1", "c2"],
            card_names_by_ref={"c1": "Énergie Eau", "c2": "Énergie Eau"},
        )


def test_parse_large_result_name_remap_still_rejects_missing_card() -> None:
    # La tolérance de libellé ne doit PAS laisser passer un paquet incomplet : une seule carte
    # rendue (fût-elle nommée) pour deux demandées reste une discordance.
    text = _payload([("Dracaufeu GX", "https://w/1")])
    with pytest.raises(PacketMixingError):
        parse_large_result(
            text,
            requested_refs=["c1", "c2"],
            card_names_by_ref={"c1": "Dracaufeu GX", "c2": "Bulbizarre"},
        )


def _packet_card(ref: str, name: str, url: str) -> PacketCard:
    return PacketCard(
        card_ref=ref,
        card_name=name,
        card_pages=[ContextPage(title=name, source_url=url, text="…")],
        supertype="Pokemon",
        legal_standard=True,
        legal_expanded=False,
        prize_label="2 Prix (carte ex)",
        rule_marker="ex",
        hp=220,
        retreat_cost=2,
        attacks=[{"name": "Charge", "cost": ["Feu", "Feu"], "damage": 120, "effect": "Défausse."}],
        abilities=[{"type": "Talent", "name": "Brasier", "effect": "…"}],
        weaknesses=[{"type": "Eau", "value": "×2"}],
        resistances=None,
    )


def test_build_large_prompt_shares_set_context_once_and_lists_each_card() -> None:
    set_pages = [ContextPage(title="Extension", source_url="https://w/set", text="Contexte set.")]
    cards = [
        _packet_card("c1", "Dracaufeu ex", "https://w/dracaufeu"),
        _packet_card("c2", "Bulbizarre", "https://w/bulbizarre"),
    ]
    prompt = build_large_prompt(set_name="Set de Base", set_pages=set_pages, cards=cards)
    # contexte d'extension partagé (une seule fois)
    assert prompt.count("https://w/set") == 1
    # chaque carte a son en-tête recopiable et ses sources propres
    assert 'CARTE c1 : "Dracaufeu ex"' in prompt
    assert 'CARTE c2 : "Bulbizarre"' in prompt
    assert "https://w/dracaufeu" in prompt and "https://w/bulbizarre" in prompt


def test_build_large_prompt_grounds_game_rules_in_catalog_data() -> None:
    cards = [_packet_card("c1", "Dracaufeu ex", "https://w/dracaufeu")]
    prompt = build_large_prompt(set_name="Set de Base", set_pages=[], cards=cards)
    # les données déterministes du catalogue sont injectées pour être MISES EN FORME
    assert "2 Prix (carte ex)" in prompt
    assert "Charge" in prompt  # l'attaque du catalogue
    assert "Standard : légale" in prompt and "Étendu : non légale" in prompt
    # et l'instruction anti-invention est présente
    assert "N'invente aucune attaque" in prompt


def test_build_large_prompt_says_two_anecdotes_french_only() -> None:
    prompt = build_large_prompt(
        set_name="S", set_pages=[], cards=[_packet_card("c1", "X", "https://w/x")]
    )
    assert "DEUX" in prompt  # au plus deux anecdotes
    assert "anglais" not in prompt.lower()  # français seulement, pas d'anglais


def test_allowed_urls_scopes_to_set_plus_that_cards_sources() -> None:
    set_pages = [ContextPage(title="Extension", source_url="https://w/set", text="x")]
    c1 = _packet_card("c1", "Dracaufeu ex", "https://w/dracaufeu")
    urls = allowed_urls_for(set_pages, c1)
    assert urls == {"https://w/set", "https://w/dracaufeu"}


def _load_generation_script():
    # build_packets vit dans le SCRIPT (apps/api/scripts/generate_large_insights.py), pas dans le
    # module : on le charge par chemin. sys.modules doit être renseigné avant exec_module, sinon la
    # résolution des `@dataclass` du script échoue (cls.__module__ introuvable).
    import importlib.util
    import sys
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts" / "generate_large_insights.py"
    spec = importlib.util.spec_from_file_location("generate_large_insights", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["generate_large_insights"] = module
    spec.loader.exec_module(module)
    return module


def test_build_packets_custom_id_is_api_valid_even_with_dotted_set_id() -> None:
    # Défaut réel du lot : `custom_id = f"{tag}-{set_id}-{chunk}"` produisait `g25-swsh3.5-0` — le
    # point est INTERDIT par l'API Anthropic (`^[a-zA-Z0-9_-]{1,64}$`), les paquets de ces
    # extensions (`me02.5`, `swsh10.5`, `swsh3.5`…) échouaient en silence. Le custom_id est
    # désormais un simple index ; le mappage résultat→paquet passe par le dict, pas par ce libellé.
    import re

    module = _load_generation_script()
    cards = [
        {
            "tcgdex_id": "swsh3.5-13", "set_tcgdex_id": "swsh3.5", "name": "Pika",
            "number": "13", "supertype": "Pokémon", "set_name": "Champions Path",
            "attacks": [], "abilities": [], "legal_standard": False, "legal_expanded": True,
        }
    ]
    packets = module.build_packets(
        cards, {"swsh3.5": []}, {}, model="claude-haiku-4-5-20251001",
        packet_size=25, tag="g25",
    )
    assert packets, "au moins un paquet attendu"
    for p in packets:
        assert re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", p.custom_id), p.custom_id


# --------------------------------------------------------------------------- RÈGLES SEULES
#
# Lot `pbm-fiches-reste` : mêmes preuves ciblées que ci-dessus, transposées à la variante sans
# anecdotes — le schéma ne porte QUE `game_rules` (aucune anecdote possible), le prompt ne réclame
# aucune source wiki (il n'y en a pas), et l'anti-mélange par `card_ref` reste exact.

from pbm_api.insights_batch.large_generation import (  # noqa: E402
    RULES_ONLY_JSON_SCHEMA,
    RulesOnlyCardInsight,
    RulesOnlyExtraction,
    build_rules_only_prompt,
    parse_rules_only_result,
)


def _rules_payload(refs: list[str]) -> str:
    return RulesOnlyExtraction(
        cards=[
            RulesOnlyCardInsight(card_ref=r, game_rules="Attaque à 2 énergies.")
            for r in refs
        ]
    ).model_dump_json()


def _packet_card_bare(ref: str, name: str) -> PacketCard:
    return PacketCard(
        card_ref=ref, card_name=name, card_pages=[], supertype="Pokémon",
        legal_standard=True, legal_expanded=True, prize_label="1 Prix", rule_marker=None,
        hp=70, retreat_cost=1, attacks=[{"name": "Éclair", "cost": ["Lightning"], "damage": "20"}],
        abilities=None, weaknesses=None, resistances=None,
    )


def test_rules_only_schema_has_no_anecdotes_field() -> None:
    # Le contenu attendu par carte est UNIQUEMENT les règles de jeu (décision de JF).
    item = RULES_ONLY_JSON_SCHEMA["properties"]["cards"]["items"]
    assert set(item["properties"]) == {"card_ref", "game_rules"}
    assert item["additionalProperties"] is False


def test_rules_only_prompt_carries_game_data_and_no_wiki() -> None:
    prompt = build_rules_only_prompt(
        set_name="Écarlate et Violet",
        cards=[_packet_card_bare("c1", "Pikachu"), _packet_card_bare("c2", "Salamèche")],
    )
    assert "CARTE c1" in prompt and "CARTE c2" in prompt
    assert "Éclair" in prompt  # données de jeu du catalogue mises à disposition
    assert "n'invente" in prompt.lower() or "invente" in prompt.lower()
    # Aucune section anecdote / source wiki dans le prompt règles-seules.
    assert "anecdote" not in prompt.lower()
    assert "Source [" not in prompt


def test_parse_rules_only_happy_path_indexes_by_ref() -> None:
    parsed = parse_rules_only_result(_rules_payload(["c1", "c2"]), ["c1", "c2"])
    assert set(parsed) == {"c1", "c2"}
    assert parsed["c1"].game_rules


def test_parse_rules_only_rejects_missing_card() -> None:
    with pytest.raises(PacketMixingError):
        parse_rules_only_result(_rules_payload(["c1"]), ["c1", "c2"])


def test_parse_rules_only_rejects_unknown_card() -> None:
    with pytest.raises(PacketMixingError):
        parse_rules_only_result(_rules_payload(["c1", "c2", "c3"]), ["c1", "c2"])


def test_parse_rules_only_remaps_name_to_ref_when_unique() -> None:
    # Le modèle rend parfois le NOM au lieu du code court : remappé si le nom est unique au paquet.
    payload = _rules_payload(["Dracaufeu GX", "c2"])
    parsed = parse_rules_only_result(
        payload, ["c1", "c2"], card_names_by_ref={"c1": "Dracaufeu GX", "c2": "Bulbizarre"}
    )
    assert set(parsed) == {"c1", "c2"}


def test_parse_rules_only_rejects_truncated_json() -> None:
    with pytest.raises(ValidationError):
        parse_rules_only_result('{"cards": [{"card_ref": "c1", "game_rules', ["c1"])
