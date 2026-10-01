"""Pureté du paquet d'état — lot j-modele-etat.

Critère d'acceptation : aucune dépendance à FastAPI, SQLAlchemy ou au réseau dans le
paquet du moteur, vérifié par un test d'import. (L'analyse statique de tout le paquet
``pbm_game`` vit dans ``test_corpus_regles.py`` et couvre déjà ``pbm_game.state`` via
``rglob`` ; ce test-ci prouve que l'import lui-même ne tire aucune dépendance lourde.)
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


def test_import_state_ne_tire_aucune_dependance_lourde():
    """Importer ``pbm_game.state`` ne charge aucun module interdit."""
    importlib.import_module("pbm_game.state")
    charges = MODULES_INTERDITS & set(sys.modules)
    assert not charges, f"L'import du moteur a tiré des dépendances interdites : {sorted(charges)}"


def test_state_expose_son_api():
    """Le paquet réexporte bien les points d'entrée attendus du lot."""
    state = importlib.import_module("pbm_game.state")
    for nom in ("EtatPartie", "vue", "vers_json", "depuis_json", "verifier", "assert_invariants"):
        assert hasattr(state, nom), f"pbm_game.state n'expose pas « {nom} »"
