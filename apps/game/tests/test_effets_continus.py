"""Effets continus = modificateurs *dérivés* de ce qui est en jeu. Lot j-effets-architecture.

Le critère d'acceptation n°2 : **le retrait d'un effet continu (Outil défaussé, Stade remplacé)
restaure exactement l'état antérieur du calcul.** On le prouve ici par construction — aucun
effet n'est « défait », c'est la source qui disparaît de l'état et le modificateur qui cesse
d'être produit. Aucune carte réelle n'est scriptée (D9) : producteurs *jouets*.
"""

from __future__ import annotations

from dataclasses import replace

from pbm_game.combat.modele import modificateur_ajout
from pbm_game.combat.resolution import resoudre_degats
from pbm_game.effets.continus import (
    FACE_ATTAQUANT,
    FACE_DEFENSEUR,
    PORTEE_OUTIL,
    PORTEE_STADE,
    EffetContinu,
    collecter_effets_continus,
    modificateurs_degats,
    seuil_ko,
)
from pbm_game.effets.pile import SourceEffet
from pbm_game.state.modele import Carte, EtatPartie, Joueur, PokemonEnJeu, Tour

# --- Producteurs jouets (le rôle des lots j-cartes-outils / j-cartes-stades) -------------

REF_OUTIL = "jouet-bandeau"
REF_STADE = "jouet-stade"


def _producteur_outil(etat, ref, cible):
    """Un Outil jouet : +20 dégâts quand son porteur attaque, +30 PV (R-3.7)."""
    src = SourceEffet(libelle="Bandeau jouet", ref=ref, instance_id=f"outil-{cible}")
    return [
        EffetContinu(
            libelle="Bandeau +20", regle="R-3.7", source=src, portee=PORTEE_OUTIL, cible=cible,
            modificateur=modificateur_ajout("Bandeau", "R-3.7", 20), face=FACE_ATTAQUANT,
        ),
        EffetContinu(
            libelle="Bandeau +30 PV", regle="R-3.7", source=src, portee=PORTEE_OUTIL,
            cible=cible, pv=30,
        ),
    ]


def _producteur_stade(etat, ref, cible):
    """Un Stade jouet : −20 aux dégâts reçus par le défenseur, les deux camps (R-3.5)."""
    src = SourceEffet(libelle="Stade jouet", ref=ref)
    return [
        EffetContinu(
            libelle="Stade −20", regle="R-3.5", source=src, portee=PORTEE_STADE, cible=None,
            modificateur=modificateur_ajout("Stade", "R-3.5", -20), face=FACE_DEFENSEUR,
        )
    ]


def _etat(*, avec_outil: bool, stade: bool = False) -> EtatPartie:
    outil = Carte("outil-x", REF_OUTIL) if avec_outil else None
    attaquant = PokemonEnJeu(cartes=(Carte("a-1", "ref-atk"),), outil=outil)
    defenseur = PokemonEnJeu(cartes=(Carte("b-1", "ref-def"),))
    return EtatPartie(
        joueurs=(Joueur(id="alice", actif=attaquant), Joueur(id="bob", actif=defenseur)),
        tour=Tour(joueur_actif="alice", numero=3, phase="attaque"),
        stade=Carte("stade-c", REF_STADE) if stade else None,
    )


_REGISTRE = {REF_OUTIL: _producteur_outil, REF_STADE: _producteur_stade}


def _degats(etat: EtatPartie, base: int) -> int:
    effets = collecter_effets_continus(etat, _REGISTRE)
    att, deff = modificateurs_degats(effets, attaquant="a-1", defenseur="b-1")
    res = resoudre_degats(base=base, modificateurs_attaquant=att, modificateurs_defenseur=deff)
    return res.degats


def test_retrait_d_un_outil_restaure_exactement_le_calcul_r37():
    avec = _etat(avec_outil=True)
    sans = replace(
        avec,
        joueurs=(replace(avec.joueurs[0], actif=replace(avec.joueurs[0].actif, outil=None)),
                 avec.joueurs[1]),
    )
    assert _degats(avec, base=50) == 70  # +20 Bandeau
    assert _degats(sans, base=50) == 50  # Outil retiré → le +20 n'est plus produit, calcul restauré


def test_retrait_d_un_outil_de_pv_abaisse_le_seuil_de_ko_r131():
    avec = _etat(avec_outil=True)
    effets_avec = collecter_effets_continus(avec, _REGISTRE)
    assert seuil_ko(120, effets_avec, "a-1") == 150  # +30 PV
    sans_effets = collecter_effets_continus(replace(avec, joueurs=(
        replace(avec.joueurs[0], actif=replace(avec.joueurs[0].actif, outil=None)),
        avec.joueurs[1])), _REGISTRE)
    assert seuil_ko(120, sans_effets, "a-1") == 120
    # 130 compteurs : en vie sous Outil (130 < 150), K.O. dès son retrait (130 ≥ 120).
    compteurs = 130
    assert compteurs < seuil_ko(120, effets_avec, "a-1")
    assert compteurs >= seuil_ko(120, sans_effets, "a-1")


def test_remplacement_d_un_stade_restaure_le_calcul_r35():
    avec = _etat(avec_outil=False, stade=True)
    sans = replace(avec, stade=None)
    assert _degats(avec, base=50) == 30  # −20 Stade côté défenseur
    assert _degats(sans, base=50) == 50  # Stade retiré → réduction disparue, calcul restauré


def test_stade_frappe_les_deux_camps_cible_none():
    """Un effet de Stade (cible None) s'applique quel que soit le défenseur (R-3.5)."""
    etat = _etat(avec_outil=False, stade=True)
    effets = collecter_effets_continus(etat, _REGISTRE)
    _, deff = modificateurs_degats(effets, attaquant="a-1", defenseur="b-1")
    assert len(deff) == 1  # global → s'applique
    _, deff_autre = modificateurs_degats(effets, attaquant="b-1", defenseur="a-1")
    assert len(deff_autre) == 1  # et dans l'autre sens aussi


def test_collecte_vide_sans_source_en_jeu():
    etat = _etat(avec_outil=False)
    assert collecter_effets_continus(etat, _REGISTRE) == []


def test_effet_continu_sans_contribution_est_refuse():
    import pytest

    with pytest.raises(ValueError, match="ne contribue rien"):
        EffetContinu(libelle="vide", regle="R-3.5", source=SourceEffet("x"), portee=PORTEE_STADE)
