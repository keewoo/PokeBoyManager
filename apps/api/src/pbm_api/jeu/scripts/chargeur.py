"""Le **chargeur de scripts** : résout chaque carte d'un deck vers son script validé, ou refuse.

Au lancement d'une partie, chaque carte qui porte un effet doit se résoudre vers un script
**scripté, lisible, valide**. Une seule carte sans script valide fait **refuser la partie** — avant
la mise en place, jamais en plein milieu (critère n°3). C'est la porte D9 du jeu : « je ne sais pas
jouer cette carte » plutôt que la jouer de travers.

Ce module lit la base (il vit dans `apps/api`) ; le moteur `pbm_game` reste pur. Il appuie sa
décision sur deux choses, et uniquement elles : l'**empreinte** du texte vivant de la carte
(:mod:`pbm_api.jeu.scripts.empreinte`) et le registre `card_scripts` (:mod:`.depot`). Un script
marqué ``scripte`` est **rechargé par l'interprète** (``charger_programme``) avant d'être accepté :
une version future, un ``op`` disparu du vocabulaire, une clé devenue invalide sont attrapés ici,
au chargement — pas en pleine partie.

**Un deck de cartes sans effet (dégâts secs, Énergies de base) ne déclenche aucun refus** : ces
cartes n'ont aucune empreinte à exiger. Le chargeur ne resserre donc le jeu que là où un effet
existe réellement — exactement le passage du jalon J1 (« la carte est posable ») au J2 (« ce que la
carte dit, le moteur le fait »).
"""

from __future__ import annotations

import uuid

from pbm_game.effets.dsl.chargement import ProgrammeInvalide, charger_programme
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.jeu.scripts.depot import scripts_par_empreintes
from pbm_api.jeu.scripts.empreinte import EffetCarte, effets_scriptables
from pbm_api.models import Card, DeckCard
from pbm_api.models.card_scripts import (
    SCRIPT_STATUT_A_REVOIR,
    SCRIPT_STATUT_NON_SUPPORTE,
    SCRIPT_STATUT_SCRIPTE,
    CardScript,
)


def _libelle_effet(nom_carte: str, effet: EffetCarte) -> str:
    """« Carte (talent « Fouille ») » — nomme la carte ET l'effet fautif, pour un refus lisible."""
    if effet.intitule:
        return f"{nom_carte} ({effet.origine} « {effet.intitule} »)"
    return f"{nom_carte} ({effet.origine})"


def _raison_refus(effet: EffetCarte, script: CardScript | None) -> str | None:
    """La raison pour laquelle un effet n'est pas jouable, ou ``None`` s'il l'est (D9, nommé).

    Un script absent, « à revoir » (texte modifié ou jamais validé), « non supporté » (hors
    langage), ou dont le programme ne se recharge plus (version future, vocabulaire changé) : chacun
    bloque, et le dit. On ne devine jamais un effet neutre pour « débloquer ».
    """
    if script is None:
        return "aucun script pour ce texte d'effet — effet non implémenté, carte refusée (D9)"
    if script.statut == SCRIPT_STATUT_A_REVOIR:
        return "script « à revoir » (texte modifié en base, ou jamais validé) — ne se joue plus"
    if script.statut == SCRIPT_STATUT_NON_SUPPORTE:
        motif = f" ({script.notes})" if script.notes else ""
        return f"effet non supporté par le langage v1 — carte refusée, jamais approximée{motif}"
    if script.statut != SCRIPT_STATUT_SCRIPTE:
        return f"statut de script inattendu « {script.statut} » — refus (jamais joué « au mieux »)"
    # Statut « scripté » : dernière garde, on recharge le programme par l'interprète (pur).
    try:
        charger_programme(script.script)
    except ProgrammeInvalide as exc:
        return f"script invalide au rechargement ({exc}) — refus avant la partie"
    return None


