"""Résolution complète d'une **attaque déclarée** — coût, dégâts, K.O. (R-9, R-10, R-13).

Module **pur** (aucune E/S). Il **branche** sur la déclaration d'attaque la machinerie déjà livrée :
:func:`pbm_game.combat.cout.payer_cout` (R-9.2), :func:`pbm_game.combat.resolution.resoudre_degats`
(l'ordre strict R-10) et :func:`pbm_game.combat.fin.resoudre_kos` (K.O., récompenses, conditions de
victoire — R-13/R-14). ``j-degats-resolution`` et ``j-ko-recompenses`` avaient livré ce calcul ;
rien ne l'appelait depuis une attaque (la transition ne faisait que terminer le tour,
``degats: 0``).
C'est ``j-coups-joueur`` qui l'appelle.

**Le moteur ne devine rien (D9).** L'action ``declarer_attaque`` porte, depuis le catalogue (fourni
par le service, transporté par le journal) : l'``attaque`` choisie (coût, dégâts secs, type), les
``energies`` attachées à l'Actif (pour payer le coût), la ``faiblesse``/``resistance`` de l'Actif
adverse (R-10.2/R-10.3) et les ``fiches`` PV/marqueur des Pokémon en jeu (pour la mise K.O.). Une
attaque **à effet** (texte non vide) n'est pas scriptée au jalon J1 : elle est refusée (R-15.12/D9),
jamais approximée.

Cette fonction **n'entre pas** en Checkup : c'est la transition ``declarer_attaque`` qui termine le
tour (R-5.8), sauf si l'attaque a déjà terminé la partie.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from ..journal.modele import EVT_ATTAQUE_DECLAREE, Action, Evenement
from ..state.modele import EtatPartie, Joueur, carte_active
from .cout import EnergieAttachee, payer_cout
from .fin import resoudre_kos
from .modele import CoutAttaque, Faiblesse, Resistance
from .resolution import evenement_degats, poser_degats, resoudre_degats


def _index_joueur(etat: EtatPartie, jid: str) -> int:
    for i, joueur in enumerate(etat.joueurs):
        if joueur.id == jid:
            return i
    raise ValueError(f"Joueur « {jid} » absent de la partie.")


def _remplacer_joueur(etat: EtatPartie, index: int, joueur: Joueur) -> EtatPartie:
    joueurs = list(etat.joueurs)
    joueurs[index] = joueur
    return replace(etat, joueurs=(joueurs[0], joueurs[1]))


def _autre_joueur(etat: EtatPartie, jid: str) -> str:
    a, b = etat.joueurs[0].id, etat.joueurs[1].id
    if jid == a:
        return b
    if jid == b:
        return a
    raise ValueError(f"Joueur « {jid} » absent de la partie.")


def _cout_depuis(brut: object) -> CoutAttaque:
    if not isinstance(brut, Mapping):
        return CoutAttaque()
    return CoutAttaque(types=dict(brut.get("types", {})), incolore=brut.get("incolore", 0))


def _energies_depuis(brut: object) -> list[EnergieAttachee]:
    """Les énergies attachées à l'Actif, telles que le service les a extraites (R-9.2)."""
    if brut is None:
        return []
    if not isinstance(brut, (list, tuple)):
        raise ValueError("« energies » doit être une liste de fournitures d'énergie (R-9.2).")
    energies: list[EnergieAttachee] = []
    for e in brut:
        if not isinstance(e, Mapping):
            raise ValueError("Chaque énergie attachée se décrit par un mapping (R-9.2).")
        energies.append(
            EnergieAttachee(
                instance_id=e.get("instance_id", ""),
                fournit=dict(e.get("fournit", {})),
                libelle=e.get("libelle", ""),
            )
        )
    return energies


def _faiblesse_depuis(brut: object) -> Faiblesse | None:
    if not isinstance(brut, Mapping):
        return None
    return Faiblesse(type=brut.get("type", ""), facteur=brut.get("facteur", 2))


def _resistance_depuis(brut: object) -> Resistance | None:
    if not isinstance(brut, Mapping):
        return None
    return Resistance(type=brut.get("type", ""), reduction=brut.get("reduction", 30))


def resoudre_attaque_declaree(
    etat: EtatPartie, action: Action, jid: str, attaque_a_lieu: bool, rng: object
) -> tuple[EtatPartie, list[Evenement]]:
    """Résout le coût, les dégâts et les K.O. d'une attaque déclarée par ``jid`` (R-9/R-10/R-13).

    ``attaque_a_lieu`` est le verdict des états **avant** l'attaque (``pbm_game.etats.attaque``) :
    faux signifie que la Confusion est tombée sur pile — l'attaque ne porte alors aucun dégât
    (l'auto-blessure a déjà été posée par l'appelant), mais le coût **reste payé** (R-11.5). Ne gère
    pas la fin du tour (c'est la transition ``declarer_attaque``).
    """
    evenements: list[Evenement] = []
    attaque = action.params.get("attaque")
    if not isinstance(attaque, Mapping):
        raise ValueError("« attaque » (fiche de l'attaque choisie) est requise (R-9.1, D9).")
    effet = (attaque.get("effet") or "").strip()
    if effet:
        raise ValueError(
            f"L'attaque « {attaque.get('nom')} » porte un effet non scripté — un effet non "
            "implémenté n'est jamais approximé (R-15.12/D9)."
        )

    cout = _cout_depuis(attaque.get("cout"))
    energies = _energies_depuis(action.params.get("energies"))
    paiement = payer_cout(cout, energies)
    if not paiement.paye:
        raise ValueError(f"{paiement.verdict.message}")
    if cout.types or cout.incolore:
        evenements.append(paiement.evenement(cout))

    if not attaque_a_lieu:
        # Confusion sur pile : l'attaque ne porte pas (R-11.5). Rien d'autre à résoudre ici.
        return etat, evenements

    base = attaque.get("degats", 0)
    adversaire = _autre_joueur(etat, jid)
    idx_adv = _index_joueur(etat, adversaire)
    adv = etat.joueurs[idx_adv]
    cible = adv.actif
    if cible is None:
        # Aucun Actif adverse à toucher : l'attaque est déclarée, aucun dégât posé (R-9.1).
        evenements.append(Evenement(EVT_ATTAQUE_DECLAREE, {"joueur": jid, "degats": 0}))
        return etat, evenements

    resultat = resoudre_degats(
        base=base,
        type_attaque=action.params.get("type_attaque"),
        faiblesse=_faiblesse_depuis(action.params.get("faiblesse")),
        resistance=_resistance_depuis(action.params.get("resistance")),
    )
    adv = replace(adv, actif=poser_degats(cible, resultat.degats))
    etat = _remplacer_joueur(etat, idx_adv, adv)
    evenements.append(evenement_degats(resultat, carte_active(cible).instance_id))
    evenements.append(Evenement(EVT_ATTAQUE_DECLAREE, {"joueur": jid, "degats": resultat.degats}))

    # K.O., récompenses et conditions de victoire (R-13/R-14) — ordre (attaquant, défenseur).
    etat, evts_ko = resoudre_kos(etat, action.params.get("fiches", {}), (jid, adversaire))
    evenements.extend(evts_ko)
    return etat, evenements


__all__ = ["resoudre_attaque_declaree"]
