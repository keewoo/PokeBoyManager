"""Mesure de performance de `GET /me/decks/cards` (mission `v7-decks-recherche`, point 2 :
150 ms au 95e centile sur 22 000 cartes et 5 000 exemplaires).

Sème 22 000 cartes (200 extensions × 110 cartes) avec noms localisés FR, prix pour ~80 % d'entre
elles, et 5 000 exemplaires pour un utilisateur de mesure (dont des doublons), puis RAFRAÎCHIT la
vue matérialisée `card_value_rank` — sans quoi le tri par valeur mesurerait un chemin où toutes
les valeurs sont NULL. Mesure ensuite le temps de réponse HTTP réel (`ASGITransport`, même
technique que `tests/conftest.py`) sur des scénarios représentatifs : page par défaut, recherche
par nom, par numéro, filtres cumulés, tri par valeur, « mes cartes », annotation avec le deck
courant, et une pagination profonde (10 pages suivies au curseur — c'est là qu'un OFFSET
s'effondrerait, pas le keyset).

L'objectif est jugé sur le 95e centile de 25 requêtes par scénario ; la médiane et le maximum
sont aussi imprimés (chimera est une machine partagée, `~/.claude/CLAUDE.md` : un pic isolé n'est
pas le temps de réponse du chemin de code). La transaction est annulée en fin de script : aucune
donnée n'est laissée dans la base pointée par `DATABASE_URL`.

Usage :
    uv run python scripts/measure_deck_card_search_performance.py
"""

import asyncio
import json
import math
import statistics
import time
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from pbm_api.config import settings
from pbm_api.db import get_session
from pbm_api.main import app
from pbm_api.models import Card, CardName, CardPriceDaily, Deck, DeckCard, Set, User
from pbm_api.models.collection import CollectionItem
from pbm_api.models.users import Session as UserSession
from pbm_api.security.tokens import generate_opaque_token, hash_token

SET_COUNT = 200
CARDS_PER_SET = 110
CARD_COUNT = SET_COUNT * CARDS_PER_SET  # 22 000
ITEM_COUNT = 5000
TARGET_MS = 150
REPEATS = 25
RARITIES = ["Commune", "Peu commune", "Rare", "Rare Holo", "Ultra Rare"]
TYPES = ["Pokémon", "Pokémon", "Pokémon", "Dresseur", "Énergie"]  # Pokémon majoritaire


async def _seed(session: AsyncSession) -> tuple[User, str, uuid.UUID]:
    user = User(
        email=f"perf-dcs-{uuid.uuid4()}@example.com",
        password_hash="x",
        last_name="Perf",
        birth_date=date(2000, 1, 1),
        terms_version="test",
        terms_accepted_at=datetime(2000, 1, 1),
    )
    session.add(user)
    await session.flush()

    raw_token = generate_opaque_token()
    session.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_token(raw_token),
            expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1),
        )
    )
    await session.flush()

    today = date.today()
    set_ids = [uuid.uuid4() for _ in range(SET_COUNT)]
    await session.execute(
        insert(Set),
        [
            {"id": set_ids[s], "code": f"perf-dcs-{s}", "name": f"Extension {s}",
             "series": f"Série {s % 8}", "total_cards": CARDS_PER_SET}
            for s in range(SET_COUNT)
        ],
    )

    cards: list[dict] = []
    names: list[dict] = []
    prices: list[dict] = []
    card_ids: list[uuid.UUID] = []
    for s in range(SET_COUNT):
        for c in range(CARDS_PER_SET):
            card_id = uuid.uuid4()
            card_ids.append(card_id)
            supertype = TYPES[c % len(TYPES)]
            display = f"Carte {s}-{c}"
            cards.append(
                {
                    "id": card_id,
                    "set_id": set_ids[s],
                    "number": str(c + 1),
                    "name": display,
                    "rarity": RARITIES[c % len(RARITIES)],
                    "supertype": supertype,
                    "hp": (30 + (c % 24) * 10) if supertype == "Pokémon" else None,
                    "image_url": f"https://img.example/{s}/{c}",
                }
            )
            names.append(
                {"id": uuid.uuid4(), "card_id": card_id, "language": "fr", "name": display}
            )
            # ~80 % valorisées : une carte sur cinq sans prix connu.
            if (s * CARDS_PER_SET + c) % 5 != 0:
                trend = 1 + (c % 60)
                prices.append(
                    {
                        "id": uuid.uuid4(),
                        "card_id": card_id,
                        "source": "cardmarket",
                        "variant": "normal",
                        "day": today,
                        "currency": "EUR",
                        "price_low": trend,
                        "price_mid": trend,
                        "price_trend": trend,
                    }
                )

    await _chunked_insert(session, Card, cards)
    await _chunked_insert(session, CardName, names)
    await _chunked_insert(session, CardPriceDaily, prices)

    # 5 000 exemplaires sur les 4 000 premières cartes -> 1 000 doublons.
    items = [
        {
            "id": uuid.uuid4(),
            "user_id": user.id,
            "card_id": card_ids[i % 4000],
            "language": "fr",
            "variant": "normal",
            "counterfeit_suspected": False,
            "acquired_at": today - timedelta(days=i % 365),
        }
        for i in range(ITEM_COUNT)
    ]
    await _chunked_insert(session, CollectionItem, items)

    # Un petit deck de l'utilisateur, pour mesurer la jointure `deck_cards` (in_deck_count).
    deck = Deck(user_id=user.id, name="Deck perf")
    session.add(deck)
    await session.flush()
    session.add_all(
        [DeckCard(deck_id=deck.id, card_id=card_ids[i], quantity=1 + (i % 4)) for i in range(20)]
    )
    await session.flush()

    # La vue matérialisée voit les données de CETTE transaction (même connexion) : le tri par
    # valeur mesure alors un vrai prix de référence, pas une colonne NULL.
    await session.execute(text("REFRESH MATERIALIZED VIEW card_value_rank"))

    # Statistiques du planificateur. En production les tables sont analysées (autovacuum) ;
    # mesurer sur des insertions en masse NON analysées donne des plans pathologiques (boucles
    # imbriquées sur des estimations fausses — un filtre indexé y devient 50× plus lent qu'un
    # simple parcours) qui n'existent jamais en ligne. ANALYZE rend la mesure réaliste.
    for tbl in (
        "sets", "cards", "card_names", "card_prices_daily",
        "collection_items", "deck_cards", "card_value_rank",
    ):
        await session.execute(text(f"ANALYZE {tbl}"))
    return user, raw_token, deck.id


