"""Vérifie que la migration 0001 pose bien le schéma attendu.

Avant ce lot, aucune de ces tables n'existait : chacun de ces tests échoue sur une base
vierge (`relation "..." does not exist`) et passe une fois `alembic upgrade head` joué.
"""

import uuid
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from pbm_api.models import Card, PriceSource, PriceVariant, Set, User
from pbm_api.models.catalog import CardPriceDaily
from pbm_api.models.collection import CollectionItem

EXPECTED_TABLES = {
    "users",
    "sessions",
    "email_tokens",
    "ai_credentials",
    "sets",
    "cards",
    "card_names",
    "card_prices_daily",
    "uploads",
    "detections",
    "collection_items",
    "card_insights",
    "jobs",
}


async def test_all_expected_tables_exist(db_session):
    result = await db_session.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    )
    tables = {row[0] for row in result.fetchall()}
    missing = EXPECTED_TABLES - tables
    assert not missing, f"tables manquantes : {missing}"


async def test_trigram_indexes_exist(db_session):
    result = await db_session.execute(
        text(
            "SELECT indexname FROM pg_indexes "
            "WHERE indexname IN ('ix_cards_name_trgm', 'ix_card_names_name_trgm')"
        )
    )
    names = {row[0] for row in result.fetchall()}
    assert names == {"ix_cards_name_trgm", "ix_card_names_name_trgm"}


async def test_set_number_and_card_day_indexes_exist(db_session):
    result = await db_session.execute(
        text(
            "SELECT indexname FROM pg_indexes "
            "WHERE tablename = 'cards' AND indexdef LIKE '%set_id%number%'"
        )
    )
    assert result.fetchone() is not None, "index/contrainte (set_id, number) absente sur cards"

    result = await db_session.execute(
        text("SELECT indexname FROM pg_indexes WHERE indexname = 'ix_card_prices_daily_card_day'")
    )
    assert result.fetchone() is not None


async def _make_set_and_card(session, suffix: str) -> Card:
    set_row = Set(code=f"test-{suffix}", name=f"Set {suffix}")
    session.add(set_row)
    await session.flush()
    card = Card(set_id=set_row.id, number="1", name=f"Card {suffix}")
    session.add(card)
    await session.flush()
    return card


async def test_card_prices_daily_unique_constraint_enforced(db_session):
    card = await _make_set_and_card(db_session, "price")
    today = date.today()
    db_session.add(
        CardPriceDaily(
            card_id=card.id,
            source=PriceSource.cardmarket,
            variant=PriceVariant.normal,
            day=today,
            currency="EUR",
            price_trend=12.5,
        )
    )
    await db_session.flush()

    db_session.add(
        CardPriceDaily(
            card_id=card.id,
            source=PriceSource.cardmarket,
            variant=PriceVariant.normal,
            day=today,
            currency="EUR",
            price_trend=13.0,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_user_id_columns_are_foreign_keys_with_index(db_session):
    user_scoped_tables = [
        "sessions",
        "email_tokens",
        "ai_credentials",
        "uploads",
        "collection_items",
    ]
    for table in user_scoped_tables:
        result = await db_session.execute(
            text(
                """
                SELECT tc.constraint_type
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                WHERE tc.table_name = :table AND kcu.column_name = 'user_id'
                  AND tc.constraint_type = 'FOREIGN KEY'
                """
            ),
            {"table": table},
        )
        assert result.fetchone() is not None, f"{table}.user_id n'a pas de clé étrangère"

        result = await db_session.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = :table AND indexdef LIKE '%user_id%'"
            ),
            {"table": table},
        )
        assert result.fetchone() is not None, f"{table}.user_id n'a pas d'index"


async def test_delete_user_cascades_to_collection_items(db_session):
    user = User(email=f"cascade-{uuid.uuid4()}@example.com", password_hash="x")
    db_session.add(user)
    card = await _make_set_and_card(db_session, "cascade")
    await db_session.flush()

    item = CollectionItem(user_id=user.id, card_id=card.id, language="fr")
    db_session.add(item)
    await db_session.flush()
    item_id = item.id

    await db_session.delete(user)
    await db_session.flush()

    result = await db_session.execute(
        text("SELECT id FROM collection_items WHERE id = :id"), {"id": item_id}
    )
    assert result.fetchone() is None


async def test_ai_credentials_never_store_plaintext_key(db_session):
    """Le modèle n'expose aucune colonne en clair pour une clé IA — seulement chiffré et masque."""
    from pbm_api.models import AiCredential

    columns = {c.name for c in AiCredential.__table__.columns}
    assert "plaintext_key" not in columns
    assert "api_key" not in columns
    assert {"encrypted_key", "nonce", "key_mask"}.issubset(columns)
