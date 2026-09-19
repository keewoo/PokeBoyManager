"""Mesure de performance de `GET /me/collection` (mission `v4-collection`, point 4 : 5 000
exemplaires, réponse < 300 ms).

Sème 5 000 `CollectionItem` pour un utilisateur de mesure, répartis sur 50 extensions × 100
cartes, prix connu pour 80 % d'entre eux (une collection réelle n'a jamais 100 % de cartes
valorisées) — puis mesure le temps de réponse HTTP réel de `GET /me/collection` (`ASGITransport`,
même technique que `tests/conftest.py`) sur plusieurs scénarios représentatifs : page par défaut
(tri valeur), recherche, filtre de valeur, tri par date d'ajout — 9 requêtes par scénario,
objectif jugé sur la médiane (chimera est une machine partagée avec d'autres lots, voir
`~/.claude/CLAUDE.md` : un pic isolé sur une requête n'est pas le temps de réponse réel du
chemin de code). La transaction est annulée en fin de script : aucune donnée n'est laissée dans
la base pointée par `DATABASE_URL`.

Usage :
    uv run python scripts/measure_collection_performance.py
"""

import asyncio
import json
import statistics
import time
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from pbm_api.config import settings
from pbm_api.db import get_session
from pbm_api.main import app
from pbm_api.models import Card, CardPriceDaily, PriceSource, PriceVariant, Set, User
from pbm_api.models.collection import CollectionItem
from pbm_api.models.users import Session as UserSession
from pbm_api.security.tokens import generate_opaque_token, hash_token

SET_COUNT = 50
CARDS_PER_SET = 100
ITEM_COUNT = SET_COUNT * CARDS_PER_SET
TARGET_MS = 300
REPEATS = 9


async def _seed(session: AsyncSession) -> tuple[User, str]:
    user = User(
        email=f"perf-{uuid.uuid4()}@example.com",
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

    today = datetime.now(UTC).date()
    for set_index in range(SET_COUNT):
        set_row = Set(
            code=f"perf-{set_index}",
            name=f"Extension perf {set_index}",
            series=f"Série {set_index % 5}",
        )
        session.add(set_row)
        await session.flush()
        for card_index in range(CARDS_PER_SET):
            card = Card(
                set_id=set_row.id,
                number=str(card_index + 1),
                name=f"Carte {set_index}-{card_index}",
                rarity=["commune", "peu commune", "rare"][card_index % 3],
                supertype="Pokémon",
            )
            session.add(card)
            await session.flush()
            # 80 % valorisées : une collection réelle n'a jamais 100 % de cartes cotées.
            if (set_index * CARDS_PER_SET + card_index) % 5 != 0:
                trend = Decimal(str(1 + (card_index % 50)))
                session.add(
                    CardPriceDaily(
                        card_id=card.id,
                        source=PriceSource.cardmarket,
                        variant=PriceVariant.normal,
                        day=today,
                        currency="EUR",
                        price_low=trend,
                        price_mid=trend,
                        price_trend=trend,
                    )
                )
            session.add(
                CollectionItem(
                    user_id=user.id,
                    card_id=card.id,
                    language="fr",
                    variant=PriceVariant.normal,
                    condition_grade="near_mint",
                    acquired_at=today - timedelta(days=card_index),
                )
            )
    await session.flush()
    return user, raw_token


async def _time_request(
    client: httpx.AsyncClient, params: dict[str, str]
) -> float:
    start = time.perf_counter()
    response = await client.get("/me/collection", params=params)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert response.status_code == 200, response.text
    return elapsed_ms


async def main() -> None:
    engine = create_async_engine(settings.database_url)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        results: dict[str, dict[str, float]] = {}
        try:
            print(f"Semis de {ITEM_COUNT} exemplaires...")
            user, raw_token = await _seed(session)
            print(f"Semis terminé pour l'utilisateur {user.id}.")

            async def _get_session_override():
                yield session

            app.dependency_overrides[get_session] = _get_session_override
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="https://testserver"
            ) as client:
                client.cookies.set(settings.session_cookie_name, raw_token)

                scenarios: dict[str, dict[str, str]] = {
                    "défaut (tri valeur, page 1)": {},
                    "recherche": {"q": "Carte 10"},
                    "filtre valeur min": {"value_min": "10"},
                    "tri date d'ajout": {"sort": "acquired_at_desc"},
                    "tri variation 30 j": {"sort": "value_change_30d_desc"},
                }
                for label, params in scenarios.items():
                    timings = [await _time_request(client, params) for _ in range(REPEATS)]
                    stats = {
                        "min_ms": round(min(timings), 1),
                        "median_ms": round(statistics.median(timings), 1),
                        "max_ms": round(max(timings), 1),
                        "mean_ms": round(sum(timings) / len(timings), 1),
                    }
                    results[label] = stats
                    print(f"  {label}: {stats}")
            app.dependency_overrides.clear()
        finally:
            await session.close()
            await transaction.rollback()
    await engine.dispose()

    report_path = Path(__file__).resolve().parent.parent / "var" / "collection-performance.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(
            {"item_count": ITEM_COUNT, "target_ms": TARGET_MS, "results": results}, indent=2
        )
    )
    print(f"Rapport écrit dans {report_path}")

    # Objectif jugé sur la médiane, pas le maximum d'un échantillon de 9 : chimera est une
    # machine partagée avec d'autres lots en cours (`~/.claude/CLAUDE.md`), une requête isolée
    # y subit parfois un pic (GC, contention Postgres) sans que ce soit le temps de réponse
    # réel du chemin de code — le maximum reste imprimé/journalisé pour ne rien cacher.
    failures = {label: s for label, s in results.items() if s["median_ms"] >= TARGET_MS}
    if failures:
        raise SystemExit(f"Objectif non tenu (< {TARGET_MS} ms, médiane) pour : {failures}")
    print(f"Objectif tenu : médiane sous {TARGET_MS} ms pour tous les scénarios.")


if __name__ == "__main__":
    asyncio.run(main())
