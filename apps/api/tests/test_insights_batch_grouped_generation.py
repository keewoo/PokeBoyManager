"""Génération groupée (lot `pbm-insights-toutes-cartes`) —
`pbm_api.insights_batch.grouped_generation`.

`test_parse_grouped_result_rejects_*` sont la preuve ciblée du contrôle anti-mélange exigé par
la mission (« vérifie que chaque objet rendu correspond bien à l'identifiant demandé, et rejette
le paquet entier si un identifiant manque ou est inconnu ; un test doit couvrir ce cas ») : sans
la vérification d'égalité exacte des `card_ref`, un paquet auquel il manque une carte — ou qui en
ajoute une inconnue — passerait, attribuant potentiellement les anecdotes d'une carte à une autre.
"""

import pytest
from pydantic import ValidationError

from pbm_api.insights.context import ContextPage
from pbm_api.insights_batch.grouped_generation import (
    GROUPED_JSON_SCHEMA,
    GroupedAnecdote,
    GroupedCardInsight,
    GroupedGameStudy,
    GroupedInsightExtraction,
    PacketCard,
    PacketMixingError,
    allowed_urls_for,
    build_grouped_prompt,
    parse_grouped_result,
)


def _study() -> GroupedGameStudy:
    return GroupedGameStudy(
        role="Attaquant principal",
        strengths="Gros dégâts",
        weaknesses="Fragile",
        related_cards=[],
        playability_note="Correcte en Standard.",
    )


def _card(ref: str, url: str) -> GroupedCardInsight:
    return GroupedCardInsight(
        card_ref=ref,
        anecdotes_fr=[GroupedAnecdote(text="Illustrée par X.", source_url=url)],
        anecdotes_en=[GroupedAnecdote(text="Illustrated by X.", source_url=url)],
        game_study=_study(),
    )


def _payload(refs_with_urls: list[tuple[str, str]]) -> str:
    return GroupedInsightExtraction(
        cards=[_card(ref, url) for ref, url in refs_with_urls]
    ).model_dump_json()


def test_grouped_schema_strips_unsupported_constraints_and_keeps_card_ref() -> None:
    # Même contrainte réelle que `combined_generation` : Anthropic refuse `output_config.format`
    # avec un 400 dès qu'une borne de longueur/d'items y figure (voir `ai.json_schema`).
    card_schema = GROUPED_JSON_SCHEMA["properties"]["cards"]
    assert "maxItems" not in card_schema
    item = card_schema["items"]
    assert set(item["properties"]) == {"card_ref", "anecdotes_fr", "anecdotes_en", "game_study"}
    assert "maxItems" not in item["properties"]["anecdotes_fr"]
    assert item["additionalProperties"] is False


def test_parse_grouped_result_happy_path_indexes_by_ref() -> None:
    text = _payload([("c1", "https://w/1"), ("c2", "https://w/2")])
    parsed = parse_grouped_result(text, requested_refs=["c1", "c2"])
    assert set(parsed) == {"c1", "c2"}
    assert parsed["c1"].anecdotes_fr[0].source_url == "https://w/1"


def test_parse_grouped_result_rejects_missing_ref() -> None:
    # Le modèle a « oublié » c2 : sans rejet, c2 resterait non traitée en silence.
    text = _payload([("c1", "https://w/1")])
    with pytest.raises(PacketMixingError):
        parse_grouped_result(text, requested_refs=["c1", "c2"])


def test_parse_grouped_result_rejects_unknown_ref() -> None:
    # Le modèle a inventé c9 : identifiant inconnu → paquet entier rejeté.
    text = _payload([("c1", "https://w/1"), ("c9", "https://w/9")])
    with pytest.raises(PacketMixingError):
        parse_grouped_result(text, requested_refs=["c1", "c2"])


def test_parse_grouped_result_rejects_duplicate_ref() -> None:
    # Deux objets pour c1 (mélange probable) → rejet plutôt que d'en garder un au hasard.
    text = _payload([("c1", "https://w/1"), ("c1", "https://w/1b")])
    with pytest.raises(PacketMixingError):
        parse_grouped_result(text, requested_refs=["c1", "c2"])


def test_parse_grouped_result_rejects_invalid_or_truncated_json() -> None:
    # Réponse tronquée (fréquente si max_tokens trop bas pour un gros paquet) : le JSON ne valide
    # pas le schéma → ValidationError, l'appelant rejette le paquet comme pour un mélange.
    truncated = _payload([("c1", "https://w/1")])[:-15]
    with pytest.raises((ValidationError, ValueError)):
        parse_grouped_result(truncated, requested_refs=["c1"])


def _packet_card(ref: str, name: str, url: str) -> PacketCard:
    return PacketCard(
        card_ref=ref,
        card_name=name,
        card_pages=[ContextPage(title=name, source_url=url, text="…")],
        legal_standard=True,
        legal_expanded=True,
        prize_label="1 Prix (carte standard)",
        attacks=[{"name": "Charge"}],
        abilities=None,
    )


def test_build_grouped_prompt_shares_set_context_once_and_lists_each_card() -> None:
    set_pages = [ContextPage(title="Extension", source_url="https://w/set", text="Contexte set.")]
    cards = [
        _packet_card("c1", "Dracaufeu", "https://w/dracaufeu"),
        _packet_card("c2", "Bulbizarre", "https://w/bulbizarre"),
    ]
    prompt = build_grouped_prompt(set_name="Set de Base", set_pages=set_pages, cards=cards)
    # Le contexte d'extension n'apparaît qu'une fois (partagé) …
    assert prompt.count("https://w/set") == 1
    # … et chaque carte a son en-tête `card_ref` recopiable et ses sources propres.
    assert 'CARTE c1 : "Dracaufeu"' in prompt
    assert 'CARTE c2 : "Bulbizarre"' in prompt
    assert "https://w/dracaufeu" in prompt and "https://w/bulbizarre" in prompt


def test_allowed_urls_scopes_to_set_plus_that_cards_sources() -> None:
    set_pages = [ContextPage(title="Extension", source_url="https://w/set", text="x")]
    c1 = _packet_card("c1", "Dracaufeu", "https://w/dracaufeu")
    urls = allowed_urls_for(set_pages, c1)
    assert urls == {"https://w/set", "https://w/dracaufeu"}
