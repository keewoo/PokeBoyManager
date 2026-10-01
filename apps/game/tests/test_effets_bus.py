"""Le bus d'événements et son **pont vers le socle** — lot j-effets-architecture.

Le cœur du critère n°4 : les effets « se branchent sur les points d'accroche existants ». On
le prouve en enregistrant un déclencheur du bus dans la table ``declencheurs`` que le socle
accepte déjà d'injecter (``pbm_game.tour.fenetres.declencher`` et
``pbm_game.checkup.resolution.resoudre_checkup`` l'exposent exprès pour cela) — **sans toucher
une ligne du socle**.
"""

from __future__ import annotations

import pytest

from pbm_game.checkup.resolution import resoudre_checkup
from pbm_game.effets.bus import Bus, declencheur_fenetre
from pbm_game.effets.evenements import EJ_ENTRE_TOURS, EJ_FIN_TOUR, EJ_POSE
from pbm_game.effets.pile import EVT_EFFET_RESOLU, EffetEnAttente, SourceEffet
from pbm_game.journal.modele import Evenement
from pbm_game.rng import Rng
from pbm_game.state.modele import (
    PHASE_CHECKUP,
    Carte,
    EtatPartie,
    Joueur,
    PokemonEnJeu,
    Tour,
)
from pbm_game.tour.fenetres import (
    FENETRE_EXPIRATION_EFFETS,
    FENETRE_FIN_TOUR,
    declencher,
)

_RNG = Rng(b"effets-bus-graine")


def _etat(phase: str = "attaque") -> EtatPartie:
    a = PokemonEnJeu(cartes=(Carte("a-1", "ref-a"),))
    b = PokemonEnJeu(cartes=(Carte("b-1", "ref-b"),))
    return EtatPartie(
        joueurs=(Joueur(id="alice", actif=a), Joueur(id="bob", actif=b)),
        tour=Tour(joueur_actif="alice", numero=4, phase=phase),
    )


def _effet_jouet(libelle: str) -> EffetEnAttente:
    return EffetEnAttente(
        type_effet="note",
        source=SourceEffet(libelle=libelle, ref="ref-j", instance_id="i-j"),
        regle="R-12.3",
        libelle=libelle,
    )


def _resolveur_note(etat, effet, rng):
    return etat, [Evenement("note", {"libelle": effet.libelle})], []


def _reacteur_qui_empile(etat, evenement, pile, rng):
    """Un talent déclenché jouet : à l'événement, il empile son effet."""
    return pile.empiler(_effet_jouet(f"reaction-{evenement.type}")), []


def test_le_bus_se_branche_sur_la_fenetre_fin_de_tour_du_socle():
    bus = Bus().abonner(EJ_FIN_TOUR, _reacteur_qui_empile)
    decl = declencheur_fenetre(bus, EJ_FIN_TOUR, {"note": _resolveur_note})
    # On injecte via le paramètre `declencheurs` que le socle expose — on ne modifie rien.
    etat2, evenements = declencher(
        _etat(), FENETRE_FIN_TOUR, _RNG, declencheurs={FENETRE_FIN_TOUR: (decl,)}
    )
    types = [e.type for e in evenements]
    assert "note" in types  # l'effet s'est résolu
    resolus = [e for e in evenements if e.type == EVT_EFFET_RESOLU]
    assert resolus and resolus[0].donnees["source"]["libelle"] == "reaction-fin_tour"


def test_bus_sans_reacteur_est_un_no_op_le_socle_est_inchange():
    """Sans réacteur abonné, la fenêtre ne produit rien et l'état ne bouge pas (sûr à poser)."""
    bus = Bus()
    decl = declencheur_fenetre(bus, EJ_FIN_TOUR, {})
    etat = _etat()
    etat2, evenements = declencher(
        etat, FENETRE_FIN_TOUR, _RNG, declencheurs={FENETRE_FIN_TOUR: (decl,)}
    )
    assert etat2 is etat and evenements == []


def test_le_bus_se_branche_sur_l_expiration_du_checkup():
    """Un déclencheur du bus injecté dans la fenêtre d'expiration du Pokémon Checkup (R-12.5)."""
    bus = Bus().abonner(EJ_ENTRE_TOURS, _reacteur_qui_empile)
    decl = declencheur_fenetre(bus, EJ_ENTRE_TOURS, {"note": _resolveur_note})
    fiches = {
        "a-1": {"pv": 100, "recompenses": 1},
        "b-1": {"pv": 100, "recompenses": 1},
    }
    _, evenements = resoudre_checkup(
        _etat(PHASE_CHECKUP), _RNG, fiches=fiches,
        declencheurs={FENETRE_EXPIRATION_EFFETS: (decl,)},
    )
    libelles = [e.donnees.get("libelle") for e in evenements if e.type == "note"]
    assert "reaction-entre_tours" in libelles


def test_abonnement_a_un_evenement_inconnu_refuse_d9():
    with pytest.raises(ValueError, match="jamais approximé"):
        Bus().abonner("quand_il_pleut", _reacteur_qui_empile)


def test_ordre_des_reacteurs_est_preserve():
    """R-12.3 : les réacteurs réagissent dans l'ordre d'abonnement (ordre de résolution fixe)."""
    ordre: list[str] = []

    def _r1(etat, ev, pile, rng):
        ordre.append("r1")
        return pile, []

    def _r2(etat, ev, pile, rng):
        ordre.append("r2")
        return pile, []

    bus = Bus().abonner(EJ_POSE, _r1).abonner(EJ_POSE, _r2)
    decl = declencheur_fenetre(bus, EJ_POSE, {})
    declencher(_etat(), FENETRE_FIN_TOUR, _RNG, declencheurs={FENETRE_FIN_TOUR: (decl,)})
    assert ordre == ["r1", "r2"]
