"""Crée (ou met à jour) directement en base un utilisateur vérifié **avec le droit d'accès au jeu**
(`game_access = True`, D11), pour l'e2e du plateau (lot `j-plateau-layout`,
`apps/web/e2e/plateau-responsive.spec.ts`).

Le plateau gate l'accès sur `GET /me` (`game_access`) : sans ce droit, la route `/jeu/parties/{id}`
rend une page inexistante et le test ne peut rien mesurer. On accorde donc le droit ici, sur un
compte dédié au test.

Ne passe PAS par `POST /auth/register` (limité en débit par IP, compteur partagé par toutes les
specs e2e, cf. `seed_e2e_second_user.py`) : l'utilisateur est créé directement en base. Le test se
connecte ensuite via `POST /auth/login` (scope de débit distinct).

Usage : uv run python scripts/seed_game_access_e2e.py <email> <password>
"""

import asyncio
import sys
from datetime import UTC, date, datetime

from sqlalchemy import select

from pbm_api.db import async_session_factory
from pbm_api.legal import CURRENT_TERMS_VERSION
from pbm_api.models import User
from pbm_api.security.passwords import hash_password


async def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(1)
    email, password = sys.argv[1], sys.argv[2]

    async with async_session_factory() as session:
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if user is None:
            user = User(
                email=email,
                password_hash=hash_password(password),
                last_name="Joueur",
                birth_date=date(2000, 1, 1),
                terms_version=CURRENT_TERMS_VERSION,
                terms_accepted_at=datetime.now(UTC).replace(tzinfo=None),
                email_verified_at=datetime.now(UTC).replace(tzinfo=None),
            )
            session.add(user)
        user.game_access = True
        await session.commit()


if __name__ == "__main__":
    asyncio.run(main())
