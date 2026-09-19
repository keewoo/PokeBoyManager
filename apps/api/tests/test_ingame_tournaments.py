"""Rapprochement Limitless TCG (mission `v4-jeu` point 2) — parsing HTML et logique de
rapprochement en isolation, aucun réseau réel dans cette suite (voir `scripts/
prove_ingame_20_cards.py` pour l'essai contre le vrai site).

Les extraits HTML ci-dessous sont des versions réduites, mais structurellement fidèles, des
pages réellement observées sur limitlesstcg.com le 2026-09-19 (mêmes classes CSS, même
disposition des `<tr>`) — pas la page complète (scripts, publicités, sans intérêt pour le
parseur).
"""

from datetime import date

import httpx
import pytest

from pbm_api.ingame.tournaments import (
    LimitlessBlockedError,
    LimitlessTcgClient,
    find_card_page,
    match_set_code,
    normalize_card_number,
    parse_card_title,
    parse_decklists,
    parse_sets_index,
)

SETS_INDEX_HTML = """
<table>
<tr><th>Set</th><th>Release</th></tr>
<tr>
    <td><a href="/cards/MEW"><img class="set" alt="MEW" src="x.png">
        Pokémon 151 <span class="code annotation">MEW</span></a></td>
    <td><a href="/cards/MEW">22 Sep 23</a></td>
</tr>
<tr>
    <td><a href="/cards/OBF"><img class="set" alt="OBF" src="x.png">
        Obsidian Flames <span class="code annotation">OBF</span></a></td>
    <td><a href="/cards/OBF">11 Aug 23</a></td>
</tr>
<tr>
    <td><a href="/cards/SVP"><img class="set" alt="SVP" src="x.png">
        Scarlet &amp; Violet Promos <span class="code annotation">SVP</span></a></td>
    <td><a href="/cards/SVP"></a></td>
</tr>
</table>
"""

CARD_PAGE_WITH_DECKLISTS_HTML = """
<title>Charizard ex - Pokémon 151 (MEW) #6 – Limitless</title>
<div class="card-tournament-results">
    <h2>Decklists that include this card</h2>
    <table class="data-table striped">
    <tr><th></th><th>Deck</th><th>Tournament</th><th>Place</th></tr>
    <tr>
        <td><img class="pokemon" src="x.png" alt="charizard"></td>
        <td><a href="https://limitlesstcg.com/decks/list/20863">
            Charizard Pidgeot by Toby Woolner</a></td>
        <td><a href="/tournaments/524">Regional Lille</a></td>
        <td>229th</td>
    </tr>
    <tr>
        <td><img class="pokemon" src="x.png" alt="charizard"></td>
        <td><a href="https://limitlesstcg.com/decks/list/9075">
            Charizard Arceus by Rinesh John</a></td>
        <td><a href="/tournaments/414">Malaysia Regional League</a></td>
        <td>1st</td>
    </tr>
    </table>
    <div class="table-extension">
        <a class="button text-button" href="https://limitlesstcg.com/cards/MEW/6/decklists">
            Open all decklists (2)</a>
    </div>
</div>
"""

CARD_PAGE_WITHOUT_DECKLISTS_HTML = """
<title>Rare Candy - Obsidian Flames (OBF) #191 – Limitless</title>
<div class="card-tournament-results">
    <h2>Decklists that include this card</h2>
    <table class="data-table striped">
    <tr><th></th><th>Deck</th><th>Tournament</th><th>Place</th></tr>
    </table>
</div>
"""


def test_parse_sets_index_reads_code_name_and_release_date():
    sets = parse_sets_index(SETS_INDEX_HTML)
    assert [s.code for s in sets] == ["MEW", "OBF", "SVP"]
    assert sets[0].name == "Pokémon 151"
    assert sets[0].release_date == date(2023, 9, 22)


def test_parse_sets_index_treats_a_blank_date_as_none():
    sets = parse_sets_index(SETS_INDEX_HTML)
    promo_set = next(s for s in sets if s.code == "SVP")
    assert promo_set.release_date is None


def test_parse_card_title_extracts_the_card_name_only():
    assert parse_card_title(CARD_PAGE_WITH_DECKLISTS_HTML) == "Charizard ex"


