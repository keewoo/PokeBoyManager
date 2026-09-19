"""Collecte de contexte Poképédia/Bulbapedia (mission `v4-anecdotes` point 1) — liste blanche
fixe de domaines, résilience à un wiki muet ou en panne (aucune exception ne doit faire
échouer toute la génération, voir `pbm_api.insights.service`)."""

import httpx

from pbm_api.insights.context import (
    BULBAPEDIA_API_URL,
    POKEPEDIA_API_URL,
    MediaWikiClient,
    collect_context,
)


def test_allowed_domains_are_the_two_wikis_named_by_the_mission() -> None:
    assert POKEPEDIA_API_URL == "https://www.pokepedia.fr/api.php"
    assert BULBAPEDIA_API_URL == "https://bulbapedia.bulbagarden.net/w/api.php"


def _client_with(handler) -> MediaWikiClient:
    transport = httpx.MockTransport(handler)
    return MediaWikiClient(
        "https://example-wiki.test/api.php", http_client=httpx.AsyncClient(transport=transport)
    )


async def test_fetch_page_returns_none_when_search_has_no_result() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"query": {"search": []}})

    client = _client_with(handler)
    page = await client.fetch_page("carte inconnue")
    assert page is None


async def test_fetch_page_returns_none_on_server_error_instead_of_raising() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="indisponible")

    client = _client_with(handler)
    page = await client.fetch_page("carte")
    assert page is None


async def test_fetch_page_returns_the_extract_and_canonical_url() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("list") == "search":
            return httpx.Response(200, json={"query": {"search": [{"title": "Dracaufeu"}]}})
        return httpx.Response(
            200,
            json={
                "query": {
                    "pages": {
                        "1298": {
                            "title": "Dracaufeu",
                            "fullurl": "https://example-wiki.test/Dracaufeu",
                            "extract": "Dracaufeu est un Pokémon de type Feu/Vol.",
                        }
                    }
                }
            },
        )

    client = _client_with(handler)
    page = await client.fetch_page("Dracaufeu")
    assert page is not None
    assert page.title == "Dracaufeu"
    assert page.source_url == "https://example-wiki.test/Dracaufeu"
    assert page.text.startswith("Dracaufeu est un Pokémon")


async def test_collect_context_deduplicates_by_url_across_the_two_queries_per_wiki() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("list") == "search":
            return httpx.Response(200, json={"query": {"search": [{"title": "Page"}]}})
        return httpx.Response(
            200,
            json={
                "query": {
                    "pages": {
                        "1": {
                            "title": "Page",
                            "fullurl": "https://example-wiki.test/Page",
                            "extract": "Texte.",
                        }
                    }
                }
            },
        )

    same_client = _client_with(handler)
    pages = await collect_context(
        card_name="Carte",
        set_name="Extension",
        en_card_name="Card",
        pokepedia_client=same_client,
        bulbapedia_client=same_client,
    )
    # Les quatre requêtes (carte/extension x pokepedia/bulbapedia) pointent la même page ici :
    # une seule entrée doit survivre à la déduplication par URL.
    assert len(pages) == 1
    assert pages[0].source_url == "https://example-wiki.test/Page"


async def test_collect_context_skips_a_wiki_that_never_finds_anything() -> None:
    def empty_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"query": {"search": []}})

    def found_handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("list") == "search":
            return httpx.Response(200, json={"query": {"search": [{"title": "Page"}]}})
        return httpx.Response(
            200,
            json={
                "query": {
                    "pages": {
                        "1": {
                            "title": "Page",
                            "fullurl": "https://example-wiki.test/Page",
                            "extract": "Texte.",
                        }
                    }
                }
            },
        )

    pages = await collect_context(
        card_name="Carte",
        set_name="Extension",
        en_card_name="Card",
        pokepedia_client=_client_with(empty_handler),
        bulbapedia_client=_client_with(found_handler),
    )
    assert len(pages) == 1
    assert pages[0].source_url == "https://example-wiki.test/Page"
