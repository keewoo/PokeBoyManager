"""Relevé périodique de présence en tournoi — mission `v4-jeu` point 2, appelé par
`pbm_api.worker.weekly_tournament_presence_task`.

Reprise sur erreur à la carte près, comme `pbm_api.pricing.service` : une carte qui échoue à se
rapprocher (extension/numéro non trouvés) est enregistrée `unavailable`, jamais une exception
qui interromprait tout le relevé. Seul un blocage explicite du site (`LimitlessBlockedError`,
HTTP 403/429) arrête le relevé en cours — inutile d'insister carte par carte contre un site qui
vient de nous refuser.

Bridé aux cartes légales dans au moins un format (Standard ou Étendu, mission point 2 : « est-ce
que cette carte sert encore ? ») et à une faible concurrence (mission réseau — chimera plafonne
à ~250 ko/s, et Limitless TCG est un site tiers à ménager, pas une API dédiée)."""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.ingame.tournaments import (
    LimitlessBlockedError,
    LimitlessTcgClient,
    find_card_page,
    parse_decklists,
)
from pbm_api.models import Card, CardName, CardTournamentPresence, Set, TournamentPresenceStatus

logger = logging.getLogger(__name__)

# Une seule requête à la fois : courtoisie envers un site tiers sans API dédiée (contrairement
# à TCGdex/Pokémon TCG API, publics et documentés pour cet usage).
LIMITLESS_CONCURRENCY = 1


def _now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _upsert_presence(
    session: AsyncSession,
    card_id: Any,
    status: TournamentPresenceStatus,
    source_url: str | None,
    decks: list[dict] | None,
    checked_at: datetime,
) -> None:
    stmt = pg_insert(CardTournamentPresence).values(
        card_id=card_id,
        status=status,
        source_url=source_url,
        decks=decks,
        checked_at=checked_at,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["card_id"],
        set_={
            "status": stmt.excluded.status,
            "source_url": stmt.excluded.source_url,
            "decks": stmt.excluded.decks,
            "checked_at": stmt.excluded.checked_at,
        },
    )
    await session.execute(stmt)


async def refresh_tournament_presence(
    session: AsyncSession, client: LimitlessTcgClient
) -> dict[str, Any]:
    sets = await client.list_sets()

    rows = (
        await session.execute(
            select(Card.id, Card.number, Card.name, Card.set_id)
            .where(or_(Card.legal_standard.is_(True), Card.legal_expanded.is_(True)))
        )
    ).all()

    en_names = dict(
        (
            await session.execute(
                select(CardName.card_id, CardName.name).where(CardName.language == "en")
            )
        ).all()
    )
    sets_rows = (await session.execute(select(Set.id, Set.name, Set.release_date))).all()
    sets_by_id = {s.id: s for s in sets_rows}

    checked_at = _now_naive()
    report: dict[str, Any] = {
        "cards_eligible": len(rows),
        "matched": 0,
        "unavailable": 0,
        "errors": [],
    }

    semaphore = asyncio.Semaphore(LIMITLESS_CONCURRENCY)
    blocked: list[LimitlessBlockedError] = []

    async def _one(row: Any) -> None:
        if blocked:
            return
        async with semaphore:
            set_row = sets_by_id.get(row.set_id)
            if set_row is None:
                return
            expected_en_name = en_names.get(row.id, row.name)
            try:
                found = await find_card_page(
                    client,
                    sets=sets,
                    set_release_date=set_row.release_date,
                    set_name=set_row.name,
                    card_number=row.number,
                    expected_en_name=expected_en_name,
                )
            except LimitlessBlockedError as exc:
                blocked.append(exc)
                report["errors"].append(str(exc))
                return
            except Exception as exc:  # noqa: BLE001 — une carte en échec ne stoppe pas le relevé
                logger.warning("Échec relevé tournoi %s : %s", row.id, exc)
                report["errors"].append(f"{row.name} ({row.id}) : {exc}")
                return

            if found is None:
                await _upsert_presence(
                    session, row.id, TournamentPresenceStatus.unavailable, None, None, checked_at
                )
                report["unavailable"] += 1
                return

            source_url, html_page = found
            decks = [d.model_dump() for d in parse_decklists(html_page)]
            await _upsert_presence(
                session, row.id, TournamentPresenceStatus.checked, source_url, decks, checked_at
            )
            report["matched"] += 1

    await asyncio.gather(*(_one(row) for row in rows))
    await session.commit()

    if blocked:
        raise LimitlessBlockedError(str(blocked[0]))

    return report
