"""Mise au point du pipeline de détection sur un lot d'images (mission `v3-detection`, point 4).

Sans argument, mesure le taux de détection sur les 30 photos synthétiques
(`pbm_api.detection.synthetic.generate_dataset`, voir l'avertissement dans ce module : aucun
appareil photo ni carte physique sur chimera). Deux colonnes sont rapportées :

- « opencv seul » : ce que le pipeline fait sans aucun appel IA (D4 : reconnaissance
  désactivée sans clé) ;
- « avec repli » : `--provider`/`--api-key` fournis -> un vrai fournisseur IA est utilisé pour
  le repli sur les photos jugées incohérentes par OpenCV (mission point 2). Sans ces options,
  cette colonne utilise un repli **simulé** (boîtes exactes de la photo) uniquement pour
  illustrer le gain attendu de l'architecture — ce n'est pas une mesure de précision IA réelle.

Écrit une image annotée de contrôle par photo dans `--out` (mission point 4 : « résultat par
photo : cartes détectées + image annotée de contrôle »).

Usage :
    uv run python scripts/measure_detection_rate.py
    uv run python scripts/measure_detection_rate.py --out /tmp/detection-tuning
    uv run python scripts/measure_detection_rate.py --provider anthropic --api-key sk-ant-...
"""

import argparse
import asyncio
import json
from pathlib import Path

from pbm_api.ai.base import AIProvider, ExtractionUsage
from pbm_api.ai.factory import create_provider
from pbm_api.detection.annotate import draw_control_image, encode_jpeg
from pbm_api.detection.pipeline import run_detection
from pbm_api.detection.synthetic import generate_dataset
from pbm_api.models import AiProvider as AiProviderEnum


class _SimulatedGroundTruthProvider(AIProvider):
    """Repli simulé (voir docstring du module) : renvoie les boîtes exactes de la photo."""

    PROVIDER = AiProviderEnum.anthropic
    DEFAULT_MODEL = "simulated"

    def __init__(self, boxes: list[dict]) -> None:
        super().__init__(api_key="unused")
        self._boxes = boxes

    async def _call(self, images, schema, prompt, model, retry_hint):
        return (
            json.dumps({"boxes": self._boxes}),
            ExtractionUsage(provider=self.PROVIDER, model=model, input_tokens=0, output_tokens=0),
        )


def _ground_truth_boxes(photo, width: int, height: int) -> list[dict]:
    def clamp(v: float) -> float:
        return max(0.0, min(1.0, v))

    return [
        {
            "x_min": clamp(float(q[:, 0].min() / width)),
            "y_min": clamp(float(q[:, 1].min() / height)),
            "x_max": clamp(float(q[:, 0].max() / width)),
            "y_max": clamp(float(q[:, 1].max() / height)),
        }
        for q in photo.ground_truth_quads
    ]


async def _run_one(image_bytes: bytes, ai_provider: AIProvider | None) -> tuple[int, str]:
    result = await run_detection(
        image_bytes, ai_provider=ai_provider, ai_model=None, ai_media_type="image/jpeg"
    )
    return len(result.crops), result.method


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="var/detection-tuning")
    parser.add_argument("--provider", choices=[p.value for p in AiProviderEnum])
    parser.add_argument("--api-key")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    photos = generate_dataset()
    rows = []
    opencv_ok = 0
    fallback_ok = 0

    for photo in photos:
        height, width = photo.image.shape[:2]

        opencv_count, opencv_method = await _run_one(encode_jpeg(photo.image), ai_provider=None)

        if args.provider and args.api_key:
            ai_provider = create_provider(AiProviderEnum(args.provider), args.api_key)
        else:
            ai_provider = _SimulatedGroundTruthProvider(
                _ground_truth_boxes(photo, width, height)
            )
        try:
            full_result = await run_detection(
                encode_jpeg(photo.image),
                ai_provider=ai_provider,
                ai_model=None,
                ai_media_type="image/jpeg",
            )
        finally:
            await ai_provider.aclose()

        annotated = draw_control_image(photo.image, full_result.quads)
        (out_dir / f"{photo.id}.jpg").write_bytes(annotated)

        opencv_ok += int(opencv_count == photo.expected_count)
        fallback_ok += int(len(full_result.crops) == photo.expected_count)
        rows.append(
            {
                "id": photo.id,
                "category": photo.category,
                "expected": photo.expected_count,
                "opencv_only": opencv_count,
                "with_fallback": len(full_result.crops),
                "method": full_result.method,
            }
        )

    total = len(photos)
    simulated = not (args.provider and args.api_key)
    report = {
        "total_photos": total,
        "opencv_only_rate": opencv_ok / total,
        "with_fallback_rate": fallback_ok / total,
        "fallback_simulated": simulated,
        "photos": rows,
    }
    (out_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))

    print(f"{total} photos — images annotées et rapport dans {out_dir}/")
    print(f"taux OpenCV seul     : {ok_pct(opencv_ok, total)}")
    label = "avec repli SIMULÉ" if simulated else f"avec repli ({args.provider})"
    print(f"taux {label} : {ok_pct(fallback_ok, total)}")


def ok_pct(ok: int, total: int) -> str:
    return f"{ok}/{total} = {ok / total:.1%}"


if __name__ == "__main__":
    asyncio.run(main())
