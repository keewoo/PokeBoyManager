"""Pouvoirs « une fois par partie » — attaque GX (R-15.3) et VSTAR Power (R-15.6).

L'usage est suivi dans l'état du JOUEUR, pas dans celui de la carte : ces tests prouvent (1) la
garde pure, (2) le refus d'un **second** VSTAR Power en pleine résolution d'attaque, (3) que
l'interdiction **survit à une reprise après F5** (aller-retour de sérialisation).
"""

from __future__ import annotations

import pytest

from pbm_game.combat.attaque import resoudre_attaque_declaree
from pbm_game.combat.pouvoirs_uniques import (
    POUVOIR_GX,
    POUVOIR_VSTAR,
    deja_utilise,
    marquer_utilise,
    valider_pouvoir,
)
from pbm_game.journal.modele import ACTION_DECLARER_ATTAQUE, Action
from pbm_game.state.modele import (
    PHASE_ATTAQUE,
    Carte,
    EtatPartie,
    Joueur,
    PokemonEnJeu,
    Tour,
)
from pbm_game.state.serialisation import depuis_json, vers_json


def _joueur(jid: str) -> Joueur:
    return Joueur(
        id=jid,
        actif=PokemonEnJeu(cartes=(Carte(f"{jid}-pk-1", f"ref-{jid}"),)),
        recompenses=tuple(Carte(f"{jid}-r{i}", "ref-r") for i in range(6)),
    )


def _etat() -> EtatPartie:
    return EtatPartie(
        joueurs=(_joueur("alice"), _joueur("bob")),
        tour=Tour(joueur_actif="alice", numero=3, phase=PHASE_ATTAQUE),
    )


def _action_vstar() -> Action:
    return Action(
        ACTION_DECLARER_ATTAQUE,
        "alice",
        {
            "attaque": {
                "nom": "Étoile Déchaînée",
                "cout": {"types": {}, "incolore": 0},
                "degats": 0,
                "effet": "",
                "pouvoir_unique": POUVOIR_VSTAR,
            },
            "energies": [],
            "fiches": {},
        },
    )


def test_valider_pouvoir_refuse_inconnu():
    """Un identifiant de pouvoir hors du vocabulaire est refusé bruyamment (D9, R-15.3/R-15.6)."""
    assert valider_pouvoir(POUVOIR_GX) == POUVOIR_GX
    with pytest.raises(ValueError, match="usage unique inconnu"):
        valider_pouvoir("mega_power")


def test_marquer_puis_deja_utilise():
    """Marquer un pouvoir le rend « déjà utilisé » ; les autres restent disponibles (R-15.6)."""
    j = _joueur("alice")
    assert not deja_utilise(j, POUVOIR_VSTAR)
    j2 = marquer_utilise(j, POUVOIR_VSTAR)
    assert deja_utilise(j2, POUVOIR_VSTAR)
    assert not deja_utilise(j2, POUVOIR_GX)


def test_deuxieme_vstar_power_refuse_en_partie():
    """R-15.6 — le **premier** VSTAR Power passe, le **second** est refusé en pleine partie."""
    etat = _etat()
    etat2, _ = resoudre_attaque_declaree(etat, _action_vstar(), "alice", True, None)
    alice = next(j for j in etat2.joueurs if j.id == "alice")
    assert deja_utilise(alice, POUVOIR_VSTAR)  # le premier a été dépensé

    with pytest.raises(ValueError, match="R-15.6"):
        resoudre_attaque_declaree(etat2, _action_vstar(), "alice", True, None)


def test_usage_unique_survit_a_un_f5():
    """R-15.6 — l'interdiction est portée par l'état sérialisé : elle survit à un aller-retour JSON
    (reprise après F5) et au rejeu."""
    etat = _etat()
    etat2, _ = resoudre_attaque_declaree(etat, _action_vstar(), "alice", True, None)
    # Aller-retour de sérialisation = ce que subit une partie reprise après un F5.
    repris = depuis_json(vers_json(etat2))
    assert repris == etat2
    with pytest.raises(ValueError, match="R-15.6"):
        resoudre_attaque_declaree(repris, _action_vstar(), "alice", True, None)
