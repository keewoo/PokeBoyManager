"""Garde de couverture — **la CI échoue si une règle du corpus n'a aucun cas**.

Mission ``j-tests-regles``, critère : « Aucune règle du corpus n'est sans cas (ou l'exception est
écrite et justifiée) » et « Faire échouer la CI si une règle du corpus n'a aucun cas associé ».

Une règle est **couverte** si un cas la cite — exécutable (``docs/jeu/cas-executables/``) ou
documentaire (``docs/jeu/cas-de-regles.yaml``). Les règles non exécutables au jalon J1 (méta sur
le corpus, mécaniques non implémentées) sont listées, **avec justification**, dans
``docs/jeu/couverture-exceptions.yaml``. La garde vérifie :

1. **aucune règle sans cas ni exception** (le cœur de la garde) ;
2. **aucune exception périmée** (une règle en exception qu'un cas couvre déjà) ;
3. **aucune exception hors corpus** (un identifiant absent de REGLES.md) ;
4. chaque exception **porte une justification** non vide.

Ce fichier fait l'entrée/sortie (charger les fichiers) ; le calcul (``pbm_game.cas.couverture``)
reste pur.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from pbm_game.cas.couverture import rapport, regles_couvertes
from pbm_game.regles import identifiants_definis

RACINE_DEPOT = Path(__file__).resolve().parents[3]
JEU = RACINE_DEPOT / "docs" / "jeu"
CHEMIN_REGLES = JEU / "REGLES.md"
CHEMIN_DOC = JEU / "cas-de-regles.yaml"
CHEMIN_EXCEPTIONS = JEU / "couverture-exceptions.yaml"
DOSSIER_CAS = JEU / "cas-executables"

#: Plancher de couverture **exécutable** : au moins ce nombre de règles doit avoir un vrai cas
#: exécutable (pas seulement documentaire). Garde qu'on ne remplace pas des cas par des exceptions.
PLANCHER_EXECUTABLE = 90


def _regles_definies() -> set[str]:
    return identifiants_definis(CHEMIN_REGLES.read_text(encoding="utf-8"))


def _regles_documentaires() -> set[str]:
    donnees = yaml.safe_load(CHEMIN_DOC.read_text(encoding="utf-8"))
    return {r for c in donnees["cas"] for r in c["regles"]}


def _cas_executables() -> list[dict]:
    cas: list[dict] = []
    for fichier in sorted(DOSSIER_CAS.glob("*.yaml")):
        cas.extend(yaml.safe_load(fichier.read_text(encoding="utf-8"))["cas"])
    return cas


def _exceptions() -> dict[str, str]:
    donnees = yaml.safe_load(CHEMIN_EXCEPTIONS.read_text(encoding="utf-8"))
    return dict(donnees["exceptions"])


def _rapport():
    exceptions = _exceptions()
    return (
        rapport(
            definies=_regles_definies(),
            par_executable=regles_couvertes(_cas_executables()),
            par_documentaire=_regles_documentaires(),
            exceptions=set(exceptions),
        ),
        exceptions,
    )


def test_aucune_regle_sans_cas():
    """Cœur de la garde : chaque règle a un cas (exécutable ou documentaire) ou une exception."""
    r, _ = _rapport()
    assert not r.sans_cas, (
        "Règles du corpus SANS aucun cas ni exception — ajouter un cas, ou une exception "
        f"justifiée : {sorted(r.sans_cas)}"
    )


def test_aucune_exception_perimee():
    """Une exception ne se garde que tant qu'AUCUN cas ne couvre la règle (sinon on la retire)."""
    r, _ = _rapport()
    assert not r.exceptions_perimees, (
        "Exceptions périmées (un cas couvre déjà la règle) — à retirer de "
        f"couverture-exceptions.yaml : {sorted(r.exceptions_perimees)}"
    )


def test_aucune_exception_hors_corpus():
    r, _ = _rapport()
    assert not r.exceptions_inconnues, (
        f"Exceptions nommant une règle absente de REGLES.md : {sorted(r.exceptions_inconnues)}"
    )


def test_chaque_exception_est_justifiee():
    _, exceptions = _rapport()
    sans_raison = [reg for reg, raison in exceptions.items() if not str(raison).strip()]
    assert not sans_raison, f"Exceptions sans justification écrite : {sans_raison}"


def test_couverture_executable_suffisante():
    """On couvre la majorité des règles par de VRAIS cas exécutables, pas par des exceptions."""
    r, _ = _rapport()
    couvertes = len(r.par_executable & r.definies)
    assert couvertes >= PLANCHER_EXECUTABLE, (
        f"Couverture exécutable {couvertes} < plancher {PLANCHER_EXECUTABLE}."
    )


def test_tout_le_corpus_est_couvert_par_union():
    """Cas exécutables + documentaires + exceptions couvrent exactement le corpus."""
    r, _ = _rapport()
    union = (r.par_executable | r.par_documentaire | r.exceptions) & r.definies
    assert union == r.definies, f"Non couvert : {sorted(r.definies - union)}"
