"""Tests de la machine à tour — lot ``j-machine-tour``.

Ce fichier FAIT FOI sur les critères d'acceptation de la mission :

1. **les six contraintes de tour** sont testées **dans les deux sens** (autorisé / refusé
   motivé), chaque refus citant un ``R-x.y`` qui **existe** dans ``docs/jeu/REGLES.md`` ;
2. les **drapeaux** d'énergie, de Supporter et de retraite — et l'ensemble « entré en jeu
   ce tour » — **survivent à une sérialisation / reprise** (round-trip exact) ;
3. **déclarer une attaque termine le tour même sans aucun dégât** (R-5.8).

S'y ajoutent : la **pioche impossible = défaite** (R-14.2) vérifiée au bon moment et non en
exception, les **fenêtres de déclenchement** câblées (début / fin de tour), et la **remise à
zéro** des drapeaux au tour suivant. Chaque test de règle nomme le ``R-x.y`` qu'il vérifie.

La suite échoue naturellement sans le paquet ``pbm_game.tour`` (import en tête) : c'est le
« test qui échoue sans le changement et passe avec ».
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

from pbm_game.actions import actions_legales, valider
from pbm_game.journal import (
    ACTION_AVANCER_PHASE,
    ACTION_DEBUT_TOUR,
    ACTION_DECLARER_ATTAQUE,
    AUTEUR_SYSTEME,
    EVT_ATTAQUE_DECLAREE,
    EVT_CARTES_PIOCHEES,
    EVT_PARTIE_TERMINEE,
    RAISON_PIOCHE_IMPOSSIBLE,
    Action,
    appliquer,
)
from pbm_game.regles import identifiants_definis
from pbm_game.rng import Rng
from pbm_game.state import (
    PHASE_ATTAQUE,
    PHASE_CHECKUP,
    PHASE_PIOCHE,
    PHASE_PRINCIPALE,
    Carte,
    EtatPartie,
    Joueur,
    PokemonEnJeu,
    Tour,
    assert_invariants,
    depuis_json,
    vers_json,
)
from pbm_game.tour import (
    FENETRE_DEBUT_TOUR,
    FENETRE_FIN_TOUR,
    declencher,
    identite_pokemon,
    marquer_energie_posee,
    marquer_entree_en_jeu,
    marquer_retraite_faite,
    marquer_supporter_joue,
)
from pbm_game.tour.contraintes import (
    attaque_permise,
    peut_attacher_energie,
    peut_battre_retraite,
    peut_evoluer,
    peut_jouer_supporter,
)

# apps/game/tests/test_machine_tour.py -> racine du dépôt (parents[3]).
RACINE_DEPOT = Path(__file__).resolve().parents[3]
CHEMIN_REGLES = RACINE_DEPOT / "docs" / "jeu" / "REGLES.md"

# Ni le début de tour, ni la fin de tour ne tirent d'aléatoire (les fenêtres sont vides) :
# un Rng partagé suffit, et il ne doit jamais avancer dans ces tests.
_RNG = Rng(b"machine-tour-seed")


def _regles_definies() -> set[str]:
    assert CHEMIN_REGLES.is_file(), f"Corpus introuvable : {CHEMIN_REGLES}"
    return identifiants_definis(CHEMIN_REGLES.read_text(encoding="utf-8"))


def _tour(
    numero: int,
    *,
    phase: str = PHASE_PRINCIPALE,
    actif: str = "alice",
    energie_posee: bool = False,
    supporter_joue: bool = False,
    retraite_faite: bool = False,
    entres: frozenset[str] = frozenset(),
) -> Tour:
    return Tour(
        joueur_actif=actif,
        numero=numero,
        phase=phase,
        energie_posee=energie_posee,
        supporter_joue=supporter_joue,
        retraite_faite=retraite_faite,
        entres_en_jeu_ce_tour=entres,
    )


def _etat(tour: Tour, *, pioche_alice: tuple[Carte, ...] = ()) -> EtatPartie:
    """Un état minimal à deux joueurs, chacun avec un Actif ; alice reçoit ``pioche_alice``."""
    alice = Joueur(
        id="alice",
        actif=PokemonEnJeu(cartes=(Carte("a-pk-1", "ref-pk"),)),
        pioche=pioche_alice,
    )
    bob = Joueur(id="bob", actif=PokemonEnJeu(cartes=(Carte("b-pk-1", "ref-pk"),)))
    return EtatPartie(joueurs=(alice, bob), tour=tour)


# --- Pureté et API -----------------------------------------------------------


def test_import_tour_ne_tire_aucune_dependance_lourde():
    """Importer ``pbm_game.tour`` (et ses contraintes) ne charge aucun module interdit."""
    interdits = {"fastapi", "sqlalchemy", "httpx", "requests", "redis", "boto3", "pbm_api"}
    importlib.import_module("pbm_game.tour")
    importlib.import_module("pbm_game.tour.contraintes")
    charges = interdits & set(sys.modules)
    assert not charges, f"L'import a tiré des dépendances interdites : {sorted(charges)}"


# --- Les SIX contraintes de tour, dans les deux sens (motivées) --------------


def test_contrainte_1_energie_une_par_tour_r54():
    """R-5.4 — attacher une énergie : permis une fois, refusé la seconde, règle citée."""
    assert peut_attacher_energie(_tour(3)).accepte
    v = peut_attacher_energie(_tour(3, energie_posee=True))
    assert v.refuse and v.regle == "R-5.4" and v.message
    # Le marqueur reproduit le refus : poser l'énergie ferme la porte.
    assert peut_attacher_energie(marquer_energie_posee(_tour(3))).refuse


def test_contrainte_2_supporter_un_par_tour_r55():
    """R-5.5 — un seul Supporter par tour (hors premier tour, voir R-6.2)."""
    assert peut_jouer_supporter(_tour(3)).accepte
    v = peut_jouer_supporter(_tour(3, supporter_joue=True))
    assert v.refuse and v.regle == "R-5.5" and v.message
    assert peut_jouer_supporter(marquer_supporter_joue(_tour(3))).refuse


def test_contrainte_3_retraite_une_par_tour_r56():
    """R-5.6 — une seule retraite par tour."""
    assert peut_battre_retraite(_tour(3)).accepte
    v = peut_battre_retraite(_tour(3, retraite_faite=True))
    assert v.refuse and v.regle == "R-5.6" and v.message
    assert peut_battre_retraite(marquer_retraite_faite(_tour(3))).refuse


def test_contrainte_4_pas_evolution_pokemon_entre_ce_tour_r73():
    """R-7.3 — pas d'évolution d'un Pokémon entré en jeu ce tour-ci."""
    base = "a-pk-1"
    # Tour ordinaire (numéro 3), Pokémon présent de longue date : évolution permise…
    assert peut_evoluer(_tour(3), base).accepte
    # …mais refusée s'il est entré en jeu CE tour (règle citée).
    v = peut_evoluer(_tour(3, entres=frozenset({base})), base)
    assert v.refuse and v.regle == "R-7.3" and v.message
    # Le marqueur d'entrée en jeu reproduit le refus pour ce Pokémon précis.
    marque = marquer_entree_en_jeu(_tour(3), base)
    assert peut_evoluer(marque, base).refuse
    assert peut_evoluer(marque, "autre-pk").accepte  # un autre Pokémon n'est pas concerné


def test_contrainte_5_pas_evolution_au_premier_tour_r65():
    """R-6.5 — aucun joueur ne peut faire évoluer à son premier tour (numéros 1 et 2)."""
    for numero in (1, 2):
        v = peut_evoluer(_tour(numero), "a-pk-1")
        assert v.refuse and v.regle == "R-6.5" and v.message
    # Dès le tour suivant du joueur, l'évolution redevient permise.
    assert peut_evoluer(_tour(3), "a-pk-1").accepte


def test_contrainte_6_regle_du_premier_tour_attaque_et_supporter_r61_r62():
    """R-6.1 / R-6.2 — le joueur qui commence (tour 1) n'attaque pas et ne joue pas de Supporter."""
    # R-6.1 : pas d'attaque au premier tour du joueur qui commence (tour 1).
    v_att = attaque_permise(_tour(1))
    assert v_att.refuse and v_att.regle == "R-6.1" and v_att.message
    # R-6.2 : pas de Supporter non plus.
    v_sup = peut_jouer_supporter(_tour(1))
    assert v_sup.refuse and v_sup.regle == "R-6.2" and v_sup.message
    # Le second joueur (tour 2) PEUT attaquer et jouer un Supporter dès son premier tour.
    assert attaque_permise(_tour(2)).accepte
    assert peut_jouer_supporter(_tour(2)).accepte
    # Et le joueur qui commence attaque normalement à son second tour (numéro 3).
    assert attaque_permise(_tour(3)).accepte


