"""La **détection d'errata** : un texte de carte qui change fait repasser son script « à revoir ».

Le catalogue vit : une correction d'import, une *errata* officielle, et le texte d'une carte change
en base. Son empreinte ne correspond alors plus à celle du script qui la couvrait. Ce module
réconcilie le registre `card_scripts` avec le catalogue vivant (critère n°1).

**Le mécanisme, et pourquoi il suffit.** Un script est repéré par l'empreinte de son texte source.
Si plus **aucune** carte du catalogue ne porte ce texte (après normalisation), c'est que le texte a
changé partout où il existait : le script est **orphelin**, il décrit un effet que le jeu ne
rencontrera plus tel quel. On le fait passer ``scripte`` → ``a_revoir`` : il ne se joue plus tant
qu'une relecture ne l'a pas reconfirmé contre le nouveau texte.

Deux garde-fous que ce mécanisme offre **sans rien de plus** :

* la carte dont le texte a changé exige désormais une **nouvelle** empreinte, pour laquelle aucun
  script n'existe : le chargeur la refuse déjà, et le deck le dit (critère n°1, versant carte) ;
* on ne « rebascule » jamais un ``a_revoir`` en ``scripte`` automatiquement : la revalidation est un
  acte explicite (``valider``), jamais deviné (D9). La détection ne fait que **soulever** le doute.

Ce module lit (beaucoup) la base : il parcourt le catalogue. Il tourne en commande de maintenance,
jamais sur le chemin d'une requête.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.jeu.scripts.empreinte import effets_scriptables
from pbm_api.models import Card
from pbm_api.models.card_scripts import (
    SCRIPT_STATUT_A_REVOIR,
    SCRIPT_STATUT_SCRIPTE,
    CardScript,
)


async def empreintes_vivantes(db: AsyncSession) -> set[str]:
    """L'ensemble des empreintes de **tous** les textes d'effet présents dans le catalogue ce jour.

    Parcourt les cartes en **flux** (``stream``, pas tout en mémoire d'un coup) et ne lit que les
    quatre champs utiles à l'extraction (``abilities``, ``attacks``, ``effect``, plus
    ``name``/``id`` pour la robustesse). Le résultat est la vérité du jour : une empreinte absente
    d'ici n'est plus portée par aucune carte.
    """
    vivantes: set[str] = set()
    resultat = await db.stream(
        select(Card.id, Card.name, Card.abilities, Card.attacks, Card.effect)
    )
    async for row in resultat:
        vivantes.update(effet.empreinte for effet in effets_scriptables(row))
    return vivantes


async def detecter_errata(db: AsyncSession, *, appliquer: bool = True) -> list[CardScript]:
    """Fait repasser « à revoir » les scripts ``scripte`` dont le texte source a disparu du jeu.

    Renvoie la liste des scripts concernés (ceux dont l'empreinte n'est plus vivante). Avec
    ``appliquer=True`` (défaut), la bascule est **écrite et commitée** ; avec ``appliquer=False``,
    rien n'est modifié (mode « à blanc » de la commande de maintenance : montrer avant d'agir).

    Ne touche **que** les scripts ``scripte`` : un ``non_supporte`` reste une décision explicite, un
    ``a_revoir`` est déjà soulevé. La note du script conserve la trace du jour de la bascule, sans
    jamais effacer le programme (la relecture en aura besoin pour comparer à l'ancien).
    """
    vivantes = await empreintes_vivantes(db)
    scriptes = list(
        (
            await db.execute(
                select(CardScript).where(CardScript.statut == SCRIPT_STATUT_SCRIPTE)
            )
        ).scalars()
    )
    orphelins = [s for s in scriptes if s.text_fingerprint not in vivantes]
    if appliquer and orphelins:
        quand = datetime.now(UTC).date().isoformat()
        for s in orphelins:
            s.statut = SCRIPT_STATUT_A_REVOIR
            s.validated_at = None
            trace = f"errata {quand} : texte source absent du catalogue, revalidation requise"
            s.notes = f"{s.notes} | {trace}" if s.notes else trace
        await db.commit()
    return orphelins


__all__ = ["empreintes_vivantes", "detecter_errata"]
