"""Lecture et écriture des réglages **globaux** du jeu en base (lot `j-classement-prive`, DJ6).

La seule couche qui touche :class:`pbm_api.models.jeu_reglages.JeuReglage`. Le vocabulaire et les
défauts vivent dans :mod:`pbm_api.jeu.reglages` (pur) ; l'écriture n'est atteignable que par la
commande d'administration :mod:`pbm_api.admin` — **aucune route HTTP n'écrit ici**, et c'est
délibéré : « activable par JF » (DJ6) veut dire par JF sur le serveur, pas par un compte muni du
bon cookie.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.jeu.reglages import REGLAGES, declaration, interpreter, valider
from pbm_api.models import JeuReglage


async def lire(db: AsyncSession, cle: str) -> str:
    """La valeur **effective** d'un réglage : celle en base, ou son défaut déclaré.

    Lève :class:`~pbm_api.jeu.reglages.ReglageInconnu` sur une clé non déclarée — un appelant qui se
    trompe de clé doit l'apprendre, pas recevoir un défaut plausible.
    """
    declaration(cle)  # lève si la clé n'existe pas, avant de parler à la base
    stockee = (
        await db.execute(select(JeuReglage.valeur).where(JeuReglage.cle == cle))
    ).scalar_one_or_none()
    return interpreter(cle, stockee)


async def lire_stockees(db: AsyncSession) -> dict[str, str]:
    """Les valeurs réellement **écrites** en base, clé par clé (sans les défauts).

    Sert à la commande d'administration, qui montre à JF la valeur stockée *et* la valeur effective
    : c'est ce qui rend visible le cas d'une valeur devenue illisible (barème supprimé depuis),
    pour lequel :func:`~pbm_api.jeu.reglages.interpreter` rend le défaut.
    """
    lignes = (await db.execute(select(JeuReglage.cle, JeuReglage.valeur))).all()
    return {cle: valeur for cle, valeur in lignes}


async def ecrire(db: AsyncSession, cle: str, valeur: str) -> str:
    """Pose la valeur d'un réglage global et **commite** ; rend la valeur normalisée écrite.

    Valide d'abord (clé déclarée, valeur dans le vocabulaire) : une faute de frappe lève, elle
    n'écrit pas une ligne que personne ne lira jamais. L'écriture est un ``ON CONFLICT DO UPDATE``
    — poser deux fois la même valeur est sans effet, et deux commandes concurrentes ne se
    marchent pas dessus.
    """
    normalisee = valider(cle, valeur)
    await db.execute(
        pg_insert(JeuReglage)
        .values(cle=cle, valeur=normalisee)
        .on_conflict_do_update(index_elements=["cle"], set_={"valeur": normalisee})
    )
    await db.commit()
    return normalisee


async def etat_complet(db: AsyncSession) -> list[tuple[str, str | None, str]]:
    """Pour chaque réglage déclaré : ``(clé, valeur stockée ou None, valeur effective)``.

    Trié par clé, pour que la sortie de la commande d'administration soit stable d'un jour à
    l'autre.
    """
    stockees = await lire_stockees(db)
    return [
        (cle, stockees.get(cle), interpreter(cle, stockees.get(cle))) for cle in sorted(REGLAGES)
    ]


__all__ = ["ecrire", "etat_complet", "lire", "lire_stockees"]
