#!/usr/bin/env python3
"""Passe l'**audit de confidentialité** sur tous les scripts d'effet d'une base — hors requête.

Pourquoi cet outil existe. Le corpus réel de scripts vit en base (`card_scripts`), **pas dans le
dépôt** : la CI ne peut donc pas le lire, et le balayage génératif de
`apps/game/tests/test_securite_scripts_fuite.py` garde le *langage*, pas le *corpus*. Après la
revue de sécurité du jeu (lot `j-securite-jeu`), le chargeur **refuse** un script qui ferait fuir
une carte cachée : un script du corpus qui tomberait dans ce cas rendrait sa carte injouable, en le
disant, mais sans que personne l'ait vu venir. Cet outil permet de le voir **avant**.

À passer sur chaque base qui porte un corpus (dev, UAT, PROD) **avant** une livraison du jeu, et
après chaque passe de génération de scripts :

    uv run python scripts/auditer_scripts_effets.py                 # la base de `settings`
    uv run python scripts/auditer_scripts_effets.py --dsn "postgresql+asyncpg://…"

Lecture **seule** : aucune écriture, aucune migration, rien de lourd (un `SELECT` et un parcours
d'arbre en mémoire). Sortie : une ligne par script fautif, puis un décompte. Code de sortie **1**
s'il reste au moins un script fautif — pour qu'un appel en chaîne s'arrête au lieu de continuer.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from pbm_game.effets.dsl.audit import fuites
from pbm_game.effets.dsl.chargement import ProgrammeInvalide, charger_programme
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pbm_api.config import settings
from pbm_api.models.card_scripts import SCRIPT_STATUT_SCRIPTE, CardScript


async def auditer(dsn: str) -> int:
    """Audite tous les scripts « scriptés » de la base ``dsn`` ; renvoie le nombre de fautifs.

    Les scripts qui ne se chargent plus sont **comptés et nommés** eux aussi : ce n'est pas l'objet
    de l'audit, mais un script illisible rend déjà sa carte injouable, et le taire reviendrait à
    rendre un rapport rassurant sur un corpus cassé.
    """
    moteur = create_async_engine(dsn, pool_pre_ping=True)
    fabrique = async_sessionmaker(moteur, expire_on_commit=False)
    fautifs = 0
    illisibles = 0
    total = 0
    try:
        async with fabrique() as db:
            rows = await db.execute(
                select(CardScript).where(CardScript.statut == SCRIPT_STATUT_SCRIPTE)
            )
            for script in rows.scalars():
                total += 1
                try:
                    programme = charger_programme(script.script)
                except ProgrammeInvalide as exc:
                    illisibles += 1
                    print(
                        f"ILLISIBLE  empreinte={script.text_fingerprint}  {exc}",
                        file=sys.stderr,
                    )
                    continue
                trouvees = fuites(programme)
                if not trouvees:
                    continue
                fautifs += 1
                for fuite in trouvees:
                    print(
                        f"FUITE      empreinte={script.text_fingerprint}  "
                        f"op={fuite.op} zone={fuite.zone} proprietaire={fuite.proprietaire}\n"
                        f"           {fuite.raison}",
                        file=sys.stderr,
                    )
    finally:
        await moteur.dispose()

    print(
        f"\nAudit de confidentialité : {total} script(s) « scripté(s) » examiné(s), "
        f"{fautifs} avec fuite, {illisibles} illisible(s)."
    )
    if fautifs or illisibles:
        print(
            "⚠️  Chaque script listé rend sa carte REFUSÉE à la construction du deck (D9) : "
            "corriger le script, ou assumer que la carte n'est pas jouable."
        )
    return fautifs + illisibles


def main() -> int:
    parseur = argparse.ArgumentParser(description=__doc__)
    parseur.add_argument(
        "--dsn",
        default=None,
        help="DSN SQLAlchemy async ; par défaut celui de la configuration de l'API.",
    )
    args = parseur.parse_args()
    dsn = args.dsn or settings.database_url
    # Le DSN peut porter un mot de passe : on n'affiche jamais que l'hôte et la base.
    sans_secret = dsn.rsplit("@", 1)[-1] if "@" in dsn else dsn
    print(f"Audit des scripts d'effet sur … {sans_secret}")
    return 1 if asyncio.run(auditer(dsn)) else 0


if __name__ == "__main__":
    raise SystemExit(main())
