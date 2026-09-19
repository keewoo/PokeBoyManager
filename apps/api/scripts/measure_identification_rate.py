"""Mise au point du rapprochement catalogue sur le jeu de 100 cartes étiquetées (mission
`v3-identification`, point 5 — objectif top-3 ≥ 95 %).

`tests/test_identification_synthetic_dataset.py` est la mesure qui fait foi (vérifiée par la
CI à chaque exécution) ; ce script sert à explorer le détail palier par palier pendant la mise
au point (mêmes cartes, même bruit déterministe), sans dépendre de pytest. Aucune vraie photo ni
clé IA réelle : voir l'avertissement de `pbm_api.identification.synthetic`.

La transaction est annulée en fin de script : aucune donnée n'est laissée dans la base pointée
par `DATABASE_URL`.

Usage :
    uv run python scripts/measure_identification_rate.py
    uv run python scripts/measure_identification_rate.py --out /tmp/identification-tuning
"""

import argparse
import asyncio
import json
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from pbm_api.config import settings
from pbm_api.identification.reconciliation import reconcile
from pbm_api.identification.synthetic import generate_dataset
from pbm_api.models import Card, CardName, Set

_TARGET_TOP3_RATE = 0.95


async def _seed_catalog(session: AsyncSession, cases) -> dict[str, str]:
    sets_by_code: dict[str, Set] = {}
    card_id_by_case: dict[str, str] = {}
    for case in cases:
        set_row = sets_by_code.get(case.card.set_code)
        if set_row is None:
            set_row = Set(
                code=case.card.set_code, name=case.card.set_name, total_cards=case.card.total_cards
            )
            session.add(set_row)
            await session.flush()
            sets_by_code[case.card.set_code] = set_row

        card = Card(set_id=set_row.id, number=case.card.number, name=case.card.name_fr)
        session.add(card)
        await session.flush()
        session.add_all(
            [
                CardName(card_id=card.id, language="fr", name=case.card.name_fr),
                CardName(card_id=card.id, language="en", name=case.card.name_en),
            ]
        )
        card_id_by_case[case.id] = str(card.id)
    await session.flush()
    return card_id_by_case


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="var/identification-tuning")
    args = parser.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    engine = create_async_engine(settings.database_url)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(bind=connection, join_transaction_mode="create_savepoint")
        try:
            cases = generate_dataset()
            card_id_by_case = await _seed_catalog(session, cases)

            rows = []
            top1 = top3 = 0
            tier_counts: dict[str, int] = {}
            for case in cases:
                result = await reconcile(session, case.extraction)
                tier_counts[result.tier] = tier_counts.get(result.tier, 0) + 1
                candidate_ids = [c.card_id for c in result.candidates]
                expected_id = card_id_by_case[case.id]
                is_top1 = candidate_ids[:1] == [expected_id]
                is_top3 = expected_id in candidate_ids[:3]
                top1 += int(is_top1)
                top3 += int(is_top3)
                expected_label = f"{case.card.set_code} {case.card.number} {case.card.name_fr}"
                combined_score = result.candidates[0].combined_score if result.candidates else 0.0
                rows.append(
                    {
                        "id": case.id,
                        "expected_card": expected_label,
                        "tier": result.tier,
                        "top1": is_top1,
                        "top3": is_top3,
                        "combined_score": combined_score,
                    }
                )
        finally:
            await transaction.rollback()
    await engine.dispose()

    total = len(cases)
    report = {
        "total_cards": total,
        "top1_rate": top1 / total,
        "top3_rate": top3 / total,
        "target_top3_rate": _TARGET_TOP3_RATE,
        "tier_counts": tier_counts,
        "cost_per_card": (
            "non mesurable en euros sur chimera (aucune clé IA réelle, aucune table de "
            "tarification par modèle dans ce dépôt — voir pbm_api.ai.service.record_usage). "
            "Estimation en jetons via scripts/test_identification_manual.py une fois une vraie "
            "clé disponible."
        ),
        "cards": rows,
    }
    (out_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))

    print(f"{total} cartes — rapport dans {out_dir}/report.json")
    print(f"top-1 : {top1}/{total} = {top1 / total:.1%}")
    print(f"top-3 : {top3}/{total} = {top3 / total:.1%} (objectif >= {_TARGET_TOP3_RATE:.0%})")
    print(f"paliers : {tier_counts}")


if __name__ == "__main__":
    asyncio.run(main())
