"""Produit les **variantes de jeu** du corpus existant (lot ``j-rendu-carte``).

Les exemplaires photographiés avant ce lot n'ont ni variante ni note de qualité : en partie, ils se
replient sur l'image officielle **en le disant** (``RAISON_PAS_PRETE``). C'est correct, mais ce
n'est pas ce que le joueur attend — il veut voir SA carte. Ce script rattrape le corpus d'un coup.

À lancer **sur la flotte**, jamais sur la machine qui sert (règle du dépôt) : il décode et réencode
une image par exemplaire photographié.

    uv run python scripts/preparer_rendus_jeu.py --lot 200          # tout le corpus, par paquets
    uv run python scripts/preparer_rendus_jeu.py --utilisateur <id> # un seul compte
    uv run python scripts/preparer_rendus_jeu.py --a-blanc          # ce qu'il FERAIT, sans écrire

Reprenable : il ne traite que les exemplaires dont il **manque au moins une variante**, donc un
second passage ne refait rien. Aucun repli silencieux — chaque exemplaire traité est compté, et le
détail des replis est affiché à la fin.

**Étendu par le lot ``j-assets-pipeline``**, qui a dédoublé les variantes (plateau 12 Ko, zoom
45 Ko) et posé un plafond de poids par variante. Trois changements, chacun pour une raison :

1. la sélection ne peut plus être ``jeu_qualite IS NULL``. Tout le parc préparé par
   ``j-rendu-carte`` a une note **et** une seule variante : ce filtre l'aurait déclaré complet, et
   ces joueurs auraient joué indéfiniment avec les images officielles sans que rien ne le signale.
   On retient donc aussi les exemplaires notés **sans liste de variantes**
   (``rendu_service.CLE_VARIANTES``) — c'est la signature d'une préparation d'avant le dédoublement,
   et c'est ce qui rend le script utilisable après **tout** changement de recette ;
2. il rend la **distribution réelle des poids** par variante (médiane, p95, max face au plafond) :
   c'est le chiffre qu'on cite dans un compte rendu, et une moyenne n'aurait rien dit ;
3. il **sort en erreur** si un plafond de budget est violé (:mod:`pbm_api.jeu.budget`) : un
   dépassement doit faire échouer le passage, pas laisser une ligne dans un journal que personne
   ne relit.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from collections import Counter

from sqlalchemy import or_, select

from pbm_api.db import async_session_factory
from pbm_api.jeu import budget
from pbm_api.jeu.rendu_image import VARIANTES, cle_variante
from pbm_api.jeu.rendu_service import CLE_VARIANTES, preparer_variante
from pbm_api.models import CollectionItem
from pbm_api.storage import build_storage


def _distribution(poids: dict[str, list[int]]) -> str:
    """Les poids produits, variante par variante, face à leur plafond.

    Médiane **et** p95 **et** max : une moyenne masquerait justement le cas qui fait sauter un
    budget — c'est la queue de la distribution qui compte, pas son centre.
    """
    lignes = []
    for variante in VARIANTES:
        mesures = sorted(poids.get(variante.nom, []))
        if not mesures:
            lignes.append(f"  {variante.nom:<8} aucune variante produite")
            continue
        p95 = mesures[min(len(mesures) - 1, int(len(mesures) * 0.95))]
        lignes.append(
            f"  {variante.nom:<8} n={len(mesures):<5} "
            f"médiane {mesures[len(mesures) // 2] / 1024:>6.1f} Kio · "
            f"p95 {p95 / 1024:>6.1f} Kio · max {mesures[-1] / 1024:>6.1f} Kio "
            f"(plafond {variante.plafond_octets / 1024:.0f} Kio)"
        )
    return "\n".join(lignes)


async def _traiter(
    *, lot: int, utilisateur: uuid.UUID | None, a_blanc: bool, plafond: int | None
) -> tuple[Counter, dict[str, list[int]]]:
    """Prépare les variantes manquantes ; rend le compte par verdict et les poids produits."""
    compte: Counter = Counter()
    poids: dict[str, list[int]] = {}
    storage = build_storage()
    traites = 0
    while plafond is None or traites < plafond:
        async with async_session_factory() as db:
            requete = (
                select(CollectionItem)
                .where(
                    CollectionItem.photo_s3_key.isnot(None),
                    # Jamais noté, OU noté avant le dédoublement des variantes (lot
                    # `j-assets-pipeline`) : les deux cas ont une variante à produire.
                    or_(
                        CollectionItem.jeu_qualite.is_(None),
                        ~CollectionItem.jeu_qualite.op("?")(CLE_VARIANTES),
                    ),
                )
                .order_by(CollectionItem.created_at)
                .limit(lot)
            )
            if utilisateur is not None:
                requete = requete.where(CollectionItem.user_id == utilisateur)
            items = (await db.execute(requete)).scalars().all()
            if not items:
                break
            for item in items:
                if a_blanc:
                    compte["a_preparer"] += 1
                    continue
                note = await preparer_variante(db, storage, item)
                if note is None:
                    compte["sans_photo"] += 1
                elif note.exploitable:
                    compte["variante_produite"] += 1
                    for variante in VARIANTES:
                        donnees = await storage.get(
                            cle_variante(item.user_id, item.id, variante)
                        )
                        if donnees is not None:
                            poids.setdefault(variante.nom, []).append(len(donnees))
                else:
                    compte[f"repli: {note.raison}"] += 1
            if a_blanc:
                # À blanc on n'écrit pas, donc le même paquet reviendrait indéfiniment.
                break
            await db.commit()
            traites += len(items)
            print(f"… {traites} exemplaires traités", flush=True)
    return compte, poids


def main() -> int:
    """Point d'entrée : analyse les options, lance la préparation, affiche le compte."""
    parseur = argparse.ArgumentParser(description=__doc__)
    parseur.add_argument("--lot", type=int, default=200, help="taille d'un paquet (défaut 200)")
    parseur.add_argument("--utilisateur", type=str, default=None, help="limiter à un compte")
    parseur.add_argument("--plafond", type=int, default=None, help="s'arrêter après N exemplaires")
    parseur.add_argument("--a-blanc", action="store_true", help="ne rien écrire, juste compter")
    args = parseur.parse_args()

    compte, poids = asyncio.run(
        _traiter(
            lot=args.lot,
            utilisateur=uuid.UUID(args.utilisateur) if args.utilisateur else None,
            a_blanc=args.a_blanc,
            plafond=args.plafond,
        )
    )
    if not compte:
        print("Rien à préparer : tous les exemplaires photographiés ont toutes leurs variantes.")
    else:
        print("\nVerdicts :")
        for cle, valeur in compte.most_common():
            print(f"  {valeur:6d}  {cle}")

    # Les poids réellement produits, puis le budget qu'ils doivent respecter : ce bloc est la
    # preuve qu'on cite dans un compte rendu de lot.
    print("\nPoids produits :")
    print(_distribution(poids))
    print(budget.rapport())

    depassements = budget.depassements()
    for constat in depassements:
        print(f"⛔ budget : {constat}", file=sys.stderr)
    return 1 if depassements else 0


if __name__ == "__main__":
    raise SystemExit(main())
