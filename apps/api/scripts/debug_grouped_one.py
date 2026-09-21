"""Diagnostic ponctuel : soumet UNE requête groupée (2 cartes) en synchrone et imprime la
réponse brute + l'erreur de validation exacte, pour comprendre pourquoi le paquet est rejeté.
Réutilise le cache de contexte déjà collecté. Clé lue depuis le fichier chmod 600, jamais loggée.
"""

import asyncio
import json
from collections import defaultdict
from pathlib import Path

import httpx
from pydantic import ValidationError

from pbm_api.ingame.rules import prize_rule_of
from pbm_api.insights.context import ContextPage
from pbm_api.insights_batch.grouped_generation import (
    GROUPED_JSON_SCHEMA,
    PacketCard,
    build_grouped_prompt,
    parse_grouped_result,
)

WORK = Path.home() / "dev/pbm-insights-work"


def _pages(raw):
    return [ContextPage(**p) for p in raw]


async def main() -> None:
    data = json.loads((WORK / "sample_cards.json").read_text())
    cache = json.loads((WORK / "context_cache.json").read_text())
    sets_by_id = {s["id"]: s for s in data["sets"]}
    by_set = defaultdict(list)
    for c in data["cards"]:
        by_set[c["set_id"]].append(c)

    set_id = next(sid for sid in by_set if sid in cache["sets"])
    set_pages = _pages(cache["sets"][set_id])
    cards = [c for c in by_set[set_id] if c["id"] in cache["cards"]][:2]
    packet = []
    for i, card in enumerate(cards, start=1):
        prize = prize_rule_of(card_name=card["name"], supertype=card.get("supertype"))
        packet.append(
            PacketCard(
                card_ref=f"c{i}",
                card_name=card["name"],
                card_pages=_pages(cache["cards"][card["id"]]),
                legal_standard=card.get("legal_standard"),
                legal_expanded=card.get("legal_expanded"),
                prize_label=prize.label,
                attacks=card.get("attacks"),
                abilities=card.get("abilities"),
            )
        )
    prompt = build_grouped_prompt(
        set_name=sets_by_id[set_id]["name"], set_pages=set_pages, cards=packet
    )
    key = (Path.home() / ".pokeboy-secrets/aymeric-anthropic-key").read_text().strip()

    body = {
        "model": "claude-haiku-4-5",
        "max_tokens": 3300,
        "messages": [{"role": "user", "content": prompt}],
        "output_config": {"format": {"type": "json_schema", "schema": GROUPED_JSON_SCHEMA}},
    }
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            json=body,
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )
    print("HTTP", resp.status_code)
    payload = resp.json()
    print("stop_reason:", payload.get("stop_reason"))
    print("usage:", payload.get("usage"))
    text = next(
        (b["text"] for b in payload.get("content", []) if b.get("type") == "text"), None
    )
    print("=== RAW TEXT (first 1600 chars) ===")
    print((text or "")[:1600])
    print("=== RAW TEXT (last 400 chars) ===")
    print((text or "")[-400:])
    if text:
        try:
            parse_grouped_result(text, ["c1", "c2"])
            print("=== PARSE OK ===")
        except ValidationError as exc:
            print("=== ValidationError ===")
            print(exc)
        except Exception as exc:  # noqa: BLE001
            print("=== other error ===", type(exc).__name__, exc)


if __name__ == "__main__":
    asyncio.run(main())
