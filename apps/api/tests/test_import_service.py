"""Import du catalogue — TCGdex et Pokémon TCG API sont remplacés par des doublures fidèles à la
forme réelle des réponses (capturée le 2026-09-19, voir compte rendu) : ces tests ne dépendent
d'aucun réseau et ne sont jamais flaky à cause d'une API tierce.

`test_import_catalogue_creates_sets_cards_and_names` échoue sans ce lot (aucune des colonnes
tcgdex_id/ptcg_id/illustrator/attacks/abilities/legal_* n'existe avant la migration) et passe avec.

`test_import_catalogue_fills_completeness_fields` échoue sans le lot `v2-catalogue-complet`
(colonnes weaknesses/resistances/retreat_cost/rule_suffix/variants inexistantes avant sa
migration `b671eb503fa3`) et passe avec.
"""

import pytest
from sqlalchemy import select

from pbm_api.catalog.import_service import (
    _card_number,
    _is_safe_image_url,
    _rule_marker,
    import_catalogue,
)
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
        "weaknesses": [{"type": "Eau", "value": "×2"}],
        "resistances": [{"type": "Combat", "value": "-30"}],
        "retreat": 2,
        "stage": "Niveau 2",
        "suffix": "ex",
        "variants": {
            "firstEdition": False,
            "holo": True,
            "normal": False,
            "reverse": False,
            "wPromo": False,
        },
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


class MissingSecondaryLangTcgdexClient(FakeTcgdexClient):
    """Simule une extension sans édition anglaise (ex. `2013bw`, `2018sm-fr` : constaté le
    2026-09-19, 404 permanent sur TCGdex — pas une panne réseau)."""

    async def get_set(self, lang: str, set_id: str) -> dict:
        if lang == "en":
            raise RuntimeError("404 Not Found")
        return await super().get_set(lang, set_id)


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


async def test_import_catalogue_fills_completeness_fields(db_session):
    await import_catalogue(
        db_session, FakeTcgdexClient(), FakePtcgClient(), languages=("fr", "en")
    )

    card = (
        await db_session.execute(select(Card).where(Card.tcgdex_id == "sv03.5-006"))
    ).scalar_one()
    assert card.weaknesses == [{"type": "Eau", "value": "×2"}]
    assert card.resistances == [{"type": "Combat", "value": "-30"}]
    assert card.retreat_cost == 2
    assert card.rule_marker == "ex"
    assert card.variants == {
        "firstEdition": False,
        "holo": True,
        "normal": False,
        "reverse": False,
        "wPromo": False,
    }

    # Pikachu (fixture sans weaknesses/resistances/retreat/suffix) : jamais une exception,
    # les colonnes restent nulles plutôt qu'une valeur inventée.
    other = (
        await db_session.execute(select(Card).where(Card.tcgdex_id == "sv03.5-025"))
    ).scalar_one()
    assert other.weaknesses is None
    assert other.rule_marker is None


def test_rule_marker_uses_stage_when_no_suffix():
    """VMAX/VSTAR n'ont pas de `suffix` chez TCGdex, la règle est portée par `stage` seul
    (constaté en direct le 2026-09-19 sur `swsh4-21`, Astronelle VMAX)."""
    assert _rule_marker({"suffix": None, "stage": "VMAX"}) == "VMAX"
    assert _rule_marker({"suffix": "ex", "stage": "Niveau 2"}) == "ex"
    assert _rule_marker({"suffix": None, "stage": "Base"}) is None
    assert _rule_marker({"suffix": None, "stage": None}) is None


def test_is_safe_image_url_accepts_https_domain_names():
    """La forme réelle (`assets.tcgdex.net`) et celle des doublures de test (`https://x/...`,
    voir `FR_SET_DETAIL` ci-dessus) doivent toutes deux passer : seuls schéma et IP littérale
    sont contrôlés, pas un domaine précis (mission `v5-securite`, SSRF en défense en
    profondeur)."""
    assert _is_safe_image_url("https://assets.tcgdex.net/fr/sv/sv03.5/006") is True
    assert _is_safe_image_url("https://x/006") is True


