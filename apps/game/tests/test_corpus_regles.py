"""Tests du corpus de règles de référence — lot j-regles-reference.

Ces tests FONT FOI sur deux choses :

1. le moteur `pbm_game` est **pur** (aucun import de FastAPI, SQLAlchemy, réseau…) ;
2. le corpus écrit (`docs/jeu/REGLES.md`) et sa table de cas (`docs/jeu/cas-de-regles.yaml`)
   sont **cohérents** : chaque cas cite une règle qui existe, chaque règle est définie une
   seule fois, et les dix cas limites de la mission sont couverts.

Chaque cas de la table nomme la règle `R-x.y` qu'il vérifie — ces tests garantissent que
ce lien n'est jamais rompu. Un test échoue naturellement si les fichiers du corpus
manquent : c'est le « test qui échoue sans le changement et passe avec ».
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml

from pbm_game import regles
from pbm_game.regles import (
    CAS_LIMITES_REQUIS,
    cas_limites_manquants,
    charger_cas,
    definitions_en_double,
    identifiants_definis,
    regles_orphelines,
)

# apps/game/tests/test_corpus_regles.py -> racine du dépôt (parents[3]).
RACINE_DEPOT = Path(__file__).resolve().parents[3]
CHEMIN_REGLES = RACINE_DEPOT / "docs" / "jeu" / "REGLES.md"
CHEMIN_CAS = RACINE_DEPOT / "docs" / "jeu" / "cas-de-regles.yaml"

# Modules interdits dans le paquet moteur : le moteur ne connaît ni HTTP, ni base, ni réseau.
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


@pytest.fixture(scope="module")
def texte_regles() -> str:
    assert CHEMIN_REGLES.is_file(), f"Corpus de règles introuvable : {CHEMIN_REGLES}"
    return CHEMIN_REGLES.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def cas(texte_regles: str):  # noqa: ARG001 — dépendance d'ordre documentaire
    assert CHEMIN_CAS.is_file(), f"Table de cas introuvable : {CHEMIN_CAS}"
    donnees = yaml.safe_load(CHEMIN_CAS.read_text(encoding="utf-8"))
    return charger_cas(donnees)


def test_moteur_importe_sans_dependance_lourde():
    """Le paquet s'importe sans tirer HTTP, base ni réseau (preuve de pureté)."""
    import importlib

    importlib.import_module("pbm_game")
    importlib.import_module("pbm_game.regles")


def test_source_du_moteur_n_importe_rien_d_interdit():
    """Analyse statique : aucun fichier du paquet n'importe un module interdit."""
    paquet = Path(regles.__file__).parent
    offenses: list[str] = []
    for fichier in paquet.rglob("*.py"):
        arbre = ast.parse(fichier.read_text(encoding="utf-8"), filename=str(fichier))
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.Import):
                noms = [a.name.split(".")[0] for a in noeud.names]
            elif isinstance(noeud, ast.ImportFrom):
                noms = [(noeud.module or "").split(".")[0]]
            else:
                continue
            for nom in noms:
                if nom in MODULES_INTERDITS:
                    offenses.append(f"{fichier.name}: import interdit « {nom} »")
    assert not offenses, "Le moteur doit rester pur :\n" + "\n".join(offenses)


def test_corpus_definit_des_regles(texte_regles: str):
    definies = identifiants_definis(texte_regles)
    assert definies, "Le corpus ne définit aucune règle R-x.y en gras."
    # Garde-fou de sanité : le corpus couvre au moins les grandes mécaniques attendues.
    assert len(definies) >= 50, f"Corpus anormalement court : {len(definies)} règles définies."


def test_aucune_regle_definie_en_double(texte_regles: str):
    doublons = definitions_en_double(texte_regles)
    assert not doublons, f"Règles définies plusieurs fois : {doublons}"


def test_chaque_cas_nomme_au_moins_une_regle(cas):
    sans_regle = [c.id for c in cas if not c.regles]
    assert not sans_regle, f"Cas sans règle citée : {sans_regle}"


def test_cas_citent_des_regles_existantes(texte_regles: str, cas):
    definies = identifiants_definis(texte_regles)
    orphelines = regles_orphelines(cas, definies)
    assert not orphelines, f"Cas citant des règles absentes de REGLES.md : {orphelines}"


def test_dix_cas_limites_couverts(cas):
    manquants = cas_limites_manquants(cas)
    assert not manquants, f"Cas limites de la mission non couverts : {sorted(manquants)}"
    assert len(CAS_LIMITES_REQUIS) >= 10, "La mission exige au moins dix cas limites."


def test_cas_limites_des_six_mecaniques_nommees(cas):
    """Les six cas limites explicitement listés dans la mission sont présents."""
    six_nommes = {
        "pioche-vide-debut-tour",
        "banc-vide-apres-ko",
        "ko-simultane",
        "dernier-pokemon-ko-hors-attaque",
        "abandon",
        "egalite",
    }
    couverts = {c.cas_limite for c in cas if c.cas_limite}
    assert six_nommes <= couverts, f"Manque : {sorted(six_nommes - couverts)}"


def test_ids_de_cas_uniques(cas):
    ids = [c.id for c in cas]
    assert len(ids) == len(set(ids)), "Identifiants de cas en double."


# --- Tests du vérificateur lui-même : il doit MORDRE sur un corpus incohérent. ---


def test_charger_cas_refuse_un_cas_sans_regle():
    with pytest.raises(ValueError, match="au moins une règle"):
        charger_cas({"cas": [{"id": "x", "regles": [], "categorie": "t", "description": "d"}]})


def test_charger_cas_refuse_un_identifiant_mal_forme():
    with pytest.raises(ValueError, match="identifiant de règle"):
        charger_cas(
            {"cas": [{"id": "x", "regles": ["R10.3"], "categorie": "t", "description": "d"}]}
        )


def test_regles_orphelines_detecte_une_citation_absente():
    cas = charger_cas(
        {"cas": [{"id": "x", "regles": ["R-99.9"], "categorie": "t", "description": "d"}]}
    )
    assert regles_orphelines(cas, {"R-1.1"}) == {"x": ["R-99.9"]}


def test_cas_limites_manquants_signale_un_trou():
    cas = charger_cas(
        {
            "cas": [
                {
                    "id": "x",
                    "regles": ["R-1.1"],
                    "categorie": "cas-limite",
                    "description": "d",
                    "cas_limite": "abandon",
                }
            ]
        }
    )
    manquants = cas_limites_manquants(cas)
    assert "abandon" not in manquants
    assert "egalite" in manquants
