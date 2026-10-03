"""Reproduction et campagne : une anomalie se rejoue en une commande, une campagne agrège sans
jamais s'arrêter au premier pépin.
"""

from __future__ import annotations

from pbm_sim.__main__ import main
from pbm_sim.campagne import campagne, graines
from pbm_sim.orchestrateur import ANOMALIE_PARTIE_SANS_FIN


def test_le_parallelisme_et_la_serie_donnent_le_meme_bilan():
    """Une campagne doit donner le même résultat en parallèle et en série (le parallélisme ne
    change que la vitesse, jamais l'issue)."""
    serie = campagne(graines("repro", 8), parallele=False)
    para = campagne(graines("repro", 8), parallele=True)
    assert serie.nombre == para.nombre == 8
    assert serie.saines == para.saines
    assert serie.raisons == para.raisons


def test_une_campagne_collecte_toutes_les_anomalies_sans_s_arreter():
    """Avec un plafond de coups bas, toutes les parties deviennent « sans fin » : la campagne les
    compte toutes (elle ne s'arrête pas au premier échec) et chacune porte sa graine."""
    r = campagne(graines("repro", 8), parallele=False, max_pas=3)
    assert r.nombre == 8
    assert r.saines == 0
    assert len(r.anomalies) == 8
    assert all(a.type == ANOMALIE_PARTIE_SANS_FIN for a in r.anomalies)
    assert {a.graine for a in r.anomalies} == set(graines("repro", 8))


def test_cli_reproduire_rend_0_sur_une_partie_saine():
    """``python -m pbm_sim reproduire <graine>`` sort en 0 sur une partie saine (une commande)."""
    assert main(["reproduire", "repro:0"]) == 0


def test_cli_reproduire_rend_1_quand_la_partie_porte_une_anomalie():
    """Même commande, plafond bas : la partie est « sans fin », le code de sortie vaut 1."""
    assert main(["reproduire", "repro:0", "--max-pas", "3"]) == 1


def test_cli_campagne_rend_1_quand_il_reste_une_anomalie():
    """La campagne en ligne de commande sert de garde : code 1 s'il reste une anomalie."""
    code = main(["campagne", "--prefixe", "repro", "--nombre", "4", "--serie", "--max-pas", "3"])
    assert code == 1
