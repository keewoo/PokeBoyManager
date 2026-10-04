"""Fournisseur et parsing (`pbm_api.jeu.scripts.assistance.fournisseur`) — purs, aucun réseau.

On vérifie le parsing strict (JSON même entouré de prose, refus explicite si illisible) et le
double factice (déterministe, sans dépense).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pbm_api.jeu.scripts.assistance.fournisseur import (
    FournisseurFactice,
    Proposition,
    ReponseIllisibleError,
    Usage,
    parser_proposition,
    parser_verdict,
)


def test_parser_proposition_json_pur():
    texte = (
        '{"non_supporte": false, "confiance": "haute",'
        ' "script": {"version": 1, "effets": []}, "essais": [{"etat": {}}]}'
    )
    prop = parser_proposition(texte)
    assert isinstance(prop, Proposition)
    assert prop.confiance == "haute"
    assert prop.script == {"version": 1, "effets": []}


def test_parser_proposition_json_entoure_de_prose():
    texte = (
        'Voici ma réponse :\n'
        '{"non_supporte": true, "raison": "hors langage", "confiance": "basse"}\nVoilà.'
    )
    prop = parser_proposition(texte)
    assert prop.non_supporte is True
    assert prop.raison == "hors langage"


def test_parser_proposition_refuse_une_reponse_sans_json():
    with pytest.raises(ReponseIllisibleError):
        parser_proposition("Je ne sais pas quoi répondre.")


def test_parser_proposition_refuse_une_confiance_inconnue():
    with pytest.raises(ValidationError):
        parser_proposition('{"confiance": "énorme"}')


def test_parser_verdict():
    v = parser_verdict('{"verdict": "rejete", "raison": "mauvaise cible"}')
    assert v.verdict == "rejete"
    assert v.essai_contre is None


def test_parser_verdict_refuse_un_verdict_inconnu():
    with pytest.raises(ValidationError):
        parser_verdict('{"verdict": "peut-être"}')


@pytest.mark.asyncio
async def test_fournisseur_factice_est_deterministe_et_sans_cout():
    factice = FournisseurFactice(lambda prompt: '{"ok": true}', usage=Usage(0, 0))
    texte, usage = await factice.generer("un prompt")
    assert texte == '{"ok": true}'
    assert usage == Usage(0, 0)
    assert factice.prompts == ["un prompt"]  # la trace des prompts est gardée pour les tests
