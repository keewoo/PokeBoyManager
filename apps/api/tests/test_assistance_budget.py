"""Grand livre (`pbm_api.jeu.scripts.assistance.budget`) — pur, un fichier JSON temporaire.

Couvre les points 2 et 4 de la mission : plafond cumulé, coût par carte, reprise sans retraitement.
"""

from __future__ import annotations

from decimal import Decimal

from pbm_api.jeu.scripts.assistance import budget as budget_mod
from pbm_api.jeu.scripts.assistance.budget import GrandLivre


def test_reprise_ne_retraite_pas_un_effet_deja_vu(tmp_path):
    chemin = tmp_path / "ledger.json"
    livre = GrandLivre()
    livre.enregistrer(
        empreinte="aaa", resultat="scripte", cost_usd=Decimal("0.01"), cost_eur=Decimal("0.009")
    )
    budget_mod.sauver(livre, chemin)

    relu = budget_mod.charger(chemin)
    assert relu.deja_traitee("aaa") is True
    assert relu.deja_traitee("bbb") is False


def test_enregistrer_est_idempotent_par_empreinte(tmp_path):
    """Ré-enregistrer le même effet ne double ni le coût ni le compteur (reprise après crash)."""
    livre = GrandLivre()
    livre.enregistrer(
        empreinte="aaa", resultat="scripte", cost_usd=Decimal("0.01"), cost_eur=Decimal("0.009")
    )
    livre.enregistrer(
        empreinte="aaa", resultat="scripte", cost_usd=Decimal("0.01"), cost_eur=Decimal("0.009")
    )
    assert livre.scriptes == 1
    assert Decimal(livre.total_spent_eur) == Decimal("0.009")


def test_reste_eur_et_cout_par_carte_validee():
    livre = GrandLivre()
    livre.enregistrer(
        empreinte="a", resultat="scripte", cost_usd=Decimal("0"), cost_eur=Decimal("0.40")
    )
    livre.enregistrer(
        empreinte="b", resultat="non_supporte", cost_usd=Decimal("0"), cost_eur=Decimal("0.20")
    )
    assert livre.reste_eur(Decimal("50")) == Decimal("49.40")
    # Coût par SCRIPT validé = dépense totale / nb scriptés (1 ici) = 0.60 (b a aussi coûté).
    assert livre.cout_par_carte_validee() == Decimal("0.60")


def test_cout_par_carte_validee_est_zero_sans_script(tmp_path):
    livre = GrandLivre()
    livre.enregistrer(
        empreinte="a", resultat="non_supporte", cost_usd=Decimal("0"), cost_eur=Decimal("0.10")
    )
    assert livre.cout_par_carte_validee() == Decimal("0")  # jamais une division par zéro
