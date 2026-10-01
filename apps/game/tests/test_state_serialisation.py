"""Sérialisation JSON bidirectionnelle de l'état — lot j-modele-etat.

Propriété centrale (rejouabilité) : ``depuis_json(vers_json(etat)) == etat`` pour tout
état valide. Ces tests échouent sans le module ``pbm_game.state.serialisation`` (import
impossible) : ce sont les « tests qui échouent sans le changement et passent avec ».
"""

from __future__ import annotations

import json

import pytest
from fabrique_etats import fabrique_etat

from pbm_game.state import (
    SCHEMA_VERSION,
    Carte,
    EtatPartie,
    Joueur,
    PokemonEnJeu,
    Tour,
    depuis_json,
    vers_json,
)


def test_round_trip_identique_sur_etats_aleatoires():
    """Sérialiser puis désérialiser un état quelconque le laisse identique."""
    for seed in range(300):
        etat = fabrique_etat(seed)
        assert depuis_json(vers_json(etat)) == etat, f"round-trip cassé pour seed={seed}"


def test_sortie_est_json_pur():
    """La sortie ne contient que des types JSON (json.dumps ne lève pas)."""
    for seed in range(50):
        json.dumps(vers_json(fabrique_etat(seed)))


def test_sortie_deterministe():
    """Deux sérialisations du même état sont identiques, et les états sont triés."""
    etat = fabrique_etat(7)
    assert vers_json(etat) == vers_json(etat)
    # Un état avec plusieurs marqueurs : la liste sérialisée doit être triée.
    pk = PokemonEnJeu(
        cartes=(Carte("c1", "ref-c1"),),
        etats_speciaux=frozenset({"empoisonne", "brule"}),
    )
    j = Joueur(id="a", actif=pk)
    etat2 = EtatPartie(joueurs=(j, Joueur(id="b")), tour=Tour("a", 1, "principale"))
    sortie = vers_json(etat2)
    assert sortie["joueurs"][0]["actif"]["etats_speciaux"] == ["brule", "empoisonne"]


def test_schema_version_presente_et_exacte():
    sortie = vers_json(fabrique_etat(1))
    assert sortie["schema_version"] == SCHEMA_VERSION


def test_depuis_json_refuse_version_inconnue():
    """Une version inconnue échoue bruyamment — jamais de repli silencieux."""
    sortie = vers_json(fabrique_etat(1))
    sortie["schema_version"] = 999
    with pytest.raises(ValueError, match="schema_version"):
        depuis_json(sortie)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d.pop("joueurs"),
        lambda d: d.__setitem__("joueurs", [d["joueurs"][0]]),  # un seul joueur
        lambda d: d["joueurs"][0].__setitem__("id", ""),  # id vide
        lambda d: d.__setitem__("tour", {"joueur_actif": "alice"}),  # tour incomplet
        lambda d: d["joueurs"][0]["pioche"].append({"ref": "sans-id"}),  # carte sans instance_id
    ],
)
def test_depuis_json_refuse_structures_malformees(mutation):
    sortie = vers_json(fabrique_etat(3))
    mutation(sortie)
    with pytest.raises(ValueError):
        depuis_json(sortie)


def test_pokemon_sans_carte_refuse_a_la_relecture():
    """Un Pokémon en jeu a toujours au moins une carte (R-3.6)."""
    sortie = vers_json(fabrique_etat(5))
    # Forcer un Actif sur le premier joueur puis vider sa pile.
    sortie["joueurs"][0]["actif"] = {
        "cartes": [],
        "energies": [],
        "outil": None,
        "compteurs_degats": 0,
        "etats_speciaux": [],
    }
    with pytest.raises(ValueError, match="cartes"):
        depuis_json(sortie)
