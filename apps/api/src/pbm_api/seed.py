"""Données de démonstration : un utilisateur, trois extensions, neuf cartes.

Idempotent — relançable sans dupliquer (upsert par clé naturelle : email, code de set,
couple set+numéro de carte). Aucune clé IA réelle : ce lot n'en dépose aucune.

Usage : uv run python -m pbm_api.seed
"""

import asyncio
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.db import async_session_factory
from pbm_api.models import Card, CardName, Set, User

DEMO_USER_EMAIL = "demo@pokeboymanager.local"

DEMO_SETS = [
    {
        "code": "sv01",
        "name": "Écarlate et Violet",
        "series": "Écarlate et Violet",
        "release_date": date(2023, 3, 31),
        "total_cards": 198,
    },
    {
        "code": "sv03pt5",
        "name": "151",
        "series": "Écarlate et Violet",
        "release_date": date(2023, 9, 22),
        "total_cards": 165,
    },
    {
        "code": "swsh07",
        "name": "Poing de Fusion",
        "series": "Épée et Bouclier",
        "release_date": date(2021, 6, 25),
        "total_cards": 163,
    },
]

DEMO_CARDS = [
    {
        "set_code": "sv01",
        "number": "1",
        "name": "Sarmuraï",
        "rarity": "Common",
        "supertype": "Pokémon",
        "hp": 60,
        "names": {"fr": "Sarmuraï", "en": "Sprigatito"},
    },
    {
        "set_code": "sv01",
        "number": "20",
        "name": "Chochodile",
        "rarity": "Common",
        "supertype": "Pokémon",
        "hp": 80,
        "names": {"fr": "Chochodile", "en": "Quaxwell"},
    },
    {
        "set_code": "sv01",
        "number": "234",
        "name": "Miraidon ex",
        "rarity": "Special Illustration Rare",
        "supertype": "Pokémon",
        "hp": 220,
        "names": {"fr": "Miraidon-ex", "en": "Miraidon ex"},
    },
    {
        "set_code": "sv03pt5",
        "number": "6",
        "name": "Mewtwo",
        "rarity": "Rare Holo",
        "supertype": "Pokémon",
        "hp": 130,
        "names": {"fr": "Mewtwo", "en": "Mewtwo"},
    },
    {
        "set_code": "sv03pt5",
        "number": "25",
        "name": "Pikachu",
        "rarity": "Common",
        "supertype": "Pokémon",
        "hp": 60,
        "names": {"fr": "Pikachu", "en": "Pikachu"},
    },
    {
        "set_code": "sv03pt5",
        "number": "151",
        "name": "Mew ex",
        "rarity": "Special Illustration Rare",
        "supertype": "Pokémon",
        "hp": 180,
        "names": {"fr": "Mew-ex", "en": "Mew ex"},
    },
    {
        "set_code": "swsh07",
        "number": "1",
        "name": "Germignon",
        "rarity": "Common",
        "supertype": "Pokémon",
        "hp": 70,
        "names": {"fr": "Germignon", "en": "Chikorita"},
    },
    {
        "set_code": "swsh07",
        "number": "154",
        "name": "Dracaufeu V",
        "rarity": "Ultra Rare",
        "supertype": "Pokémon",
        "hp": 220,
        "names": {"fr": "Dracaufeu-V", "en": "Charizard V"},
    },
    {
        "set_code": "swsh07",
        "number": "155",
        "name": "Dracaufeu VMAX",
        "rarity": "Ultra Rare",
        "supertype": "Pokémon",
        "hp": 330,
        "names": {"fr": "Dracaufeu-VMAX", "en": "Charizard VMAX"},
    },
]


async def seed(session: AsyncSession) -> None:
    result = await session.execute(select(User).where(User.email == DEMO_USER_EMAIL))
    if result.scalar_one_or_none() is None:
        # `last_name`/`birth_date`/`terms_version`/`terms_accepted_at` sont NOT NULL depuis le
        # lot `v1-identite` (migration `328aef94ea58`), postérieur à ce module — un compte
        # « démo » désactivé (`password_hash`) porte les mêmes valeurs par défaut que
        # `pbm_api.admin create-user` pour un consentement porté par JF.
        session.add(
            User(
                email=DEMO_USER_EMAIL,
                password_hash="!disabled!",
                last_name="Démo",
                birth_date=date(2000, 1, 1),
                terms_version="demo",
                terms_accepted_at=datetime.now(UTC).replace(tzinfo=None),
            )
        )

    sets_by_code: dict[str, Set] = {}
    for set_data in DEMO_SETS:
        result = await session.execute(select(Set).where(Set.code == set_data["code"]))
        existing = result.scalar_one_or_none()
        if existing is None:
            existing = Set(**set_data)
            session.add(existing)
        sets_by_code[set_data["code"]] = existing

    await session.flush()

    for card_data in DEMO_CARDS:
        set_row = sets_by_code[card_data["set_code"]]
        result = await session.execute(
            select(Card).where(Card.set_id == set_row.id, Card.number == card_data["number"])
        )
        card = result.scalar_one_or_none()
        if card is None:
            card = Card(
                set_id=set_row.id,
                number=card_data["number"],
                name=card_data["name"],
                rarity=card_data["rarity"],
                supertype=card_data["supertype"],
                hp=card_data["hp"],
            )
            session.add(card)
            await session.flush()

        for language, name in card_data["names"].items():
            result = await session.execute(
                select(CardName).where(CardName.card_id == card.id, CardName.language == language)
            )
            if result.scalar_one_or_none() is None:
                session.add(CardName(card_id=card.id, language=language, name=name))

    await session.commit()


async def main() -> None:
    async with async_session_factory() as session:
        await seed(session)


if __name__ == "__main__":
    asyncio.run(main())
