"""Pureté et **innocuité à l'import** du paquet d'effets — lot j-effets-architecture.

Deux garanties, chacune un critère d'acceptation :

1. ``pbm_game.effets`` s'importe sans tirer la moindre dépendance lourde (le moteur reste pur) ;
2. **l'importer ne modifie pas le socle** : ni ``REGISTRE`` (transitions), ni ``DECLENCHEURS``
   (fenêtres) ne changent. C'est la preuve que les effets « se branchent sur les points
   d'accroche existants » par injection explicite, et non en mutant le socle à l'import.
"""

from __future__ import annotations

import importlib
import sys

MODULES_INTERDITS = {
    "fastapi",
    "starlette",
    "sqlalchemy",
    "alembic",
    "asyncpg",
    "redis",
    "boto3",
    "httpx",
    "requests",
    "pbm_api",
}


def test_import_effets_ne_tire_aucune_dependance_lourde():
    importlib.import_module("pbm_game.effets")
    charges = MODULES_INTERDITS & set(sys.modules)
    assert not charges, f"L'import des effets a tiré des dépendances interdites : {sorted(charges)}"


def test_importer_effets_ne_modifie_pas_le_socle():
    """Critère n°4 : importer le paquet d'effets laisse REGISTRE et DECLENCHEURS intacts."""
    from pbm_game.journal.transitions import REGISTRE
    from pbm_game.tour.fenetres import DECLENCHEURS

    avant_registre = dict(REGISTRE)
    avant_declencheurs = {k: v for k, v in DECLENCHEURS.items()}

    importlib.reload(importlib.import_module("pbm_game.effets"))

    assert dict(REGISTRE) == avant_registre, "L'import des effets a modifié le REGISTRE du socle."
    assert {k: v for k, v in DECLENCHEURS.items()} == avant_declencheurs, (
        "L'import des effets a modifié les DECLENCHEURS du socle."
    )
    # Les trois fenêtres du socle restent sans déclencheur enregistré globalement (vides).
    assert all(decls == () for decls in DECLENCHEURS.values()), (
        "Une fenêtre du socle a reçu un déclencheur à l'import — branchement non explicite."
    )


def test_effets_expose_son_api():
    effets = importlib.import_module("pbm_game.effets")
    for nom in (
        "EvenementJeu",
        "EVENEMENTS_JEU",
        "PileEffets",
        "resoudre_pile",
        "collecter_effets_continus",
        "modificateurs_degats",
        "seuil_ko",
        "JeuDeVerrous",
        "Bus",
        "declencheur_fenetre",
    ):
        assert hasattr(effets, nom), f"pbm_game.effets n'expose pas « {nom} »"
