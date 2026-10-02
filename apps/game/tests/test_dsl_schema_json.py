"""Le **schéma JSON** formel du langage — publié, et vérifié contre le validateur Python.

Le schéma (``src/pbm_game/effets/dsl/schema.json``, Draft 2020-12) est la *spécification publiée*.
Le validateur d'exécution (``charger_programme``) est pur et sans dépendance. Ce test prouve
**deux** choses :

1. le schéma accepte des scripts valides et rejette des scripts invalides (il « mord ») ;
2. schéma et validateur Python disent **la même chose** sur une batterie de cas — un test de
   non-divergence, pour qu'on ne tienne pas deux spécifications qui s'éloignent en silence.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

import pbm_game.effets.dsl as dsl
from pbm_game.effets.dsl.chargement import ProgrammeInvalide, charger_programme
from pbm_game.effets.dsl.vocabulaire import CONDITIONS, INSTRUCTIONS, ZONES

SCHEMA = json.loads(
    (Path(dsl.__file__).resolve().parent / "schema.json").read_text(encoding="utf-8")
)


def _valide_schema(script) -> bool:
    try:
        jsonschema.validate(script, SCHEMA)
        return True
    except jsonschema.ValidationError:
        return False


# Une batterie (script, conforme ?) exercée par les DEUX validateurs.
_SCRIPTS = [
    ({"version": 1, "effets": [{"op": "piocher", "nombre": 2}]}, True),
    (
        {
            "version": 1,
            "effets": [
                {
                    "op": "si",
                    "condition": {"type": "resultat_pile", "attendu": "face"},
                    "alors": [
                        {
                            "op": "soigner",
                            "cible": {"zone": "actif", "proprietaire": "moi"},
                            "nombre": 2,
                        }
                    ],
                }
            ],
        },
        True,
    ),
    (
        {
            "version": 1,
            "effets": [
                {
                    "op": "choisir",
                    "cible": {"zone": "en_jeu", "proprietaire": "moi", "nombre": 1},
                    "alors": [{"op": "soigner"}],
                }
            ],
        },
        True,
    ),
    (
        {
            "version": 1,
            "effets": [],
            "cout": [
                {"op": "defausser", "cible": {"zone": "main", "proprietaire": "moi", "nombre": 1}}
            ],
        },
        True,
    ),
    # Non conformes :
    ({"version": 1, "effets": [{"op": "faire_du_cafe"}]}, False),  # op inconnu
    ({"version": 1, "effets": [{"op": "piocher", "nombre": 1, "x": 1}]}, False),  # clé parasite
    ({"version": 2, "effets": []}, False),  # version future
    ({"effets": []}, False),  # version absente
    (
        {"version": 1, "effets": [{"op": "soigner", "cible": {"zone": "frigo"}}]},
        False,
    ),  # zone inconnue
    (
        {
            "version": 1,
            "effets": [
                {
                    "op": "poser_etat",
                    "cible": {"zone": "actif", "proprietaire": "moi"},
                    "etat": "petrifie",
                }
            ],
        },
        False,
    ),
]


@pytest.mark.parametrize("script,conforme", _SCRIPTS)
def test_le_schema_json_mord(script, conforme):
    assert _valide_schema(script) is conforme


@pytest.mark.parametrize("script,conforme", _SCRIPTS)
def test_schema_et_validateur_python_sont_d_accord(script, conforme):
    """Non-divergence : les deux spécifications rendent le même verdict sur chaque cas."""
    try:
        charger_programme(script)
        python_ok = True
    except ProgrammeInvalide:
        python_ok = False
    assert python_ok is _valide_schema(script) is conforme


def test_le_schema_est_un_schema_valide():
    jsonschema.Draft202012Validator.check_schema(SCHEMA)


def test_le_schema_liste_les_memes_mots_que_le_code():
    """Les énumérations du schéma = les ensembles fermés du vocabulaire (une seule vérité)."""
    ops_schema = set(SCHEMA["$defs"]["instruction"]["properties"]["op"]["enum"])
    assert ops_schema == set(INSTRUCTIONS)
    zones_schema = set(SCHEMA["$defs"]["selecteur"]["properties"]["zone"]["enum"])
    assert zones_schema == set(ZONES)
    conds_schema = set(SCHEMA["$defs"]["condition"]["properties"]["type"]["enum"])
    assert conds_schema == set(CONDITIONS)
