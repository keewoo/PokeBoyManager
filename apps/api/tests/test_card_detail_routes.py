"""Fiche carte (mission `v4-fiche`) : `GET /cards/{id}` (catalogue + prix + classement),
`GET /cards/{id}/price-history` (courbe de valeur par variante) et `GET /cards/{id}/my-items`
(exemplaires possédés, onglet « Mes exemplaires »), plus `GET /me/collection/{item}/photo`
(bascule « Ma photo » de l'en-tête). Avant ce lot, aucune de ces routes n'existait
(`404 Not Found`) : chaque test échoue sans elles et passe une fois branchées.
"""

import re
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx

from pbm_api.config import settings
from pbm_api.detection.annotate import encode_jpeg
from pbm_api.models import (
    Card,
    CardPriceDaily,
    Detection,
    DetectionStatus,
    PriceSource,
    PriceVariant,
    Set,
    Upload,
    UploadStatus,
)
from pbm_api.models.collection import CollectionItem
from pbm_api.models.pricing import ExchangeRateDaily
from pbm_api.ranking.service import refresh_card_value_rank
from pbm_api.s3 import ObjectStorage

TODAY = datetime.now(UTC).date()


def _unique_email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@example.com"


async def _register_verify_login(client: httpx.AsyncClient, email: str) -> tuple[str, str]:
    response = await client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "correct horse battery staple",
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
    login = await client.post(
        "/auth/login", json={"email": email, "password": "correct horse battery staple"}
    )
    assert login.status_code == 200, login.text
    return login.json()["id"], client.cookies.get(settings.csrf_cookie_name)


async def _make_card(
    db_session,
    *,
    number: str = "1",
    name: str = "Dracaufeu",
    rarity: str | None = "rare",
) -> tuple[Card, Set]:
    set_row = Set(
        code=f"fiche-{uuid.uuid4().hex[:8]}",
        name="Écarlate et Violet",
        series="Écarlate et Violet",
        release_date=date(2023, 3, 31),
        total_cards=198,
        logo_url="https://example.com/logo.png",
    )
    db_session.add(set_row)
    await db_session.flush()
    card = Card(set_id=set_row.id, number=number, name=name, rarity=rarity, supertype="Pokémon")
    db_session.add(card)
    await db_session.flush()
    return card, set_row


async def _add_price(
    db_session,
    card: Card,
    *,
    trend: Decimal,
    variant: PriceVariant = PriceVariant.normal,
    day: date = TODAY,
    source: PriceSource = PriceSource.cardmarket,
) -> None:
    db_session.add(
        CardPriceDaily(
            card_id=card.id,
            source=source,
            variant=variant,
            day=day,
            currency="EUR",
            price_low=trend,
            price_mid=trend,
            price_trend=trend,
        )
    )
    await db_session.flush()


async def _add_item(
    db_session,
    user_id: uuid.UUID,
    card: Card,
    *,
    variant: PriceVariant = PriceVariant.normal,
    condition_grade: str | None = None,
    detection_id: uuid.UUID | None = None,
    photo_s3_key: str | None = None,
    acquired_at: date | None = None,
    purchase_price: Decimal | None = None,
    purchase_currency: str | None = None,
) -> CollectionItem:
    item = CollectionItem(
        user_id=user_id,
        card_id=card.id,
        variant=variant,
        condition_grade=condition_grade,
        detection_id=detection_id,
        photo_s3_key=photo_s3_key,
        acquired_at=acquired_at,
        purchase_price=purchase_price,
        purchase_currency=purchase_currency,
    )
    db_session.add(item)
    await db_session.flush()
    return item


async def test_get_card_requires_authentication(api_client):
    response = await api_client.get(f"/cards/{uuid.uuid4()}")

    assert response.status_code == 401


async def test_get_card_returns_404_for_unknown_card(api_client, db_session):
    await _register_verify_login(api_client, _unique_email("fiche-404"))

    response = await api_client.get(f"/cards/{uuid.uuid4()}")

    assert response.status_code == 404


