"""Import du catalogue — TCGdex et Pokémon TCG API sont remplacés par des doublures fidèles à la
forme réelle des réponses (capturée le 2026-09-19, voir compte rendu) : ces tests ne dépendent
d'aucun réseau et ne sont jamais flaky à cause d'une API tierce.

`test_import_catalogue_creates_sets_cards_and_names` échoue sans ce lot (aucune des colonnes
tcgdex_id/ptcg_id/illustrator/attacks/abilities/legal_* n'existe avant la migration) et passe avec.
"""

from sqlalchemy import select

from pbm_api.catalog.import_service import import_catalogue
from pbm_api.catalog.ptcg_client import PtcgUnavailableError
from pbm_api.models import Card, CardName, Set

FR_SET_DETAIL = {
    "id": "sv03.5",
    "name": "151",
    "serie": {"id": "sv", "name": "Écarlate et Violet"},
    "releaseDate": "2023-09-22",
    "cardCount": {"official": 165, "total": 207},
    "symbol": "https://assets.tcgdex.net/univ/sv/sv03.5/symbol",
    "logo": "https://assets.tcgdex.net/fr/sv/sv03.5/logo",
    "cards": [
        {"id": "sv03.5-006", "localId": "006", "name": "Dracaufeu-ex", "image": "https://x/006"},
        {"id": "sv03.5-025", "localId": "025", "name": "Pikachu", "image": "https://x/025"},
    ],
}

EN_SET_DETAIL = {
    **FR_SET_DETAIL,
    "cards": [
        {"id": "sv03.5-006", "localId": "006", "name": "Charizard ex", "image": "https://x/006"},
        {"id": "sv03.5-025", "localId": "025", "name": "Pikachu", "image": "https://x/025"},
    ],
}

FR_CARD_DETAILS = {
    "sv03.5-006": {
        "id": "sv03.5-006",
        "localId": "006",
        "name": "Dracaufeu-ex",
        "image": "https://assets.tcgdex.net/fr/sv/sv03.5/006",
        "rarity": "Double rare",
        "category": "Pokemon",
        "hp": 330,
        "illustrator": "PLANETA Mochizuki",
        "attacks": [{"name": "Vortex Explosif", "damage": 330}],
        "abilities": None,
        "legal": {"standard": False, "expanded": True},
    },
    "sv03.5-025": {
        "id": "sv03.5-025",
        "localId": "025",
        "name": "Pikachu",
        "image": "https://assets.tcgdex.net/fr/sv/sv03.5/025",
        "rarity": "Common",
        "category": "Pokemon",
        "hp": 60,
        "illustrator": "Someone",
        "attacks": [{"name": "Éclair", "damage": 20}],
        "abilities": None,
        "legal": {"standard": False, "expanded": True},
    },
}

PTCG_SETS = [{"id": "sv3pt5", "name": "151"}]
PTCG_CARDS_IN_SET = [
    {"id": "sv3pt5-6", "number": "6"},
    {"id": "sv3pt5-25", "number": "25"},
]


class FakeTcgdexClient:
    def __init__(self):
        self.card_calls: list[str] = []

    async def list_sets(self, lang: str) -> list[dict]:
        return [{"id": "sv03.5", "name": "151", "cardCount": {"total": 207, "official": 165}}]

    async def get_set(self, lang: str, set_id: str) -> dict:
        assert set_id == "sv03.5"
        return FR_SET_DETAIL if lang == "fr" else EN_SET_DETAIL

    async def get_card(self, lang: str, card_id: str) -> dict:
        self.card_calls.append(card_id)
        return FR_CARD_DETAILS[card_id]


class FailingCardTcgdexClient(FakeTcgdexClient):
    async def get_card(self, lang: str, card_id: str) -> dict:
        if card_id == "sv03.5-025":
            raise RuntimeError("panne simulée TCGdex")
        return await super().get_card(lang, card_id)


