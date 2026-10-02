"""La **sélection de cibles** — résoudre un :class:`~pbm_game.effets.dsl.modele.Selecteur`.

Module **pur** (aucune E/S). Un sélecteur décrit *quelles* cartes ou Pokémon une instruction
vise ; :func:`candidats` les trouve dans l'état, dans l'ordre naturel de leur zone (le **sommet**
de la pioche est ``pioche[0]`` — même convention que ``journal.transitions``). Le *choix* final
parmi les candidats (quand il y en a plus que ``nombre`` et que la position est ``au_choix``) est
fait par l'interprète, qui tient la stratégie de décision ; ici on ne fait que **trouver**.

Deux formes de cible, parce que l'état sépare cartes et Pokémon en jeu :

* :class:`CibleCarte` — une carte dans une zone de cartes (main, pioche, défausse, récompenses,
  zone perdue, Stade), repérée par son ``instance_id`` **stable** ;
* :class:`CiblePokemon` — un Pokémon en jeu (Actif ou banc), repéré par l'``instance_id`` de sa
  **carte de base** (qui ne change pas à l'évolution — même identité que ``entres_en_jeu_ce_tour``).

Les filtres ``categorie`` et ``stade`` lisent les **métadonnées de catalogue** du contexte : l'état
ne connaît qu'``instance_id`` et ``ref``. Une ``ref`` sans métadonnée n'est **pas** retenue par un
filtre (on ne devine pas, D9) — l'absence de cible qui en résulte est journalisée par la primitive.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...state.modele import EtatPartie, Joueur, carte_active
from .contexte import ContexteEffet
from .modele import Selecteur
from .vocabulaire import (
    CAT_POKEMON,
    PROPRIO_LES_DEUX,
    ZONE_ACTIF,
    ZONE_BANC,
    ZONE_EN_JEU,
    ZONE_STADE,
)

# Les zones de cartes dont le nom est **exactement** l'attribut du Joueur (main, pioche, …).
_ZONES_CARTES_JOUEUR = ("main", "pioche", "defausse", "recompenses", "zone_perdue")


@dataclass(frozen=True)
class CibleCarte:
    """Une carte repérée dans une zone de cartes — ``instance_id`` stable pour la retrouver."""

    joueur: str
    zone: str
    instance_id: str
    ref: str


@dataclass(frozen=True)
class CiblePokemon:
    """Un Pokémon en jeu — repéré par l'``instance_id`` de sa carte de base (identité stable)."""

    joueur: str
    emplacement: str  # "actif" | "banc"
    identite: str
    ref: str


def _joueur(etat: EtatPartie, jid: str) -> Joueur:
    for j in etat.joueurs:
        if j.id == jid:
            return j
    raise ValueError(f"Joueur « {jid} » absent de la partie.")


def _stade_ref(ctx: ContexteEffet, ref: str) -> str | None:
    meta = ctx.metadonnees.get(ref)
    return meta.get("stade") if isinstance(meta, dict) else None


def _categorie_ref(ctx: ContexteEffet, ref: str) -> str | None:
    meta = ctx.metadonnees.get(ref)
    return meta.get("categorie") if isinstance(meta, dict) else None


def candidats(
    etat: EtatPartie, selecteur: Selecteur, ctx: ContexteEffet
) -> list[CibleCarte | CiblePokemon]:
    """Tous les candidats que ``selecteur`` désigne, dans l'ordre naturel de leur zone.

    N'applique **ni** ``nombre`` **ni** le choix ``au_choix`` : c'est l'interprète qui restreint,
    parce que lui seul tient la stratégie de décision. Ici, on trouve l'ensemble éligible.
    """
    resultats: list[CibleCarte | CiblePokemon] = []

    # Le Stade est **unique et global** (R-3.5) : on le traite à part pour ne pas le compter deux
    # fois, et on respecte le propriétaire demandé (celui qui l'a posé).
    if selecteur.zone == ZONE_STADE:
        if etat.stade is not None:
            proprio = etat.stade_proprietaire
            vise = selecteur.proprietaire == PROPRIO_LES_DEUX or (
                proprio in ctx.ids_proprietaire(selecteur.proprietaire)
            )
            if vise:
                resultats.append(
                    CibleCarte(proprio or "", ZONE_STADE, etat.stade.instance_id, etat.stade.ref)
                )
        return resultats

    for jid in ctx.ids_proprietaire(selecteur.proprietaire):
        joueur = _joueur(etat, jid)

        # Pokémon en jeu (Actif / banc / les deux).
        if selecteur.zone in (ZONE_ACTIF, ZONE_BANC, ZONE_EN_JEU):
            # Un sélecteur de Pokémon ne peut filtrer que sur la catégorie « pokemon ».
            if selecteur.categorie not in (None, CAT_POKEMON):
                continue
            en_jeu: list[tuple[str, object]] = []
            if selecteur.zone in (ZONE_ACTIF, ZONE_EN_JEU) and joueur.actif is not None:
                en_jeu.append(("actif", joueur.actif))
            if selecteur.zone in (ZONE_BANC, ZONE_EN_JEU):
                en_jeu.extend(("banc", p) for p in joueur.banc)
            for emplacement, pok in en_jeu:
                ref = carte_active(pok).ref
                if selecteur.stade is not None and _stade_ref(ctx, ref) != selecteur.stade:
                    continue
                resultats.append(CiblePokemon(jid, emplacement, pok.cartes[0].instance_id, ref))
            continue

        # Zones de cartes (main, pioche, défausse, récompenses, zone perdue).
        if selecteur.zone in _ZONES_CARTES_JOUEUR:
            for carte in getattr(joueur, selecteur.zone):
                if (
                    selecteur.categorie is not None
                    and _categorie_ref(ctx, carte.ref) != selecteur.categorie
                ):
                    continue
                if selecteur.stade is not None and _stade_ref(ctx, carte.ref) != selecteur.stade:
                    continue
                resultats.append(CibleCarte(jid, selecteur.zone, carte.instance_id, carte.ref))
            continue

        raise ValueError(f"Zone non gérée par la sélection : {selecteur.zone!r}.")

    return resultats


__all__ = ["CibleCarte", "CiblePokemon", "candidats"]
