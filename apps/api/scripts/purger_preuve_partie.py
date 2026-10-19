#!/usr/bin/env python
"""Supprime ce que la preuve de partie a créé en production, et le prouve.

Pendant de ``prouver_partie_prod.py`` et de ``seed_partie_e2e.py`` : une preuve qui laisse des
comptes et des cartes derrière elle salit la base qu'elle était censée valider. Les livraisons
précédentes supprimaient à la main ; ce script le fait de façon bornée et répétable.

⛔ **Bornes dures, parce qu'un `DELETE` non borné en production ne se rattrape pas** :

* seuls les comptes dont l'adresse correspond à ``MOTIFS_EMAIL`` sont touchés ;
* seule l'extension de code :data:`SET_CODE` (celle du seed) et ses cartes sont touchées ;
* au-delà de :data:`PLAFOND_COMPTES` comptes visés, le script **s'arrête sans rien supprimer** —
  c'est le signe que le motif attrape autre chose que les comptes de preuve ;
* ``--a-blanc`` montre ce qu'il ferait sans rien écrire. À lancer d'abord, toujours.

    .venv/bin/python scripts/purger_preuve_partie.py --a-blanc
    .venv/bin/python scripts/purger_preuve_partie.py
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import delete, func, or_, select

from pbm_api.db import async_session_factory
from pbm_api.models import Card, Deck, Set, User
from pbm_api.models.games import Game, GamePlayer

SET_CODE = "e2epartie"
MOTIFS_EMAIL = ("preuve-%@example.com", "preuve-%@pokeboy.invalid")
PLAFOND_COMPTES = 6


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--a-blanc", action="store_true", help="montre sans rien supprimer")
    args = ap.parse_args()

    async with async_session_factory() as session:
        comptes = list(
            (
                await session.execute(
                    select(User).where(or_(*(User.email.like(m) for m in MOTIFS_EMAIL)))
                )
            ).scalars()
        )
        print(f"comptes de preuve visés : {len(comptes)}")
        for u in comptes:
            print(f"  - {u.email} ({u.id})")
        if len(comptes) > PLAFOND_COMPTES:
            print(f"⛔ plafond de {PLAFOND_COMPTES} dépassé — rien supprimé, le motif attrape trop")
            return 1

        ids = [u.id for u in comptes]
        parties = decks = 0
        if ids:
            parties_ids = list(
                (
                    await session.execute(
                        select(GamePlayer.game_id).where(GamePlayer.user_id.in_(ids)).distinct()
                    )
                ).scalars()
            )
            parties = len(parties_ids)
            decks = (
                await session.execute(
                    select(func.count()).select_from(Deck).where(Deck.user_id.in_(ids))
                )
            ).scalar_one()
        print(f"parties liées : {parties} · decks liés : {decks}")

        ext = (
            await session.execute(select(Set).where(Set.code == SET_CODE))
        ).scalar_one_or_none()
        cartes = 0
        if ext is not None:
            cartes = (
                await session.execute(
                    select(func.count()).select_from(Card).where(Card.set_id == ext.id)
                )
            ).scalar_one()
        print(f"extension « {SET_CODE} » : {'présente' if ext else 'absente'} · cartes : {cartes}")

        if args.a_blanc:
            print("À BLANC — rien n'a été écrit")
            return 0

        # Ordre imposé par les clés étrangères : les parties et les decks d'abord (ils citent les
        # cartes de test ET les comptes), puis les comptes, puis les cartes et leur extension.
        if ids:
            if parties_ids:
                # `game_players` d'abord (il cite la partie ET le compte), puis les parties :
                # les événements et instantanés partent en cascade avec elles.
                await session.execute(delete(GamePlayer).where(GamePlayer.game_id.in_(parties_ids)))
                await session.execute(delete(Game).where(Game.id.in_(parties_ids)))
            await session.execute(delete(Deck).where(Deck.user_id.in_(ids)))
            await session.execute(delete(User).where(User.id.in_(ids)))
        if ext is not None:
            await session.execute(delete(Card).where(Card.set_id == ext.id))
            await session.execute(delete(Set).where(Set.id == ext.id))
        await session.commit()

        # Preuve de suppression : on recompte après coup, on ne se fie pas au fait d'avoir appelé.
        restants = (
            await session.execute(
                select(func.count())
                .select_from(User)
                .where(or_(*(User.email.like(m) for m in MOTIFS_EMAIL)))
            )
        ).scalar_one()
        ext_restante = (
            await session.execute(select(func.count()).select_from(Set).where(Set.code == SET_CODE))
        ).scalar_one()
        print(f"APRÈS — comptes de preuve : {restants} · extension « {SET_CODE} » : {ext_restante}")
        return 0 if restants == 0 and ext_restante == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
