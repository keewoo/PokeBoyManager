"""Chargement & validation du langage d'effets — critères d'acceptation n°3 et n°4.

* **n°3** : un script non conforme est refusé **au chargement** (``ProgrammeInvalide``), jamais
  en pleine partie. On exerce ici chaque forme de non-conformité.
* **n°4** : le langage est **versionné** — un script v1 reste lisible, une version future est
  refusée bruyamment.
"""

from __future__ import annotations

import pytest

from pbm_game.effets.dsl import DSL_VERSION, Programme, charger_programme
from pbm_game.effets.dsl.chargement import ProgrammeInvalide


def _valide(effets, **extra):
    return {"version": 1, "effets": effets, **extra}


def test_un_script_minimal_valide_se_charge():
    prog = charger_programme(_valide([{"op": "piocher", "nombre": 2}]))
    assert isinstance(prog, Programme)
    assert prog.version == 1
    assert prog.effets[0].op == "piocher"
    assert prog.effets[0].nombre == 2


def test_aller_retour_json_est_stable():
    """charger_programme(p.en_json()) redonne p : le script survit à la sérialisation (F5)."""
    source = _valide(
        [
            {
                "op": "si",
                "condition": {"type": "resultat_pile", "attendu": "face"},
                "alors": [
                    {
                        "op": "soigner",
                        "cible": {"zone": "actif", "proprietaire": "moi"},
                        "nombre": 3,
                    }
                ],
            },
            {
                "op": "pile_ou_face",
                "nombre": 1,
                "alors": [
                    {
                        "op": "infliger_degats",
                        "cible": {"zone": "actif", "proprietaire": "adversaire"},
                        "nombre": 20,
                    }
                ],
            },
        ],
        cout=[{"op": "defausser", "cible": {"zone": "main", "proprietaire": "moi", "nombre": 1}}],
    )
    prog = charger_programme(source)
    assert charger_programme(prog.en_json()) == prog


def test_op_inconnu_refuse_et_nomme_l_absence_de_code_libre():
    with pytest.raises(ProgrammeInvalide, match="code libre"):
        charger_programme(_valide([{"op": "faire_nimporte_quoi"}]))


def test_cle_parasite_refusee_strictement():
    """Une clé inconnue est une erreur (un effet qu'on croit avoir décrit), jamais ignorée."""
    with pytest.raises(ProgrammeInvalide, match="inconnue"):
        charger_programme(_valide([{"op": "piocher", "nombre": 1, "coleur": "rouge"}]))


def test_version_future_refusee():
    with pytest.raises(ProgrammeInvalide, match="postérieure"):
        charger_programme({"version": DSL_VERSION + 1, "effets": []})


def test_version_obligatoire():
    with pytest.raises(ProgrammeInvalide, match="version"):
        charger_programme({"effets": []})


def test_effets_obligatoires():
    with pytest.raises(ProgrammeInvalide, match="effets"):
        charger_programme({"version": 1})


def test_cible_requise_pour_soigner():
    with pytest.raises(ProgrammeInvalide, match="exige une cible"):
        charger_programme(_valide([{"op": "soigner"}]))


def test_nombre_requis_pour_infliger_degats():
    with pytest.raises(ProgrammeInvalide, match="exige un"):
        charger_programme(
            _valide(
                [
                    {
                        "op": "infliger_degats",
                        "cible": {"zone": "actif", "proprietaire": "adversaire"},
                    }
                ]
            )
        )


def test_degats_doivent_etre_multiples_de_10():
    with pytest.raises(ProgrammeInvalide, match="multiples de 10"):
        charger_programme(
            _valide(
                [
                    {
                        "op": "infliger_degats",
                        "cible": {"zone": "actif", "proprietaire": "adversaire"},
                        "nombre": 25,
                    }
                ]
            )
        )


def test_etat_inconnu_refuse():
    with pytest.raises(ProgrammeInvalide, match="état"):
        charger_programme(
            _valide(
                [
                    {
                        "op": "poser_etat",
                        "cible": {"zone": "actif", "proprietaire": "adversaire"},
                        "etat": "petrifie",
                    }
                ]
            )
        )


def test_poser_etat_exige_un_etat():
    with pytest.raises(ProgrammeInvalide, match="poser_etat"):
        charger_programme(
            _valide(
                [{"op": "poser_etat", "cible": {"zone": "actif", "proprietaire": "adversaire"}}]
            )
        )


def test_empecher_exige_verrou_et_portee():
    with pytest.raises(ProgrammeInvalide, match="verrou"):
        charger_programme(_valide([{"op": "empecher", "portee": "ce_tour"}]))
    with pytest.raises(ProgrammeInvalide, match="portée"):
        charger_programme(_valide([{"op": "empecher", "verrou": "pas_de_supporter"}]))


def test_verrou_inconnu_refuse():
    with pytest.raises(ProgrammeInvalide, match="verrou"):
        charger_programme(
            _valide([{"op": "empecher", "verrou": "pas_de_pizza", "portee": "ce_tour"}])
        )


def test_zone_inconnue_refusee():
    with pytest.raises(ProgrammeInvalide, match="zone inconnue"):
        charger_programme(_valide([{"op": "soigner", "cible": {"zone": "frigo"}, "nombre": 1}]))


def test_si_sans_condition_refuse():
    with pytest.raises(ProgrammeInvalide, match="condition"):
        charger_programme(_valide([{"op": "si", "alors": [{"op": "piocher", "nombre": 1}]}]))


def test_si_vide_refuse():
    with pytest.raises(ProgrammeInvalide, match="vide"):
        charger_programme(_valide([{"op": "si", "condition": {"type": "resultat_pile"}}]))


def test_repeter_exige_nombre_ou_source():
    with pytest.raises(ProgrammeInvalide, match="repeter"):
        charger_programme(_valide([{"op": "repeter", "alors": [{"op": "piocher", "nombre": 1}]}]))


def test_attacher_exige_une_source():
    with pytest.raises(ProgrammeInvalide, match="source"):
        charger_programme(
            _valide([{"op": "attacher", "cible": {"zone": "actif", "proprietaire": "moi"}}])
        )
