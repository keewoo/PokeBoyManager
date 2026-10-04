"""Accès base au registre `card_scripts` : lire, enregistrer, valider un script d'effet.

Ce module **lit et écrit la base** (il vit donc dans `apps/api`, jamais dans le moteur pur
`pbm_game`). Il isole le reste du code des requêtes SQLAlchemy : le chargeur, la détection d'errata
et la commande de maintenance passent tous par ici.

Convention de persistance du dépôt (comme le reste de `pbm_api`) : les fonctions qui modifient
l'état **commitent** — un appelant qui enregistre un script s'attend à ce qu'il soit durable.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.jeu.scripts.empreinte import empreinte_texte
from pbm_api.models.card_scripts import (
    SCRIPT_STATUT_SCRIPTE,
    SCRIPT_STATUTS,
    CardScript,
)


async def script_par_empreinte(db: AsyncSession, empreinte: str) -> CardScript | None:
    """Le script enregistré pour une empreinte de texte, ou ``None`` si aucun n'existe."""
    return (
        await db.execute(select(CardScript).where(CardScript.text_fingerprint == empreinte))
    ).scalar_one_or_none()


async def scripts_par_empreintes(
    db: AsyncSession, empreintes: Iterable[str]
) -> dict[str, CardScript]:
    """Les scripts enregistrés pour un ensemble d'empreintes, indexés par empreinte.

    Une empreinte absente du résultat n'a **aucun** script : le chargeur en fait un refus (D9). On
    charge en une requête (``IN``) plutôt qu'une par carte — le lancement d'une partie touche vite
    des dizaines d'empreintes.
    """
    cles = list({e for e in empreintes if e})
    if not cles:
        return {}
    lignes = (
        await db.execute(select(CardScript).where(CardScript.text_fingerprint.in_(cles)))
    ).scalars()
    return {s.text_fingerprint: s for s in lignes}


async def tous_les_scripts(db: AsyncSession) -> list[CardScript]:
    """Tout le registre, ordonné par statut puis empreinte — pour lister et pour l'errata."""
    return list(
        (
            await db.execute(
                select(CardScript).order_by(CardScript.statut, CardScript.text_fingerprint)
            )
        ).scalars()
    )


async def enregistrer_script(
    db: AsyncSession,
    *,
    source_text: str,
    statut: str,
    dsl_version: int,
    script: dict | None = None,
    lang: str | None = None,
    author: str | None = None,
    tests: list | None = None,
    notes: str | None = None,
) -> CardScript:
    """Enregistre (ou met à jour) le script d'un texte d'effet, repéré par son empreinte.

    L'empreinte est **calculée** depuis ``source_text`` (jamais fournie à la main : elle doit rester
    cohérente avec ce que le chargeur recalcule sur le texte vivant de la carte). Rejouable :
    réenregistrer la même empreinte **met à jour** la ligne existante plutôt que d'en créer une
    seconde (l'empreinte est unique). Lève :class:`ValueError` si le statut est inconnu ou si un
    statut ``scripte`` arrive sans programme.

    La date de validation (``validated_at``) est posée **ici** quand le statut passe à ``scripte`` :
    c'est le dépôt qui tient l'horodatage, pas l'appelant (la validation est un fait d'exploitation,
    pas une donnée de partie rejouable où un ``_maintenant`` injecté aurait un sens).
    """
    if statut not in SCRIPT_STATUTS:
        raise ValueError(f"Statut inconnu : {statut!r} (connus : {sorted(SCRIPT_STATUTS)}).")
    if statut == SCRIPT_STATUT_SCRIPTE and script is None:
        raise ValueError("Un script « scripté » doit porter un programme (D9 : rien de deviné).")
    empreinte = empreinte_texte(source_text)
    ligne = await script_par_empreinte(db, empreinte)
    if ligne is None:
        ligne = CardScript(text_fingerprint=empreinte, source_text=source_text)
        db.add(ligne)
    ligne.source_text = source_text
    ligne.lang = lang
    ligne.dsl_version = dsl_version
    ligne.script = script
    ligne.statut = statut
    ligne.author = author
    ligne.tests = tests
    ligne.notes = notes
    ligne.validated_at = datetime.now(UTC) if statut == SCRIPT_STATUT_SCRIPTE else None
    await db.commit()
    await db.refresh(ligne)
    return ligne


__all__ = [
    "script_par_empreinte",
    "scripts_par_empreintes",
    "tous_les_scripts",
    "enregistrer_script",
]