def test_parse_decklists_extracts_all_rows():
    decks = parse_decklists(CARD_PAGE_WITH_DECKLISTS_HTML)
    assert len(decks) == 2
    assert decks[0].deck_name == "Charizard Pidgeot by Toby Woolner"
    assert decks[0].tournament_name == "Regional Lille"
    assert decks[0].tournament_url == "https://limitlesstcg.com/tournaments/524"
    assert decks[0].placement == "229th"


def test_parse_decklists_returns_empty_list_when_table_has_no_data_rows():
    assert parse_decklists(CARD_PAGE_WITHOUT_DECKLISTS_HTML) == []


def test_normalize_card_number_strips_leading_zeros():
    assert normalize_card_number("006") == "6"
    assert normalize_card_number("025") == "25"


def test_normalize_card_number_leaves_non_numeric_untouched():
    assert normalize_card_number("TG05") == "TG05"


def test_match_set_code_by_exact_release_date():
    sets = parse_sets_index(SETS_INDEX_HTML)
    code = match_set_code(sets=sets, release_date=date(2023, 9, 22), set_name="151")
    assert code == "MEW"


def test_match_set_code_returns_none_without_a_reliable_match():
    sets = parse_sets_index(SETS_INDEX_HTML)
    # Ni la date ni le nom ne correspondent à une extension connue : jamais une extension
    # "probable" (mission : "ne jamais inventer un résultat de tournoi").
    code = match_set_code(sets=sets, release_date=date(1999, 1, 1), set_name="Extension inconnue")
    assert code is None


def test_match_set_code_falls_back_to_name_when_no_release_date_is_known():
    sets = parse_sets_index(SETS_INDEX_HTML)
    code = match_set_code(sets=sets, release_date=None, set_name="Obsidian Flames")
    assert code == "OBF"


class _FakeTransport:
    def __init__(self, html_by_path: dict[str, str], status_by_path: dict[str, int] | None = None):
        self._html_by_path = html_by_path
        self._status_by_path = status_by_path or {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        status = self._status_by_path.get(path, 200 if path in self._html_by_path else 404)
        return httpx.Response(status, text=self._html_by_path.get(path, ""))


def _client_with(html_by_path: dict[str, str], status_by_path: dict[str, int] | None = None):
    transport = httpx.MockTransport(_FakeTransport(html_by_path, status_by_path))
    return LimitlessTcgClient(http_client=httpx.AsyncClient(transport=transport))


async def test_fetch_card_page_returns_none_on_404():
    client = _client_with({})
    page = await client.fetch_card_page("MEW", "9999")
    assert page is None


async def test_fetch_card_page_raises_on_block():
    client = _client_with({}, status_by_path={"/cards/MEW/6": 403})
    with pytest.raises(LimitlessBlockedError):
        await client.fetch_card_page("MEW", "6")


async def test_find_card_page_returns_verified_match():
    client = _client_with({"/cards/MEW/6": CARD_PAGE_WITH_DECKLISTS_HTML})
    sets = parse_sets_index(SETS_INDEX_HTML)

    found = await find_card_page(
        client,
        sets=sets,
        set_release_date=date(2023, 9, 22),
        set_name="151",
        card_number="006",
        expected_en_name="Charizard ex",
    )

    assert found is not None
    url, html_page = found
    assert url == "https://limitlesstcg.com/cards/MEW/6"
    assert html_page == CARD_PAGE_WITH_DECKLISTS_HTML


async def test_find_card_page_rejects_a_name_mismatch():
    """Défense en profondeur (mission : "ne jamais inventer un résultat de tournoi") : même une
    extension et un numéro correctement rapprochés ne suffisent pas si le nom affiché sur la
    page Limitless ne correspond pas à la carte attendue — sans cette vérification, un décalage
    de catalogue afficherait la présence en tournoi d'une autre carte."""
    client = _client_with({"/cards/MEW/6": CARD_PAGE_WITH_DECKLISTS_HTML})
    sets = parse_sets_index(SETS_INDEX_HTML)

    found = await find_card_page(
        client,
        sets=sets,
        set_release_date=date(2023, 9, 22),
        set_name="151",
        card_number="006",
        expected_en_name="Pikachu",
    )

    assert found is None


async def test_find_card_page_returns_none_when_set_cannot_be_matched():
    client = _client_with({"/cards/MEW/6": CARD_PAGE_WITH_DECKLISTS_HTML})
    found = await find_card_page(
        client,
        sets=[],
        set_release_date=date(2023, 9, 22),
        set_name="151",
        card_number="006",
        expected_en_name="Charizard ex",
    )
    assert found is None
