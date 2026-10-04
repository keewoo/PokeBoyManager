"""Empreinte, extraction et regroupement des textes d'effet (`pbm_api.jeu.scripts`).

Tests **purs** (aucune base) : ils prouvent le socle du registre `card_scripts` — la normalisation
qui décide de ce qui « change », l'extraction des effets d'une carte, et le regroupement chiffré
qui répond au critère n°2 (« le partage réduit mesurablement le nombre de scripts à écrire »).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from pbm_api.jeu.scripts.empreinte import (
    ORIGINE_ATTAQUE,
    ORIGINE_DRESSEUR,
    ORIGINE_TALENT,
    effets_scriptables,
    empreinte_texte,
    normaliser_texte,
)
from pbm_api.jeu.scripts.groupement import mesurer_groupement


def _carte(*, abilities=None, attacks=None, effect=None, name="Carte"):
    """Une carte factice portant les seuls champs que l'extraction lit (abilities/attacks/effet)."""
    return SimpleNamespace(
        name=name, abilities=abilities, attacks=attacks, effect=effect, id="x"
    )


def test_normalisation_absorbe_espaces_et_casse():
    """Espaces, retours à la ligne et casse sont hors du calcul : même forme normalisée."""
    a = "Piochez  2\ncartes."
    b = "piochez 2 cartes."
    assert normaliser_texte(a) == normaliser_texte(b)
    assert empreinte_texte(a) == empreinte_texte(b)


def test_un_mot_qui_change_change_l_empreinte():
    """Une vraie errata (un nombre, un mot) change l'empreinte — la carte ne se joue plus pareil."""
    assert empreinte_texte("Piochez 2 cartes.") != empreinte_texte("Piochez 3 cartes.")


def test_texte_vide_na_pas_d_empreinte():
    """Un texte vide ou fait d'espaces ne donne aucune empreinte (rien à scripter)."""
    with pytest.raises(ValueError):
        empreinte_texte("   \n  ")


def test_extraction_talent_attaque_dresseur():
    """L'extraction lit talents, attaques à effet et texte de Dresseur ; ignore les dégâts secs."""
    carte = _carte(
        abilities=[{"name": "Fouille", "effect": "Piochez 1 carte."}],
        attacks=[
            {"name": "Charge", "effect": ""},  # dégâts secs : rien à scripter
            {"name": "Éclair", "effect": "Lancez une pièce. Si face, paralysez."},
        ],
    )
    effets = effets_scriptables(carte)
    origines = {e.origine for e in effets}
    assert origines == {ORIGINE_TALENT, ORIGINE_ATTAQUE}
    assert len(effets) == 2  # l'attaque sans effet n'est pas comptée
    dresseur = _carte(abilities=None, attacks=None, effect="Soignez 30 dégâts.")
    assert effets_scriptables(dresseur)[0].origine == ORIGINE_DRESSEUR


def test_carte_sans_effet_nexige_aucun_script():
    """Un Pokémon à dégâts secs / une Énergie de base n'a aucun effet scriptable."""
    carte = _carte(attacks=[{"name": "Charge", "effect": ""}])
    assert effets_scriptables(carte) == []
    assert effets_scriptables(_carte()) == []


def test_effets_identiques_dans_une_carte_comptent_pour_un():
    """Deux textes identiques sur la même carte = une seule exigence (un seul script les couvre)."""
    carte = _carte(
        attacks=[
            {"name": "A", "effect": "Piochez 1 carte."},
            {"name": "B", "effect": "piochez 1 carte."},  # même effet, casse différente
        ]
    )
    assert len(effets_scriptables(carte)) == 1


def test_regroupement_reduit_le_nombre_de_scripts():
    """Critère n°2 : des cartes au même texte partagent un script — le compte le prouve.

    Trois cartes portent le même talent « Fouille » et une attaque chacune ; une quatrième n'a que
    des dégâts secs. Voie naïve : un script par couple carte+effet. Voie groupée : un par texte
    distinct. Le regroupement doit économiser.
    """
    fouille = {"name": "Fouille", "effect": "Piochez 1 carte."}
    cartes = [
        _carte(abilities=[fouille], attacks=[{"name": "Vive-Attaque", "effect": "Reculez d'un."}]),
        _carte(abilities=[fouille], attacks=[{"name": "Vive-Attaque", "effect": "Reculez d'un."}]),
        _carte(abilities=[fouille], attacks=[{"name": "Morsure", "effect": "Soignez 10."}]),
        _carte(attacks=[{"name": "Charge", "effect": ""}]),  # aucun effet
    ]
    m = mesurer_groupement(cartes)
    assert m.cartes_examinees == 4
    assert m.cartes_porteuses == 3
    # Couples (carte, effet) : 3 Fouille + (Vive-Attaque ×2 dédupliquée dans sa carte → comptée par
    # carte) … ici chaque carte dé-duplique en interne, donc : c1 {Fouille, Reculez}, c2 idem,
    # c3 {Fouille, Soignez} = 2+2+2 = 6.
    assert m.effets_total == 6
    # Textes distincts : « Piochez 1 carte. », « Reculez d'un. », « Soignez 10. » = 3.
    assert m.textes_distincts == 3
    assert m.scripts_economises == 3
    assert m.reduction_pct == 50.0


def test_regroupement_sans_effet_ne_divise_pas_par_zero():
    """Un catalogue sans aucun effet rend une réduction de 0 %, pas une erreur."""
    m = mesurer_groupement([_carte(), _carte()])
    assert m.effets_total == 0
    assert m.reduction_pct == 0.0
