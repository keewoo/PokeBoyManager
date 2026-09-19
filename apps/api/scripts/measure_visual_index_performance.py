"""Mesure de ressources de l'index visuel à l'échelle de production (mission
`v3-identification-visuelle` point 5 : recherche < 200 ms par carte, empreinte mémoire compatible
avec le serveur de 4 Go).

Pas besoin d'images réelles ni de catalogue importé pour cette mesure : le coût de
`pbm_api.identification.visual_index.VisualIndex` (chargement, recherche) ne dépend que du
nombre de lignes, pas de leur contenu — des empreintes aléatoires à la bonne volumétrie
(~20 000 cartes × 2 langues, mission « risques & pièges ») suffisent à mesurer temps et mémoire
réels, sans télécharger un seul octet.

Usage :
    uv run python scripts/measure_visual_index_performance.py
    uv run python scripts/measure_visual_index_performance.py --rows 40000 --searches 200
"""

import argparse
import json
import resource
import time
import uuid

import numpy as np

from pbm_api.identification.visual_index import VisualIndex


def _random_index(rows: int, seed: int) -> VisualIndex:
    rng = np.random.default_rng(seed)
    card_ids = [uuid.uuid4() for _ in range(rows // 2)]
    # Deux lignes par carte (fr/en), comme en production (mission « risques & pièges »).
    all_card_ids = [cid for cid in card_ids for _ in range(2)][:rows]
    languages = ["fr", "en"] * (rows // 2 + 1)
    languages = languages[:rows]
    full = rng.integers(0, 2**63, size=rows, dtype=np.int64).astype(np.uint64)
    illustration = rng.integers(0, 2**63, size=rows, dtype=np.int64).astype(np.uint64)
    return VisualIndex(all_card_ids, languages, full, illustration)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=40_000)
    parser.add_argument("--searches", type=int, default=200)
    parser.add_argument("--seed", type=int, default=20260920)
    args = parser.parse_args()

    rss_before_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    build_start = time.perf_counter()
    index = _random_index(args.rows, args.seed)
    build_seconds = time.perf_counter() - build_start

    rss_after_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    index_memory_kb = index.arrays_memory_bytes

    rng = np.random.default_rng(args.seed + 1)
    search_times_ms = []
    for _ in range(args.searches):
        full_query = int(rng.integers(0, 2**63))
        illustration_query = int(rng.integers(0, 2**63))
        start = time.perf_counter()
        index.search(full_phash=full_query, illustration_phash=illustration_query)
        search_times_ms.append((time.perf_counter() - start) * 1000)

    report = {
        "rows": args.rows,
        "distinct_cards": args.rows // 2,
        "index_build_seconds": round(build_seconds, 4),
        "index_arrays_memory_kb": round(index_memory_kb / 1024, 1),
        "process_rss_delta_kb": rss_after_kb - rss_before_kb,
        "process_rss_total_mb": round(rss_after_kb / 1024, 1),
        "search_count": args.searches,
        "search_ms_mean": round(float(np.mean(search_times_ms)), 3),
        "search_ms_p95": round(float(np.percentile(search_times_ms, 95)), 3),
        "search_ms_max": round(float(np.max(search_times_ms)), 3),
        "target_search_ms": 200,
        "target_memory_note": (
            "serveur de 4 Go visé (mission risque « pas de modèle lourd ») — comparer "
            "process_rss_total_mb à cette borne, pas seulement index_arrays_memory_kb."
        ),
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
