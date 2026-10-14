"""Lecture et écriture des réglages de **confort** (lot ``j-accessibilite-jeu``).

La seule couche qui touche la base pour ces réglages : la décision vit dans
:mod:`pbm_api.jeu.confort` (pure), les routes dans :mod:`pbm_api.routers.jeu_confort`, et le
lancement d'une partie n'appelle d'ici que :func:`temps_rallonge_des_joueurs`.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.jeu.confort import (
    ANIMATIONS,
    TAILLES_TEXTE,
    ReglagesConfort,
    temps_rallonge_partie,
)
from pbm_api.models import JeuConfortReglages


class ConfortValeurInvalide(ValueError):
    """Une valeur hors vocabulaire (:data:`~pbm_api.jeu.confort.ANIMATIONS` / ``TAILLES_TEXTE``)."""


def _depuis_ligne(ligne: JeuConfortReglages | None) -> ReglagesConfort:
    """Traduit la ligne de base en vue pure, ou rend les défauts si le compte n'en a pas.

    C'est ici que « pas de ligne » devient « les défauts », une fois pour toutes — aucun appelant
    n'a à connaître cette convention.
    """
    if ligne is None:
        return ReglagesConfort()
    return ReglagesConfort(
        animations=ligne.animations,
        taille_texte=ligne.taille_texte,
        temps_rallonge=ligne.temps_rallonge,
    )


async def charger_reglages(db: AsyncSession, user_id: uuid.UUID) -> ReglagesConfort:
    """Les réglages de confort du compte — les défauts s'il n'y a jamais touché."""
    return _depuis_ligne(await db.get(JeuConfortReglages, user_id))


async def enregistrer_reglages(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    animations: str | None = None,
    taille_texte: str | None = None,
    temps_rallonge: bool | None = None,
) -> ReglagesConfort:
    """Écrit les réglages (création de la ligne au premier passage) et rend l'état complet.

    Modification **partielle** : seuls les champs fournis changent — l'écran peut couper les
    animations sans renvoyer la taille du texte, donc sans écraser un réglage changé dans un autre
    onglet. Une valeur hors vocabulaire lève :class:`ConfortValeurInvalide` **avant** toute
    écriture : rien n'est enregistré à moitié.
    """
    if animations is not None and animations not in ANIMATIONS:
        raise ConfortValeurInvalide(
            f"animations « {animations} » inconnu (attendus : {sorted(ANIMATIONS)})"
        )
    if taille_texte is not None and taille_texte not in TAILLES_TEXTE:
        raise ConfortValeurInvalide(
            f"taille_texte « {taille_texte} » inconnue (attendues : {sorted(TAILLES_TEXTE)})"
        )
    ligne = await db.get(JeuConfortReglages, user_id)
    if ligne is None:
        defauts = ReglagesConfort()
        ligne = JeuConfortReglages(
            user_id=user_id,
            animations=defauts.animations,
            taille_texte=defauts.taille_texte,
            temps_rallonge=defauts.temps_rallonge,
        )
        db.add(ligne)
    if animations is not None:
        ligne.animations = animations
    if taille_texte is not None:
        ligne.taille_texte = taille_texte
    if temps_rallonge is not None:
        ligne.temps_rallonge = temps_rallonge
    await db.flush()
    return _depuis_ligne(ligne)


async def temps_rallonge_des_joueurs(
    db: AsyncSession, user_ids: Iterable[uuid.UUID]
) -> bool:
    """Vrai si **au moins un** des comptes cités a demandé le temps rallongé (DJ4).

    Une seule requête pour les deux joueurs : appelé sur le chemin de création d'une partie, qui
    tourne déjà sous verrou (:func:`pbm_api.games.service.verrouiller_creations`) — on n'y ajoute
    pas deux allers-retours. Un compte sans ligne compte pour ses défauts, donc pour « non ».
    """
    ids = list(user_ids)
    if not ids:
        return False
    lignes = (
        (
            await db.execute(
                select(JeuConfortReglages).where(JeuConfortReglages.user_id.in_(ids))
            )
        )
        .scalars()
        .all()
    )
    return temps_rallonge_partie(*(_depuis_ligne(ligne) for ligne in lignes))


__all__ = [
    "ConfortValeurInvalide",
    "charger_reglages",
    "enregistrer_reglages",
    "temps_rallonge_des_joueurs",
]
