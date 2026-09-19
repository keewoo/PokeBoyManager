"""Relevé périodique de présence en tournoi (mission `v4-jeu` point 2) — reprise sur erreur à la
carte près, idempotence de l'upsert, cartes hors format ignorées, blocage du site interrompt le
relevé plutôt que d'insister (comme `pbm_api.pricing.service`, voir son propre test)."""

import uuid
from datetime import date

import pytest
from sqlalchemy import select

from pbm_api.ingame.tournaments import LimitlessBlockedError, LimitlessSet
from pbm_api.ingame.tournaments_job import refresh_tournament_presence
from pbm_api.models import Card, CardName, CardTournamentPresence, Set, TournamentPresenceStatus

MEW_RELEASE = date(2023, 9, 22)


async def _make_set(db_session, *, name: str = "151", release_date=MEW_RELEASE) -> Set:
    suffix = uuid.uuid4().hex[:8]
    set_row = Set(code=f"tourney-{suffix}", name=name, release_date=release_date)
    db_session.add(set_row)
    await db_session.flush()
    return set_row


async def _make_card(
    db_session,
    set_row: Set,
    *,
    number: str = "6",
    name: str = "Charizard ex",
    en_name: str | None = "Charizard ex",
    legal_standard: bool | None = False,
    legal_expanded: bool | None = True,
) -> Card:
    card = Card(
        set_id=set_row.id,
        number=number,
        name=name,
        legal_standard=legal_standard,
        legal_expanded=legal_expanded,
    )
    db_session.add(card)
    await db_session.flush()
    if en_name is not None:
        db_session.add(CardName(card_id=card.id, language="en", name=en_name))
        await db_session.flush()
    return card


class FakeLimitlessClient:
    def __init__(
        self,
        *,
        sets: list[LimitlessSet],
        pages: dict[tuple[str, str], str],
        blocked_after: int | None = None,
    ) -> None:
        self._sets = sets
        self._pages = pages
        self._blocked_after = blocked_after
        self.fetch_calls: list[tuple[str, str]] = []

    async def list_sets(self) -> list[LimitlessSet]:
        return self._sets

    async def fetch_card_page(self, set_code: str, number: str) -> str | None:
        self.fetch_calls.append((set_code, number))
        if self._blocked_after is not None and len(self.fetch_calls) > self._blocked_after:
            raise LimitlessBlockedError("HTTP 403 sur https://limitlesstcg.com/cards/BLOCKED")
        return self._pages.get((set_code, number))


CARD_PAGE_HTML = """
<title>Charizard ex - Pokémon 151 (MEW) #6 – Limitless</title>
<div class="card-tournament-results">
    <table class="data-table striped">
    <tr><th></th><th>Deck</th><th>Tournament</th><th>Place</th></tr>
    <tr>
        <td><img class="pokemon" src="x.png"></td>
        <td><a href="https://limitlesstcg.com/decks/list/1">Charizard Pidgeot</a></td>
        <td><a href="/tournaments/1">Regional Lille</a></td>
        <td>229th</td>
    </tr>
    </table>
</div>
"""


async def test_refresh_marks_a_matched_card_as_checked_with_its_decks(db_session):
    set_row = await _make_set(db_session)
    card = await _make_card(db_session, set_row)
    await db_session.commit()

    client = FakeLimitlessClient(
        sets=[LimitlessSet(code="MEW", name="Pokémon 151", release_date=MEW_RELEASE)],
        pages={("MEW", "6"): CARD_PAGE_HTML},
    )

    report = await refresh_tournament_presence(db_session, client)

    assert report["matched"] == 1
    assert report["unavailable"] == 0
    row = (
        await db_session.execute(
            select(CardTournamentPresence).where(CardTournamentPresence.card_id == card.id)
        )
    ).scalar_one()
    assert row.status == TournamentPresenceStatus.checked
    assert row.source_url == "https://limitlesstcg.com/cards/MEW/6"
    assert row.decks == [
        {
            "deck_name": "Charizard Pidgeot",
            "tournament_name": "Regional Lille",
            "tournament_url": "https://limitlesstcg.com/tournaments/1",
            "placement": "229th",
        }
    ]


