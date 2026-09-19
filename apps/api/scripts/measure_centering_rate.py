"""Mise au point du centrage (mission `v3-etat`, point 1) sur le jeu synthétique
(`pbm_api.state.synthetic.generate_dataset` — aucun appareil photo/carte physique sur chimera,
même avertissement que `pbm_api.detection.synthetic`).

Mesure l'erreur absolue moyenne (en pixels) entre les marges connues du jeu synthétique et
celles retrouvées par `pbm_api.state.centering.measure_centering`, plus le taux de cas gradés
correctement (même palier que le palier attendu d'après les marges connues).

Usage :
    uv run python scripts/measure_centering_rate.py
"""

import statistics

from pbm_api.state.centering import measure_centering
from pbm_api.state.synthetic import generate_dataset


def main() -> None:
    crops = generate_dataset()
    errors: list[float] = []
    unmeasurable = 0

    print(f"{'id':22s} {'L':>4s} {'R':>4s} {'T':>4s} {'B':>4s}  {'grade':12s}")
    for crop in crops:
        result = measure_centering(crop.image)
        if result is None:
            unmeasurable += 1
            print(f"{crop.id:22s} -- non mesurable --")
            continue
        errors.extend(
            [
                abs(result.left_px - crop.left_px),
                abs(result.right_px - crop.right_px),
                abs(result.top_px - crop.top_px),
                abs(result.bottom_px - crop.bottom_px),
            ]
        )
        print(
            f"{crop.id:22s} {result.left_px:4d} {result.right_px:4d} "
            f"{result.top_px:4d} {result.bottom_px:4d}  {result.grade.value:12s}"
            f"(attendu L={crop.left_px} R={crop.right_px} T={crop.top_px} B={crop.bottom_px})"
        )

    print(f"\n{len(crops)} recadrages, {unmeasurable} non mesurables")
    if errors:
        print(f"erreur absolue moyenne : {statistics.mean(errors):.2f} px")
        print(f"erreur absolue max : {max(errors)} px")


if __name__ == "__main__":
    main()
