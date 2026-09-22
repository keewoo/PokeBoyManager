"""`/me/decks/{id}/stats` — agrégats chiffrés d'un deck (mission `v7-decks-stats`).

Trois niveaux : la logique pure (`stats.compute`) sur un deck connu, la route (forme + valeurs),
et l'accès croisé (le deck de A renvoie 404 à B). Le test de route échoue sans l'endpoint (404)
et passe avec — la garde « un test qui mord » exigée par le lot.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import httpx

from pbm_api.config import settings
from pbm_api.decks import stats
from pbm_api.models import Card, CardPriceDaily, PriceSource, PriceVariant, Set
from pbm_api.models.collection import CollectionItem
from pbm_api.security.csrf import CSRF_HEADER_NAME

PASSWORD = "correct horse battery staple"


def _unique_email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@example.com"


async def _register_verify_login(client: httpx.AsyncClient, email: str) -> tuple[str, str]:
    import re

    response = await client.post(
        "/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "last_name": "Dresseur",
            "birth_date": "2000-01-01",
            "accept_terms": True,
        },
    )
    assert response.status_code == 202, response.text
    sent = client.email_sender.sent  # type: ignore[attr-defined]
    match = re.search(r"token=(\S+)", sent[-1]["body"])
    assert match
    await client.post("/auth/verify-email", json={"token": match.group(1)})
    login = await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    return login.json()["id"], client.cookies.get(settings.csrf_cookie_name)


def _csrf(token: str) -> dict[str, str]:
    return {CSRF_HEADER_NAME: token}


async def _make_card(
    db_session,
    *,
    name: str,
    supertype: str = "Pokémon",
    energy_type: str | None = None,
    stage: str | None = None,
    hp: int | None = None,
    element_type: str | None = None,
    attacks: list | None = None,
    rule_marker: str | None = None,
    number: str = "1",
) -> Card:
    set_row = Set(code=f"stats-{uuid.uuid4().hex[:8]}", name="Set stats", series="Série test")
    db_session.add(set_row)
    await db_session.flush()
    card = Card(
        set_id=set_row.id,
        number=number,
        name=name,
        supertype=supertype,
        energy_type=energy_type,
        stage=stage,
        hp=hp,
        element_type=element_type,
        attacks=attacks,
        rule_marker=rule_marker,
        legal_standard=True,
    )
    db_session.add(card)
    await db_session.flush()
    return card


async def _own(db_session, user_id: str, card: Card, count: int) -> None:
    db_session.add_all(
        CollectionItem(user_id=uuid.UUID(user_id), card_id=card.id) for _ in range(count)
    )
    await db_session.flush()


# --------------------------------------------------------------------------- logique pure
def _card(
    *, name, supertype="Pokémon", energy_type=None, stage=None, hp=None, element_type=None,
    attacks=None, rule_marker=None, quantity=1, price=None,
) -> stats.StatsCardInput:
    return stats.StatsCardInput(
        card_id=uuid.uuid4(),
        name=name,
        supertype=supertype,
        energy_type=energy_type,
        stage=stage,
        hp=hp,
        element_type=element_type,
        attacks=attacks,
        rule_marker=rule_marker,
        quantity=quantity,
        reference_price_eur=price,
    )


def test_compute_partitions_roles_and_counts_everything():
    cards = [
        # Un attaquant de base, Feu, PV 120, deux attaques (coûts 1 et 3), 4 exemplaires.
        _card(
            name="Salamèche",
            stage="Base",
            hp=120,
            element_type="fire",
            attacks=[{"cost": ["Fire"]}, {"cost": ["Fire", "Fire", "Colorless"]}],
            quantity=4,
        ),
        # Un mur (PV ≥ 200), Eau, niveau 2, une carte spéciale (rule_marker VMAX), 1 exemplaire.
        _card(
            name="Léviator VMAX",
            stage="VMAX",
            hp=320,
            element_type="water",
            attacks=[{"cost": ["Water", "Water"]}],
            rule_marker="VMAX",
            quantity=1,
        ),
        # Un Pokémon sans attaque (soutien via talent), Psy, niveau 1, 2 exemplaires.
        _card(name="Tarpaud", stage="Niveau 1", hp=90, element_type="psychic", quantity=2),
        # Un Dresseur → soutien, 3 exemplaires.
        _card(name="Banque Info", supertype="Dresseur", quantity=3),
        # Énergie de base → énergie, jamais un doublon ni une valeur, 6 exemplaires.
        _card(name="Énergie Feu", supertype="Énergie", energy_type="Normal", quantity=6),
        # Énergie spéciale → énergie ET carte spéciale, 2 exemplaires.
        _card(
            name="Énergie Double Incolore",
            supertype="Énergie",
            energy_type="Special",
            quantity=2,
        ),
    ]
    s = stats.compute(cards)

    assert s.card_count == 4 + 1 + 2 + 3 + 6 + 2
    assert s.distinct_cards == 6

    roles = {b.key: b.count for b in s.by_role}
    assert roles[stats.ROLE_ATTACKER] == 4  # Salamèche
    assert roles[stats.ROLE_WALL] == 1  # Léviator VMAX (PV ≥ 200)
    assert roles[stats.ROLE_SUPPORT] == 2 + 3  # Tarpaud (sans attaque) + Dresseur
    assert roles[stats.ROLE_ENERGY] == 6 + 2
    assert sum(roles.values()) == s.card_count  # partition exacte

    supertypes = {b.key: b.count for b in s.by_supertype}
    assert supertypes[stats.SUPERTYPE_POKEMON] == 4 + 1 + 2
    assert supertypes[stats.SUPERTYPE_TRAINER] == 3
    assert supertypes[stats.SUPERTYPE_ENERGY] == 6 + 2

    # Coûts : Salamèche 1 & 3 (×4), Léviator 2 (×1). Seaux "1"→4, "2"→1, "3"→4.
    curve = {b.key: b.count for b in s.attack_cost_curve}
    assert curve == {"1": 4, "2": 1, "3": 4}
    assert s.attacks_counted == 4 + 4 + 1

    # PV moyens pondérés : (120×4 + 320×1 + 90×2) / (4+1+2) = 980/7 = 140.0
    assert s.average_hp == 140.0
    assert s.pokemon_with_hp == 7

    types = {b.key: b.count for b in s.type_distribution}
    assert types == {"fire": 4, "water": 1, "psychic": 2}

    stages = {b.key: b.count for b in s.stage_distribution}
    assert stages[stats.STAGE_BASE] == 4
    assert stages[stats.STAGE_ONE] == 2
    assert stats.STAGE_TWO not in stages  # aucun Niveau 2 → seau non émis
    assert stages[stats.STAGE_OTHER] == 1  # VMAX
    assert s.has_basic_pokemon is True
    assert s.evolution_copies_without_base == 0

    # Cartes spéciales : Léviator VMAX (×1) + Énergie spéciale (×2) = 3.
    assert s.special_cards == 1 + 2


def test_compute_flags_evolutions_without_base_and_missing_prices():
    cards = [
        _card(name="Grahyèna", stage="Niveau 1", hp=90, element_type="darkness", quantity=2),
        _card(name="Dracaufeu", stage="Niveau 2", hp=170, element_type="fire", quantity=1),
    ]
    s = stats.compute(cards)
    assert s.has_basic_pokemon is False
    assert s.evolution_copies_without_base == 3  # aucun Pokémon de base sous ces évolutions
    # Aucun prix fourni : valeur inconnue, jamais 0.
    assert s.value.total_eur is None
    assert s.value.priced_cards == 0
    assert s.value.missing_price_cards == 2


def test_compute_value_and_duplicates_exclude_basic_energy():
    cards = [
        _card(name="Pikachu", stage="Base", hp=60, element_type="lightning", quantity=4,
              price=Decimal("2.50")),
        _card(name="Dresseur X", supertype="Dresseur", quantity=1, price=Decimal("1.00")),
        _card(name="Énergie Électrique", supertype="Énergie", energy_type="Normal", quantity=20),
    ]
    s = stats.compute(cards)
    # Valeur = 2.50×4 + 1.00×1 = 11.00 ; l'Énergie de base est hors valeur (fournie).
    assert s.value.total_eur == Decimal("11.00")
    assert s.value.priced_cards == 2
    assert s.value.priced_copies == 5
    assert s.value.counted_copies == 5  # 4 Pikachu + 1 Dresseur ; l'Énergie de base exclue
    # Doublons hors Énergie de base : Pikachu 4→3 doublons, Dresseur 1→0. 3/5 = 0.6.
    assert s.duplicate_copies == 3
    assert s.duplicate_ratio == 0.6


# --------------------------------------------------------------------------------- route
async def test_deck_stats_requires_authentication(api_client):
    assert (await api_client.get(f"/me/decks/{uuid.uuid4()}/stats")).status_code == 401


async def test_deck_stats_route_shape_and_values(api_client, db_session):
    user_id, csrf = await _register_verify_login(api_client, _unique_email("deck-stats"))
    attacker = await _make_card(
        db_session,
        name="Dracaufeu ex",
        stage="Base",
        hp=180,
        element_type="fire",
        attacks=[{"cost": ["Fire", "Fire"]}],
        rule_marker="ex",
        number="4",
    )
    await _own(db_session, user_id, attacker, 3)
    # Un relevé de prix cardmarket, variante normale — via la valorisation existante.
    db_session.add(
        CardPriceDaily(
            card_id=attacker.id,
            source=PriceSource.cardmarket,
            variant=PriceVariant.normal,
            day=datetime.now(UTC).date(),
            currency="EUR",
            price_trend=Decimal("10.00"),
        )
    )
    await db_session.flush()

    created = await api_client.post(
        "/me/decks",
        json={"name": "Deck stats", "cards": [{"card_id": str(attacker.id), "quantity": 3}]},
        headers=_csrf(csrf),
    )
    assert created.status_code == 201, created.text
    deck_id = created.json()["id"]

    response = await api_client.get(f"/me/decks/{deck_id}/stats")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["deck_id"] == deck_id
    assert body["card_count"] == 3
    assert body["distinct_cards"] == 1
    assert {b["key"]: b["count"] for b in body["by_role"]}[stats.ROLE_ATTACKER] == 3
    assert {b["key"]: b["count"] for b in body["by_supertype"]}[stats.SUPERTYPE_POKEMON] == 3
    assert {b["key"]: b["count"] for b in body["attack_cost_curve"]}["2"] == 3
    assert {b["key"]: b["count"] for b in body["type_distribution"]}["fire"] == 3
    assert body["average_hp"] == 180.0
    assert body["special_cards"] == 3  # rule_marker "ex"
    assert body["has_basic_pokemon"] is True
    # Valeur = 10.00 × 3 = 30.00, via le service de valorisation.
    assert body["value"]["total_eur"] == "30.00"
    assert body["value"]["priced_cards"] == 1


async def test_deck_stats_cross_access_returns_404(api_client, db_session):
    owner_id, owner_csrf = await _register_verify_login(api_client, _unique_email("stats-owner"))
    card = await _make_card(db_session, name="Ronflex", stage="Base", hp=140)
    await _own(db_session, owner_id, card, 2)
    created = await api_client.post(
        "/me/decks",
        json={"name": "Deck de A", "cards": [{"card_id": str(card.id), "quantity": 2}]},
        headers=_csrf(owner_csrf),
    )
    assert created.status_code == 201, created.text
    deck_id = created.json()["id"]

    # B se connecte et vise le deck de A : 404 (jamais 403, pas de fuite d'existence).
    await _register_verify_login(api_client, _unique_email("stats-other"))
    cross = await api_client.get(f"/me/decks/{deck_id}/stats")
    assert cross.status_code == 404, cross.text
