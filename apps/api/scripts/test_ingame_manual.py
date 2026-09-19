"""Essai manuel de la synthèse « étude en jeu » avec une vraie clé — jamais exécuté par la
suite pytest (`tests/test_in_game_study.py` utilise un fournisseur double, aucune clé IA réelle
disponible sur chimera).

Ce script fait le trajet complet en conditions réelles : rapprochement Limitless TCG (réseau
réel), règle des Prix (déterministe), construction du prompt, puis appel du fournisseur.

Usage :
    uv run python scripts/test_ingame_manual.py anthropic sk-ant-... \\
        "Charizard ex" ASC 22 Pokemon "Ascended Heroes" true false
"""

import asyncio
import sys

from pbm_api.ai.errors import AIProviderError
from pbm_api.ai.factory import create_provider
from pbm_api.ingame.generation import InGameStudyExtraction, build_prompt, render_study_text
from pbm_api.ingame.rules import legalities_of, prize_rule_of
from pbm_api.ingame.tournaments import LimitlessTcgClient, find_card_page, parse_decklists
from pbm_api.models import AiProvider


def _parse_bool(value: str) -> bool | None:
    if value.lower() == "none":
        return None
    return value.lower() in ("1", "true", "yes", "oui")


async def main() -> None:
    if len(sys.argv) != 9:
        print(__doc__)
        raise SystemExit(1)

    provider_name = AiProvider(sys.argv[1])
    api_key = sys.argv[2]
    card_name, set_code, number, supertype, set_name = sys.argv[3:8]
    legal_standard = _parse_bool(sys.argv[8])

    prize_rule = prize_rule_of(card_name=card_name, supertype=supertype)
    legalities = legalities_of(legal_standard=legal_standard, legal_expanded=None)
    print(f"Règle des Prix : {prize_rule.label}")

    client = LimitlessTcgClient()
    try:
        sets = await client.list_sets()
        set_info = next((s for s in sets if s.code == set_code), None)
        decks = []
        if set_info is not None:
            found = await find_card_page(
                client,
                sets=sets,
                set_release_date=set_info.release_date,
                set_name=set_info.name,
                card_number=number,
                expected_en_name=card_name,
            )
            if found is not None:
                _url, html_page = found
                decks = parse_decklists(html_page)
    finally:
        await client.aclose()

    print(f"Decklists relevées : {len(decks)}")
    for deck in decks[:5]:
        print(f"  - {deck.deck_name} — {deck.tournament_name} ({deck.placement})")

    prompt = build_prompt(
        card_name=card_name,
        set_name=set_name,
        legal_standard=legalities.standard,
        legal_expanded=legalities.expanded,
        prize_label=prize_rule.label,
        attacks=None,
        abilities=None,
        tournament_decks=[d.model_dump() for d in decks] if decks else None,
    )

    provider = create_provider(provider_name, api_key)
    try:
        extraction, usage = await provider.extract([], InGameStudyExtraction, prompt)
    except AIProviderError as error:
        print(f"{provider_name.value}: échec — {error.user_message}")
        raise SystemExit(1) from error
    finally:
        await provider.aclose()

    print(f"usage={usage.model_dump()}")
    print(render_study_text(extraction))


if __name__ == "__main__":
    asyncio.run(main())
