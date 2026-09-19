"""`scripts/catalogue_seed.sh` — mission `v2-catalogue-complet` point 6 : restauration de la
graine dans une base vide.

Ce script shell dépend de `pg_dump`/`pg_restore`/`psql` (postgresql-client) sur `PATH` — présents
nativement sur les runners `ubuntu-latest` de GitHub Actions ; absents par défaut sur chimera (WSL
Ubuntu), installés localement sans `sudo` pour cette session (voir compte rendu du lot). Aucun
repli silencieux si l'outillage manque : le test échoue avec l'erreur brute (`FileNotFoundError`),
pas un skip.

`pg_dump` ne voit que des données **committées** : ce test insère et committe directement (sans
passer par la fixture `db_session`, dont la transaction est annulée en fin de test) puis nettoie
explicitement à la fin, pour ne pas polluer le reste de la suite qui partage cette base.
"""

import os
import subprocess
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from pbm_api.models import Card, CardName, CardPriceDaily, PriceSource, PriceVariant, Set

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v2_catalogue_complet_test",
)
SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "catalogue_seed.sh"


async def _wipe_catalogue(session_factory) -> None:
    async with session_factory() as session:
        await session.execute(delete(CardPriceDaily))
        await session.execute(delete(CardName))
        await session.execute(delete(Card))
        await session.execute(delete(Set))
        await session.commit()


@pytest.fixture
async def committed_catalogue():
    """Un set + deux cartes + leurs noms + un prix, réellement committés (visibles par `pg_dump`,
    contrairement à `db_session`). Nettoyé avant et après le test."""
    engine = create_async_engine(TEST_DATABASE_URL)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await _wipe_catalogue(session_factory)

    async with engine.begin() as conn:
        set_id = (
            await conn.execute(
                text(
                    "INSERT INTO sets (id, code, name, tcgdex_id, total_cards, created_at, "
                    "updated_at) VALUES (gen_random_uuid(), 'seed-test', 'Seed Test', "
                    "'seed-test', 2, now(), now()) RETURNING id"
                )
            )
        ).scalar_one()
        card_id = (
            await conn.execute(
                text(
                    "INSERT INTO cards (id, set_id, number, name, tcgdex_id, retreat_cost, "
                    "created_at, updated_at) VALUES (gen_random_uuid(), :set_id, '001', "
                    "'Carte Graine', 'seed-test-001', 2, now(), now()) RETURNING id"
                ),
                {"set_id": set_id},
            )
        ).scalar_one()
        await conn.execute(
            text(
                "INSERT INTO card_names (id, card_id, language, name) VALUES "
                "(gen_random_uuid(), :card_id, 'fr', 'Carte Graine')"
            ),
            {"card_id": card_id},
        )
        await conn.execute(
            text(
                "INSERT INTO card_prices_daily (id, card_id, source, variant, day, currency, "
                "price_trend, created_at) VALUES (gen_random_uuid(), :card_id, 'cardmarket', "
                "'normal', :day, 'EUR', 12.5, now())"
            ),
            {"card_id": card_id, "day": date(2026, 9, 19)},
        )

    yield session_factory

    await _wipe_catalogue(session_factory)
    await engine.dispose()


def _run_seed_script(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


async def test_seed_export_then_restore_into_empty_database(committed_catalogue, tmp_path):
    session_factory = committed_catalogue
    dump_path = tmp_path / "catalogue-test.dump"

    export_result = _run_seed_script("export", TEST_DATABASE_URL, str(dump_path))
    assert export_result.returncode == 0, export_result.stderr
    assert dump_path.exists()

    # Base vraiment vide (pas seulement "comme au départ") : la restauration doit repeupler
    # depuis zéro, c'est le scénario réel du déploiement (mission point 5).
    await _wipe_catalogue(session_factory)
    async with session_factory() as session:
        assert (await session.execute(select(Set))).first() is None

    import_result = _run_seed_script("import", TEST_DATABASE_URL, str(dump_path))
    assert import_result.returncode == 0, import_result.stderr

    async with session_factory() as session:
        set_row = (
            await session.execute(select(Set).where(Set.tcgdex_id == "seed-test"))
        ).scalar_one()
        assert set_row.name == "Seed Test"

        card_row = (
            await session.execute(select(Card).where(Card.tcgdex_id == "seed-test-001"))
        ).scalar_one()
        assert card_row.retreat_cost == 2

        name_row = (
            await session.execute(select(CardName).where(CardName.card_id == card_row.id))
        ).scalar_one()
        assert name_row.name == "Carte Graine"

        price_row = (
            await session.execute(
                select(CardPriceDaily).where(CardPriceDaily.card_id == card_row.id)
            )
        ).scalar_one()
        assert price_row.source == PriceSource.cardmarket
        assert price_row.variant == PriceVariant.normal
        assert float(price_row.price_trend) == 12.5


async def test_seed_import_is_idempotent(committed_catalogue, tmp_path):
    """Rejouer le même import (reprise après une interruption, ou re-déploiement) ne duplique
    rien et n'échoue pas sur une contrainte unique déjà satisfaite."""
    session_factory = committed_catalogue
    dump_path = tmp_path / "catalogue-test.dump"

    assert _run_seed_script("export", TEST_DATABASE_URL, str(dump_path)).returncode == 0
    assert _run_seed_script("import", TEST_DATABASE_URL, str(dump_path)).returncode == 0
    second = _run_seed_script("import", TEST_DATABASE_URL, str(dump_path))
    assert second.returncode == 0, second.stderr

    async with session_factory() as session:
        cards = (await session.execute(select(Card))).scalars().all()
        assert len(cards) == 1
        prices = (await session.execute(select(CardPriceDaily))).scalars().all()
        assert len(prices) == 1
