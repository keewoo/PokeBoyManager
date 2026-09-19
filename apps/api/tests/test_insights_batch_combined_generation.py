"""Schéma et prompt combiné (mission `v4-insights-batch` point 1) —
`pbm_api.insights_batch.combined_generation`.

Avant ce lot, ce module n'existait pas : la suite échoue à la collection
(`ModuleNotFoundError`) et passe une fois le fichier ajouté.
`test_build_combined_prompt_lists_only_context_urls_for_both_languages` est la preuve ciblée du
risque hallucination (mission point 4) : le prompt doit répéter explicitement l'interdiction de
citer une URL absente du contexte fourni, pour les anecdotes FR et EN à la fois.
"""

from pbm_api.insights.context import ContextPage
from pbm_api.insights_batch.combined_generation import (
    COMBINED_JSON_SCHEMA,
    CombinedCardInsightExtraction,
    build_combined_prompt,
)


def test_combined_schema_exposes_anecdotes_fr_en_and_game_study() -> None:
    properties = COMBINED_JSON_SCHEMA["properties"]
    assert set(properties) == {"anecdotes_fr", "anecdotes_en", "game_study"}
    assert properties["anecdotes_fr"]["maxItems"] == 5
    assert properties["anecdotes_en"]["maxItems"] == 5
    assert set(properties["game_study"]["properties"]) == {
        "role",
        "strengths",
        "weaknesses",
        "related_cards",
        "playability_note",
    }


def test_combined_extraction_round_trips_from_json() -> None:
    payload = {
        "anecdotes_fr": [{"text": "Fait FR.", "source_url": "https://example.test/fr"}],
        "anecdotes_en": [{"text": "EN fact.", "source_url": "https://example.test/en"}],
        "game_study": {
            "role": "Attaquant",
            "strengths": "Rapide",
            "weaknesses": "Fragile",
            "related_cards": [],
            "playability_note": "Correct",
        },
    }
    extraction = CombinedCardInsightExtraction.model_validate(payload)
    assert extraction.anecdotes_fr[0].text == "Fait FR."
    assert extraction.game_study.role == "Attaquant"


def test_build_combined_prompt_lists_only_context_urls_for_both_languages() -> None:
    pages = [ContextPage(title="Dracaufeu", source_url="https://pokepedia.test/x", text="Texte.")]
    prompt = build_combined_prompt(
        card_name="Dracaufeu",
        set_name="Base Set",
        context_pages=pages,
        legal_standard=True,
        legal_expanded=True,
        prize_label="1 Prix (carte standard)",
        attacks=None,
        abilities=None,
        tournament_decks=None,
    )
    assert "anecdotes_fr" in prompt
    assert "anecdotes_en" in prompt
    assert "https://pokepedia.test/x" in prompt
    assert "N'invente aucun fait" in prompt
    assert "Aucune présence en tournoi" in prompt


def test_build_combined_prompt_without_context_asks_for_empty_anecdotes() -> None:
    prompt = build_combined_prompt(
        card_name="Chenipan",
        set_name="Extension obscure",
        context_pages=[],
        legal_standard=None,
        legal_expanded=None,
        prize_label="1 Prix (carte standard)",
        attacks=None,
        abilities=None,
        tournament_decks=None,
    )
    assert "listes d'anecdotes vides" in prompt


def test_build_combined_prompt_includes_tournament_decks_when_present() -> None:
    prompt = build_combined_prompt(
        card_name="Dracaufeu",
        set_name="Base Set",
        context_pages=[],
        legal_standard=True,
        legal_expanded=True,
        prize_label="1 Prix (carte standard)",
        attacks=None,
        abilities=None,
        tournament_decks=[
            {"deck_name": "Charizard ex", "tournament_name": "Regionals", "placement": "1er"}
        ],
    )
    assert "Regionals" in prompt
    assert "n'invente aucun autre tournoi" in prompt