def test_chaque_refus_de_contrainte_cite_une_regle_du_corpus():
    """Critère : tout ``R-x.y`` de refus des six contraintes existe dans docs/jeu/REGLES.md."""
    definies = _regles_definies()
    refus_observes = [
        peut_attacher_energie(_tour(3, energie_posee=True)),
        peut_jouer_supporter(_tour(3, supporter_joue=True)),
        peut_jouer_supporter(_tour(1)),
        peut_battre_retraite(_tour(3, retraite_faite=True)),
        peut_evoluer(_tour(3, entres=frozenset({"a-pk-1"})), "a-pk-1"),
        peut_evoluer(_tour(1), "a-pk-1"),
        attaque_permise(_tour(1)),
    ]
    for v in refus_observes:
        assert v.refuse, "ce cas doit être un refus"
        assert v.regle in definies, f"règle citée « {v.regle} » absente du corpus REGLES.md"
        assert v.message.strip(), "un refus doit porter un message lisible"


# --- Identité d'un Pokémon à travers l'évolution -----------------------------


def test_identite_pokemon_est_la_carte_de_base():
    """L'identité stable d'un Pokémon est l'instance de sa carte de base (R-7.1)."""
    pk = PokemonEnJeu(cartes=(Carte("base-1", "ref-base"), Carte("evo-1", "ref-evo")))
    assert identite_pokemon(pk) == "base-1"


