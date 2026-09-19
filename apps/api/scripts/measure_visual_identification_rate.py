"""Mesure de la comparaison visuelle sur un jeu synthétique (mission `v3-identification-visuelle`
point 4) : part reconnue sans IA, précision top-1 parmi les cartes reconnues, et comportement sur
un groupe « même illustration » (réimpression/reverse/promo — mission « risques & pièges »).

Contrairement à `scripts/measure_identification_rate.py` (bruit simulé sur une extraction déjà
lue), ce script exerce la vraie mécanique de hachage (`pbm_api.identification.fingerprint.
compute_phash`, `pbm_api.identification.visual_index`) sur des images procédurales
(`pbm_api.identification.visual_synthetic` — aucune vraie photo/carte physique sur chimera, même
contrainte que les autres jeux synthétiques du dépôt) : ce chiffre valide le calibrage des seuils
(`CONFIDENT_SCORE_THRESHOLD`, `AMBIGUITY_MARGIN`) sur un pipeline réel de bout en bout, pas la
robustesse d'une vraie photo de carte (hors de portée sans campagne photo, voir le compte rendu).

La transaction est annulée en fin de script : aucune donnée n'est laissée dans la base pointée
par `DATABASE_URL`.

Usage :
    uv run python scripts/measure_visual_identification_rate.py
    uv run python scripts/measure_visual_identification_rate.py --out /tmp/visual-tuning
"""

import argparse
import asyncio
import json
from pathlib import Path

import cv2
import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from pbm_api.config import settings
from pbm_api.identification.fingerprint import compute_phash
from pbm_api.identification.visual_build import compute_visual_hashes
from pbm_api.identification.visual_geometry import illustration_region
from pbm_api.identification.visual_index import VisualIndex
from pbm_api.identification.visual_index import resolve as resolve_visual
from pbm_api.identification.visual_synthetic import (
    generate_dataset,
    render_official_image,
    render_user_crop,
)
from pbm_api.models import Card, Set
from pbm_api.models.identification import CardVisualIndex

_TARGET_COVERAGE = 0.5  # part attendue reconnue sans IA sur ce jeu (10 % de paires ambiguës)


async def _seed(session: AsyncSession, cards) -> dict[str, str]:
    sets_by_code: dict[str, Set] = {}
    card_id_by_synthetic_id: dict[str, str] = {}
    for card in cards:
        set_row = sets_by_code.get(card.set_code)
        if set_row is None:
            set_row = Set(code=card.set_code, name=card.set_code, total_cards=len(cards))
            session.add(set_row)
            await session.flush()
            sets_by_code[card.set_code] = set_row

        row = Card(set_id=set_row.id, number=card.number, name=card.name)
        session.add(row)
        await session.flush()
        card_id_by_synthetic_id[card.id] = str(row.id)

        official_bytes = _encode_png(render_official_image(card.base_color, card.shape_seed))
        full_phash, illustration_phash = compute_visual_hashes(official_bytes)
        session.add(
            CardVisualIndex(
                card_id=row.id,
                language="fr",
                full_phash=full_phash,
                illustration_phash=illustration_phash,
            )
        )
    await session.flush()
    return card_id_by_synthetic_id


def _encode_png(image: np.ndarray) -> bytes:
    ok, buffer = cv2.imencode(".png", image)
    assert ok
    return buffer.tobytes()


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="var/visual-identification-tuning")
    parser.add_argument("--seed", type=int, default=20260920)
    args = parser.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    cards = generate_dataset(seed=args.seed)
    rng = np.random.default_rng(args.seed + 1)

    engine = create_async_engine(settings.database_url)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(bind=connection, join_transaction_mode="create_savepoint")
        try:
            card_id_by_synthetic_id = await _seed(session, cards)
            index = await VisualIndex.load(session)

            rows = []
            confident_count = 0
            correct_among_confident = 0
            confusable_wrongly_confident = 0
            confusable_correctly_ambiguous = 0
            unique_correctly_confident = 0

            for card in cards:
                crop = render_user_crop(rng, card.base_color, card.shape_seed)
                full_phash = compute_phash(crop)
                illustration_phash = compute_phash(illustration_region(crop))
                matches = index.search(full_phash=full_phash, illustration_phash=illustration_phash)
                resolution = resolve_visual(matches)

                expected_id = card_id_by_synthetic_id[card.id]
                is_confusable = card.confusable_with is not None
                confident = resolution.confident_match is not None
                correct = confident and str(resolution.confident_match.card_id) == expected_id

                if confident:
                    confident_count += 1
                    correct_among_confident += int(correct)
                    if is_confusable:
                        if correct:
                            # Score exact malgré l'ambiguïté (motif identique) : accepté, l'IA
                            # n'aurait pas fait mieux sans lire le numéro non plus.
                            pass
                        else:
                            confusable_wrongly_confident += 1
                    else:
                        unique_correctly_confident += int(correct)
                elif is_confusable:
                    confusable_correctly_ambiguous += 1

                rows.append(
                    {
                        "id": card.id,
                        "confusable": is_confusable,
                        "confident": confident,
                        "correct": correct,
                        "top_score": matches[0].score if matches else None,
                    }
                )
        finally:
            await transaction.rollback()
    await engine.dispose()

    total = len(cards)
    total_confusable = sum(1 for c in cards if c.confusable_with is not None)
    total_unique = total - total_confusable

    report = {
        "total_cards": total,
        "confusable_cards": total_confusable,
        "unique_cards": total_unique,
        "coverage_without_ai": confident_count / total,
        "target_coverage_without_ai": _TARGET_COVERAGE,
        "precision_among_confident": (
            correct_among_confident / confident_count if confident_count else None
        ),
        "unique_cards_resolved_confidently": unique_correctly_confident,
        "unique_cards_resolved_confidently_rate": (
            unique_correctly_confident / total_unique if total_unique else None
        ),
        "confusable_pairs_correctly_left_ambiguous": confusable_correctly_ambiguous,
        "confusable_pairs_wrongly_resolved_confidently": confusable_wrongly_confident,
        "ai_calls_saved_estimate": confident_count / total,
        "cards": rows,
    }
    (out_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))

    print(
        f"{total} cartes ({total_confusable} en paires ambiguës) — "
        f"rapport dans {out_dir}/report.json"
    )
    print(f"reconnues sans IA : {confident_count}/{total} = {confident_count / total:.1%}")
    print(
        f"précision parmi les reconnues : {report['precision_among_confident']:.1%}"
        if confident_count
        else "précision parmi les reconnues : n/a"
    )
    print(
        f"cartes uniques résolues avec confiance : {unique_correctly_confident}/{total_unique}"
    )
    print(
        f"paires ambiguës laissées à l'IA (attendu) : {confusable_correctly_ambiguous}/"
        f"{total_confusable} — résolues à tort avec confiance : {confusable_wrongly_confident}"
    )


if __name__ == "__main__":
    asyncio.run(main())
