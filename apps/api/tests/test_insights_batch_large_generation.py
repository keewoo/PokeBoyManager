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