async def test_get_card_returns_catalog_price_and_ranking(api_client, db_session):
    user_id, _csrf = await _register_verify_login(api_client, _unique_email("fiche-detail"))
    card, set_row = await _make_card(db_session, name="Dracaufeu-EX")
    await _add_price(db_session, card, trend=Decimal("42"), day=TODAY)
    await refresh_card_value_rank(db_session)

    response = await api_client.get(f"/cards/{card.id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Dracaufeu-EX"
    assert body["set"]["name"] == "Écarlate et Violet"
    assert body["set"]["total_cards"] == 198
    assert body["prices_eur"]["normal"] == "42.00"
    assert body["prices_eur"]["holo"] is None
    assert body["ranking"]["rarity_rank"] == 1
    assert body["owned_count"] == 0
    assert body["collection_rank"] is None


async def test_get_card_exposes_element_type_for_the_replacement_visual(api_client, db_session):
    # Le visuel de remplacement (lot `pbm-carte-remplacement`) a besoin du type et des PV pour
    # composer la carte quand elle n'a pas d'image officielle.
    await _register_verify_login(api_client, _unique_email("fiche-element"))
    card, _set_row = await _make_card(db_session, name="Scarabrute")
    card.element_type = "grass"
    card.hp = 90
    await db_session.flush()

    response = await api_client.get(f"/cards/{card.id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["element_type"] == "grass"
    assert body["hp"] == 90
    assert body["has_image"] is False


async def test_get_card_exposes_collection_rank_for_the_best_owned_item(api_client, db_session):
    user_id, _csrf = await _register_verify_login(api_client, _unique_email("fiche-rank"))
    card, _set_row = await _make_card(db_session, name="Pikachu")
    await _add_price(db_session, card, trend=Decimal("10"))
    await _add_item(db_session, uuid.UUID(user_id), card)

    response = await api_client.get(f"/cards/{card.id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["owned_count"] == 1
    assert body["collection_rank"] == {"position": 1, "total_priced": 1}


async def test_price_history_filters_by_variant_and_range(api_client, db_session):
    await _register_verify_login(api_client, _unique_email("fiche-history"))
    card, _set_row = await _make_card(db_session, name="Mewtwo")
    await _add_price(db_session, card, trend=Decimal("5"), day=TODAY - timedelta(days=60))
    await _add_price(db_session, card, trend=Decimal("8"), day=TODAY - timedelta(days=10))
    await _add_price(db_session, card, trend=Decimal("20"), variant=PriceVariant.holo, day=TODAY)

    response = await api_client.get(
        f"/cards/{card.id}/price-history", params={"variant": "normal", "range": "30"}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    # Le relevé à -60 j est hors de la fenêtre de 30 j (mission point 2 : afficher honnêtement
    # une courbe courte plutôt que de la compléter) ; celui à -10 j y entre.
    assert len(body["points"]) == 1
    assert body["points"][0]["price_eur"] == "8.00"

    response_all = await api_client.get(
        f"/cards/{card.id}/price-history", params={"variant": "normal", "range": "all"}
    )
    assert len(response_all.json()["points"]) == 2


async def test_my_items_is_scoped_to_the_current_user(api_client, db_session):
    owner_id, _csrf_a = await _register_verify_login(api_client, _unique_email("fiche-owner"))
    card, _set_row = await _make_card(db_session, name="Ronflex")
    await _add_price(db_session, card, trend=Decimal("3"))
    await _add_item(
        db_session,
        uuid.UUID(owner_id),
        card,
        condition_grade="near_mint",
        acquired_at=TODAY,
    )

    response_owner = await api_client.get(f"/cards/{card.id}/my-items")
    assert response_owner.status_code == 200, response_owner.text
    assert len(response_owner.json()) == 1
    assert response_owner.json()[0]["value_eur"] == "2.7000"

    # Un autre utilisateur (même carte au catalogue partagé) ne voit jamais les exemplaires
    # d'un autre — même règle d'isolation que `GET /me/collection` (`CLAUDE.md`). Se réinscrire
    # sur le même client remplace le cookie de session, pas besoin d'un `/auth/logout` explicite
    # (même pattern que `tests/test_collection_routes.py`).
    await _register_verify_login(api_client, _unique_email("fiche-other"))
    response_other = await api_client.get(f"/cards/{card.id}/my-items")
    assert response_other.status_code == 200, response_other.text
    assert response_other.json() == []


async def test_my_items_exposes_condition_detail_from_linked_detection(api_client, db_session):
    user_id, _csrf = await _register_verify_login(api_client, _unique_email("fiche-condition"))
    card, _set_row = await _make_card(db_session, name="Léviator")

    upload = Upload(
        user_id=uuid.UUID(user_id),
        s3_key=f"uploads/{user_id}/{uuid.uuid4()}/original",
        status=UploadStatus.processed,
    )
    db_session.add(upload)
    await db_session.flush()
    detection = Detection(
        upload_id=upload.id,
        bbox={"x": 0, "y": 0, "w": 1, "h": 1},
        status=DetectionStatus.validated,
        condition_assessment={"overall_grade": "near_mint", "score_10": 9.0},
    )
    db_session.add(detection)
    await db_session.flush()
    await _add_item(
        db_session, uuid.UUID(user_id), card, detection_id=detection.id, condition_grade="near_mint"
    )

    response = await api_client.get(f"/cards/{card.id}/my-items")

    assert response.status_code == 200, response.text
    [item] = response.json()
    assert item["condition_detail"] == {"overall_grade": "near_mint", "score_10": 9.0}


async def test_my_items_converts_purchase_price_to_eur_for_the_plus_value(api_client, db_session):
    user_id, _csrf = await _register_verify_login(api_client, _unique_email("fiche-achat"))
    card, _set_row = await _make_card(db_session, name="Tortank")
    await _add_price(db_session, card, trend=Decimal("100"))
    db_session.add(
        ExchangeRateDaily(day=TODAY - timedelta(days=5), currency="USD", rate=Decimal("2"))
    )
    await db_session.flush()
    await _add_item(
        db_session,
        uuid.UUID(user_id),
        card,
        acquired_at=TODAY - timedelta(days=5),
        purchase_price=Decimal("40"),
        purchase_currency="USD",
    )

    response = await api_client.get(f"/cards/{card.id}/my-items")

    assert response.status_code == 200, response.text
    [item] = response.json()
    # 40 USD au taux de 2 USD pour 1 EUR (relevé BCE du jour d'achat) -> 20 EUR, jamais celui du
    # jour de lecture : ce qui a été payé ne change pas rétroactivement avec le taux d'aujourd'hui.
    assert item["purchase_price_eur"] == "20.000000"
    assert item["value_eur"] == "90.0000"


async def test_item_photo_requires_a_stored_photo(api_client, db_session):
    user_id, _csrf = await _register_verify_login(api_client, _unique_email("fiche-nophoto"))
    card, _set_row = await _make_card(db_session, name="Roucool")
    item = await _add_item(db_session, uuid.UUID(user_id), card)

    response = await api_client.get(f"/me/collection/{item.id}/photo")

    assert response.status_code == 404


async def test_item_photo_serves_the_owners_photo_and_hides_it_from_others(api_client, db_session):
    user_id, _csrf = await _register_verify_login(api_client, _unique_email("fiche-photo"))
    card, _set_row = await _make_card(db_session, name="Carapuce")
    photo_key = f"collection/{uuid.uuid4()}.jpg"
    photo_bytes = encode_jpeg_placeholder()
    storage = ObjectStorage()
    await storage.ensure_bucket()
    await storage.put(photo_key, photo_bytes, "image/jpeg")
    item = await _add_item(db_session, uuid.UUID(user_id), card, photo_s3_key=photo_key)

    response = await api_client.get(f"/me/collection/{item.id}/photo")
    assert response.status_code == 200
    assert response.content == photo_bytes

    await _register_verify_login(api_client, _unique_email("fiche-photo-other"))
    other_response = await api_client.get(f"/me/collection/{item.id}/photo")
    assert other_response.status_code == 404


def encode_jpeg_placeholder() -> bytes:
    import numpy as np

    image = np.zeros((88, 63, 3), dtype=np.uint8)
    image[:] = (10, 20, 30)
    return encode_jpeg(image)
