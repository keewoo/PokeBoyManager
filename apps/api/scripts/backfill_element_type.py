"""Backfill de `cards.element_type` pour les cartes sans image (lot `pbm-carte-remplacement`).

Pourquoi un backfill dédié, et pas l'import : la base de référence catalogue de la flotte
(`pbm_catalogue_ref`) est restée à un alembic ancien (sans `element_type`), et
`infra/fleet/export_cards.sql` ne transporte donc pas la colonne. En attendant qu'elle soit
remise à `head`, ce script peuple `element_type` **directement dans la base pointée par
`DATABASE_URL`**, pour les seules cartes qui affichent le visuel de remplacement — celles sans
image officielle. TCGdex expose `types` même pour ces cartes : c'est ce qui rend leur type
récupérable.

Sûr et rejouable :
  - ne touche QUE des lignes où `element_type IS NULL` (idempotent : un second passage ne refait
    que les cartes encore vides, p. ex. celles dont TCGdex était muet au tour précédent) ;
  - additif : n'écrit que `element_type`, jamais rien d'autre ;
  - un échec TCGdex sur une carte n'arrête pas le backfill mais est COMPTÉ et affiché — pas de
    repli silencieux : le rapport final distingue mises à jour, « TCGdex sans type » et erreurs.

Usage :
    DATABASE_URL=postgresql+asyncpg://... uv run python scripts/backfill_element_type.py
    DATABASE_URL=... uv run python scripts/backfill_element_type.py --dry-run
    DATABASE_URL=... uv run python scripts/backfill_element_type.py --limit 50   # essai borné
"""

import argparse
import asyncio
import sys
import time
from datetime import UTC, datetime

import httpx
from sqlalchemy import select, update

from pbm_api.catalog.element_type import element_code
from pbm_api.catalog.tcgdex_client import TcgdexClient
from pbm_api.db import async_session_factory
from pbm_api.models import Card

# Même ordre de grandeur que l'import complet — tient sur le lien à ~250 ko/s de chimera, mais ce
# backfill tourne en principe depuis devAI (lien rapide), voir le rapport du lot.
FETCH_CONCURRENCY = 8
# Langues d'interrogation, la primaire d'abord — comme l'import. `element_code` accepte les
# libellés FR ("Plante") comme EN ("Grass") : l'ordre ne change que la langue interrogée en premier.
LANGUAGES = ("fr", "en")


def _log(message: str) -> None:
    print(f"{datetime.now(UTC).isoformat()} {message}", flush=True)


async def _element_for(tcgdex: TcgdexClient, tcgdex_id: str) -> tuple[str | None, Exception | None]:
    """Type élémentaire normalisé pour une carte, en essayant les langues dans l'ordre.

    Renvoie `(code, None)` en cas de succès (le code peut être `None` si TCGdex ne donne aucun
    type exploitable), ou `(None, exc)` si TOUTES les langues ont échoué (réseau, 404) — la carte
    est alors comptée en erreur, pas silencieusement laissée pour un « sans type ».
    """
    last_exc: Exception | None = None
    saw_any_response = False
    for lang in LANGUAGES:
        try:
            detail = await tcgdex.get_card(lang, tcgdex_id)
        except Exception as exc:  # noqa: BLE001 — une langue muette ne doit pas arrêter le backfill
            last_exc = exc
            continue
        saw_any_response = True
        code = element_code(detail.get("types"))
        if code is not None:
            return code, None
    # Au moins une langue a répondu mais sans type exploitable → « sans type », pas une erreur.
    if saw_any_response:
        return None, None
    return None, last_exc


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="ne rien écrire, juste compter")
    parser.add_argument("--limit", type=int, default=None, help="borne le nombre de cartes (essai)")
    args = parser.parse_args()

    start = time.monotonic()

    async with (
        httpx.AsyncClient(timeout=30.0) as tcgdex_http,
        async_session_factory() as session,
    ):
        tcgdex = TcgdexClient(http_client=tcgdex_http)

        # Cartes qui affichent le visuel de remplacement (pas d'image) et dont le type reste à
        # déterminer. On se limite aux Pokémon : Dresseurs/Énergies n'ont pas de type élémentaire
        # (TCGdex ne renvoie pas de `types`), leur fond est "colorless" — inutile de les interroger.
        stmt = (
            select(Card.id, Card.tcgdex_id, Card.name)
            .where(
                Card.image_url.is_(None),
                Card.element_type.is_(None),
                Card.tcgdex_id.is_not(None),
                Card.supertype.ilike("pok%"),
            )
            .order_by(Card.id)
        )
        if args.limit is not None:
            stmt = stmt.limit(args.limit)
        candidates = (await session.execute(stmt)).all()

    total = len(candidates)
    _log(
        f"backfill element_type — {total} carte(s) Pokémon sans image et sans type"
        + (" (DRY-RUN, aucune écriture)" if args.dry_run else "")
    )
    if total == 0:
        _log("rien à faire.")
        return

    updated = 0
    no_type = 0
    errors = 0
    semaphore = asyncio.Semaphore(FETCH_CONCURRENCY)

    async with (
        httpx.AsyncClient(timeout=30.0) as tcgdex_http,
        async_session_factory() as session,
    ):
        tcgdex = TcgdexClient(http_client=tcgdex_http)

        async def _one(card_id, tcgdex_id: str, name: str):
            async with semaphore:
                return card_id, name, await _element_for(tcgdex, tcgdex_id)

        done = 0
        for chunk_start in range(0, total, 200):
            chunk = candidates[chunk_start : chunk_start + 200]
            results = await asyncio.gather(*(_one(cid, tid, nm) for (cid, tid, nm) in chunk))
            for card_id, name, (code, exc) in results:
                done += 1
                if exc is not None:
                    errors += 1
                    _log(f"  ERREUR TCGdex sur {name} ({card_id}) : {exc}")
                    continue
                if code is None:
                    no_type += 1
                    continue
                updated += 1
                if not args.dry_run:
                    await session.execute(
                        update(Card).where(Card.id == card_id).values(element_type=code)
                    )
            if not args.dry_run:
                await session.commit()
            _log(f"  {done}/{total} — maj={updated} sans_type={no_type} erreurs={errors}")

    elapsed = time.monotonic() - start
    _log(
        f"terminé en {elapsed:.0f}s — {updated} carte(s) typée(s), {no_type} sans type TCGdex, "
        f"{errors} erreur(s)"
        + (" (DRY-RUN)" if args.dry_run else "")
    )
    # Sortie non nulle si des cartes ont échoué au réseau : un backfill « réussi » avec des trous
    # d'erreur ne doit pas passer pour complet (règle « pas de repli silencieux »).
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