def test_is_safe_image_url_rejects_non_https_schemes():
    assert _is_safe_image_url("http://assets.tcgdex.net/fr/sv/sv03.5/006") is False
    assert _is_safe_image_url("file:///etc/passwd") is False
    assert _is_safe_image_url("ftp://assets.tcgdex.net/006") is False


def test_is_safe_image_url_rejects_private_and_link_local_and_loopback_ips():
    """Le trio classique d'une cible SSRF interne : métadonnées cloud (lien-local), boucle
    locale, réseau privé."""
    assert _is_safe_image_url("https://169.254.169.254/latest/meta-data") is False
    assert _is_safe_image_url("https://127.0.0.1/006") is False
    assert _is_safe_image_url("https://10.0.0.5/006") is False


def test_is_safe_image_url_rejects_url_without_host():
    assert _is_safe_image_url("https:///006") is False


class PoisonedImageUrlTcgdexClient(FakeTcgdexClient):
    """Simule une réponse TCGdex compromise dont `image` pointerait vers le réseau interne."""

    async def get_card(self, lang: str, card_id: str) -> dict:
        detail = await super().get_card(lang, card_id)
        if card_id == "sv03.5-006":
            detail = {**detail, "image": "https://169.254.169.254/006"}
        return detail


async def test_import_catalogue_rejects_a_card_image_url_pointing_at_a_private_ip(db_session):
    """Bout en bout (mission `v5-securite` point 2) : une réponse TCGdex compromise qui
    pointerait `image` vers le réseau interne n'est jamais stockée telle quelle — la carte est
    importée sans image plutôt qu'avec une URL que `GET /img/cards/{id}` irait interroger
    côté serveur."""
    await import_catalogue(db_session, PoisonedImageUrlTcgdexClient(), FakePtcgClient())

    result = await db_session.execute(select(Card).where(Card.tcgdex_id == "sv03.5-006"))
    card = result.scalar_one()
    assert card.image_url is None


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


async def test_import_catalogue_keeps_primary_lang_when_secondary_missing(db_session):
    report = await import_catalogue(
        db_session,
        MissingSecondaryLangTcgdexClient(),
        FakePtcgClient(),
        languages=("fr", "en"),
    )

    assert report["cards_created"] == 2
    assert any("pas d'édition 'en'" in e for e in report["errors"])
    card = (
        await db_session.execute(select(Card).where(Card.tcgdex_id == "sv03.5-006"))
    ).scalar_one()
    assert card is not None
    en_name = (
        await db_session.execute(
            select(CardName).where(CardName.card_id == card.id, CardName.language == "en")
        )
    ).scalar_one_or_none()
    assert en_name is None


async def test_import_catalogue_set_ids_filters_to_targeted_sets(db_session):
    """Reprise ciblée (`import_full_catalogue.py <sets>`) : sert à relancer seulement les
    extensions restées en échec après un import complet, sans retraiter les ~200 autres."""
    report = await import_catalogue(
        db_session,
        FakeTcgdexClient(),
        FakePtcgClient(),
        languages=("fr", "en"),
        set_ids=["sv03.5"],
    )
    assert report["sets_seen"] == 1
    assert report["cards_created"] == 2

    report_no_match = await import_catalogue(
        db_session,
        FakeTcgdexClient(),
        FakePtcgClient(),
        languages=("fr", "en"),
        set_ids=["autre-extension"],
    )
    assert report_no_match["sets_seen"] == 0
    assert report_no_match["cards_created"] == 0


async def test_import_catalogue_incremental_skips_known_sets(db_session):
    tcgdex = FakeTcgdexClient()
    await import_catalogue(db_session, tcgdex, FakePtcgClient(), languages=("fr", "en"))

    report = await import_catalogue(
        db_session, tcgdex, FakePtcgClient(), languages=("fr", "en"), mode="incremental"
    )
    assert report["sets_seen"] == 0
    assert report["cards_created"] == 0