async def test_refresh_marks_an_unmatched_card_as_unavailable(db_session):
    set_row = await _make_set(db_session)
    card = await _make_card(db_session, set_row, number="999")
    await db_session.commit()

    client = FakeLimitlessClient(
        sets=[LimitlessSet(code="MEW", name="Pokémon 151", release_date=MEW_RELEASE)],
        pages={},
    )

    report = await refresh_tournament_presence(db_session, client)

    assert report["matched"] == 0
    assert report["unavailable"] == 1
    row = (
        await db_session.execute(
            select(CardTournamentPresence).where(CardTournamentPresence.card_id == card.id)
        )
    ).scalar_one()
    assert row.status == TournamentPresenceStatus.unavailable
    assert row.decks is None


async def test_refresh_ignores_cards_illegal_in_every_format(db_session):
    set_row = await _make_set(db_session)
    await _make_card(db_session, set_row, legal_standard=False, legal_expanded=False)
    await db_session.commit()

    client = FakeLimitlessClient(sets=[], pages={})
    report = await refresh_tournament_presence(db_session, client)

    assert report["cards_eligible"] == 0
    assert client.fetch_calls == []


async def test_refresh_is_idempotent_on_a_second_run(db_session):
    set_row = await _make_set(db_session)
    card = await _make_card(db_session, set_row)
    await db_session.commit()

    client = FakeLimitlessClient(
        sets=[LimitlessSet(code="MEW", name="Pokémon 151", release_date=MEW_RELEASE)],
        pages={("MEW", "6"): CARD_PAGE_HTML},
    )

    await refresh_tournament_presence(db_session, client)
    await refresh_tournament_presence(db_session, client)

    rows = (
        (
            await db_session.execute(
                select(CardTournamentPresence).where(CardTournamentPresence.card_id == card.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1


async def test_refresh_continues_after_a_single_card_failure(db_session):
    set_row = await _make_set(db_session)
    failing_card = await _make_card(db_session, set_row, number="6", name="Failing Card")
    healthy_card = await _make_card(
        db_session, set_row, number="7", name="Healthy Card", en_name="Healthy Card"
    )
    await db_session.commit()

    class FlakyClient(FakeLimitlessClient):
        async def fetch_card_page(self, set_code: str, number: str) -> str | None:
            if number == "6":
                raise RuntimeError("panne réseau ponctuelle")
            return await super().fetch_card_page(set_code, number)

    client = FlakyClient(
        sets=[LimitlessSet(code="MEW", name="Pokémon 151", release_date=MEW_RELEASE)],
        pages={},
    )

    report = await refresh_tournament_presence(db_session, client)

    assert report["errors"]
    failing_row = (
        await db_session.execute(
            select(CardTournamentPresence).where(CardTournamentPresence.card_id == failing_card.id)
        )
    ).scalar_one_or_none()
    assert failing_row is None  # jamais écrit sur une carte en échec, ni un succès silencieux
    healthy_row = (
        await db_session.execute(
            select(CardTournamentPresence).where(CardTournamentPresence.card_id == healthy_card.id)
        )
    ).scalar_one()
    assert healthy_row.status == TournamentPresenceStatus.unavailable


async def test_refresh_raises_and_stops_when_the_site_blocks_us(db_session):
    set_row = await _make_set(db_session)
    await _make_card(db_session, set_row, number="6")
    await _make_card(db_session, set_row, number="7", name="Second Card", en_name="Second Card")
    await db_session.commit()

    client = FakeLimitlessClient(
        sets=[LimitlessSet(code="MEW", name="Pokémon 151", release_date=MEW_RELEASE)],
        pages={},
        blocked_after=0,
    )

    with pytest.raises(LimitlessBlockedError):
        await refresh_tournament_presence(db_session, client)
