"""Sème une carte possédée, avec historique de prix, état estimé, anecdotes et étude en jeu déjà
en cache, pour l'e2e Playwright de la fiche carte (lot `v4-fiche`,
`apps/web/e2e/card-detail.spec.ts`) : aucune clé IA réelle ni wiki réel disponible sur chimera
(voir `docs/ARCHITECTURE.md`), donc les caches partagés (`card_insights`,
`card_tournament_presence`) sont pré-remplis directement en base, comme
`seed_validation_e2e.py` le fait pour l'écran de validation — seule la fiche elle-même est
exercée par le navigateur, pas les pipelines de génération.

Usage :
    DATABASE_URL=postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v4_fiche_e2e \
        uv run python scripts/seed_card_fiche_e2e.py <email>

Affiche le `card_id` créé sur stdout (rien d'autre) pour être capturé par le test.
"""

import asyncio
import sys
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import numpy as np
from sqlalchemy import select

from pbm_api.db import async_session_factory
from pbm_api.detection.annotate import encode_jpeg
from pbm_api.models import (
    Card,
    CardInsight,
    CardPriceDaily,
    CardTournamentPresence,
    CollectionItem,
    Detection,
    DetectionStatus,
    PriceSource,
    PriceVariant,
    Set,
    TournamentPresenceStatus,
    Upload,
    UploadStatus,
    User,
)
from pbm_api.storage import build_storage

TODAY = datetime.now(UTC).date()


def _photo_bytes() -> bytes:
    image = np.zeros((880, 630, 3), dtype=np.uint8)
    image[:] = (40, 70, 150)
    return encode_jpeg(image)


async def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(1)
    email = sys.argv[1]

    async with async_session_factory() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one()

        suffix = uuid.uuid4().hex[:8]
        set_row = Set(
            code=f"e2e-fiche-{suffix}",
            name="Écarlate et Violet",
            series="Écarlate et Violet",
            release_date=date(2023, 3, 31),
            total_cards=198,
            logo_url=None,
        )
        session.add(set_row)
        await session.flush()

        card = Card(
            set_id=set_row.id,
            number="121",
            name="Dracaufeu-EX",
            rarity="rare secrète",
            supertype="Pokémon",
            hp=180,
            illustrator="Mitsuhiro Arita",
            image_url=None,  # Aucun réseau vers TCGdex sur chimera : la fiche affiche l'état
            # honnête "aucune image officielle" plutôt qu'une URL qui échouerait au premier
            # accès (voir `pbm_api.routers.images`).
            attacks=[
                {"name": "Cru-Aile", "damage": 60},
                {"name": "Explo-Combustion", "damage": 150},
            ],
            abilities=None,
            legal_standard=False,
            legal_expanded=True,
        )
        session.add(card)
        await session.flush()

        price_points = [(60, Decimal("38.00")), (30, Decimal("40.00")), (0, Decimal("42.50"))]
        for offset_days, trend in price_points:
            session.add(
                CardPriceDaily(
                    card_id=card.id,
                    source=PriceSource.cardmarket,
                    variant=PriceVariant.holo,
                    day=TODAY - timedelta(days=offset_days),
                    currency="EUR",
                    price_low=trend,
                    price_mid=trend,
                    price_trend=trend,
                )
            )

        storage = build_storage()
        await storage.ensure_bucket()

        upload = Upload(
            user_id=user.id,
            s3_key=f"uploads/{user.id}/{uuid.uuid4()}/original",
            original_filename="classeur-page-1.jpg",
            content_type="image/jpeg",
            size_bytes=1024,
            status=UploadStatus.processed,
        )
        session.add(upload)
        await session.flush()
        crop_key = f"uploads/{user.id}/{upload.id}/detections/0.jpg"
        photo_bytes = _photo_bytes()
        await storage.put(crop_key, photo_bytes, "image/jpeg")

        detection = Detection(
            upload_id=upload.id,
            bbox={"reading_order": 0, "points": []},
            crop_s3_key=crop_key,
            status=DetectionStatus.validated,
            selected_card_id=card.id,
            condition_assessment={
                "centering": {
                    "left_px": 40,
                    "right_px": 32,
                    "top_px": 28,
                    "bottom_px": 30,
                    "horizontal": {
                        "near_px": 32, "far_px": 40, "ratio": "56/44", "grade": "near_mint"
                    },
                    "vertical": {"near_px": 28, "far_px": 30, "ratio": "52/48", "grade": "mint"},
                    "grade": "near_mint",
                },
                "corners": {
                    "grade": "near_mint", "confidence": 0.82, "note": "un coin légèrement blanchi"
                },
                "edges": {"grade": "excellent", "confidence": 0.75, "note": None},
                "surface": {
                    "grade": "near_mint", "confidence": 0.6, "note": "photo à travers une pochette"
                },
                "overall_grade": "excellent",
                "overall_grade_label": "EX",
                "score_10": 8.0,
                "counterfeit_suspected": False,
                "counterfeit_reasons": [],
                "disclaimer": (
                    "Estimation indicative générée automatiquement (centrage mesuré + lecture IA "
                    "des coins, bords et surface) — ce n'est pas une gradation professionnelle."
                ),
            },
        )
        session.add(detection)
        await session.flush()

        session.add(
            CollectionItem(
                user_id=user.id,
                card_id=card.id,
                variant=PriceVariant.holo,
                language="fr",
                condition_grade="excellent",
                detection_id=detection.id,
                photo_s3_key=crop_key,
                acquired_at=TODAY - timedelta(days=30),
                purchase_price=Decimal("35.00"),
                purchase_currency="EUR",
            )
        )

        session.add(
            CardInsight(
                card_id=card.id,
                anecdotes=[
                    {
                        "text": (
                            "Distribuée en France dans les coffrets promotionnels de 2016 avec le "
                            "numéro XY121, elle reprend la pose de la version « Méga » sortie la "
                            "même année."
                        ),
                        "source_url": "https://www.pokepedia.fr/exemple",
                    },
                    {
                        "text": (
                            "L'attaque Explo-Combustion inflige 150 dégâts mais bloque la carte au "
                            "tour suivant : un compromis typique des EX de l'ère XY."
                        ),
                        "source_url": "https://bulbapedia.bulbagarden.net/exemple",
                    },
                ],
                in_game_study=(
                    "Quatre Énergies pour 150 dégâts une fois sur deux : trop lent face aux decks "
                    "Étendu actuels. Absente des decks de tournoi relevés ces 6 derniers mois. "
                    "Pièce de collection avant tout."
                ),
                generated_at=datetime.now(UTC).replace(tzinfo=None),
                cached_until=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=365),
                game_study_generated_at=datetime.now(UTC).replace(tzinfo=None),
                game_study_cached_until=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30),
            )
        )

        session.add(
            CardTournamentPresence(
                card_id=card.id,
                status=TournamentPresenceStatus.checked,
                source_url="https://limitlesstcg.com/exemple",
                decks=[],
                checked_at=datetime.now(UTC).replace(tzinfo=None),
            )
        )

        await session.commit()
        print(str(card.id))


if __name__ == "__main__":
    asyncio.run(main())
