"""L'interprète : structures de contrôle, coût atomique, pureté, et pont vers la pile d'effets."""

from __future__ import annotations

from fabrique_dsl import carte, contexte, etat, joueur, pokemon, rng

from pbm_game.effets.dsl import (
    charger_programme,
    compiler_en_effet,
    executer_programme,
    registre_dsl,
)
from pbm_game.effets.dsl.interprete import EVT_COUT_IMPAYABLE, TYPE_EFFET_DSL
from pbm_game.effets.pile import EVT_EFFET_RESOLU, PileEffets, resoudre_pile


def _run(e, instrs, **extra):
    prog = charger_programme({"version": 1, "effets": instrs, **extra})
    return executer_programme(e, prog, contexte(), rng())


def _actif(res, jid):
    return next(j.actif for j in res.etat.joueurs if j.id == jid)


# --- repeter -----------------------------------------------------------------


def test_repeter_un_nombre_fixe_de_fois():
    alice = joueur("alice", actif=pokemon("a"))
    bob = joueur("bob", actif=pokemon("b"))
    res = _run(
        etat(alice, bob),
        [
            {
                "op": "repeter",
                "nombre": 3,
                "alors": [
                    {
                        "op": "poser_compteurs",
                        "cible": {"zone": "actif", "proprietaire": "adversaire"},
                        "nombre": 1,
                    }
                ],
            },
        ],
    )
    assert _actif(res, "bob").compteurs_degats == 30


def test_repeter_pour_chaque_candidat_de_la_source():
    alice = joueur("alice", actif=pokemon("a"))
    bob = joueur("bob", actif=pokemon("b"), banc=(pokemon("b1"), pokemon("b2")))
    # « Pour chaque Pokémon de banc adverse, posez 1 marqueur sur son Actif. »
    res = _run(
        etat(alice, bob),
        [
            {
                "op": "repeter",
                "source": {"zone": "banc", "proprietaire": "adversaire"},
                "alors": [
                    {
                        "op": "poser_compteurs",
                        "cible": {"zone": "actif", "proprietaire": "adversaire"},
                        "nombre": 1,
                    }
                ],
            },
        ],
    )
    assert _actif(res, "bob").compteurs_degats == 20  # 2 Pokémon de banc → 2×10


# --- si ----------------------------------------------------------------------


def test_si_branche_alors_quand_vrai():
    alice = joueur("alice", actif=pokemon("a"))
    bob = joueur("bob", actif=pokemon("b"), main=(carte("m"),))
    res = _run(
        etat(alice, bob),
        [
            {
                "op": "si",
                "condition": {
                    "type": "zone_non_vide",
                    "cible": {"zone": "main", "proprietaire": "adversaire"},
                },
                "alors": [
                    {
                        "op": "poser_compteurs",
                        "cible": {"zone": "actif", "proprietaire": "adversaire"},
                        "nombre": 2,
                    }
                ],
            },
        ],
    )
    assert _actif(res, "bob").compteurs_degats == 20


def test_si_branche_sinon_quand_faux():
    alice = joueur("alice", actif=pokemon("a"))
    bob = joueur("bob", actif=pokemon("b"))  # main vide → condition fausse
    res = _run(
        etat(alice, bob),
        [
            {
                "op": "si",
                "condition": {
                    "type": "zone_non_vide",
                    "cible": {"zone": "main", "proprietaire": "adversaire"},
                },
                "alors": [
                    {
                        "op": "poser_compteurs",
                        "cible": {"zone": "actif", "proprietaire": "adversaire"},
                        "nombre": 9,
                    }
                ],
                "sinon": [
                    {
                        "op": "poser_compteurs",
                        "cible": {"zone": "actif", "proprietaire": "adversaire"},
                        "nombre": 1,
                    }
                ],
            },
        ],
    )
    assert _actif(res, "bob").compteurs_degats == 10


