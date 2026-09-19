"""Collecte de contexte pour les anecdotes — mission `v4-anecdotes` point 1.

Liste blanche fixe de deux domaines (API MediaWiki publique, sans clé) : les URLs de requête
sont toujours construites côté serveur à partir de `POKEPEDIA_API_URL`/`BULBAPEDIA_API_URL`
et d'un nom de carte/extension déjà connu de notre catalogue — jamais une URL fournie par
l'utilisateur. Une page introuvable ou un wiki injoignable renvoie `None`, jamais une
exception qui ferait échouer toute la génération (mission point 2 : mieux vaut moins
d'anecdotes que zéro par panne d'un seul wiki)."""

import httpx
from pydantic import BaseModel

POKEPEDIA_API_URL = "https://www.pokepedia.fr/api.php"
BULBAPEDIA_API_URL = "https://bulbapedia.bulbagarden.net/w/api.php"

_TIMEOUT_SECONDS = 10.0
# Texte brut envoyé au modèle par page — un extrait suffit très largement pour trois à cinq
# anecdotes, et limite le coût du prompt (mission point 2, appel unique par carte).
_EXTRACT_CHARS_LIMIT = 6000
# User-Agent identifié (mission `v4-insights-batch`, risque « débit raisonnable ») : les deux
# wikis sont des services communautaires sans clé, un agent générique masquerait qui les
# sollicite — utilisé ici et par la collecte à la demande (`pbm_api.insights.service`), qui
# partage cette même classe. Pas d'URL publique ni de contact ici : le projet n'a encore aucun
# domaine réel (D2/D8 hors périmètre, voir CLAUDE.md) — inventer une adresse serait plus trompeur
# pour les opérateurs de ces wikis qu'un simple nom de projet. ASCII strict : un en-tête HTTP
# n'accepte pas les caractères accentués (`UnicodeEncodeError` à la construction du client sinon).
_USER_AGENT = "PokeBoyManager/dev (private app in development, no public URL yet)"


class ContextPage(BaseModel):
    title: str
    source_url: str
    text: str


class MediaWikiClient:
    """Enveloppe fine autour de l'API MediaWiki (`action=query`) d'un wiki précis — l'URL de
    base est un argument du constructeur, jamais reçue depuis une requête entrante."""

    def __init__(self, api_url: str, http_client: httpx.AsyncClient | None = None) -> None:
        self._api_url = api_url
        self._client = http_client or httpx.AsyncClient(
            timeout=_TIMEOUT_SECONDS, headers={"User-Agent": _USER_AGENT}
        )
        self._owns_client = http_client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def fetch_page(self, query: str) -> ContextPage | None:
        """Cherche la page la plus pertinente pour `query`, renvoie son extrait en texte brut
        et son URL canonique — `None` si le wiki n'a rien de pertinent ou est injoignable."""
        try:
            title = await self._search_title(query)
            if title is None:
                return None
            return await self._fetch_extract(title)
        except (httpx.HTTPError, ValueError, KeyError):
            return None

    async def _search_title(self, query: str) -> str | None:
        response = await self._client.get(
            self._api_url,
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": 1,
                "format": "json",
            },
        )
        response.raise_for_status()
        results = response.json().get("query", {}).get("search", [])
        return results[0]["title"] if results else None

    async def _fetch_extract(self, title: str) -> ContextPage | None:
        response = await self._client.get(
            self._api_url,
            params={
                "action": "query",
                "prop": "extracts|info",
                "explaintext": 1,
                "titles": title,
                "inprop": "url",
                "format": "json",
            },
        )
        response.raise_for_status()
        pages = response.json().get("query", {}).get("pages", {})
        page = next(iter(pages.values()), None)
        if page is None or "missing" in page:
            return None
        extract = (page.get("extract") or "").strip()
        source_url = page.get("fullurl")
        if not extract or not source_url:
            return None
        return ContextPage(
            title=page.get("title", title),
            source_url=source_url,
            text=extract[:_EXTRACT_CHARS_LIMIT],
        )


async def collect_context(
    *,
    card_name: str,
    set_name: str,
    en_card_name: str,
    pokepedia_client: MediaWikiClient,
    bulbapedia_client: MediaWikiClient,
) -> list[ContextPage]:
    """Au mieux quatre pages (carte + extension, sur chacun des deux wikis) — dédupliquées par
    URL, une recherche en échec sur un wiki n'empêche pas les autres."""
    queries = [
        (pokepedia_client, card_name),
        (pokepedia_client, set_name),
        (bulbapedia_client, en_card_name),
        (bulbapedia_client, set_name),
    ]
    pages: list[ContextPage] = []
    seen_urls: set[str] = set()
    for client, query in queries:
        if not query:
            continue
        page = await client.fetch_page(query)
        if page is not None and page.source_url not in seen_urls:
            pages.append(page)
            seen_urls.add(page.source_url)
    return pages
