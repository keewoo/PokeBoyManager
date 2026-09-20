"""Crée directement en base un second utilisateur vérifié, pour le test d'accès croisé de l'e2e
du parcours complet (lot `v5-e2e`, `apps/web/e2e/parcours-complet.spec.ts`) — sans passer par
`POST /auth/register`, limité en débit par IP depuis le lot `v5-securite` (`register:ip`, 5
tentatives/15 min) : le parcours principal en consomme déjà une en s'inscrivant à l'écran, une
seconde depuis le même job Playwright s'ajouterait au décompte partagé par toutes les specs e2e
(`auth.spec.ts`/`validation.spec.ts`/`card-detail.spec.ts` en consomment déjà quatre) et
risquerait de dépasser la limite sur une CI qui rejoue la suite.

Usage : uv run python scripts/seed_e2e_second_user.py <email>

N'affiche rien sur stdout (rien à capturer : le test se connecte ensuite via `POST /auth/login`,
qui a son propre scope de débit `login:ip` distinct de `register:ip`).
"""

import asyncio
import sys
from datetime import UTC, date, datetime

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
        session.add(
            User(
                email=email,
                password_hash=hash_password(password),
                last_name="Dresseuse",
                birth_date=date(2000, 1, 1),
                terms_version=CURRENT_TERMS_VERSION,
                terms_accepted_at=datetime.now(UTC).replace(tzinfo=None),
                email_verified_at=datetime.now(UTC).replace(tzinfo=None),
            )
        )
        await session.commit()


if __name__ == "__main__":
    asyncio.run(main())
