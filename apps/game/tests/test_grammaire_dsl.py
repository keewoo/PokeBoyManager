"""La **grammaire documentée** (:mod:`pbm_game.effets.dsl.grammaire`) — anti-dérive.

Ce fichier est le garde-fou qui empêche la grammaire citée dans le prompt d'assistance IA de
**mentir** sur le langage réel. Trois familles de contrôles :

1. **Couverture** : toute instruction du langage (``INSTRUCTIONS``) a une fiche, et réciproquement —
   si le moteur gagne ou perd une primitive, ce test rougit tant que la fiche ne suit pas.
2. **Fidélité** : chaque exemple de fiche se **charge** (``charger_programme``), et retirer un
   argument déclaré « requis » fait **échouer** le chargement — la fiche ne peut donc pas prétendre
   qu'un argument est obligatoire alors qu'il ne l'est pas (ni l'inverse).
3. **Dérivation des constantes du moteur** : les « requis » reflètent ``OPS_CIBLE_REQUISE`` /
   ``OPS_SOURCE_REQUISE`` / ``OPS_NOMBRE_REQUIS`` de :mod:`.chargement` — jamais une liste recopiée.

Et les **exemples d'amorce** passent réellement la porte de vérification (:func:`verifier_script`) :
un exemple « validé » qui ne validerait pas serait pire qu'absent.
"""

from __future__ import annotations

import pytest

from pbm_game.effets.dsl.chargement import (
    OPS_CIBLE_REQUISE,
    OPS_NOMBRE_REQUIS,
    OPS_SOURCE_REQUISE,
    ProgrammeInvalide,
    charger_programme,
)
from pbm_game.effets.dsl.essais import verifier_script
from pbm_game.effets.dsl.grammaire import EXEMPLES_AMORCE, SPEC_OPS
from pbm_game.effets.dsl.vocabulaire import INSTRUCTIONS


def _programme(instr: dict) -> dict:
    """Emballe une instruction seule dans un programme v1 minimal."""
    return {"version": 1, "effets": [instr]}


def test_toutes_les_instructions_ont_une_fiche():
    """Couverture exacte : une fiche par instruction, ni plus ni moins (anti-dérive du moteur)."""
    assert set(SPEC_OPS) == set(INSTRUCTIONS)


@pytest.mark.parametrize("op", sorted(SPEC_OPS))
def test_chaque_exemple_se_charge(op: str):
    """L'exemple de chaque fiche est un script valide — s'il rote, la grammaire ment au modèle."""
    charger_programme(_programme(SPEC_OPS[op].exemple))


@pytest.mark.parametrize("op", sorted(SPEC_OPS))
def test_retirer_un_requis_fait_echouer_le_chargement(op: str):
    """Chaque clé « requise » l'est vraiment : la retirer de l'exemple casse le chargement."""
    spec = SPEC_OPS[op]
    for cle in spec.requis:
        ampute = {k: v for k, v in spec.exemple.items() if k != cle}
        with pytest.raises(ProgrammeInvalide):
            charger_programme(_programme(ampute))


def test_requis_derives_des_constantes_du_moteur():
    """Les « requis » reflètent les ensembles du chargeur — jamais une liste recopiée à la main."""
    for op in OPS_CIBLE_REQUISE:
        assert "cible" in SPEC_OPS[op].requis, f"{op} exige une cible (OPS_CIBLE_REQUISE)"
    for op in OPS_SOURCE_REQUISE:
        assert "source" in SPEC_OPS[op].requis, f"{op} exige une source (OPS_SOURCE_REQUISE)"
    for op in OPS_NOMBRE_REQUIS:
        assert "nombre" in SPEC_OPS[op].requis, f"{op} exige un nombre (OPS_NOMBRE_REQUIS)"


@pytest.mark.parametrize("i", range(len(EXEMPLES_AMORCE)))
def test_exemples_amorce_passent_la_porte(i: int):
    """Chaque exemple d'amorce passe verifier_script : script conforme + essais tous verts."""
    ex = EXEMPLES_AMORCE[i]
    verdict = verifier_script(ex["script"], ex["essais"])
    assert verdict["valide"] is True, f"{ex['source_text']} : {verdict['raison']}"


def test_amorce_couvre_plusieurs_familles():
    """L'amorce n'est pas monotone : elle montre au moins quatre primitives feuilles distinctes."""
    ops = {e["script"]["effets"][0]["op"] for e in EXEMPLES_AMORCE}
    # on descend d'un cran dans les « choisir » pour compter la primitive réellement montrée
    for e in EXEMPLES_AMORCE:
        tete = e["script"]["effets"][0]
        for sous in tete.get("alors", []):
            ops.add(sous["op"])
    assert len(ops) >= 4
