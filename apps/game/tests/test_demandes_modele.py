"""Modèle des demandes de décision — catégories, validation, réponse par défaut, sérialisation.

Lot ``j-effets-choix``. Aucune règle de jeu n'est jouée ici : on prouve que la **forme** d'une
demande et sa police (ce qu'est une réponse recevable, quelle est la réponse par défaut) tiennent.
Les demandes servent surtout R-9.3 étape D (« choix imposés par l'attaque »).
"""

from __future__ import annotations

import pytest

from pbm_game.demandes.modele import (
    CAT_CARTE,
    CAT_CARTES,
    CAT_NOMBRE,
    CAT_ORDRE,
    CAT_OUI_NON,
    CAT_TYPE,
    NON,
    OUI,
    DemandeDecision,
    Reponse,
    reponse_par_defaut,
    valider_reponse,
)
from pbm_game.effets.pile import SourceEffet

_SRC = SourceEffet("Dresseur X", ref="ref-x", instance_id="i-x")


def _demande(**kw) -> DemandeDecision:
    base = dict(
        destinataire="alice", categorie=CAT_CARTE, source=_SRC, regle="R-9.3", libelle="Choix"
    )
    base.update(kw)
    return DemandeDecision(**base).avec_id("d0")


def test_categorie_inconnue_refusee_d9():
    with pytest.raises(ValueError, match="jamais devinée"):
        DemandeDecision(
            destinataire="a", categorie="farfelue", source=_SRC, regle="R-1.1", libelle="x"
        )


def test_demande_exige_regle_et_libelle():
    with pytest.raises(ValueError, match="citer la règle"):
        DemandeDecision(destinataire="a", categorie=CAT_CARTE, source=_SRC, regle=" ", libelle="x")
    with pytest.raises(ValueError, match="libellé"):
        DemandeDecision(
            destinataire="a", categorie=CAT_CARTE, source=_SRC, regle="R-1.1", libelle=""
        )


def test_destinataire_peut_etre_l_adversaire():
    # Une demande adressée à l'adversaire est parfaitement légale (c'est tout l'enjeu du lot).
    d = _demande(destinataire="bob")
    assert d.destinataire == "bob"


def test_bornes_incoherentes_refusees():
    with pytest.raises(ValueError, match="Bornes"):
        DemandeDecision(
            destinataire="a",
            categorie=CAT_CARTES,
            source=_SRC,
            regle="R-1.1",
            libelle="x",
            minimum=2,
            maximum=1,
        )


def test_valider_carte_un_seul_id_dans_l_ensemble():
    d = _demande(categorie=CAT_CARTE, options=("c1", "c2"))
    valider_reponse(d, Reponse("d0", ("c1",)))
    with pytest.raises(ValueError, match="attendu un seul id"):
        valider_reponse(d, Reponse("d0", ("c3",)))
    with pytest.raises(ValueError, match="attendu un seul id"):
        valider_reponse(d, Reponse("d0", ("c1", "c2")))


def test_valider_mauvaise_demande_refusee():
    d = _demande(options=("c1",))
    with pytest.raises(ValueError, match="mauvaise demande"):
        valider_reponse(d, Reponse("d7", ("c1",)))


def test_valider_cartes_cardinalite_et_ensemble():
    d = _demande(categorie=CAT_CARTES, options=("c1", "c2", "c3"), minimum=1, maximum=2)
    valider_reponse(d, Reponse("d0", ("c1",)))
    valider_reponse(d, Reponse("d0", ("c1", "c3")))
    with pytest.raises(ValueError, match="hors de"):
        valider_reponse(d, Reponse("d0", ("c1", "c2", "c3")))  # trop
    with pytest.raises(ValueError, match="ids hors de l'ensemble"):
        valider_reponse(d, Reponse("d0", ("c9",)))
    with pytest.raises(ValueError, match="doublons"):
        valider_reponse(d, Reponse("d0", ("c1", "c1")))


