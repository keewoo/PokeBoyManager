"""Invariants d'un état de partie — lot j-modele-etat.

Les états aléatoires valides passent ``verifier`` sans violation ; chaque atteinte à un
invariant est détectée et nommée. Chaque test cite la règle ``R-x.y`` qu'il protège.
"""

from __future__ import annotations

import pytest
from fabrique_etats import fabrique_etat

from pbm_game.state import (
    ENDORMI,
    ORIENTATION_NORMALE,
    PARALYSE,
    Carte,
    EtatPartie,
    InvariantViole,
    Joueur,
    PokemonEnJeu,
    Tour,
    assert_invariants,
    carte_active,
    orientation,
    total_cartes_joueur,
    verifier,
)


def _pk(instance: str, etats: frozenset[str] = frozenset()) -> PokemonEnJeu:
    return PokemonEnJeu(cartes=(Carte(instance, f"ref-{instance}"),), etats_speciaux=etats)


def _etat(j0: Joueur, j1: Joueur, tour: Tour | None = None) -> EtatPartie:
    return EtatPartie(joueurs=(j0, j1), tour=tour or Tour("a", 1, "principale"))


def test_etats_aleatoires_sont_sains():
    """La fabrique produit des états valides : aucune violation (base des tests de propriété)."""
    for seed in range(300):
        assert verifier(fabrique_etat(seed)) == [], f"état invalide pour seed={seed}"


def test_banc_de_plus_de_cinq_detecte():
    """R-3.2 : banc ≤ 5."""
    banc = tuple(_pk(f"b{i}") for i in range(6))
    j = Joueur(id="a", actif=_pk("act"), banc=banc)
    violations = verifier(_etat(j, Joueur(id="b")))
    assert any("R-3.2" in v for v in violations)


def test_banc_sans_actif_detecte():
    """R-3.3 : pas de banc sans Actif."""
    j = Joueur(id="a", actif=None, banc=(_pk("b0"),))
    violations = verifier(_etat(j, Joueur(id="b")))
    assert any("R-3.3" in v for v in violations)


def test_plus_de_six_recompenses_detecte():
    """R-3.4 : au plus 6 récompenses."""
    j = Joueur(id="a", recompenses=tuple(Carte(f"r{i}", f"ref-r{i}") for i in range(7)))
    violations = verifier(_etat(j, Joueur(id="b")))
    assert any("R-3.4" in v for v in violations)


def test_carte_dans_deux_zones_detectee():
    """Pas de carte dans deux zones : un instance_id ne peut apparaître qu'une fois."""
    doublon = Carte("dup", "ref-dup")
    j = Joueur(id="a", main=(doublon,), defausse=(doublon,))
    violations = verifier(_etat(j, Joueur(id="b")))
    assert any("double" in v for v in violations)


def test_total_par_joueur_detecte_un_ecart():
    """R-2.1 : si l'attendu est donné, un total différent est signalé."""
    j = Joueur(id="a", main=(Carte("c1", "ref-c1"),))
    violations = verifier(_etat(j, Joueur(id="b")), total_par_joueur=60)
    assert any("R-2.1" in v for v in violations)
    # Et un joueur qui a bien le compte attendu ne déclenche rien de ce chef.
    assert total_cartes_joueur(j) == 1


def test_deux_etats_orientation_detectes():
    """R-11.8 : un seul état d'orientation à la fois."""
    j = Joueur(id="a", actif=_pk("act", frozenset({ENDORMI, PARALYSE})))
    violations = verifier(_etat(j, Joueur(id="b")))
    assert any("R-11.8" in v for v in violations)


def test_etat_special_inconnu_detecte():
    """R-11.1 : seuls les cinq états connus sont admis."""
    j = Joueur(id="a", actif=_pk("act", frozenset({"petrifie"})))
    violations = verifier(_etat(j, Joueur(id="b")))
    assert any("R-11.1" in v for v in violations)


def test_compteurs_negatifs_detectes():
    """R-10.4 : les compteurs de dégâts ne sont jamais négatifs."""
    pk = PokemonEnJeu(cartes=(Carte("c", "ref-c"),), compteurs_degats=-10)
    j = Joueur(id="a", actif=pk)
    violations = verifier(_etat(j, Joueur(id="b")))
    assert any("R-10.4" in v for v in violations)


def test_tour_incoherent_detecte():
    """R-5 : phase connue, numéro ≥ 1, joueur actif présent."""
    etat = _etat(Joueur(id="a"), Joueur(id="b"), Tour("fantome", 0, "sieste"))
    violations = verifier(etat)
    assert any("R-5.1" in v for v in violations)  # phase inconnue
    assert any("Numéro" in v for v in violations)
    assert any("joueur actif" in v for v in violations)


def test_identifiants_de_joueurs_non_distincts_detectes():
    violations = verifier(_etat(Joueur(id="meme"), Joueur(id="meme")))
    assert any("distinct" in v for v in violations)


def test_assert_invariants_leve_sur_etat_invalide():
    j = Joueur(id="a", actif=None, banc=(_pk("b0"),))  # R-3.3
    with pytest.raises(InvariantViole):
        assert_invariants(_etat(j, Joueur(id="b")))


def test_assert_invariants_passe_sur_etat_sain():
    # Ne lève pas : un état sain passe silencieusement.
    assert_invariants(fabrique_etat(42))


def test_orientation_derivee():
    """L'orientation dérive de l'état ; ambiguë → erreur (R-11.8)."""
    assert orientation(_pk("x")) == ORIENTATION_NORMALE
    assert orientation(_pk("x", frozenset({ENDORMI}))) == ENDORMI
    with pytest.raises(ValueError, match="R-11.8"):
        orientation(_pk("x", frozenset({ENDORMI, PARALYSE})))


def test_carte_active_est_le_sommet_de_pile():
    """R-7.1 : l'évolution courante est au sommet de la pile."""
    pk = PokemonEnJeu(cartes=(Carte("base", "ref-base"), Carte("evo", "ref-evo")))
    assert carte_active(pk).ref == "ref-evo"