# --- Drapeaux : survie à la sérialisation / reprise (critère 2) --------------


def test_drapeaux_survivent_a_une_serialisation_reprise():
    """Les trois drapeaux et « entrés en jeu ce tour » survivent à un round-trip JSON exact."""
    tour = _tour(
        4,
        phase=PHASE_ATTAQUE,
        energie_posee=True,
        supporter_joue=True,
        retraite_faite=True,
        entres=frozenset({"a-pk-1", "b-pk-1"}),
    )
    etat = _etat(tour)
    # Reprise « après un F5 » : état -> JSON (texte) -> état.
    repris = depuis_json(json.loads(json.dumps(vers_json(etat))))
    assert repris == etat
    assert repris.tour.energie_posee is True
    assert repris.tour.supporter_joue is True
    assert repris.tour.retraite_faite is True
    assert repris.tour.entres_en_jeu_ce_tour == frozenset({"a-pk-1", "b-pk-1"})


def test_entres_en_jeu_ce_tour_defaut_vide_et_retrocompatible():
    """Un JSON de tour SANS « entres_en_jeu_ce_tour » se relit avec un ensemble vide."""
    etat = _etat(_tour(3))
    brut = vers_json(etat)
    del brut["tour"]["entres_en_jeu_ce_tour"]  # ancien JSON, champ absent
    repris = depuis_json(brut)
    assert repris.tour.entres_en_jeu_ce_tour == frozenset()


# --- Déclarer une attaque termine le tour, même sans dégât (critère 3) -------


def test_declarer_attaque_termine_le_tour_sans_degat_r58():
    """R-5.8 — déclarer une attaque termine le tour même si elle n'inflige aucun dégât."""
    etat = _etat(_tour(3, phase=PHASE_PRINCIPALE, actif="alice"))
    pv_bob_avant = etat.joueurs[1].actif.compteurs_degats
    etat2, evenements = appliquer(etat, Action(ACTION_DECLARER_ATTAQUE, "alice"), _RNG)
    # Le tour est terminé : on est passé au Checkup (R-5.7).
    assert etat2.tour.phase == PHASE_CHECKUP
    # Aucun dégât posé (le calcul des dégâts arrive avec j-degats-resolution).
    assert etat2.joueurs[1].actif.compteurs_degats == pv_bob_avant
    types = [e.type for e in evenements]
    assert EVT_ATTAQUE_DECLAREE in types
    decl = next(e for e in evenements if e.type == EVT_ATTAQUE_DECLAREE)
    assert decl.donnees["degats"] == 0
    assert_invariants(etat2)


def test_declarer_attaque_possible_depuis_la_phase_d_attaque():
    """Déclarer une attaque est aussi possible depuis la phase d'attaque (R-5.1)."""
    etat = _etat(_tour(3, phase=PHASE_ATTAQUE, actif="alice"))
    etat2, _ = appliquer(etat, Action(ACTION_DECLARER_ATTAQUE, "alice"), _RNG)
    assert etat2.tour.phase == PHASE_CHECKUP


