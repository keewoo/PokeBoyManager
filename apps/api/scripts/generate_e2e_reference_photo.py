"""Génère la « photo de référence » du classeur 3×3 (mission `v5-e2e`, parcours e2e complet) :
un classeur propre, sans reflets (`make_binder_grid(glare=False)`, mission `v3-detection`) —
OpenCV seul suffit à détecter les neuf cartes, aucun repli LLM n'est donc exercé par ce lot (voir
`docs/roadmap/comptes-rendus/v5-e2e.md`).

Usage : uv run python scripts/generate_e2e_reference_photo.py <chemin_de_sortie.jpg>
"""

import sys

from pbm_api.detection.annotate import encode_jpeg
from pbm_api.detection.synthetic import make_binder_grid


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(1)

    photo = make_binder_grid(seed=1, index=0, glare=False)
    with open(sys.argv[1], "wb") as f:
        f.write(encode_jpeg(photo.image))


if __name__ == "__main__":
    main()
