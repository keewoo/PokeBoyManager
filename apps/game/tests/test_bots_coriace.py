"""Le troisième bot (« coriace ») : plus mordant que « correct », sur la **seule vue publique**.

Lot ``j-mode-solo`` — mode d'entraînement contre un bot à trois niveaux. « coriace »
(:func:`pbm_sim.bots.bot_coriace`) reprend l'heuristique « correct » mais **concentre l'énergie sur
l'Actif** : il atteint une attaque plus tôt (R-9.2). Ce test **mord** — il échoue si on remplace
``bot_coriace`` par ``bot_heuristique`` : sur la même liste de coups, « correct » attache au premier
coup trié (ici le banc), « coriace » vise l'Actif. La décision se prend sur la vue (identité de
l'Actif) et la liste légale (cible de l'attache), jamais sur l'état complet (règle d'or : le bot ne
voit que ce qu'un vrai client voit).
"""

from __future__ import annotations

from pbm_game.actions.modele import ActionLegale
from pbm_game.journal.modele import ACTION_ATTACHER_ENERGIE, Action
from pbm_sim.bots import bot_coriace, bot_heuristique, par_nom

#: Une vue minimale : mon Actif est « A-actif », j'ai un Pokémon de banc « A-banc ».
_VUE = {
    "pour": "A",
    "joueurs": [
        {
            "id": "A",
            "actif": {"cartes": [{"instance_id": "A-actif", "ref": "pika"}]},
            "banc": [{"cartes": [{"instance_id": "A-banc", "ref": "pika"}]}],
        },
        {"id": "B", "actif": None, "banc": []},
    ],
}


def _attache(cible: str, etiquette: str) -> ActionLegale:
    """Un coup « attacher une énergie » visant ``cible`` (étiquette choisie pour l'ordre de tri)."""
    return ActionLegale(
        action=Action(ACTION_ATTACHER_ENERGIE, "A", {"cible": cible, "energie": "e1"}),
        etiquette=etiquette,
        cibles=(),
    )


def test_coriace_attache_sur_l_actif_la_ou_correct_prend_le_banc():
    """R-9.2 — « coriace » concentre l'énergie sur l'Actif, « correct » prend le premier trié."""
    # Étiquettes choisies pour que le tri de « correct » préfère le banc (« aaa » < « zzz ») :
    # ainsi le test distingue les deux stratégies (il mordrait si coriace == heuristique).
    legales = [_attache("A-banc", "aaa"), _attache("A-actif", "zzz")]
    assert bot_heuristique(_VUE, legales).action.params["cible"] == "A-banc"
    assert bot_coriace(_VUE, legales).action.params["cible"] == "A-actif"


def test_coriace_se_rabat_si_aucune_attache_ne_vise_l_actif():
    """Sans attache sur l'Actif, « coriace » attache quand même (jamais de coup perdu)."""
    legales = [_attache("A-banc", "aaa")]
    assert bot_coriace(_VUE, legales).action.params["cible"] == "A-banc"


def test_coriace_resolu_par_nom():
    """``par_nom(\"coriace\")`` résout bien le troisième bot (ce que le mode solo demande)."""
    assert par_nom("coriace") is bot_coriace