def test_valider_ordre_est_une_permutation():
    d = _demande(categorie=CAT_ORDRE, options=("a", "b", "c"), minimum=3, maximum=3)
    valider_reponse(d, Reponse("d0", ("c", "a", "b")))
    with pytest.raises(ValueError, match="permutation"):
        valider_reponse(d, Reponse("d0", ("a", "b")))  # il en manque un


def test_valider_oui_non():
    d = _demande(categorie=CAT_OUI_NON, options=(OUI, NON))
    valider_reponse(d, Reponse("d0", (OUI,)))
    with pytest.raises(ValueError, match="oui.*non"):
        valider_reponse(d, Reponse("d0", ("peut-etre",)))


def test_valider_nombre_dans_les_bornes():
    d = _demande(categorie=CAT_NOMBRE, minimum=0, maximum=3)
    valider_reponse(d, Reponse("d0", ("2",)))
    with pytest.raises(ValueError, match="hors de"):
        valider_reponse(d, Reponse("d0", ("4",)))
    with pytest.raises(ValueError, match="n'est pas un entier"):
        valider_reponse(d, Reponse("d0", ("deux",)))


def test_abandon_refuse_si_obligatoire_permis_sinon():
    obligatoire = _demande(options=("c1",), obligatoire=True)
    with pytest.raises(ValueError, match="obligatoire"):
        valider_reponse(obligatoire, Reponse("d0", ()))
    facultatif = _demande(options=("c1",), obligatoire=False)
    valider_reponse(facultatif, Reponse("d0", ()))  # abandon légitime


def test_reponse_par_defaut_facultatif_abandonne():
    d = _demande(
        categorie=CAT_CARTES, options=("c1", "c2"), minimum=0, maximum=2, obligatoire=False
    )
    defaut = reponse_par_defaut(d)
    assert defaut.choix == ()  # on renonce à l'effet facultatif
    valider_reponse(d, defaut)  # et c'est recevable


def test_reponse_par_defaut_premier_choix_valide_par_categorie():
    # carte → première option ; cartes → les `minimum` premières ; ordre → identité ; nombre → min.
    assert reponse_par_defaut(_demande(categorie=CAT_CARTE, options=("a", "b"))).choix == ("a",)
    cartes = _demande(categorie=CAT_CARTES, options=("a", "b", "c"), minimum=2, maximum=3)
    assert reponse_par_defaut(cartes).choix == ("a", "b")
    ordre = _demande(categorie=CAT_ORDRE, options=("x", "y"), minimum=2, maximum=2)
    assert reponse_par_defaut(ordre).choix == ("x", "y")
    nombre = _demande(categorie=CAT_NOMBRE, minimum=1, maximum=5)
    assert reponse_par_defaut(nombre).choix == ("1",)
    ouinon = _demande(categorie=CAT_OUI_NON, options=(OUI, NON))
    assert reponse_par_defaut(ouinon).choix == (OUI,)


def test_reponse_par_defaut_toujours_recevable():
    for cat, kw in [
        (CAT_CARTE, dict(options=("a", "b"))),
        (CAT_CARTES, dict(options=("a", "b"), minimum=1, maximum=2)),
        (CAT_ORDRE, dict(options=("a", "b"), minimum=2, maximum=2)),
        (CAT_OUI_NON, dict(options=(OUI, NON))),
        (CAT_NOMBRE, dict(minimum=0, maximum=9)),
        (CAT_TYPE, dict(options=("feu", "eau"))),
    ]:
        d = _demande(categorie=cat, **kw)
        valider_reponse(d, reponse_par_defaut(d))  # ne doit jamais lever


def test_serialisation_demande_aller_retour():
    d = _demande(
        categorie=CAT_CARTES,
        options=("c1", "c2"),
        minimum=1,
        maximum=2,
        obligatoire=False,
        ensemble_cache=True,
        delai_ms=30000,
        temps_restant_ms=12000,
    )
    assert DemandeDecision.depuis_json(d.en_json()) == d


def test_serialisation_reponse_aller_retour():
    r = Reponse("d3", ("c1", "c2"))
    assert Reponse.depuis_json(r.en_json()) == r
    vide = Reponse("d4", ())
    assert Reponse.depuis_json(vide.en_json()) == vide
