"""Construit l'index visuel de toutes les cartes (mission `v3-identification-visuelle` point 1) :
télécharge l'image officielle basse définition de chaque carte (FR et EN, déduction d'URL par
langue — `pbm_api.identification.visual_build.image_url_for_language`), calcule ses empreintes
(`pbm_api.identification.visual_build.compute_visual_hashes`) et les stocke dans
`card_visual_index`. Réutilise le même stockage objet que le proxy `/img/cards/{id}`
(`cards/{card_id}/{language}/low.webp`) : un utilisateur qui consulte ensuite l'image officielle
ne la retélécharge pas.

Idempotent et reprenable comme `scripts/import_full_catalogue.py` : une carte/langue déjà
indexée est sautée par défaut (`--refresh` la reconstruit tout de même) ; une carte en échec
(image manquante, réseau) est comptée en erreur et n'interrompt pas le reste.

Usage (réseau lent sur chimera, ~250 ko/s — `--limit` pour un essai, voir compte rendu) :
    DATABASE_URL=postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v3_identification_visuelle \
        uv run python scripts/build_visual_index.py --limit 300 --languages fr,en
"""

import argparse
import asyncio
import json
import time
import uuid
from datetime import UTC, datetime

import httpx
from sqlalchemy import select

from pbm_api.catalog.tcgdex_client import TcgdexClient
from pbm_api.db import async_session_factory
from pbm_api.identification.visual_build import (
    UndecodableImageError,
    image_url_for_language,
    upsert_visual_index_entry,
)
from pbm_api.models import Card
from pbm_api.models.identification import CardVisualIndex
from pbm_api.s3 import ObjectStorage

# Même ordre de grandeur que `catalog.import_service.TCGDEX_CARD_FETCH_CONCURRENCY` : purement
# réseau (téléchargement d'image), les upserts en base restent séquentiels.
FETCH_CONCURRENCY = 8


def _log(message: str) -> None:
    print(f"{datetime.now(UTC).isoformat()} {message}", flush=True)


async def _cards_missing_language(session, language: str, set_code: str | None) -> list[Card]:
    stmt = (
        select(Card)
        .where(
            Card.image_url.is_not(None),
            ~Card.id.in_(
                select(CardVisualIndex.card_id).where(CardVisualIndex.language == language)
            ),
        )
        .order_by(Card.id)
    )
    if set_code:
        from pbm_api.models import Set

        stmt = stmt.join(Set, Set.id == Card.set_id).where(Set.code == set_code)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _fetch_one(
    tcgdex: TcgdexClient,
    storage: ObjectStorage,
    semaphore: asyncio.Semaphore,
    card: Card,
    language: str,
) -> tuple[uuid.UUID, str, bytes | None, str | None, Exception | None]:
    async with semaphore:
        try:
            image_url = image_url_for_language(card.image_url, language)
            image_bytes = await tcgdex.fetch_image_bytes(image_url, "low")
        except Exception as exc:  # noqa: BLE001 — une image en échec ne doit pas arrêter le lot
            return card.id, language, None, None, exc

        object_key = f"cards/{card.id}/{language}/low.webp"
        try:
            await storage.put(object_key, image_bytes, "image/webp")
        except Exception as exc:  # noqa: BLE001 — le cache objet est un bonus, pas une condition
            _log(f"avertissement : mise en cache {object_key} échouée ({exc})")
            object_key = None
        return card.id, language, image_bytes, object_key, None


async def build_visual_index(
    *,
    languages: list[str],
    limit: int | None,
    set_code: str | None,
    refresh: bool,
) -> dict:
    report: dict = {
        "languages": languages,
        "requested_limit": limit,
        "indexed": 0,
        "skipped_already_indexed": 0,
        "errors": [],
    }
    start = time.monotonic()

    async with (
        httpx.AsyncClient(timeout=30.0) as tcgdex_http,
        async_session_factory() as session,
    ):
        tcgdex = TcgdexClient(http_client=tcgdex_http)
        storage = ObjectStorage()
        await storage.ensure_bucket()
        semaphore = asyncio.Semaphore(FETCH_CONCURRENCY)

        for language in languages:
            if refresh:
                result = await session.execute(
                    select(Card).where(Card.image_url.is_not(None)).order_by(Card.id)
                )
                candidates = list(result.scalars().all())
            else:
                candidates = await _cards_missing_language(session, language, set_code)
            if limit is not None:
                candidates = candidates[:limit]

            _log(f"langue {language} : {len(candidates)} carte(s) à traiter")
            batch = await asyncio.gather(
                *(
                    _fetch_one(tcgdex, storage, semaphore, card, language)
                    for card in candidates
                )
            )

            done = 0
            for card_id, lang, image_bytes, object_key, error in batch:
                if error is not None:
                    report["errors"].append(
                        {"card_id": str(card_id), "language": lang, "error": str(error)}
                    )
                    continue
                try:
                    await upsert_visual_index_entry(
                        session, card_id, lang, image_bytes, object_key
                    )
                    report["indexed"] += 1
                except UndecodableImageError as exc:
                    report["errors"].append(
                        {"card_id": str(card_id), "language": lang, "error": str(exc)}
                    )
                    continue
                done += 1
                if done % 100 == 0:
                    await session.commit()
                    elapsed = time.monotonic() - start
                    _log(f"  {language} : {done}/{len(candidates)} — écoulé {elapsed:.0f}s")
            await session.commit()

    report["duration_seconds"] = round(time.monotonic() - start, 1)
    return report


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--languages", default="fr,en", help="langues séparées par des virgules (défaut fr,en)"
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="borne le nombre de cartes par langue (essai)"
    )
    parser.add_argument("--set-code", default=None, help="ne traiter qu'une extension (code)")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="reconstruit même les cartes déjà indexées (défaut : les saute)",
    )
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()
    languages = [lang.strip() for lang in args.languages.split(",") if lang.strip()]
    _log(f"construction de l'index visuel démarrée (langues={languages}, limite={args.limit})")
    report = await build_visual_index(
        languages=languages, limit=args.limit, set_code=args.set_code, refresh=args.refresh
    )
    _log(
        f"terminé en {report['duration_seconds']}s — indexées={report['indexed']} "
        f"erreurs={len(report['errors'])}"
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
