#!/usr/bin/env python
"""Chaîne de détourage des Pokémon vedettes — produit les découpes de l'apparition (DJ3).

    uv sync --extra decoupe                                        # onnxruntime, hors CI
    uv run python scripts/decouper_apparitions.py --telecharger-modele
    uv run python scripts/decouper_apparitions.py --a-blanc        # ce qu'il FERAIT
    uv run python scripts/decouper_apparitions.py                  # tout le registre
    uv run python scripts/decouper_apparitions.py --vedette base1-4
    uv run python scripts/decouper_apparitions.py --planche /tmp/planche.png --ecrire-registre

⛔ Ce script tourne **sur la flotte**, jamais sur la machine qui sert : il décode des illustrations
et fait tourner un réseau de neurones (``docs/infra/JOBS-LOURDS.md``). Il écrit dans le stockage
objet sous ``jeu/apparitions/{tcgdex_id}.webp`` — une clé de **catalogue**, pas de joueur : la
découpe vient de l'illustration officielle de la carte, elle est la même pour tout le monde.

Il rend un code de sortie non nul si une vedette demandée n'a pas pu être produite : un registre
qui annonce une apparition absente ferait tenter un chargement en 404 à chaque partie.

**La planche de contrôle est le seul moyen d'accepter une vedette.** La note refuse ce qui est
objectivement raté (fond gardé, découpe éclatée, bord vaporeux) ; elle ne sait pas dire qu'une aile
a été coupée. `--planche` fabrique une image unique, une vedette par case, à regarder avant de
publier. Les illustrations officielles ne sont pas versionnées : la planche est un artefact de
travail, elle reste hors du dépôt.
"""

import argparse
import asyncio
import sys
from collections import Counter
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pbm_api.jeu import budget, decoupe, vedettes  # noqa: E402
from pbm_api.jeu.segmentation import (  # noqa: E402
    NOM_MOTEUR,
    ModeleIndisponible,
    charger_segmenteur,
    telecharger_modele,
)

#: Largeur d'une case de la planche de contrôle, en pixels.
CASE_PLANCHE = 320
#: Nombre de cases par rangée.
COLONNES_PLANCHE = 4


def _illustration(client: httpx.Client, url_base: str) -> bytes:
    """Les octets de l'illustration officielle en haute définition.

    ``url_base`` est l'URL sans extension que porte ``cards.image_url`` : la même convention que
    le proxy ``/img/cards/{id}`` (``{base}/{size}.webp``), pour qu'une découpe soit toujours faite
    sur l'image que le joueur voit.
    """
    reponse = client.get(f"{url_base}/high.webp", follow_redirects=True, timeout=60.0)
    reponse.raise_for_status()
    return reponse.content


