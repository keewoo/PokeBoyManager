"""Produit les **variantes de jeu** du corpus existant (lot ``j-rendu-carte``).

Les exemplaires photographiés avant ce lot n'ont ni variante ni note de qualité : en partie, ils se
replient sur l'image officielle **en le disant** (``RAISON_PAS_PRETE``). C'est correct, mais ce
n'est pas ce que le joueur attend — il veut voir SA carte. Ce script rattrape le corpus d'un coup.

À lancer **sur la flotte**, jamais sur la machine qui sert (règle du dépôt) : il décode et réencode
une image par exemplaire photographié.

    uv run python scripts/preparer_rendus_jeu.py --lot 200          # tout le corpus, par paquets
    uv run python scripts/preparer_rendus_jeu.py --utilisateur <id> # un seul compte
    uv run python scripts/preparer_rendus_jeu.py --a-blanc          # ce qu'il FERAIT, sans écrire

Reprenable : il ne traite que les exemplaires dont la note manque (``jeu_qualite IS NULL``), donc
un second passage ne refait rien. Aucun repli silencieux — chaque exemplaire traité est compté, et
le détail des replis est affiché à la fin.
"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from collections import Counter

from sqlalchemy import select

from pbm_api.db import async_session_factory
from pbm_api.jeu.rendu_service import preparer_variante
from pbm_api.models import CollectionItem
from pbm_api.storage import build_storage


async def _traiter(
    *, lot: int, utilisateur: uuid.UUID | None, a_blanc: bool, plafond: int | None
) -> Counter:
    """Prépare les variantes manquantes et rend le compte par verdict."""
    compte: Counter = Counter()
    storage = build_storage()
    traites = 0
    while plafond is None or traites < plafond:
        async with async_session_factory() as db:
            requete = (
                select(CollectionItem)
                .where(
                    CollectionItem.photo_s3_key.isnot(None),
                    CollectionItem.jeu_qualite.is_(None),
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
                else:
                    compte[f"repli: {note.raison}"] += 1
            if a_blanc:
                # À blanc on n'écrit pas, donc le même paquet reviendrait indéfiniment.
                break
            await db.commit()
            traites += len(items)
            print(f"… {traites} exemplaires traités", flush=True)
    return compte


def main() -> int:
    """Point d'entrée : analyse les options, lance la préparation, affiche le compte."""
    parseur = argparse.ArgumentParser(description=__doc__)
    parseur.add_argument("--lot", type=int, default=200, help="taille d'un paquet (défaut 200)")
    parseur.add_argument("--utilisateur", type=str, default=None, help="limiter à un compte")
    parseur.add_argument("--plafond", type=int, default=None, help="s'arrêter après N exemplaires")
    parseur.add_argument("--a-blanc", action="store_true", help="ne rien écrire, juste compter")
    args = parseur.parse_args()

    compte = asyncio.run(
        _traiter(
            lot=args.lot,
            utilisateur=uuid.UUID(args.utilisateur) if args.utilisateur else None,
            a_blanc=args.a_blanc,
            plafond=args.plafond,
        )
    )
    if not compte:
        print("Rien à préparer : tous les exemplaires photographiés ont déjà leur note.")
        return 0
    print("\nVerdicts :")
    for cle, valeur in compte.most_common():
        print(f"  {valeur:6d}  {cle}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