def test_declarer_attaque_refusee_au_premier_tour_du_joueur_qui_commence_r61():
    """R-6.1 — le joueur qui commence ne peut pas déclarer d'attaque au tour 1."""
    etat = _etat(_tour(1, phase=PHASE_PRINCIPALE, actif="alice"))
    with pytest.raises(ValueError, match="R-6.1"):
        appliquer(etat, Action(ACTION_DECLARER_ATTAQUE, "alice"), _RNG)


def test_declarer_attaque_refusee_pour_le_joueur_non_actif():
    """Seul le joueur actif déclare une attaque (R-5.7)."""
    etat = _etat(_tour(3, phase=PHASE_PRINCIPALE, actif="alice"))
    with pytest.raises(ValueError, match="R-5.7"):
        appliquer(etat, Action(ACTION_DECLARER_ATTAQUE, "bob"), _RNG)


def test_declarer_attaque_n_est_pas_un_coup_liste_d9():
    """D9 — le coup d'attaque complet (coût, dégâts) n'étant pas scripté, il n'est pas listé."""
    etat = _etat(_tour(3, phase=PHASE_PRINCIPALE, actif="alice"))
    verdict = valider(etat, Action(ACTION_DECLARER_ATTAQUE, "alice"))
    assert verdict.refuse and verdict.regle == "R-15.12"


# --- Début de tour : pioche obligatoire / défaite sur pioche impossible ------


def test_debut_tour_pioche_obligatoire_et_passe_en_principale_r52():
    """R-5.2 — le début de tour pioche 1 carte (obligatoire) puis passe en phase principale."""
    carte = Carte("a-pioche-1", "ref-draw")
    etat = _etat(_tour(3, phase=PHASE_PIOCHE, actif="alice"), pioche_alice=(carte,))
    etat2, evenements = appliquer(etat, Action(ACTION_DEBUT_TOUR, AUTEUR_SYSTEME), _RNG)
    assert etat2.tour.phase == PHASE_PRINCIPALE
    assert etat2.joueurs[0].main[-1].instance_id == "a-pioche-1"
    assert len(etat2.joueurs[0].pioche) == 0
    assert any(e.type == EVT_CARTES_PIOCHEES for e in evenements)
    assert_invariants(etat2)


def test_debut_tour_pioche_impossible_est_une_defaite_r142():
    """R-14.2 — pioche impossible en début de tour = DÉFAITE (condition, pas exception)."""
    etat = _etat(_tour(5, phase=PHASE_PIOCHE, actif="alice"), pioche_alice=())
    etat2, evenements = appliquer(etat, Action(ACTION_DEBUT_TOUR, AUTEUR_SYSTEME), _RNG)
    assert etat2.terminee
    assert etat2.vainqueur == "bob"
    assert etat2.raison_fin == RAISON_PIOCHE_IMPOSSIBLE
    # La phase n'avance pas : la partie est figée.
    assert etat2.tour.phase == PHASE_PIOCHE
    fin = next(e for e in evenements if e.type == EVT_PARTIE_TERMINEE)
    assert fin.donnees["perdant"] == "alice" and fin.donnees["vainqueur"] == "bob"
    assert_invariants(etat2)


def test_debut_tour_refuse_hors_phase_de_pioche():
    """Le début de tour ne s'applique qu'en phase de pioche (R-5.1)."""
    etat = _etat(_tour(3, phase=PHASE_PRINCIPALE, actif="alice"), pioche_alice=(Carte("x", "r"),))
    with pytest.raises(ValueError, match="R-5.1"):
        appliquer(etat, Action(ACTION_DEBUT_TOUR, AUTEUR_SYSTEME), _RNG)


def test_debut_tour_n_est_pas_un_coup_du_joueur_r52():
    """R-5.2 — le début de tour est une action système, pas un coup libre du joueur."""
    etat = _etat(_tour(3, phase=PHASE_PIOCHE, actif="alice"), pioche_alice=(Carte("x", "r"),))
    verdict = valider(etat, Action(ACTION_DEBUT_TOUR, "alice"))
    assert verdict.refuse and verdict.regle == "R-5.2"


