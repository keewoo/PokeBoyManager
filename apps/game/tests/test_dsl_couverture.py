"""Couverture du vocabulaire par 500 textes réels — critère d'acceptation n°1.

« Le vocabulaire couvre au moins 80 % des 500 textes dépouillés **sans primitive code libre**. »

L'échantillon est **gelé** dans ``tests/donnees/echantillon_500_dsl.json`` (produit par
``apps/game/tools/classer_dsl.py`` sur le catalogue de référence). Ce test tourne en CI **sans**
la base : il relit le fichier gelé et **échoue** si la couverture tombe sous 80 %, si une carte
réclame une primitive hors du vocabulaire, ou si une primitive « code libre » s'y est glissée.
"""

from __future__ import annotations

import json
from pathlib import Path

from pbm_game.effets.dsl.vocabulaire import OPS

CHEMIN = Path(__file__).resolve().parent / "donnees" / "echantillon_500_dsl.json"
SEUIL = 0.80


def _echantillon() -> dict:
    assert CHEMIN.is_file(), f"Échantillon gelé introuvable : {CHEMIN}"
    return json.loads(CHEMIN.read_text(encoding="utf-8"))


def test_echantillon_compte_500_textes():
    assert _echantillon()["n"] == 500


def test_couverture_au_moins_80_pourcent():
    """La dent du critère n°1 : le langage a des mots pour au moins 80 % des effets réels."""
    ech = _echantillon()
    assert ech["taux_couverture"] >= SEUIL, (
        f"Couverture {ech['taux_couverture']:.1%} < {SEUIL:.0%} — enrichir le vocabulaire "
        "(vocabulaire.py) ou les tournures du dépouillement, puis regeler l'échantillon."
    )


def test_aucune_primitive_hors_vocabulaire():
    """Toute primitive citée par une carte est dans le vocabulaire fermé (pas de code libre)."""
    ech = _echantillon()
    for carte in ech["cartes"]:
        inconnues = set(carte["primitives"]) - OPS
        assert not inconnues, f"{carte['name']} : primitive(s) hors vocabulaire {sorted(inconnues)}"


def test_pas_de_primitive_code_libre():
    """Aucune clé « code_libre » (ou variante) ne doit exister — c'est le piège interdit (D9)."""
    ech = _echantillon()
    assert "code_libre" not in ech["histogramme_primitives"]
    assert "code_libre" not in OPS


def test_toutes_les_primitives_sont_exercees_par_des_cartes_reelles():
    """Garde de sanité : chaque primitive du vocabulaire se justifie par au moins une carte réelle.

    Si une primitive n'apparaît jamais dans 500 textes, elle n'a probablement pas sa place dans le
    vocabulaire (ou le dépouillement ne la détecte pas) — dans les deux cas, on veut le savoir.
    """
    histo = _echantillon()["histogramme_primitives"]
    assert set(histo) == set(OPS), (
        "L'histogramme et le vocabulaire doivent lister les mêmes primitives."
    )
    jamais_vues = [op for op, n in histo.items() if n == 0]
    assert not jamais_vues, f"Primitives jamais rencontrées dans 500 cartes : {jamais_vues}"