def _planche(decoupees: list[tuple[str, bytes]], chemin: Path) -> None:
    """Assemble les découpes en une planche à relire à l'œil, une vedette par case."""
    import io

    from PIL import Image

    images = [(nom, Image.open(io.BytesIO(octets)).convert("RGBA")) for nom, octets in decoupees]
    if not images:
        return
    hauteur = max(i.height for _, i in images) + 28
    rangees = (len(images) + COLONNES_PLANCHE - 1) // COLONNES_PLANCHE
    planche = Image.new(
        "RGBA", (COLONNES_PLANCHE * CASE_PLANCHE, rangees * hauteur), (24, 24, 30, 255)
    )
    for rang, (_, image) in enumerate(images):
        x = (rang % COLONNES_PLANCHE) * CASE_PLANCHE + (CASE_PLANCHE - image.width) // 2
        y = (rang // COLONNES_PLANCHE) * hauteur + 14
        planche.paste(image, (x, y), image)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    planche.convert("RGB").save(chemin)


async def _publier(cles: dict[str, bytes]) -> None:
    """Dépose les découpes dans le stockage objet, sous leur clé de catalogue."""
    from pbm_api.storage import build_storage

    stockage = build_storage()
    await stockage.ensure_bucket()
    for cle, octets in cles.items():
        await stockage.put(cle, octets, decoupe.TYPE_MIME_APPARITION)


def main() -> int:
    parseur = argparse.ArgumentParser(description=__doc__)
    parseur.add_argument("--vedette", default=None, help="n'en traiter qu'une (son tcgdex_id)")
    parseur.add_argument("--a-blanc", action="store_true", help="ne rien écrire, juste compter")
    parseur.add_argument("--planche", default=None, help="écrire la planche de contrôle ici")
    parseur.add_argument(
        "--ecrire-registre",
        action="store_true",
        help="réinscrire note et poids mesurés dans apparitions.json",
    )
    parseur.add_argument(
        "--telecharger-modele", action="store_true", help="récupérer les poids puis sortir"
    )
    parseur.add_argument(
        "--sans-publier",
        action="store_true",
        help="mesurer sans déposer dans le stockage objet (mise au point)",
    )
    arguments = parseur.parse_args()

    if arguments.telecharger_modele:
        chemin = telecharger_modele()
        print(f"modèle vérifié et posé : {chemin}")
        return 0

    candidates = vedettes.charger()
    if arguments.vedette:
        candidates = [v for v in candidates if v.tcgdex_id == arguments.vedette]
        if not candidates:
            print(f"⛔ vedette inconnue du registre : {arguments.vedette}", file=sys.stderr)
            return 2

    print(f"{len(candidates)} vedette(s) au registre")
    if arguments.a_blanc:
        for vedette in candidates:
            etat = "publiée" if vedette.publie else "à produire"
            print(f"  {vedette.tcgdex_id:16s} {vedette.nom:22s} {etat}")
        print(budget.rapport())
        return 0

    try:
        segmenter = charger_segmenteur()
    except ModeleIndisponible as exc:
        print(f"⛔ {exc}", file=sys.stderr)
        return 3

    verdicts: Counter[str] = Counter()
    poids: list[int] = []
    produites: dict[str, bytes] = {}
    pour_planche: list[tuple[str, bytes]] = []
    notes: dict[str, dict] = {}
    echecs: list[str] = []

    with httpx.Client() as client:
        for vedette in candidates:
            try:
                octets = _illustration(client, vedette.illustration)
            except httpx.HTTPError as exc:
                verdicts["illustration injoignable"] += 1
                echecs.append(f"{vedette.tcgdex_id} : illustration injoignable ({exc})")
                continue
            try:
                apparition = decoupe.decouper(octets, segmenter, moteur=NOM_MOTEUR)
            except decoupe.DecoupeRefusee as exc:
                verdicts["refusée"] += 1
                notes[vedette.tcgdex_id] = exc.note.en_json()
                echecs.append(f"{vedette.tcgdex_id} : {exc}")
                continue
            except (decoupe.ApparitionTropLourde, decoupe.IllustrationIndecodable) as exc:
                verdicts["hors budget ou illisible"] += 1
                echecs.append(f"{vedette.tcgdex_id} : {exc}")
                continue
            verdicts["produite"] += 1
            poids.append(len(apparition.image))
            notes[vedette.tcgdex_id] = apparition.note.en_json() | {
                "largeur": apparition.largeur,
                "hauteur": apparition.hauteur,
                "octets": len(apparition.image),
            }
            produites[vedettes.cle_apparition(vedette.tcgdex_id)] = apparition.image
            pour_planche.append((vedette.tcgdex_id, apparition.image))

    for ligne, nombre in verdicts.most_common():
        print(f"  {nombre:4d}  {ligne}")
    for ligne in echecs:
        print(f"  ⚠ {ligne}")
    if poids:
        poids.sort()
        plafond = decoupe.VARIANTE_APPARITION.plafond_octets
        milieu = poids[len(poids) // 2]
        print(
            f"  poids : n={len(poids)} médiane={milieu / 1024:.1f} Ko "
            f"max={poids[-1] / 1024:.1f} Ko plafond={plafond / 1024:.0f} Kio"
        )

    if arguments.planche and pour_planche:
        _planche(pour_planche, Path(arguments.planche))
        print(f"  planche de contrôle : {arguments.planche} — à relire AVANT de publier")

    if arguments.ecrire_registre:
        vedettes.ecrire_notes(notes)
        print(f"  registre mis à jour : {vedettes.CHEMIN_REGISTRE}")

    if produites and not arguments.sans_publier:
        asyncio.run(_publier(produites))
        print(f"  {len(produites)} découpe(s) déposée(s) dans le stockage objet")

    print(budget.rapport())
    depassements = budget.depassements()
    for ligne in depassements:
        print(f"⛔ budget : {ligne}", file=sys.stderr)
    if echecs:
        print(f"⛔ {len(echecs)} vedette(s) sans découpe — registre à corriger", file=sys.stderr)
    return 1 if (depassements or echecs) else 0


if __name__ == "__main__":
    raise SystemExit(main())
