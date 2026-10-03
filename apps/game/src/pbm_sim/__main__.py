"""Ligne de commande de la simulation : lancer une campagne, ou **reproduire une anomalie**.

Deux sous-commandes, et surtout la seconde — c'est le critère d'acceptation « toute anomalie est
reproductible depuis sa graine en **une** commande » :

```
python -m pbm_sim campagne --prefixe nuit --nombre 10000      # des milliers de parties
python -m pbm_sim reproduire <graine>                          # rejoue UNE partie, en détail
```

``campagne`` sort en code **1** s'il reste la moindre anomalie (utilisable comme garde en CI ou la
nuit) ; ``reproduire`` sort en **1** si la partie rejouée porte une anomalie. Aucun des deux ne
masque un échec : le code de sortie EST le verdict.
"""

from __future__ import annotations

import argparse
import sys

from .campagne import campagne, graines
from .orchestrateur import jouer_partie
from .rapport import formater


def _cmd_campagne(args: argparse.Namespace) -> int:
    """Joue ``--nombre`` parties ``"{prefixe}:{i}"`` et imprime le rapport ; 1 si anomalie."""
    rapport = campagne(
        graines(args.prefixe, args.nombre),
        parallele=not args.serie,
        processus=args.processus,
        max_pas=args.max_pas,
    )
    print(formater(rapport))
    return 0 if rapport.toutes_saines else 1


def _cmd_reproduire(args: argparse.Namespace) -> int:
    """Rejoue la partie de la graine ``args.graine``, en détail (scénario, issue, journal) ; 1 si
    anomalie."""
    r = jouer_partie(args.graine, garder_partie=True, max_pas=args.max_pas)
    print(f"Graine        : {r.graine}")
    print(f"Decks         : {r.deck0}  vs  {r.deck1}")
    print(f"Bots          : {r.bot0}  vs  {r.bot1}")
    print(f"Issue         : terminée={r.terminee}  vainqueur={r.vainqueur}  raison={r.raison_fin}")
    print(f"Durée         : {r.tours} tours, {r.pas} coups")
    if r.anomalies:
        print("ANOMALIES :")
        for a in r.anomalies:
            print(f"  coup {a.pas} → {a.type} : {a.message}")
    else:
        print("Aucune anomalie : partie saine.")
    if r.partie is not None:
        queue = r.partie.entrees[-args.derniers :] if args.derniers > 0 else r.partie.entrees
        print(f"Journal (derniers {len(queue)} coups) :")
        for entree in queue:
            print(f"  #{entree.numero:>4}  {entree.auteur:<8}  {entree.action.type}")
    return 0 if r.saine else 1


def construire_parseur() -> argparse.ArgumentParser:
    """Le parseur d'arguments de ``python -m pbm_sim`` (exposé pour le test)."""
    parseur = argparse.ArgumentParser(
        prog="python -m pbm_sim",
        description="Bots de simulation PokeBoyManager : campagnes de masse et reproduction.",
    )
    sous = parseur.add_subparsers(dest="commande", required=True)

    c = sous.add_parser("campagne", help="jouer des milliers de parties et agréger les anomalies")
    c.add_argument("--prefixe", default="campagne", help="préfixe des graines (défaut : campagne)")
    c.add_argument("--nombre", type=int, default=1000, help="nombre de parties (défaut : 1000)")
    c.add_argument("--processus", type=int, default=None, help="processus parallèles")
    c.add_argument("--max-pas", dest="max_pas", type=int, default=None, help="plafond coups/partie")
    c.add_argument("--serie", action="store_true", help="jouer en série (sans parallélisme)")
    c.set_defaults(fonction=_cmd_campagne)

    r = sous.add_parser("reproduire", help="rejouer UNE partie depuis sa graine, en détail")
    r.add_argument("graine", help="la graine du scénario à rejouer")
    r.add_argument("--max-pas", dest="max_pas", type=int, default=None, help="plafond de coups")
    r.add_argument("--derniers", type=int, default=30, help="coups de fin de journal (0=tous)")
    r.set_defaults(fonction=_cmd_reproduire)
    return parseur


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée : analyse les arguments et exécute la sous-commande ; renvoie son code."""
    args = construire_parseur().parse_args(argv)
    return args.fonction(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
