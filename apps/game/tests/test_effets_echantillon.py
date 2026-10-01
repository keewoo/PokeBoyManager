"""Couverture du vocabulaire par l'échantillon de 200 cartes — lot j-effets-architecture.

Critère d'acceptation n°1 : « Les 200 cartes de l'échantillon sont exprimables sans ajouter
d'événement nouveau — ou la liste est complétée et le test refait. »

L'échantillon est **gelé** dans ``tests/donnees/echantillon_200_effets.json`` (produit par
``apps/game/tools/classer_echantillon.py`` à partir du catalogue de référence). Ce test tourne
en CI **sans** la base : il relit le fichier gelé et vérifie que chaque effet se range dans un
moment connu (:data:`EVENEMENTS_JEU`) ou un mécanisme connu (:data:`MECANISMES`). Sa dent : il
**échoue** si une carte réclame un déclencheur hors vocabulaire (``declencheurs_non_reconnus``),
ce qui force à compléter la liste et à refaire l'étude — exactement ce que prévoit le critère.
"""

from __future__ import annotations

import json
from pathlib import Path

from pbm_game.effets.evenements import EVENEMENTS_JEU, MECANISMES

CHEMIN = Path(__file__).resolve().parent / "donnees" / "echantillon_200_effets.json"


def _echantillon() -> dict:
    assert CHEMIN.is_file(), f"Échantillon gelé introuvable : {CHEMIN}"
    return json.loads(CHEMIN.read_text(encoding="utf-8"))


def test_echantillon_compte_200_cartes():
    assert _echantillon()["n"] == 200


def test_aucun_declencheur_hors_vocabulaire():
    """La dent du critère n°1 : aucune carte ne réclame un moment que la liste ne porte pas."""
    ech = _echantillon()
    assert ech["declencheurs_non_reconnus"] == 0, (
        "Des cartes de l'échantillon portent un déclencheur non reconnu : compléter "
        "EVENEMENTS_JEU puis refaire l'étude (tools/classer_echantillon.py)."
    )


def test_chaque_evenement_rencontre_est_dans_le_vocabulaire():
    ech = _echantillon()
    inconnus = set(ech["evenements_rencontres"]) - EVENEMENTS_JEU
    assert not inconnus, f"Moments hors vocabulaire dans l'échantillon : {sorted(inconnus)}"


def test_chaque_carte_se_range_dans_moments_et_mecanismes_connus():
    for carte in _echantillon()["cartes"]:
        for ev in carte["evenements"]:
            assert ev in EVENEMENTS_JEU, f"{carte['name']} : moment inconnu {ev!r}"
        for mec in carte["mecanismes"]:
            assert mec in MECANISMES, f"{carte['name']} : mécanisme inconnu {mec!r}"
        assert carte["mecanismes"], f"{carte['name']} : aucun mécanisme classé"


def test_l_echantillon_exerce_plusieurs_moments_et_mecanismes():
    """Garde de sanité : l'échantillon n'est pas vide de sens (sinon le test ne prouve rien)."""
    ech = _echantillon()
    assert len(ech["evenements_rencontres"]) >= 1
    mecanismes = {m for c in ech["cartes"] for m in c["mecanismes"]}
    # Les trois mécanismes non déclenchés et le déclenché sont tous représentés dans l'échantillon.
    assert {"attaque", "continu", "active", "declenche"} <= mecanismes