def test_condition_a_degats():
    alice = joueur("alice", actif=pokemon("a"))
    bob = joueur("bob", actif=pokemon("b", compteurs=30))  # 3 marqueurs ≥ 2
    res = _run(
        etat(alice, bob),
        [
            {
                "op": "si",
                "condition": {
                    "type": "a_degats",
                    "cible": {"zone": "actif", "proprietaire": "adversaire"},
                    "minimum": 2,
                },
                "alors": [
                    {
                        "op": "infliger_degats",
                        "cible": {"zone": "actif", "proprietaire": "adversaire"},
                        "nombre": 10,
                    }
                ],
            },
        ],
    )
    assert _actif(res, "bob").compteurs_degats == 40


# --- pile_ou_face ------------------------------------------------------------


def test_pile_ou_face_execute_exactement_une_branche():
    alice = joueur("alice", actif=pokemon("a"))
    bob = joueur("bob", actif=pokemon("b"))
    res = _run(
        etat(alice, bob),
        [
            {
                "op": "pile_ou_face",
                "nombre": 1,
                "alors": [
                    {
                        "op": "poser_compteurs",
                        "cible": {"zone": "actif", "proprietaire": "adversaire"},
                        "nombre": 1,
                    }
                ],
                "sinon": [
                    {
                        "op": "poser_compteurs",
                        "cible": {"zone": "actif", "proprietaire": "moi"},
                        "nombre": 1,
                    }
                ],
            },
        ],
    )
    touche_bob = _actif(res, "bob").compteurs_degats
    touche_alice = _actif(res, "alice").compteurs_degats
    # Exactement une branche (face → bob, pile → alice) a posé un marqueur.
    assert (touche_bob, touche_alice) in [(10, 0), (0, 10)]


def test_pile_ou_face_est_rejouable():
    """Même graine ⇒ même résultat : la base de la rejouabilité (deux exécutions identiques)."""

    def joue():
        alice = joueur("alice", actif=pokemon("a"))
        bob = joueur("bob", actif=pokemon("b"))
        prog = charger_programme(
            {
                "version": 1,
                "effets": [
                    {
                        "op": "pile_ou_face",
                        "nombre": 3,
                        "alors": [
                            {
                                "op": "poser_compteurs",
                                "cible": {"zone": "actif", "proprietaire": "adversaire"},
                                "nombre": 1,
                            }
                        ],
                    },
                ],
            }
        )
        return (
            executer_programme(etat(alice, bob), prog, contexte(), rng())
            .etat.joueurs[1]
            .actif.compteurs_degats
        )

    assert joue() == joue()


# --- choisir -----------------------------------------------------------------


def test_choisir_borne_le_corps_a_la_selection():
    alice = joueur(
        "alice", actif=pokemon("a-actif", compteurs=30), banc=(pokemon("a-banc", compteurs=20),)
    )
    bob = joueur("bob", actif=pokemon("b"))
    # « Choisissez 1 de vos Pokémon et soignez-le entièrement. » (stratégie canonique → l'Actif)
    res = _run(
        etat(alice, bob),
        [
            {
                "op": "choisir",
                "cible": {"zone": "en_jeu", "proprietaire": "moi", "nombre": 1},
                "alors": [{"op": "soigner"}],
            },
        ],
    )
    a = next(j for j in res.etat.joueurs if j.id == "alice")
    soignes = [p.compteurs_degats for p in (a.actif, *a.banc)]
    assert sorted(soignes) == [0, 20]  # exactement un Pokémon soigné


def test_choisir_sans_option_le_dit_et_n_execute_pas_le_corps():
    alice = joueur("alice", actif=pokemon("a"))
    bob = joueur("bob", actif=pokemon("b"))
    res = _run(
        etat(alice, bob),
        [
            {
                "op": "choisir",
                "cible": {"zone": "banc", "proprietaire": "moi", "nombre": 1},
                "alors": [
                    {
                        "op": "poser_compteurs",
                        "cible": {"zone": "actif", "proprietaire": "adversaire"},
                        "nombre": 5,
                    }
                ],
            },
        ],
    )
    assert next(j.actif for j in res.etat.joueurs if j.id == "bob").compteurs_degats == 0
    assert any(ev.donnees.get("choisis") == 0 for ev in res.evenements if ev.type == "dsl_choix")