def test_avancer_phase_non_propose_pendant_la_pioche_r52():
    """R-5.2 — « avancer la phase » n'est pas un coup listé pendant la pioche (automatique)."""
    etat = _etat(_tour(3, phase=PHASE_PIOCHE, actif="alice"), pioche_alice=(Carte("x", "r"),))
    types = {al.action.type for al in actions_legales(etat, "alice")}
    assert ACTION_AVANCER_PHASE not in types
    verdict = valider(etat, Action(ACTION_AVANCER_PHASE, "alice"))
    assert verdict.refuse and verdict.regle == "R-5.2"


# --- Fenêtres de déclenchement (câblées, vides au jalon J1) ------------------


def test_fenetres_vides_ne_produisent_rien_mais_existent():
    """Une fenêtre sans déclencheur renvoie l'état inchangé et aucun événement (pas un silence)."""
    etat = _etat(_tour(3))
    for fenetre in (FENETRE_DEBUT_TOUR, FENETRE_FIN_TOUR):
        etat2, evenements = declencher(etat, fenetre, _RNG)
        assert etat2 == etat
        assert evenements == []


def test_fenetre_inconnue_est_refusee_jamais_approximee():
    """Demander une fenêtre inconnue lève (jamais un passage silencieux)."""
    with pytest.raises(ValueError, match="inconnue"):
        declencher(_etat(_tour(3)), "fenetre_imaginaire", _RNG)


def test_fenetre_declenche_bien_les_declencheurs_enregistres():
    """Le mécanisme est réellement câblé : un déclencheur jouet injecté produit son effet."""
    from pbm_game.journal import Evenement

    temoin = []

    def _jouet(etat, rng):
        temoin.append("vu")
        return etat, [Evenement("jouet_declenche", {})]

    etat = _etat(_tour(3))
    _, evenements = declencher(
        etat, FENETRE_DEBUT_TOUR, _RNG, declencheurs={FENETRE_DEBUT_TOUR: (_jouet,)}
    )
    assert temoin == ["vu"]
    assert [e.type for e in evenements] == ["jouet_declenche"]


# --- Remise à zéro des drapeaux au tour suivant ------------------------------


def test_drapeaux_remis_a_zero_au_tour_suivant_r54_r55_r56():
    """Passer au tour suivant (depuis le Checkup) remet TOUS les drapeaux du tour à zéro."""
    tour = _tour(
        3,
        phase=PHASE_CHECKUP,
        actif="alice",
        energie_posee=True,
        supporter_joue=True,
        retraite_faite=True,
        entres=frozenset({"a-pk-1"}),
    )
    etat = _etat(tour)
    etat2, _ = appliquer(etat, Action(ACTION_AVANCER_PHASE, "alice"), _RNG)
    assert etat2.tour.numero == 4
    assert etat2.tour.joueur_actif == "bob"
    assert etat2.tour.phase == PHASE_PIOCHE
    assert etat2.tour.energie_posee is False
    assert etat2.tour.supporter_joue is False
    assert etat2.tour.retraite_faite is False
    assert etat2.tour.entres_en_jeu_ce_tour == frozenset()


# --- Déroulé complet d'un tour (intégration) ---------------------------------


def test_deroule_complet_d_un_tour_de_bout_en_bout():
    """Un tour complet : début (pioche) → principale → attaque → fin → tour suivant.

    Prouve que la machine enchaîne ses phases (R-5.1), que déclarer une attaque termine le
    tour (R-5.7), et que le tour suivant s'ouvre chez l'adversaire, drapeaux à zéro (R-5.4/5/6).
    """
    carte = Carte("a-pioche-1", "ref-draw")
    etat = _etat(_tour(3, phase=PHASE_PIOCHE, actif="alice"), pioche_alice=(carte,))
    # Début de tour (système) : pioche + passage en principale.
    etat, _ = appliquer(etat, Action(ACTION_DEBUT_TOUR, AUTEUR_SYSTEME), _RNG)
    assert etat.tour.phase == PHASE_PRINCIPALE
    # Le joueur déclare une attaque : le tour se termine (→ Checkup).
    etat, _ = appliquer(etat, Action(ACTION_DECLARER_ATTAQUE, "alice"), _RNG)
    assert etat.tour.phase == PHASE_CHECKUP
    # Passage au tour suivant.
    etat, _ = appliquer(etat, Action(ACTION_AVANCER_PHASE, "alice"), _RNG)
    assert etat.tour.numero == 4
    assert etat.tour.joueur_actif == "bob"
    assert etat.tour.phase == PHASE_PIOCHE
    assert etat.tour.energie_posee is False
    assert_invariants(etat)
