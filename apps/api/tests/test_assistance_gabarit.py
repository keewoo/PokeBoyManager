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


def test_grammaire_donne_le_schema_par_primitive():
    """Le trou du premier passage : la grammaire donne désormais les arguments PAR op (pas que
    leurs noms). On vérifie les deux pièges mesurés : « piocher » exige « nombre », « soigner »
    compte en marqueurs (pas en PV)."""
    g = grammaire_dsl()
    assert "requis:" in g and "optionnels:" in g
    assert "exemple:" in g
    # « piocher » doit montrer son argument requis (sinon le modèle l'oublie, cf. compte rendu)
    bloc_piocher = g.split("- piocher —", 1)[1].split("\n- ", 1)[0]
    assert "nombre" in bloc_piocher and "requis" in bloc_piocher
    # « soigner » doit dire que « nombre » est en MARQUEURS (le piège « Soignez 30 » → 3, pas 30)
    bloc_soigner = g.split("- soigner —", 1)[1].split("\n- ", 1)[0]
    assert "MARQUEUR" in bloc_soigner.upper()


def test_prompt_proposition_porte_texte_exemples_et_format():
    exemples = [ExempleValide(source_text="Piochez 1 carte.", script={"version": 1, "effets": []})]
    p = prompt_proposition(
        texte_fr="Piochez 2 cartes.", texte_en="Draw 2 cards.", exemples=exemples
    )
    assert "Piochez 2 cartes." in p
    assert "Draw 2 cards." in p
    assert "Piochez 1 carte." in p  # l'exemple validé est inclus
    assert "non_supporte" in p  # le format strict exige le champ de refus (D9)


def test_prompt_proposition_montre_un_exemple_complet_avec_essais():
    """Le prompt montre un exemple complet (script + essais qui passent) : c'est ce que le modèle
    imitait mal (ses cas de test ne collaient pas à l'état du moteur)."""
    p = prompt_proposition(texte_fr="Un effet.", texte_en=None, exemples=[])
    assert "EXEMPLE COMPLET" in p
    assert '"essais"' in p or "essais :" in p
    assert '"attendu"' in p  # le format d'état attendu est illustré, pas seulement décrit


def test_prompt_contradiction_demande_de_rejeter_au_doute():
    p = prompt_contradiction(
        texte_fr="Piochez 2 cartes.",
        script={"version": 1, "effets": [{"op": "piocher", "nombre": 2}]},
        essais=[{"nom": "x", "etat": {}}],
    )
    assert "CONTREDIRE" in p
    assert "rejette" in p.lower()
    assert "verdict" in p
