"""Pureté du paquet des horloges — lot ``j-timer``.

Critère transverse du moteur : aucune dépendance à FastAPI, SQLAlchemy, au réseau **ni à une
horloge système** dans ``pbm_game.horloges``. Le temps entre toujours par paramètre
(``maintenant`` en secondes) ; rien ne lit l'heure. On le prouve par l'import et par
l'absence d'usage de ``time``/``datetime`` dans le source du paquet.
"""

from __future__ import annotations

import ast
import importlib
import pathlib
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


def test_import_horloges_ne_tire_aucune_dependance_lourde():
    """Importer ``pbm_game.horloges`` ne charge aucun module interdit."""
    importlib.import_module("pbm_game.horloges")
    charges = MODULES_INTERDITS & set(sys.modules)
    assert not charges, f"L'import des horloges a tiré des dépendances : {sorted(charges)}"


def test_le_paquet_ne_lit_jamais_l_horloge_systeme():
    """Aucun module du paquet n'importe ``time`` ni ``datetime`` : le temps vient du dehors.

    Garantit que les horloges ne sont pas un minuteur vivant : elles se calculent depuis un instant
    fourni (risque nommé du lot). Test **statique** (lit le source), donc insensible au fait qu'un
    import conditionnel ne soit pas exécuté.
    """
    paquet = pathlib.Path(importlib.import_module("pbm_game.horloges").__file__).parent
    fautifs: list[str] = []
    for fichier in sorted(paquet.rglob("*.py")):
        if fichier.name.startswith("."):
            continue  # ignore un éventuel fichier caché (métadonnées, AppleDouble)
        arbre = ast.parse(fichier.read_text(encoding="utf-8"))
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.Import):
                noms = {alias.name.split(".")[0] for alias in noeud.names}
            elif isinstance(noeud, ast.ImportFrom):
                noms = {(noeud.module or "").split(".")[0]}
            else:
                continue
            if {"time", "datetime"} & noms:
                fautifs.append(f"{fichier.name}: {sorted({'time', 'datetime'} & noms)}")
    assert not fautifs, f"Le paquet horloges lit une horloge système : {fautifs}"


def test_horloges_expose_son_api():
    """Le paquet réexporte les points d'entrée attendus du lot."""
    horloges = importlib.import_module("pbm_game.horloges")
    for nom in (
        "ConfigHorloges",
        "EtatHorloges",
        "demarrer",
        "restant",
        "premiere_echeance",
        "pause",
        "reprendre",
        "poser_decision",
        "lever_decision",
        "basculer",
    ):
        assert hasattr(horloges, nom), f"pbm_game.horloges n'expose pas « {nom} »"