async def _chunked_insert(session: AsyncSession, model, rows: list[dict], chunk: int = 2000):
    for start in range(0, len(rows), chunk):
        await session.execute(insert(model), rows[start : start + chunk])


async def _time(client: httpx.AsyncClient, params: dict[str, str]) -> float:
    start = time.perf_counter()
    response = await client.get("/me/decks/cards", params=params)
    elapsed = (time.perf_counter() - start) * 1000
    assert response.status_code == 200, response.text
    return elapsed


async def _time_deep_pagination(client: httpx.AsyncClient, pages: int = 10) -> float:
    """Suit `pages` pages au curseur (tri par valeur) et renvoie le temps TOTAL — c'est le
    scénario où un OFFSET s'effondre et où le keyset doit rester plat."""
    start = time.perf_counter()
    cursor: str | None = None
    for _ in range(pages):
        params = {"sort": "value_desc", "limit": "50"}
        if cursor:
            params["cursor"] = cursor
        response = await client.get("/me/decks/cards", params=params)
        assert response.status_code == 200, response.text
        cursor = response.json()["next_cursor"]
        if cursor is None:
            break
    return (time.perf_counter() - start) * 1000


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    idx = min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1)
    return ordered[idx]


async def main() -> None:
    engine = create_async_engine(settings.database_url)
    results: dict[str, dict[str, float]] = {}
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            print(f"Semis de {CARD_COUNT} cartes et {ITEM_COUNT} exemplaires...")
            user, raw_token, deck_id = await _seed(session)
            print(f"Semis terminé (utilisateur {user.id}, deck {deck_id}).")

            async def _get_session_override():
                yield session

            app.dependency_overrides[get_session] = _get_session_override
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="https://testserver"
            ) as client:
                client.cookies.set(settings.session_cookie_name, raw_token)

                scenarios: dict[str, dict[str, str]] = {
                    "défaut (tri nom, page 1)": {},
                    "recherche par nom": {"q": "Carte 10"},
                    "recherche par numéro": {"q": "42"},
                    "filtre type + rareté": {"card_type": "Pokémon", "rarity": "Rare"},
                    "filtre PV": {"hp_min": "100", "hp_max": "200"},
                    "tri par valeur (page 1)": {"sort": "value_desc"},
                    "seulement mes cartes": {"owned": "true"},
                    "doublons": {"duplicates": "true"},
                    "annoté du deck courant": {"deck_id": str(deck_id), "sort": "name_asc"},
                }
                for label, params in scenarios.items():
                    await _time(client, params)  # préchauffage (plans, caches) hors mesure
                    timings = [await _time(client, params) for _ in range(REPEATS)]
                    results[label] = _stats(timings)
                    print(f"  {label}: {results[label]}")

                # Pagination profonde : 10 pages suivies au curseur, temps total.
                await _time_deep_pagination(client)
                deep = [await _time_deep_pagination(client) for _ in range(REPEATS)]
                results["pagination 10 pages (total)"] = _stats(deep)
                print(f"  pagination 10 pages (total): {results['pagination 10 pages (total)']}")

            app.dependency_overrides.clear()
        finally:
            await session.close()
            await transaction.rollback()
    await engine.dispose()

    report_path = (
        Path(__file__).resolve().parent.parent / "var" / "deck-card-search-performance.json"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(
            {"card_count": CARD_COUNT, "item_count": ITEM_COUNT, "target_ms_p95": TARGET_MS,
             "results": results},
            indent=2,
            ensure_ascii=False,
        )
    )
    print(f"Rapport écrit dans {report_path}")

    # La pagination profonde couvre 10 pages : son budget est 10× celui d'une requête unique.
    def _budget(label: str) -> float:
        return TARGET_MS * 10 if label.startswith("pagination") else TARGET_MS

    failures = {label: s for label, s in results.items() if s["p95_ms"] >= _budget(label)}
    if failures:
        raise SystemExit(f"Objectif non tenu (p95 < {TARGET_MS} ms) pour : {failures}")
    print(f"Objectif tenu : p95 sous {TARGET_MS} ms pour chaque requête.")


def _stats(timings: list[float]) -> dict[str, float]:
    return {
        "min_ms": round(min(timings), 1),
        "median_ms": round(statistics.median(timings), 1),
        "p95_ms": round(_p95(timings), 1),
        "max_ms": round(max(timings), 1),
    }


if __name__ == "__main__":
    asyncio.run(main())