async def refus_scripts_cartes(
    db: AsyncSession, cartes: list[Card]
) -> list[tuple[str, str]]:
    """Les cartes du lot dont un effet n'a pas de script valide, en ``(libellé, raison)``.

    Collecte d'abord **toutes** les empreintes exigées (une requête, pas une par carte), puis juge
    chaque effet. Une carte peut apparaître plusieurs fois si elle porte plusieurs effets non
    scriptés — chacun est nommé. Liste vide = tout est jouable.
    """
    # Imports locaux : `catalogue`/`couverture_jeu` importent (par `scripts.empreinte`) ce paquet —
    # les charger au niveau module ferait un cycle. On les charge à l'appel, où tout est en place.
    from pbm_api.jeu.catalogue import ref_catalogue
    from pbm_api.jeu.couverture_jeu import effet_couvert_hors_dsl

    exigences: list[tuple[Card, EffetCarte]] = []
    for card in cartes:
        ref = ref_catalogue(card)
        for effet in effets_scriptables(card):
            # Outils, Stades et talents activés sont scriptés **hors** du registre DSL (moteur /
            # fiche écrite à la main) : leur effet est déjà implémenté et testé ailleurs, il n'exige
            # donc aucune ligne `card_scripts` (D9 — pas d'approximation, une vraie couverture).
            if effet_couvert_hors_dsl(ref, effet.origine):
                continue
            exigences.append((card, effet))
    if not exigences:
        return []

    scripts = await scripts_par_empreintes(db, (effet.empreinte for _, effet in exigences))

    refus: list[tuple[str, str]] = []
    for card, effet in exigences:
        raison = _raison_refus(effet, scripts.get(effet.empreinte))
        if raison is not None:
            nom = getattr(card, "name", None) or str(getattr(card, "id", "?"))
            refus.append((_libelle_effet(nom, effet), raison))
    return refus


async def refus_scripts_par_carte(
    db: AsyncSession, cartes: list[Card]
) -> dict[uuid.UUID, str]:
    """Les cartes dont un effet n'est pas jouable, en ``{card_id: première raison bloquante}``.

    Même jugement que :func:`refus_scripts_cartes`, mais **indexé par carte** (une seule raison par
    carte, celle du premier effet fautif) : c'est ce dont la légalité d'un deck a besoin pour
    marquer *quelle* carte est bloquée, et dire pourquoi (le constat « effet non supporté » du
    constructeur, `v7-decks-legalite`). La raison est **indépendante du deck** : un même ``card_id``
    donne toujours la même raison, donc on peut calculer la carte une fois et réutiliser.
    """
    from pbm_api.jeu.catalogue import ref_catalogue
    from pbm_api.jeu.couverture_jeu import effet_couvert_hors_dsl

    exigences: list[tuple[Card, EffetCarte]] = []
    for card in cartes:
        ref = ref_catalogue(card)
        for effet in effets_scriptables(card):
            if effet_couvert_hors_dsl(ref, effet.origine):
                continue  # couvert hors DSL (Outil/Stade/talent) — aucun script `card_scripts` dû
            exigences.append((card, effet))
    if not exigences:
        return {}

    scripts = await scripts_par_empreintes(db, (effet.empreinte for _, effet in exigences))

    refus: dict[uuid.UUID, str] = {}
    for card, effet in exigences:
        card_id = getattr(card, "id", None)
        if card_id is None or card_id in refus:
            continue  # première raison seulement : le constructeur en affiche une par carte
        raison = _raison_refus(effet, scripts.get(effet.empreinte))
        if raison is not None:
            refus[card_id] = raison
    return refus


async def refus_scripts_deck(db: AsyncSession, deck_id: uuid.UUID) -> list[tuple[str, str]]:
    """Les cartes d'un deck dont un effet n'a pas de script valide, en ``(libellé, raison)``.

    Charge les ``Card`` complètes du deck (l'extraction d'effets lit ``abilities``/``attacks``/
    ``effect``), puis délègue à :func:`refus_scripts_cartes`. Ne lève pas : l'appelant décide quoi
    faire d'un refus (la file et le lancement en font un 422 nommé).
    """
    cartes = list(
        (
            await db.execute(
                select(Card).join(DeckCard, DeckCard.card_id == Card.id).where(
                    DeckCard.deck_id == deck_id
                )
            )
        ).scalars()
    )
    return await refus_scripts_cartes(db, cartes)


__all__ = ["refus_scripts_cartes", "refus_scripts_par_carte", "refus_scripts_deck"]
