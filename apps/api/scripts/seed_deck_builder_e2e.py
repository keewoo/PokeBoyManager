"""Sème de quoi construire un deck LÉGAL de bout en bout pour l'e2e du constructeur (lot
`v7-decks-ui`, `apps/web/e2e/deck-builder.spec.ts`) :

  - une extension de démonstration et deux cartes : un Pokémon de base possédé (légal Standard)
    et une Énergie de base (fournie, jamais décomptée de la collection) ;
  - un utilisateur vérifié, à qui l'on donne QUATRE exemplaires du Pokémon (une ligne de
    `collection_items` = un exemplaire, cf. `pbm_api.decks.service._owned_counts`).

Un deck de 4 × ce Pokémon + 56 × cette Énergie = 60 cartes, possédées, format Standard : légal
(`pbm_api.decks.legality`). Idempotent — relançable sans dupliquer (upsert par code d'extension,
numéro de carte, e-mail).

Ne passe PAS par `POST /auth/register` (limité en débit par IP depuis `v5-securite`, compteur
partagé par toutes les specs e2e) : l'utilisateur est créé directement en base, comme
`scripts/seed_e2e_second_user.py`. Le test se connecte ensuite via `POST /auth/login` (scope de
débit distinct).

Usage : uv run python scripts/seed_deck_builder_e2e.py <email> <password>
"""

import asyncio
import sys
from datetime import UTC, date, datetime

from sqlalchemy import func, select

from pbm_api.db import async_session_factory
from pbm_api.legal import CURRENT_TERMS_VERSION
from pbm_api.models import Card, CollectionItem, Set, User
from pbm_api.models.catalog import PriceVariant
from pbm_api.security.passwords import hash_password

SET_CODE = "e2edeck"
POKEMON_NUMBER = "1"
POKEMON_NAME = "Ronflex E2E"
ENERGY_NUMBER = "2"
ENERGY_NAME = "Énergie E2E"
OWNED_COPIES = 4


async def _get_or_create_set(session) -> Set:
    row = (await session.execute(select(Set).where(Set.code == SET_CODE))).scalar_one_or_none()
    if row is not None:
        return row
    row = Set(code=SET_CODE, name="Démo constructeur", series="E2E")
    session.add(row)
    await session.flush()
    return row


async def _get_or_create_card(session, set_id, number: str, **fields) -> Card:
    row = (
        await session.execute(select(Card).where(Card.set_id == set_id, Card.number == number))
    ).scalar_one_or_none()
    if row is not None:
        return row
    row = Card(set_id=set_id, number=number, **fields)
    session.add(row)
    await session.flush()
    return row


async def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(1)
    email, password = sys.argv[1], sys.argv[2]

    async with async_session_factory() as session:
        set_row = await _get_or_create_set(session)
        pokemon = await _get_or_create_card(
            session,
            set_row.id,
            POKEMON_NUMBER,
            name=POKEMON_NAME,
            supertype="Pokémon",
            stage="Basic",
            rarity="Commune",
            hp=110,
            legal_standard=True,
            legal_expanded=True,
        )
        await _get_or_create_card(
            session,
            set_row.id,
            ENERGY_NUMBER,
            name=ENERGY_NAME,
            supertype="Énergie",
            energy_type="Normal",
            rarity="Commune",
            legal_standard=True,
            legal_expanded=True,
        )

        user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user is None:
            user = User(
                email=email,
                password_hash=hash_password(password),
                last_name="Constructeur",
                birth_date=date(2000, 1, 1),
                terms_version=CURRENT_TERMS_VERSION,
                terms_accepted_at=datetime.now(UTC).replace(tzinfo=None),
                email_verified_at=datetime.now(UTC).replace(tzinfo=None),
            )
            session.add(user)
            await session.flush()

        owned = (
            await session.execute(
                select(func.count())
                .select_from(CollectionItem)
                .where(
                    CollectionItem.user_id == user.id,
                    CollectionItem.card_id == pokemon.id,
                )
            )
        ).scalar_one()
        for _ in range(max(0, OWNED_COPIES - owned)):
            session.add(
                CollectionItem(
                    user_id=user.id,
                    card_id=pokemon.id,
                    language="fr",
                    variant=PriceVariant.normal,
                )
            )

        await session.commit()


if __name__ == "__main__":
    asyncio.run(main())
