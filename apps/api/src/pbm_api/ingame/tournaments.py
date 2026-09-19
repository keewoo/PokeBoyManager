"""Présence en tournoi — mission `v4-jeu` point 2, source publique Limitless TCG
(`limitlesstcg.com`, `robots.txt` vérifié le 2026-09-19 : `Disallow:` vide, aucune restriction).

Aucun identifiant stable partagé avec notre catalogue (TCGdex/Pokémon TCG API) : Limitless
utilise ses propres codes d'extension à 2-4 lettres (`MEW`, `OBF`...), absents de `Set`/`Card`.
Le rapprochement se fait sur la **date de sortie** de l'extension (`Set.release_date`, posée par
TCGdex à l'import comme la vraie date d'impression officielle — identique quelle que soit la
source), départagée par le nom normalisé en cas d'ambiguïté ; jamais par similarité de nom
seule (les noms d'extension sont en français côté catalogue, en anglais côté Limitless). Une
fois l'extension trouvée, la carte est vérifiée une seconde fois par son nom anglais affiché en
titre de la page — sans ces deux vérifications croisées, une carte homonyme d'une autre édition
afficherait la présence en tournoi d'une carte différente (risque de la mission : "ne jamais
inventer un résultat de tournoi", une association erronée serait pire qu'une absence de
donnée).

Résilient par construction : `find_card_page` ne renvoie qu'un résultat vérifié sans ambiguïté,
`None` dans tous les autres cas (extension non trouvée, carte hors bornes, nom qui ne
correspond pas) — jamais une carte "probable". Seul un blocage explicite du site
(`LimitlessBlockedError`, HTTP 403/429) interrompt le relevé plutôt que d'insister.
"""

import re
import unicodedata
from datetime import date, datetime
from html import unescape

import httpx
from pydantic import BaseModel

LIMITLESS_BASE_URL = "https://limitlesstcg.com"
_USER_AGENT = "PokeBoyManager/1.0 (+https://pokeboy.life; contact: contact@pokeboy.life)"
_TIMEOUT_SECONDS = 20.0
_DATE_FORMAT = "%d %b %y"

_SET_ROW_PATTERN = re.compile(
    r'<td><a href="/cards/(?P<code>[A-Za-z0-9]+)"><img[^>]*>\s*(?P<name>[^<]+?)\s*'
    r'<span class="code annotation">(?P=code)</span></a></td>\s*'
    r'<td><a href="/cards/(?P=code)">(?P<date>[^<]*)</a></td>'
)
_TITLE_PATTERN = re.compile(r"<title>([^<]+)</title>")
_TOURNAMENT_SECTION_PATTERN = re.compile(
    r'<div class="card-tournament-results">(.*?)</table>', re.DOTALL
)
_DECK_ROW_PATTERN = re.compile(
    r"<tr>\s*<td>(?:<img[^>]*>)*</td>\s*"
    r'<td><a href="(?P<deck_url>[^"]+)">(?P<deck_name>[^<]+)</a></td>\s*'
    r'<td><a href="(?P<tournament_url>[^"]+)">(?P<tournament_name>[^<]+)</a></td>\s*'
    r"<td>(?P<placement>[^<]+)</td>\s*</tr>"
)


class LimitlessSet(BaseModel):
    code: str
    name: str
    release_date: date | None


class TournamentDeck(BaseModel):
    deck_name: str
    tournament_name: str
    tournament_url: str | None
    placement: str


class LimitlessBlockedError(RuntimeError):
    """Le site a répondu 403/429 : on cesse d'insister plutôt que de risquer de se faire
    bannir — le relevé en cours s'arrête, la section reste masquée jusqu'au prochain essai."""


def _absolute_url(url: str) -> str:
    return url if url.startswith("http") else f"{LIMITLESS_BASE_URL}{url}"


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", without_accents.lower())


def normalize_card_number(number: str) -> str:
    """`Card.number` porte des zéros de bourrage ("006") hérités de TCGdex ; l'URL Limitless
    ne les a jamais ("6"). Un numéro non purement numérique (promos "TG05", "SWSH001") est
    transmis tel quel — s'il ne correspond à rien, `fetch_card_page` renverra `None`."""
    return str(int(number)) if number.isdigit() else number


