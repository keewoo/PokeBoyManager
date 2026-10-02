"""Pureté et **innocuité à l'import** du langage d'effets — le moteur reste pur.

Deux garanties, comme pour le paquet d'effets :

1. importer ``pbm_game.effets.dsl`` ne tire **aucune** dépendance lourde (ni HTTP, ni base) ;
2. l'importer **ne modifie pas le socle** : ni ``REGISTRE`` (transitions), ni ``DECLENCHEURS``
   (fenêtres) ne changent — le DSL se branche par **injection** (``registre_dsl``), jamais en
   mutant le socle à l'import.
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


def test_import_dsl_ne_tire_aucune_dependance_lourde():
    importlib.import_module("pbm_game.effets.dsl")
    charges = MODULES_INTERDITS & set(sys.modules)
    assert not charges, f"L'import du DSL a tiré des dépendances interdites : {sorted(charges)}"


def test_importer_le_dsl_ne_modifie_pas_le_socle():
    from pbm_game.journal.transitions import REGISTRE
    from pbm_game.tour.fenetres import DECLENCHEURS

    avant_registre = dict(REGISTRE)
    avant_declencheurs = dict(DECLENCHEURS)
    importlib.import_module("pbm_game.effets.dsl")
    assert dict(REGISTRE) == avant_registre
    assert dict(DECLENCHEURS) == avant_declencheurs


def test_registre_dsl_ne_connait_que_le_type_dsl():
    from pbm_game.effets.dsl import registre_dsl

    assert set(registre_dsl()) == {"dsl"}