# --- Repli de langue (2026-09-22) -------------------------------------------------------------
# TCGdex-fr est incomplet : 202 extensions / 22 170 cartes contre 220 / 23 736 en anglais. Les
# doublures ci-dessous reproduisent les deux formes du manque, mesurées ce jour-là sur la PROD :
#   - une extension entière absente du catalogue fr (18 cas réels : Gym Heroes, Base Set 2...) ;
#   - une carte absente de l'édition fr d'une extension pourtant listée en fr (1 659 cas réels).

EN_ONLY_SET_SUMMARY = {
    "id": "gym1",
    "name": "Gym Heroes",
    "cardCount": {"total": 132, "official": 132},
}

EN_ONLY_SET_DETAIL = {
    "id": "gym1",
    "name": "Gym Heroes",
    "serie": {"id": "gym", "name": "Gym"},
    "releaseDate": "2000-08-14",
    "cardCount": {"official": 132, "total": 132},
    "symbol": "https://assets.tcgdex.net/univ/gym/gym1/symbol",
    "logo": "https://assets.tcgdex.net/en/gym/gym1/logo",
    "cards": [{"id": "gym1-1", "localId": "1", "name": "Blaine's Moltres", "image": "https://x/1"}],
}

EN_SET_DETAIL_WITH_EXTRA_CARD = {
    **FR_SET_DETAIL,
    "cards": [
        *EN_SET_DETAIL["cards"],
        {"id": "sv03.5-199", "localId": "199", "name": "Terapagos ex", "image": "https://x/199"},
    ],
}

EN_CARD_DETAILS = {
    "gym1-1": {
        "id": "gym1-1",
        "localId": "1",
        "name": "Blaine's Moltres",
        "image": "https://assets.tcgdex.net/en/gym/gym1/001",
        "rarity": "Rare Holo",
        "category": "Pokemon",
        "hp": 70,
        # Libellé anglais : sans les stades anglais dans ORDINARY_STAGES, "Basic" serait recopié
        # dans `rule_marker` et cette carte passerait pour une carte à règle spéciale.
        "stage": "Basic",
        "suffix": None,
        "legal": {"standard": False, "expanded": False},
    },
    "sv03.5-199": {
        "id": "sv03.5-199",
        "localId": "199",
        "name": "Terapagos ex",
        "image": "https://assets.tcgdex.net/en/sv/sv03.5/199",
        "rarity": "Special Illustration Rare",
        "category": "Pokemon",
        "hp": 230,
        "stage": "Basic",
        "suffix": "ex",
        "legal": {"standard": True, "expanded": True},
    },
}


class PartialFrenchTcgdexClient(FakeTcgdexClient):
    """TCGdex tel qu'il répond vraiment : le catalogue `fr` ne liste ni toutes les extensions,
    ni toutes les cartes des extensions qu'il liste."""

    def __init__(self):
        super().__init__()
        self.card_calls_by_lang: list[tuple[str, str]] = []

    async def list_sets(self, lang: str) -> list[dict]:
        fr_sets = await super().list_sets(lang)
        return fr_sets if lang == "fr" else [*fr_sets, EN_ONLY_SET_SUMMARY]

    async def get_set(self, lang: str, set_id: str) -> dict:
        if set_id == "gym1":
            if lang == "fr":
                raise RuntimeError("404 Not Found")
            return EN_ONLY_SET_DETAIL
        return FR_SET_DETAIL if lang == "fr" else EN_SET_DETAIL_WITH_EXTRA_CARD

    async def get_card(self, lang: str, card_id: str) -> dict:
        self.card_calls_by_lang.append((lang, card_id))
        if lang == "en":
            return EN_CARD_DETAILS[card_id]
        return FR_CARD_DETAILS[card_id]


class MuteTcgdexClient(FakeTcgdexClient):
    async def list_sets(self, lang: str) -> list[dict]:
        raise RuntimeError("TCGdex injoignable")


