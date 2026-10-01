"""Vérificateur commit-reveal en **une commande** — le seul endroit du paquet qui fait
de l'E/S (lecture d'un fichier, écriture sur la sortie), volontairement isolé du cœur
pur :mod:`pbm_game.rng`.

    uv run python -m pbm_game.rng verifier <enregistrement.json>

L'enregistrement est le JSON publié à la fin d'une partie :

    {
      "engagement": "<l'empreinte publiée AVANT la partie>",
      "graine":     "<la graine révélée À LA FIN, en hexadécimal>",
      "journal":    [ { "flux": …, "indice": …, "genre": …, "parametre": …,
                        "resultat": … }, … ]
    }

Le vérificateur confirme deux choses, et le dit sans repli silencieux :

1. la graine révélée correspond bien à l'engagement publié (personne n'a changé de
   graine en cours de route) ;
2. chaque tirage du journal est **exactement** le i-ème tirage de son flux sous cette
   graine, dans l'ordre et sans trou (personne n'a rejoué le mélange jusqu'à un bon
   résultat, ni truqué un pile ou face).

Sort 0 si tout est cohérent, 1 si une anomalie est trouvée, 2 si l'entrée est illisible.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import tirage_depuis_json, verifier_engagement, verifier_journal


def _verifier_fichier(chemin: Path) -> int:
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"⛔ Lecture impossible : {exc}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"⛔ JSON invalide : {exc}", file=sys.stderr)
        return 2

    if not isinstance(donnees, dict):
        print("⛔ L'enregistrement doit être un objet JSON.", file=sys.stderr)
        return 2

    engagement_publie = donnees.get("engagement")
    graine_hex = donnees.get("graine")
    journal_brut = donnees.get("journal")
    if not isinstance(engagement_publie, str):
        print("⛔ « engagement » manquant.", file=sys.stderr)
        return 2
    if not isinstance(graine_hex, str):
        print("⛔ « graine » (hex) manquante.", file=sys.stderr)
        return 2
    if not isinstance(journal_brut, list):
        print("⛔ « journal » manquant ou n'est pas une liste.", file=sys.stderr)
        return 2

    try:
        graine = bytes.fromhex(graine_hex)
    except ValueError as exc:
        print(f"⛔ Graine hex illisible : {exc}", file=sys.stderr)
        return 2
    try:
        journal = [tirage_depuis_json(t) for t in journal_brut]
    except ValueError as exc:
        print(f"⛔ Journal illisible : {exc}", file=sys.stderr)
        return 2

    probleme = False

    if verifier_engagement(graine, engagement_publie):
        print("✅ Engagement : la graine révélée correspond à l'empreinte publiée.")
    else:
        print("❌ Engagement : la graine révélée NE correspond PAS à l'empreinte publiée.")
        probleme = True

    anomalies = verifier_journal(graine, journal)
    if not anomalies:
        print(f"✅ Journal : {len(journal)} tirage(s) recalculés, tous conformes à la graine.")
    else:
        print(f"❌ Journal : {len(anomalies)} anomalie(s) sur {len(journal)} tirage(s) :")
        for anomalie in anomalies:
            print(f"   • tirage #{anomalie.rang} (flux « {anomalie.flux} ») : {anomalie.probleme}")
        probleme = True

    if probleme:
        print("\n⛔ Mélange NON vérifié — l'aléatoire de cette partie est contestable.")
        return 1
    print("\n✅ Mélange vérifié : l'aléatoire de cette partie est honnête et reproductible.")
    return 0


def main(argv: list[str] | None = None) -> int:
    analyseur = argparse.ArgumentParser(
        prog="python -m pbm_game.rng",
        description="Vérifie a posteriori l'aléatoire d'une partie (commit-reveal).",
    )
    sous = analyseur.add_subparsers(dest="commande", required=True)
    v = sous.add_parser("verifier", help="vérifie un enregistrement de partie (JSON).")
    v.add_argument("fichier", type=Path, help="chemin de l'enregistrement JSON à vérifier.")
    args = analyseur.parse_args(argv)
    if args.commande == "verifier":
        return _verifier_fichier(args.fichier)
    analyseur.error(f"commande inconnue : {args.commande}")  # argparse sort en code 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