class FakePtcgClient:
    async def list_sets(self) -> list[dict]:
        return PTCG_SETS

    async def list_cards_in_set(self, ptcg_set_id: str) -> list[dict]:
        assert ptcg_set_id == "sv3pt5"
        return PTCG_CARDS_IN_SET


class UnavailablePtcgClient:
    async def list_sets(self) -> list[dict]:
        raise PtcgUnavailableError("Pokémon TCG API indisponible après 3 tentatives (500)")


async def test_import_catalogue_creates_sets_cards_and_names(db_session):
    report = await import_catalogue(
        db_session, FakeTcgdexClient(), FakePtcgClient(), languages=("fr", "en")
    )

    assert report["sets_created"] == 1
    assert report["cards_created"] == 2
    assert report["errors"] == []

    set_row = (await db_session.execute(select(Set).where(Set.tcgdex_id == "sv03.5"))).scalar_one()
    assert set_row.name == "151"
    assert set_row.series == "Écarlate et Violet"
    assert set_row.total_cards == 165

    card = (
        await db_session.execute(select(Card).where(Card.tcgdex_id == "sv03.5-006"))
    ).scalar_one()
    assert card.name == "Dracaufeu-ex"
    assert card.illustrator == "PLANETA Mochizuki"
    assert card.attacks == [{"name": "Vortex Explosif", "damage": 330}]
    assert card.legal_expanded is True
    assert card.legal_standard is False
    assert card.ptcg_id == "sv3pt5-6"

    names = (
        await db_session.execute(select(CardName).where(CardName.card_id == card.id))
    ).scalars().all()
    names_by_lang = {n.language: n.name for n in names}
    assert names_by_lang == {"fr": "Dracaufeu-ex", "en": "Charizard ex"}


async def test_import_catalogue_is_idempotent(db_session):
    tcgdex = FakeTcgdexClient()
    await import_catalogue(db_session, tcgdex, FakePtcgClient(), languages=("fr", "en"))
    report_two = await import_catalogue(
        db_session, tcgdex, FakePtcgClient(), languages=("fr", "en")
    )

    assert report_two["sets_created"] == 0
    assert report_two["sets_updated"] == 1
    assert report_two["cards_created"] == 0
    assert report_two["cards_updated"] == 2

    all_sets = (await db_session.execute(select(Set))).scalars().all()
    all_cards = (await db_session.execute(select(Card))).scalars().all()
    assert len(all_sets) == 1
    assert len(all_cards) == 2


async def test_import_catalogue_degrades_when_ptcg_unavailable(db_session):
    report = await import_catalogue(
        db_session, FakeTcgdexClient(), UnavailablePtcgClient(), languages=("fr", "en")
    )

    assert report["cards_created"] == 2
    assert "indisponible" in report["ptcg_reconciliation"]
    card = (
        await db_session.execute(select(Card).where(Card.tcgdex_id == "sv03.5-006"))
    ).scalar_one()
    assert card.ptcg_id is None


async def test_import_catalogue_continues_after_a_card_failure(db_session):
    report = await import_catalogue(
        db_session, FailingCardTcgdexClient(), FakePtcgClient(), languages=("fr", "en")
    )

    assert report["cards_created"] == 1
    assert len(report["errors"]) == 1
    assert "sv03.5-025" in report["errors"][0]

    ok_card = (
        await db_session.execute(select(Card).where(Card.tcgdex_id == "sv03.5-006"))
    ).scalar_one_or_none()
    assert ok_card is not None
    missing_card = (
        await db_session.execute(select(Card).where(Card.tcgdex_id == "sv03.5-025"))
    ).scalar_one_or_none()
    assert missing_card is None


async def test_import_catalogue_incremental_skips_known_sets(db_session):
    tcgdex = FakeTcgdexClient()
    await import_catalogue(db_session, tcgdex, FakePtcgClient(), languages=("fr", "en"))

    report = await import_catalogue(
        db_session, tcgdex, FakePtcgClient(), languages=("fr", "en"), mode="incremental"
    )
    assert report["sets_seen"] == 0
    assert report["cards_created"] == 0
