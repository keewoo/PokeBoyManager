"""Gabarits de requête (`pbm_api.jeu.scripts.assistance.gabarit`) — purs, aucune E/S.

On vérifie que la grammaire est bien dérivée du vocabulaire réel du moteur (jamais recopiée à la
main) et que les prompts portent les éléments exigés : texte, langage, exemples, format strict.
"""

from __future__ import annotations

from pbm_game.effets.dsl.vocabulaire import DSL_VERSION, OP_PIOCHER

from pbm_api.jeu.scripts.assistance.gabarit import (
    ExempleValide,
    grammaire_dsl,
    prompt_contradiction,
    prompt_proposition,
)


def test_grammaire_derivee_du_vocabulaire_reel():
    """La grammaire cite les primitives réelles : si le moteur en gagne une, le prompt la montre."""
    g = grammaire_dsl()
    assert OP_PIOCHER in g
    assert f"version {DSL_VERSION}" in g
    assert "code libre" in g  # la règle dure (D9) est rappelée au modèle


def test_prompt_proposition_porte_texte_exemples_et_format():
    exemples = [ExempleValide(source_text="Piochez 1 carte.", script={"version": 1, "effets": []})]
    p = prompt_proposition(
        texte_fr="Piochez 2 cartes.", texte_en="Draw 2 cards.", exemples=exemples
    )
    assert "Piochez 2 cartes." in p
    assert "Draw 2 cards." in p
    assert "Piochez 1 carte." in p  # l'exemple validé est inclus
    assert "non_supporte" in p  # le format strict exige le champ de refus (D9)


def test_prompt_contradiction_demande_de_rejeter_au_doute():
    p = prompt_contradiction(
        texte_fr="Piochez 2 cartes.",
        script={"version": 1, "effets": [{"op": "piocher", "nombre": 2}]},
        essais=[{"nom": "x", "etat": {}}],
    )
    assert "CONTREDIRE" in p
    assert "rejette" in p.lower()
    assert "verdict" in p
