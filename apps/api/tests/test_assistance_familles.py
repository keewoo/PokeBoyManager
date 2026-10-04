"""Classement par famille (`pbm_api.jeu.scripts.assistance.familles`) — pur, aucune E/S."""

from __future__ import annotations

from pbm_api.jeu.scripts.assistance.familles import (
    FAMILLE_AUTRE,
    famille,
    famille_du_script,
    famille_du_texte,
)


def test_famille_du_script_lit_la_premiere_primitive_classante():
    script = {"version": 1, "effets": [{"op": "piocher", "nombre": 2}]}
    assert famille_du_script(script) == "pioche"


def test_famille_du_script_descend_dans_les_structures_de_controle():
    """Un « si » n'est pas classant : on descend jusqu'à la primitive (ici des dégâts)."""
    script = {
        "version": 1,
        "effets": [
            {
                "op": "si",
                "condition": {"type": "resultat_pile", "attendu": "face"},
                "alors": [{"op": "poser_compteurs", "cible": {"zone": "actif"}, "nombre": 2}],
            }
        ],
    }
    assert famille_du_script(script) == "degats"


def test_famille_du_texte_par_mot_cle():
    assert famille_du_texte("Piochez 2 cartes.") == "pioche"
    assert famille_du_texte("Votre adversaire est maintenant Empoisonné.") == "etat_special"


def test_famille_prefere_le_script_au_texte():
    """Le script dit ce que l'effet FAIT ; le texte n'est qu'un repli (effet non supporté)."""
    texte = "Piochez 2 cartes."  # mot-clé « pioche »
    script = {"version": 1, "effets": [{"op": "soigner", "cible": {"zone": "actif"}, "nombre": 2}]}
    assert famille(texte, script) == "soin"  # le script l'emporte


def test_famille_inconnue_tombe_dans_autre_sans_deviner():
    assert famille_du_texte("Texte sans mot-clé reconnu.") == FAMILLE_AUTRE
    assert famille("Texte opaque.", None) == FAMILLE_AUTRE