def parse_sets_index(html_text: str) -> list[LimitlessSet]:
    sets: list[LimitlessSet] = []
    for match in _SET_ROW_PATTERN.finditer(html_text):
        date_str = match.group("date").strip()
        release_date: date | None = None
        if date_str:
            try:
                release_date = datetime.strptime(date_str, _DATE_FORMAT).date()
            except ValueError:
                release_date = None
        sets.append(
            LimitlessSet(
                code=match.group("code"),
                name=unescape(match.group("name")).strip(),
                release_date=release_date,
            )
        )
    return sets


def parse_card_title(html_text: str) -> str | None:
    match = _TITLE_PATTERN.search(html_text)
    if match is None:
        return None
    # "Charizard ex - Pokémon 151 (MEW) #6 – Limitless" -> "Charizard ex"
    return unescape(match.group(1)).split(" - ", 1)[0].strip()


def parse_decklists(html_text: str) -> list[TournamentDeck]:
    section_match = _TOURNAMENT_SECTION_PATTERN.search(html_text)
    if section_match is None:
        return []
    decks = []
    for match in _DECK_ROW_PATTERN.finditer(section_match.group(1)):
        decks.append(
            TournamentDeck(
                deck_name=unescape(match.group("deck_name")).strip(),
                tournament_name=unescape(match.group("tournament_name")).strip(),
                tournament_url=_absolute_url(match.group("tournament_url")),
                placement=match.group("placement").strip(),
            )
        )
    return decks


def match_set_code(
    *, sets: list[LimitlessSet], release_date: date | None, set_name: str
) -> str | None:
    """Une seule correspondance non ambiguë, sinon `None` — jamais une extension "probable"."""
    normalized_target = _normalize(set_name)
    if release_date is not None:
        by_date = [s for s in sets if s.release_date == release_date]
        if len(by_date) == 1:
            return by_date[0].code
        if len(by_date) > 1:
            by_name = [s for s in by_date if _normalize(s.name) == normalized_target]
            return by_name[0].code if len(by_name) == 1 else None
    by_name = [s for s in sets if _normalize(s.name) == normalized_target]
    return by_name[0].code if len(by_name) == 1 else None


class LimitlessTcgClient:
    """Enveloppe fine autour des pages HTML publiques de Limitless — pas d'API documentée,
    pas de clé (site public, `robots.txt` sans restriction)."""

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        self._client = http_client or httpx.AsyncClient(
            timeout=_TIMEOUT_SECONDS, headers={"User-Agent": _USER_AGENT}
        )
        self._owns_client = http_client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _raise_if_blocked(self, response: httpx.Response) -> None:
        if response.status_code in (403, 429):
            raise LimitlessBlockedError(f"HTTP {response.status_code} sur {response.request.url}")

    async def list_sets(self) -> list[LimitlessSet]:
        response = await self._client.get(f"{LIMITLESS_BASE_URL}/cards")
        self._raise_if_blocked(response)
        response.raise_for_status()
        return parse_sets_index(response.text)

    async def fetch_card_page(self, set_code: str, number: str) -> str | None:
        response = await self._client.get(f"{LIMITLESS_BASE_URL}/cards/{set_code}/{number}")
        if response.status_code == 404:
            return None
        self._raise_if_blocked(response)
        response.raise_for_status()
        return response.text


async def find_card_page(
    client: LimitlessTcgClient,
    *,
    sets: list[LimitlessSet],
    set_release_date: date | None,
    set_name: str,
    card_number: str,
    expected_en_name: str,
) -> tuple[str, str] | None:
    """`(url, html)` d'une page vérifiée, ou `None` — jamais un résultat probable."""
    set_code = match_set_code(sets=sets, release_date=set_release_date, set_name=set_name)
    if set_code is None:
        return None
    number = normalize_card_number(card_number)
    html_page = await client.fetch_card_page(set_code, number)
    if html_page is None:
        return None
    title_name = parse_card_title(html_page)
    if title_name is None or _normalize(title_name) != _normalize(expected_en_name):
        return None
    return f"{LIMITLESS_BASE_URL}/cards/{set_code}/{number}", html_page