# --- coût atomique -----------------------------------------------------------


def test_cout_impayable_ne_fait_rien():
    alice = joueur("alice", actif=pokemon("a"), main=(carte("m1"),))  # 1 carte, coût en exige 2
    bob = joueur("bob", actif=pokemon("b"))
    res = _run(
        etat(alice, bob),
        [
            {
                "op": "poser_compteurs",
                "cible": {"zone": "actif", "proprietaire": "adversaire"},
                "nombre": 5,
            }
        ],
        cout=[{"op": "defausser", "cible": {"zone": "main", "proprietaire": "moi", "nombre": 2}}],
    )
    assert res.cout_paye is False
    assert any(ev.type == EVT_COUT_IMPAYABLE for ev in res.evenements)
    assert _actif(res, "bob").compteurs_degats == 0  # l'effet n'a PAS été joué
    assert len(next(j for j in res.etat.joueurs if j.id == "alice").main) == 1  # main intacte


def test_cout_payable_est_preleve_puis_effet_joue():
    alice = joueur("alice", actif=pokemon("a"), main=(carte("m1"), carte("m2")))
    bob = joueur("bob", actif=pokemon("b"))
    res = _run(
        etat(alice, bob),
        [
            {
                "op": "poser_compteurs",
                "cible": {"zone": "actif", "proprietaire": "adversaire"},
                "nombre": 5,
            }
        ],
        cout=[{"op": "defausser", "cible": {"zone": "main", "proprietaire": "moi", "nombre": 1}}],
    )
    assert res.cout_paye is True
    a = next(j for j in res.etat.joueurs if j.id == "alice")
    assert len(a.main) == 1 and len(a.defausse) == 1
    assert _actif(res, "bob").compteurs_degats == 50


# --- pureté ------------------------------------------------------------------


def test_l_etat_d_entree_n_est_pas_mute():
    alice = joueur("alice", actif=pokemon("a"))
    bob = joueur("bob", actif=pokemon("b", compteurs=0))
    depart = etat(alice, bob)
    res = _run(
        depart,
        [
            {
                "op": "poser_compteurs",
                "cible": {"zone": "actif", "proprietaire": "adversaire"},
                "nombre": 3,
            }
        ],
    )
    assert depart.joueurs[1].actif.compteurs_degats == 0  # l'original n'a pas bougé
    assert res.etat.joueurs[1].actif.compteurs_degats == 30
    assert res.etat is not depart


# --- pont vers la pile d'effets ----------------------------------------------


def test_un_script_se_resout_comme_un_effet_de_la_pile():
    alice = joueur("alice", actif=pokemon("a"))
    bob = joueur("bob", actif=pokemon("b"))
    prog = charger_programme(
        {
            "version": 1,
            "effets": [
                {
                    "op": "poser_compteurs",
                    "cible": {"zone": "actif", "proprietaire": "adversaire"},
                    "nombre": 2,
                    "regle": "R-10.6",
                },
            ],
        }
    )
    effet = compiler_en_effet(prog, contexte(), libelle="Attaque de test", regle="R-10.6")
    assert effet.type_effet == TYPE_EFFET_DSL
    pile = PileEffets().empiler(effet)
    nouvel_etat, evenements = resoudre_pile(etat(alice, bob), pile, registre_dsl(), rng())
    # La résolution est journalisée avec sa source (EVT_EFFET_RESOLU) AVANT l'effet propre.
    assert evenements[0].type == EVT_EFFET_RESOLU
    assert any(ev.type == "dsl_primitive" for ev in evenements)
    assert next(j.actif for j in nouvel_etat.joueurs if j.id == "bob").compteurs_degats == 20