def test_rule_marker_accepts_ordinary_stages_in_both_languages():
    """Une carte tirée en anglais annonce "Basic"/"Stage 1" : ce sont des stades ordinaires, pas
    des règles spéciales. Sans ça le repli `fr` → `en` remplirait `rule_marker` à tort."""
    assert _rule_marker({"suffix": None, "stage": "Basic"}) is None
    assert _rule_marker({"suffix": None, "stage": "Stage 1"}) is None
    assert _rule_marker({"suffix": None, "stage": "Stage 2"}) is None
    assert _rule_marker({"suffix": None, "stage": "VMAX"}) == "VMAX"


def test_card_number_decodes_a_percent_encoded_local_id():
    """Le Zarbi « ? » de `exu` a `localId="%3F"` chez TCGdex : on stocke le numéro imprimé."""
    assert _card_number({"localId": "%3F"}) == "?"
    assert _card_number({"localId": "006"}) == "006"
    assert _card_number({"localId": "TG05"}) == "TG05"


async def test_import_catalogue_imports_a_set_absent_from_the_primary_language(db_session):
    tcgdex = PartialFrenchTcgdexClient()
    report = await import_catalogue(db_session, tcgdex, None, languages=("fr", "en"))

    gym = (
        await db_session.execute(select(Set).where(Set.tcgdex_id == "gym1"))
    ).scalar_one_or_none()
    assert gym is not None, "une extension listée en anglais seulement doit entrer en base"
    assert gym.name == "Gym Heroes"
    assert gym.series == "Gym"
    assert report["sets_seen"] == 2
    assert report["sets_by_source_language"] == {"fr": 1, "en": 1}


async def test_import_catalogue_imports_a_card_absent_from_the_primary_language(db_session):
    tcgdex = PartialFrenchTcgdexClient()
    report = await import_catalogue(db_session, tcgdex, None, languages=("fr", "en"))

    card = (
        await db_session.execute(select(Card).where(Card.tcgdex_id == "sv03.5-199"))
    ).scalar_one_or_none()
    assert card is not None, "une carte listée en anglais seulement doit entrer en base"
    assert card.name == "Terapagos ex"
    assert card.number == "199"
    # Le détail a bien été demandé en anglais, pas en français où la carte n'existe pas.
    assert ("en", "sv03.5-199") in tcgdex.card_calls_by_lang
    assert ("fr", "sv03.5-199") not in tcgdex.card_calls_by_lang

    # 2 cartes fr (sv03.5-006, sv03.5-025) + 2 cartes en (sv03.5-199, gym1-1)
    assert report["cards_created"] == 4
    assert report["cards_by_source_language"] == {"fr": 2, "en": 2}


async def test_import_catalogue_records_no_rule_marker_for_an_english_basic_card(db_session):
    """Garde-fou du repli : « Basic » est un stade ordinaire, pas une règle spéciale."""
    await import_catalogue(db_session, PartialFrenchTcgdexClient(), None, languages=("fr", "en"))

    card = (
        await db_session.execute(select(Card).where(Card.tcgdex_id == "gym1-1"))
    ).scalar_one()
    assert card.stage == "Basic"
    assert card.rule_marker is None


async def test_import_catalogue_names_an_english_sourced_card_in_english_only(db_session):
    await import_catalogue(db_session, PartialFrenchTcgdexClient(), None, languages=("fr", "en"))

    card = (
        await db_session.execute(select(Card).where(Card.tcgdex_id == "sv03.5-199"))
    ).scalar_one()
    names = (
        await db_session.execute(select(CardName).where(CardName.card_id == card.id))
    ).scalars().all()
    assert {n.language: n.name for n in names} == {"en": "Terapagos ex"}


async def test_import_catalogue_refuses_to_report_success_when_no_language_answers(db_session):
    """Un catalogue muet doit lever, pas rendre un rapport « 0 extension vue » indiscernable
    d'un catalogue déjà à jour (règle : un repli silencieux masque une panne)."""
    with pytest.raises(RuntimeError, match="aucune extension listée"):
        await import_catalogue(db_session, MuteTcgdexClient(), None, languages=("fr", "en"))
